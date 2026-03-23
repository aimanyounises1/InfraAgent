"""Natural language chat endpoint -- routes queries through the LangGraph orchestrator.

Provides two endpoints:
- POST /chat — standard request/response
- POST /chat/stream — SSE streaming with token-by-token LLM output
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agents.orchestrator import app as orchestrator
from api.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Incoming chat request from the dashboard or API client."""

    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    thread_id: str = Field(default="default", description="Conversation thread ID")


class ChatResponse(BaseModel):
    """Structured response returned to the caller."""

    response: str
    intent: str
    actions_taken: list[str] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a natural language infrastructure query through the orchestrator.

    Invokes the LangGraph orchestrator with the user query, extracts the
    classified intent, generated response, and any actions taken, then
    broadcasts the result over WebSocket for real-time dashboard updates.

    Args:
        request: The chat request containing the query and thread ID.

    Returns:
        ChatResponse with the orchestrator's response, intent, and actions.
    """
    logger.info(
        "chat endpoint called",
        extra={"query": request.query, "thread_id": request.thread_id},
    )

    try:
        raw_result = await orchestrator.ainvoke(
            {"query": request.query},
            config={"configurable": {"thread_id": request.thread_id}},
        )

        # LangGraph may return InfraState (Pydantic) or dict depending on version
        if hasattr(raw_result, "model_dump"):
            result: dict[str, Any] = raw_result.model_dump()
        elif isinstance(raw_result, dict):
            result = raw_result
        else:
            result = dict(raw_result)

        response_text: str = result.get("response", "No response generated.")
        intent: str = result.get("intent", "unknown")
        actions_taken: list[str] = result.get("actions_taken", [])

        logger.info(
            "chat orchestrator completed",
            extra={"intent": intent, "actions_count": len(actions_taken)},
        )

        # Broadcast to WebSocket clients for real-time updates
        await manager.broadcast(
            {
                "type": "chat_response",
                "query": request.query,
                "response": response_text,
                "intent": intent,
                "actions_taken": actions_taken,
            }
        )

        return ChatResponse(
            response=response_text,
            intent=intent,
            actions_taken=actions_taken,
        )

    except Exception as e:
        logger.error(
            "chat endpoint failed",
            extra={"error": str(e), "query": request.query},
        )
        error_msg = f"Failed to process query: {e}"
        # Best-effort broadcast of the error
        try:
            await manager.broadcast(
                {
                    "type": "chat_error",
                    "query": request.query,
                    "error": str(e),
                }
            )
        except Exception:
            logger.warning("Failed to broadcast chat error over WebSocket")

        return ChatResponse(
            response=error_msg,
            intent="error",
            actions_taken=[],
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    """SSE streaming chat — sends tool results immediately, then streams LLM tokens.

    Event types:
    - status: {"status": "classifying"/"routing"/"analyzing"}
    - tool_result: {"intent": ..., "response": ..., "actions_taken": [...]}
    - token: {"token": "..."}  (LLM analysis tokens)
    - done: {"complete": true}
    - error: {"error": "..."}
    """

    async def event_generator():  # type: ignore[return]
        try:
            # Phase 1: Classify and route
            yield {"event": "status", "data": json.dumps({"status": "classifying"})}

            raw_result = await orchestrator.ainvoke(
                {"query": request.query},
                config={"configurable": {"thread_id": request.thread_id}},
            )

            if hasattr(raw_result, "model_dump"):
                result: dict[str, Any] = raw_result.model_dump()
            elif isinstance(raw_result, dict):
                result = raw_result
            else:
                result = dict(raw_result)

            response_text: str = result.get("response", "")
            intent: str = result.get("intent", "unknown")
            actions: list[str] = result.get("actions_taken", [])

            # Phase 2: Send tool results immediately
            yield {
                "event": "tool_result",
                "data": json.dumps({
                    "intent": intent,
                    "response": response_text,
                    "actions_taken": actions,
                }),
            }

            # Phase 3: Stream LLM analysis tokens if available
            yield {"event": "status", "data": json.dumps({"status": "analyzing"})}

            domain_key = {"kubernetes": "k8s_data", "gpu": "gpu_data"}.get(
                intent, "incident_data"
            )
            raw_data = result.get(domain_key, {})
            if isinstance(raw_data, dict):
                raw_data = raw_data.get("raw", raw_data)

            prompts = {
                "kubernetes": "You are a Kubernetes specialist. Analyze concisely.",
                "gpu": "You are a GPU monitoring specialist. Analyze concisely.",
                "incident": "You are an incident response specialist. Analyze concisely.",
            }

            from agents.llm_analysis import stream_llm_analysis

            async for token in stream_llm_analysis(
                query=request.query,
                results=raw_data if isinstance(raw_data, dict) else {},
                system_prompt=prompts.get(intent, prompts["kubernetes"]),
                agent_name="chat_stream",
            ):
                yield {"event": "token", "data": json.dumps({"token": token})}

            # Phase 4: Done
            yield {"event": "done", "data": json.dumps({"complete": True})}

        except Exception as e:
            logger.error("chat_stream failed: %s", e)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())
