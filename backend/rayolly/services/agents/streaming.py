"""Server-Sent Events streaming for agent responses."""
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from anthropic import AsyncAnthropic

logger = structlog.get_logger(__name__)


class AgentStreamingService:
    """Stream agent responses token-by-token via SSE."""

    MAX_ITERATIONS = 15

    def __init__(
        self,
        anthropic_client: AsyncAnthropic,
        tool_registry: Any,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.llm = anthropic_client
        self.tools = tool_registry
        self.model = model

    async def stream_response(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        tenant_id: str,
        context: Any,
    ) -> AsyncIterator[dict]:
        """Yield SSE events as the agent thinks and responds."""
        messages = [{"role": "user", "content": user_message}]
        total_tokens = 0
        iteration = 0
        start = time.monotonic()

        while iteration < self.MAX_ITERATIONS:
            iteration += 1
            yield {"event": "thinking", "data": {"iteration": iteration}}

            try:
                async with self.llm.messages.stream(
                    model=self.model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                ) as stream:
                    collected_text = ""

                    async for event in stream:
                        if event.type == "content_block_start":
                            if hasattr(event.content_block, "text"):
                                yield {"event": "text_start", "data": {}}
                            elif event.content_block.type == "tool_use":
                                yield {
                                    "event": "tool_start",
                                    "data": {"tool": event.content_block.name},
                                }

                        elif event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                collected_text += event.delta.text
                                yield {
                                    "event": "text_delta",
                                    "data": {"text": event.delta.text},
                                }

                        elif event.type == "message_delta":
                            if hasattr(event.usage, "output_tokens"):
                                total_tokens += event.usage.output_tokens

                    # Get the final message
                    response = await stream.get_final_message()
                    total_tokens += response.usage.input_tokens

                    # Check if done
                    if response.stop_reason == "end_turn":
                        yield {
                            "event": "complete",
                            "data": {
                                "text": collected_text,
                                "tokens": total_tokens,
                                "duration_ms": int(
                                    (time.monotonic() - start) * 1000
                                ),
                                "iterations": iteration,
                            },
                        }
                        return

                    # Process tool calls
                    assistant_content = response.content
                    messages.append(
                        {"role": "assistant", "content": assistant_content}
                    )

                    tool_results = []
                    for block in assistant_content:
                        if block.type == "tool_use":
                            yield {
                                "event": "tool_executing",
                                "data": {
                                    "tool": block.name,
                                    "input": str(block.input)[:200],
                                },
                            }

                            try:
                                result = await self.tools.execute_tool(
                                    block.name, block.input, context
                                )
                            except Exception as exc:
                                logger.error(
                                    "streaming.tool_error",
                                    tool=block.name,
                                    error=str(exc),
                                )
                                result = {"error": str(exc)}

                            yield {
                                "event": "tool_result",
                                "data": {
                                    "tool": block.name,
                                    "result_preview": str(result)[:300],
                                },
                            }

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps(result, default=str),
                                }
                            )

                    messages.append({"role": "user", "content": tool_results})

            except Exception as exc:
                logger.error(
                    "streaming.llm_error",
                    iteration=iteration,
                    error=str(exc),
                )
                yield {
                    "event": "error",
                    "data": {
                        "message": f"LLM streaming error: {exc}",
                        "iteration": iteration,
                    },
                }
                return

        yield {"event": "max_iterations", "data": {"iterations": iteration}}
