"""Agent API routes — invoke, stream, chat, and manage agent executions."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from rayolly.core.config import Settings
from rayolly.core.dependencies import (
    get_current_tenant,
    get_redis,
    get_settings,
)
from rayolly.models.agents import AgentExecution, AgentStatus, AgentType

# Built-in agent definitions
from rayolly.services.agents.definitions import (
    ANOMALY_AGENT_DEFINITION,
    INCIDENT_AGENT_DEFINITION,
    QUERY_AGENT_DEFINITION,
    RCA_AGENT_DEFINITION,
)
from rayolly.services.agents.memory import AgentMemoryStore
from rayolly.services.agents.runtime import AgentRuntime, ConversationManager
from rayolly.services.agents.tools import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Agent registry (maps type -> definition)
# ---------------------------------------------------------------------------

_BUILTIN_AGENTS = {
    AgentType.RCA: RCA_AGENT_DEFINITION,
    AgentType.QUERY: QUERY_AGENT_DEFINITION,
    AgentType.INCIDENT: INCIDENT_AGENT_DEFINITION,
    AgentType.ANOMALY: ANOMALY_AGENT_DEFINITION,
}

# ---------------------------------------------------------------------------
# In-memory execution store (production would use PostgreSQL)
# ---------------------------------------------------------------------------
_executions: dict[str, AgentExecution] = {}


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_tool_registry() -> ToolRegistry:
    return create_default_registry()


async def _get_runtime(
    request: Request,
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> AgentRuntime:
    """Build an AgentRuntime from request-scoped dependencies."""
    client = AsyncAnthropic(api_key=settings.ai.anthropic_api_key)
    registry = _get_tool_registry()
    memory = AgentMemoryStore(redis=redis)

    # Inject infra handles so agent tools can query real data
    nats = getattr(request.app.state, "nats", None)
    clickhouse = getattr(request.app.state, "clickhouse", None)

    return AgentRuntime(
        anthropic_client=client,
        tool_registry=registry,
        memory_store=memory,
        nats_client=nats,
        clickhouse_client=clickhouse,
        redis_client=redis,
        model=settings.ai.default_model,
        max_tokens=settings.ai.max_tokens,
    )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class InvokeRequest(BaseModel):
    agent_type: AgentType
    input: dict[str, Any] = Field(default_factory=dict)
    async_mode: bool = Field(False, alias="async")

    class Config:
        populate_by_name = True


class ChatRequest(BaseModel):
    agent_type: AgentType
    message: str
    conversation_id: str | None = None


class ExecutionResponse(BaseModel):
    execution_id: str
    status: AgentStatus
    agent_type: AgentType
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    execution_id: str
    tokens_used: int = 0
    cost_usd: float = 0.0


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    type: AgentType
    tools: list[str]
    triggers: list[str]
    version: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    """List all available agents (built-in + custom)."""
    agents: list[AgentInfo] = []
    for agent_def in _BUILTIN_AGENTS.values():
        agents.append(
            AgentInfo(
                id=str(agent_def.id),
                name=agent_def.name,
                description=agent_def.description,
                type=agent_def.type,
                tools=[t.name for t in agent_def.tools],
                triggers=[f"{t.type}:{t.condition}" for t in agent_def.triggers],
                version=agent_def.version,
            )
        )
    return agents


@router.post("/invoke", response_model=ExecutionResponse)
async def invoke_agent(
    body: InvokeRequest,
    tenant_id: str = Depends(get_current_tenant),
    runtime: AgentRuntime = Depends(_get_runtime),
    request: Request = None,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Invoke an agent.

    - ``async=false`` (default): runs synchronously and returns the full result.
    - ``async=true``: starts the execution in the background and returns an
      execution_id for polling.
    - For SSE streaming, use the ``/invoke`` endpoint with
      ``Accept: text/event-stream`` header.
    """
    agent_def = _BUILTIN_AGENTS.get(body.agent_type)
    if agent_def is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent type: {body.agent_type}",
        )

    # Check if client wants SSE
    accept = request.headers.get("accept", "") if request else ""
    if "text/event-stream" in accept:
        return _stream_response(runtime, agent_def, body.input, tenant_id)

    if body.async_mode:
        # Fire-and-forget — return execution_id immediately
        execution_id = str(uuid.uuid4())
        placeholder = AgentExecution(
            id=uuid.UUID(execution_id),
            agent_id=agent_def.id,
            tenant_id=tenant_id,
            status=AgentStatus.PENDING,
            input=body.input,
            started_at=datetime.now(UTC),
        )
        _executions[execution_id] = placeholder

        async def _run_background() -> None:
            try:
                result = await runtime.execute(
                    agent_def, body.input, tenant_id
                )
                _executions[str(result.id)] = result
            except Exception:
                logger.exception("Background execution %s failed", execution_id)
                placeholder.status = AgentStatus.FAILED
                placeholder.completed_at = datetime.now(UTC)

        asyncio.create_task(_run_background())

        return ExecutionResponse(
            execution_id=execution_id,
            status=AgentStatus.PENDING,
            agent_type=body.agent_type,
            input=body.input,
            started_at=placeholder.started_at.isoformat(),
        )

    # Synchronous execution
    execution = await runtime.execute(agent_def, body.input, tenant_id)
    _executions[str(execution.id)] = execution

    return ExecutionResponse(
        execution_id=str(execution.id),
        status=execution.status,
        agent_type=body.agent_type,
        input=execution.input,
        output=execution.output,
        started_at=execution.started_at.isoformat(),
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        tokens_used=execution.tokens_used,
        cost_usd=execution.cost,
    )


