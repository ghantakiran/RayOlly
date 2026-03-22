"""AgentRuntime — the core agentic loop orchestrator.

Implements a proper tool-use loop against the Anthropic Messages API:

    1. Build system prompt + user message from agent definition + input
    2. Send to Claude with tool definitions
    3. If response contains tool_use blocks → execute tools → append results → loop
    4. If response is text-only → done
    5. Track tokens, enforce max iterations and timeout, persist execution state
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic

from rayolly.models.agents import (
    AgentDefinition,
    AgentExecution,
    AgentStatus,
)
from rayolly.services.agents.memory import AgentMemoryStore
from rayolly.services.agents.tools import AgentContext, ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost tracking (per 1M tokens as of 2025 pricing for Sonnet 4)
# ---------------------------------------------------------------------------
_COST_PER_1M_INPUT = 3.00
_COST_PER_1M_OUTPUT = 15.00

MAX_ITERATIONS = 25
DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1_000_000) * _COST_PER_1M_INPUT
        + (output_tokens / 1_000_000) * _COST_PER_1M_OUTPUT
    )


class AgentRuntime:
    """Orchestrates the agentic loop for any ``AgentDefinition``."""

    def __init__(
        self,
        anthropic_client: AsyncAnthropic,
        tool_registry: ToolRegistry,
        memory_store: AgentMemoryStore,
        nats_client: Any | None = None,
        clickhouse_client: Any | None = None,
        redis_client: Any | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        self._llm = anthropic_client
        self._tools = tool_registry
        self._memory = memory_store
        self._nats = nats_client
        self._clickhouse = clickhouse_client
        self._redis = redis_client
        self._model = model
        self._max_tokens = max_tokens

        # In-flight executions (for cancellation)
        self._running: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        agent_def: AgentDefinition,
        input_data: dict[str, Any],
        tenant_id: str,
        user_id: str = "",
        timeout: int | None = None,
    ) -> AgentExecution:
        """Run the full agentic loop and return the execution record."""

        execution_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        self._running[execution_id] = cancel_event

        execution = AgentExecution(
            id=uuid.UUID(execution_id),
            agent_id=agent_def.id,
            tenant_id=tenant_id,
            status=AgentStatus.RUNNING,
            input=input_data,
            started_at=datetime.now(UTC),
        )

        effective_timeout = timeout or agent_def.config.get(
            "timeout_seconds", DEFAULT_TIMEOUT_SECONDS
        )

        try:
            result = await asyncio.wait_for(
                self._run_loop(agent_def, input_data, execution, tenant_id, user_id, cancel_event),
                timeout=effective_timeout,
            )
            execution.output = result
            execution.status = AgentStatus.COMPLETED
        except TimeoutError:
            logger.warning("Agent execution %s timed out", execution_id)
            execution.output = {"error": "Execution timed out", "partial": True}
            execution.status = AgentStatus.FAILED
        except asyncio.CancelledError:
            execution.status = AgentStatus.CANCELLED
            execution.output = {"error": "Execution cancelled"}
        except Exception as exc:
            logger.exception("Agent execution %s failed", execution_id)
            execution.output = {"error": str(exc)}
            execution.status = AgentStatus.FAILED
        finally:
            execution.completed_at = datetime.now(UTC)
            self._running.pop(execution_id, None)
            await self._memory.clear_short_term(execution_id)

        return execution

    async def execute_streaming(
        self,
        agent_def: AgentDefinition,
        input_data: dict[str, Any],
        tenant_id: str,
        user_id: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield incremental events as the agent works (for SSE)."""

        execution_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        self._running[execution_id] = cancel_event

        execution = AgentExecution(
            id=uuid.UUID(execution_id),
            agent_id=agent_def.id,
            tenant_id=tenant_id,
            status=AgentStatus.RUNNING,
            input=input_data,
            started_at=datetime.now(UTC),
        )

        yield {"event": "execution_started", "execution_id": execution_id}

        try:
            async for event in self._run_loop_streaming(
                agent_def, input_data, execution, tenant_id, user_id, cancel_event
            ):
                yield event

            execution.status = AgentStatus.COMPLETED
            yield {"event": "execution_completed", "output": execution.output}
        except Exception as exc:
            execution.status = AgentStatus.FAILED
            execution.output = {"error": str(exc)}
            yield {"event": "execution_failed", "error": str(exc)}
        finally:
            execution.completed_at = datetime.now(UTC)
            self._running.pop(execution_id, None)

    async def cancel(self, execution_id: str) -> bool:
        """Signal a running execution to stop."""
        event = self._running.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    # ------------------------------------------------------------------
    # Core agentic loop
    # ------------------------------------------------------------------

    async def _run_loop(
        self,
        agent_def: AgentDefinition,
        input_data: dict[str, Any],
        execution: AgentExecution,
        tenant_id: str,
        user_id: str,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        """The main tool-use loop — non-streaming variant."""

        system_prompt = self._build_system_prompt(agent_def)
        tools = self._get_tool_definitions(agent_def)
        messages = self._build_initial_messages(input_data)
        context = self._build_context(
            tenant_id, user_id, str(execution.id)
        )

        total_input_tokens = 0
        total_output_tokens = 0
        iterations = 0
        final_text = ""

        while iterations < MAX_ITERATIONS:
            if cancel_event.is_set():
                raise asyncio.CancelledError()

            iterations += 1
            logger.debug(
                "Agent loop iteration %d/%d for %s",
                iterations, MAX_ITERATIONS, execution.id,
            )

            # --- Call the LLM ---
            response = await self._llm.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # --- Process the response ---
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Persist conversation for potential recovery
            await self._memory.set_short_term(
                str(execution.id),
                self._serialize_messages(messages),
            )

            # Check stop reason
            if response.stop_reason == "end_turn" or response.stop_reason != "tool_use":
                # Agent is done — extract final text
                final_text = self._extract_text(assistant_content)
                break

            # --- Execute tool calls ---
            tool_results: list[dict[str, Any]] = []
            for block in assistant_content:
                if block.type == "tool_use":
                    logger.info(
                        "Executing tool %s (id=%s)", block.name, block.id
                    )
                    result = await self._tools.execute_tool(
                        block.name, block.input, context
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        # --- Finalise ---
        execution.tokens_used = total_input_tokens + total_output_tokens
        execution.cost = _estimate_cost(total_input_tokens, total_output_tokens)

        return {
            "response": final_text,
            "iterations": iterations,
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "total": total_input_tokens + total_output_tokens,
            },
            "cost_usd": execution.cost,
        }

    async def _run_loop_streaming(
        self,
        agent_def: AgentDefinition,
        input_data: dict[str, Any],
        execution: AgentExecution,
        tenant_id: str,
        user_id: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming variant — yields events at each step."""

        system_prompt = self._build_system_prompt(agent_def)
        tools = self._get_tool_definitions(agent_def)
        messages = self._build_initial_messages(input_data)
        context = self._build_context(tenant_id, user_id, str(execution.id))

        total_input_tokens = 0
        total_output_tokens = 0
        iterations = 0

        while iterations < MAX_ITERATIONS:
            if cancel_event.is_set():
                return

            iterations += 1

            response = await self._llm.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn" or response.stop_reason != "tool_use":
                final_text = self._extract_text(assistant_content)
                execution.output = {
                    "response": final_text,
                    "iterations": iterations,
                    "tokens": {
                        "input": total_input_tokens,
                        "output": total_output_tokens,
                    },
                }
                execution.tokens_used = total_input_tokens + total_output_tokens
                execution.cost = _estimate_cost(total_input_tokens, total_output_tokens)
                yield {"event": "text", "content": final_text}
                return

            # Execute tools and stream events
            tool_results: list[dict[str, Any]] = []
            for block in assistant_content:
                if block.type == "tool_use":
                    yield {
                        "event": "tool_call",
                        "tool": block.name,
                        "input": block.input,
                    }
                    result = await self._tools.execute_tool(
                        block.name, block.input, context
                    )
                    yield {
                        "event": "tool_result",
                        "tool": block.name,
                        "result": result,
                    }
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self, agent_def: AgentDefinition) -> str:
        """Construct the full system prompt from the agent definition."""
        base = agent_def.config.get("system_prompt", "")
        preamble = (
            "You are a RayOlly AI Agent. You have access to observability tools "
            "to query logs, metrics, traces, and manage incidents. Always cite "
            "evidence from tool results. Be concise and structured.\n\n"
        )
        return preamble + base

    def _get_tool_definitions(self, agent_def: AgentDefinition) -> list[dict[str, Any]]:
        """Return Anthropic-compatible tool definitions for this agent."""
        # If the agent definition has explicit tool names, use those
        if agent_def.tools:
            tool_names = {t.name for t in agent_def.tools}
            return [
                tool.to_anthropic_tool()
                for tool in self._tools.list_tools()
                if tool.name in tool_names
            ]
        # Otherwise use all tools registered for this agent type
        return [
            tool.to_anthropic_tool()
            for tool in self._tools.list_tools(agent_def.type)
        ]

    def _build_initial_messages(
        self, input_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Build the first user message from the input payload."""
        # Support both free-text questions and structured alert contexts
        if "question" in input_data:
            user_text = input_data["question"]
        elif "alert" in input_data:
            alert = input_data["alert"]
            user_text = (
                f"An alert has fired. Investigate and determine the root cause.\n\n"
                f"Alert: {alert.get('name', 'Unknown')}\n"
                f"Severity: {alert.get('severity', 'unknown')}\n"
                f"Service: {alert.get('service', 'unknown')}\n"
                f"Message: {alert.get('message', '')}\n"
                f"Fired at: {alert.get('fired_at', 'unknown')}\n"
            )
            if alert.get("metric"):
                user_text += f"Metric: {alert['metric']}\n"
            if alert.get("threshold"):
                user_text += f"Threshold: {alert['threshold']}\n"
            if alert.get("current_value"):
                user_text += f"Current value: {alert['current_value']}\n"
        elif "anomaly" in input_data:
            a = input_data["anomaly"]
            user_text = (
                f"An anomaly has been detected. Investigate whether it is actionable.\n\n"
                f"Metric: {a.get('metric_name', 'unknown')}\n"
                f"Service: {a.get('service', 'unknown')}\n"
                f"Score: {a.get('score', 'N/A')}\n"
                f"Value: {a.get('value', 'N/A')}\n"
                f"Expected: {a.get('expected', 'N/A')}\n"
                f"Detected at: {a.get('detected_at', 'unknown')}\n"
            )
        elif "incident_id" in input_data:
            user_text = (
                f"You are managing incident {input_data['incident_id']}. "
                f"Coordinate the response: gather context, update the timeline, "
                f"and determine next steps.\n"
            )
            if input_data.get("message"):
                user_text += f"\nAdditional context: {input_data['message']}\n"
        else:
            user_text = json.dumps(input_data, default=str)

        return [{"role": "user", "content": user_text}]

    def _build_context(
        self, tenant_id: str, user_id: str, execution_id: str
    ) -> AgentContext:
        """Create an AgentContext with infra handles for tool execution."""
        # Wrap ClickHouse client with adapter for .execute() compatibility
        ch = self._clickhouse
        if ch is not None:
            from rayolly.services.agents.ch_adapter import ClickHouseAdapter
            if not isinstance(ch, ClickHouseAdapter):
                ch = ClickHouseAdapter(ch)
        return AgentContext(
            tenant_id=tenant_id,
            user_id=user_id,
            execution_id=execution_id,
            clickhouse=ch,
            redis=self._redis,
            nats=self._nats,
        )

    @staticmethod
    def _extract_text(content: list[Any]) -> str:
        """Pull plain text from the assistant content blocks."""
        parts: list[str] = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _serialize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert messages to JSON-safe format for Redis storage."""
        serialized: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                serialized.append(msg)
            elif isinstance(content, list):
                # Could be content blocks or tool results
                safe_content: list[Any] = []
                for item in content:
                    if isinstance(item, dict):
                        safe_content.append(item)
                    elif hasattr(item, "model_dump"):
                        safe_content.append(item.model_dump())
                    else:
                        safe_content.append({"type": "text", "text": str(item)})
                serialized.append({"role": msg["role"], "content": safe_content})
            else:
                serialized.append({"role": msg["role"], "content": str(content)})
        return serialized


class ConversationManager:
    """Manages stateful multi-turn conversations with agents.

    Each conversation stores its message history in short-term memory
    and can be continued across multiple HTTP requests.
    """

    def __init__(self, runtime: AgentRuntime, memory: AgentMemoryStore) -> None:
        self._runtime = runtime
        self._memory = memory

    async def chat(
        self,
        agent_def: AgentDefinition,
        message: str,
        tenant_id: str,
        user_id: str = "",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message and get the agent's response.

        If ``conversation_id`` is provided, the prior history is loaded.
        Otherwise a new conversation is created.
        """
        conv_id = conversation_id or str(uuid.uuid4())

        # Load existing conversation
        history = await self._memory.get_short_term(conv_id)

        # Build the full input — runtime.execute expects an input dict
        input_data: dict[str, Any] = {"question": message}
        if history:
            input_data["_conversation_history"] = history

        execution = await self._runtime.execute(
            agent_def, input_data, tenant_id, user_id
        )

        # Append to conversation history
        history.append({"role": "user", "content": message})
        history.append(
            {"role": "assistant", "content": execution.output.get("response", "")}
        )
        await self._memory.set_short_term(conv_id, history)

        return {
            "conversation_id": conv_id,
            "response": execution.output.get("response", ""),
            "execution_id": str(execution.id),
            "status": execution.status,
            "tokens_used": execution.tokens_used,
            "cost_usd": execution.cost,
        }