def _stream_response(
    runtime: AgentRuntime,
    agent_def: Any,
    input_data: dict[str, Any],
    tenant_id: str,
) -> StreamingResponse:
    """Return an SSE streaming response."""

    async def event_generator():
        async for event in runtime.execute_streaming(
            agent_def, input_data, tenant_id
        ):
            data = json.dumps(event, default=str)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: str,
    tenant_id: str = Depends(get_current_tenant),
) -> ExecutionResponse:
    """Get the status and result of an agent execution."""
    execution = _executions.get(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    if execution.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ExecutionResponse(
        execution_id=str(execution.id),
        status=execution.status,
        agent_type=AgentType.RCA,  # TODO: store agent_type in execution
        input=execution.input,
        output=execution.output,
        started_at=execution.started_at.isoformat(),
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        tokens_used=execution.tokens_used,
        cost_usd=execution.cost,
    )


@router.get("/executions", response_model=list[ExecutionResponse])
async def list_executions(
    tenant_id: str = Depends(get_current_tenant),
    limit: int = 20,
    status_filter: AgentStatus | None = None,
) -> list[ExecutionResponse]:
    """List recent agent executions for the tenant."""
    results: list[ExecutionResponse] = []
    for exec_obj in sorted(
        _executions.values(), key=lambda e: e.started_at, reverse=True
    ):
        if exec_obj.tenant_id != tenant_id:
            continue
        if status_filter and exec_obj.status != status_filter:
            continue
        results.append(
            ExecutionResponse(
                execution_id=str(exec_obj.id),
                status=exec_obj.status,
                agent_type=AgentType.RCA,
                input=exec_obj.input,
                output=exec_obj.output,
                started_at=exec_obj.started_at.isoformat(),
                completed_at=(
                    exec_obj.completed_at.isoformat() if exec_obj.completed_at else None
                ),
                tokens_used=exec_obj.tokens_used,
                cost_usd=exec_obj.cost,
            )
        )
        if len(results) >= limit:
            break
    return results


@router.delete("/executions/{execution_id}")
async def cancel_execution(
    execution_id: str,
    tenant_id: str = Depends(get_current_tenant),
    runtime: AgentRuntime = Depends(_get_runtime),
) -> dict[str, Any]:
    """Cancel a running agent execution."""
    execution = _executions.get(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    if execution.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    if execution.status != AgentStatus.RUNNING:
        return {"status": "already_finished", "execution_id": execution_id}

    cancelled = await runtime.cancel(execution_id)
    if cancelled:
        execution.status = AgentStatus.CANCELLED
        execution.completed_at = datetime.now(UTC)
    return {"status": "cancelled" if cancelled else "not_found", "execution_id": execution_id}


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(
    body: ChatRequest,
    tenant_id: str = Depends(get_current_tenant),
    runtime: AgentRuntime = Depends(_get_runtime),
    redis: Redis = Depends(get_redis),
) -> ChatResponse:
    """Stateful conversational agent interaction.

    Provide a ``conversation_id`` to continue a previous conversation,
    or omit it to start a new one.
    """
    agent_def = _BUILTIN_AGENTS.get(body.agent_type)
    if agent_def is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent type: {body.agent_type}",
        )

    memory = AgentMemoryStore(redis=redis)
    manager = ConversationManager(runtime, memory)

    result = await manager.chat(
        agent_def=agent_def,
        message=body.message,
        tenant_id=tenant_id,
        conversation_id=body.conversation_id,
    )

    return ChatResponse(
        conversation_id=result["conversation_id"],
        response=result["response"],
        execution_id=result["execution_id"],
        tokens_used=result.get("tokens_used", 0),
        cost_usd=result.get("cost_usd", 0.0),
    )


@router.get("/marketplace")
async def list_marketplace_agents(
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, Any]:
    """List marketplace agents (stub for future implementation)."""
    return {
        "agents": [],
        "total": 0,
        "message": "Agent marketplace coming soon. Community-contributed agents will appear here.",
    }
