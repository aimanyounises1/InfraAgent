"""Shared agent factory — modern LangGraph StateGraph + tool binding.

Replaces the deprecated `langchain.agents.create_agent()` pattern with
the correct LangGraph 1.0 approach: model.bind_tools() + StateGraph with
llm_call / tool_node / should_continue loop.

Each domain agent (GPU, K8s, Incident) uses `build_tool_agent()` to
create a compiled LangGraph agent that the LLM can use for tool calling.
"""

from __future__ import annotations

import asyncio
import logging
import operator
from typing import Annotated, Any

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Default per-tool execution timeout (seconds).
_TOOL_TIMEOUT: int = 30


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------


class AgentState(BaseModel):
    """State for tool-calling agent loop."""

    messages: Annotated[list[AnyMessage], operator.add] = []
    iteration_count: int = 0


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def build_tool_agent(
    tools: list,
    system_prompt: str,
    agent_name: str = "tool_agent",
    max_iterations: int = 10,
) -> StateGraph:
    """Build a compiled LangGraph agent with tool calling.

    Uses the modern LangGraph pattern:
    1. Bind tools to the LLM via model.bind_tools()
    2. Create a StateGraph with llm_call → should_continue → tool_node loop
    3. Compile and return

    Args:
        tools: List of LangChain @tool-decorated functions.
        system_prompt: System message for the LLM.
        agent_name: Name for logging.
        max_iterations: Max tool-calling rounds before forcing stop.

    Returns:
        Compiled StateGraph agent ready for .ainvoke().
    """
    from agents.llm_provider import get_llm

    # Build tool lookup and bind tools to LLM
    tools_by_name: dict[str, Any] = {t.name: t for t in tools}
    llm = get_llm()
    model_with_tools = llm.bind_tools(tools)

    sys_msg = SystemMessage(content=system_prompt)

    # --- Node: call the LLM (async) ---
    async def llm_call(state: dict) -> dict:
        messages: list[AnyMessage] = state.get("messages", [])
        response = await model_with_tools.ainvoke([sys_msg] + messages)
        return {
            "messages": [response],
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    # --- Node: execute tool calls (async with timeout) ---
    async def tool_node(state: dict) -> dict:
        messages: list[AnyMessage] = state.get("messages", [])
        last_message = messages[-1]
        results: list[ToolMessage] = []

        for tool_call in last_message.tool_calls:
            tool_name: str = tool_call["name"]
            tool_args: dict[str, Any] = tool_call["args"]

            tool = tools_by_name.get(tool_name)
            if tool is None:
                results.append(
                    ToolMessage(
                        content=f"Error: Unknown tool '{tool_name}'",
                        tool_call_id=tool_call["id"],
                    )
                )
                continue

            try:
                observation = await asyncio.wait_for(
                    tool.ainvoke(tool_args),
                    timeout=_TOOL_TIMEOUT,
                )
                results.append(
                    ToolMessage(
                        content=str(observation),
                        tool_call_id=tool_call["id"],
                    )
                )
            except TimeoutError:
                logger.error(
                    "%s: tool %s timed out after %ds",
                    agent_name,
                    tool_name,
                    _TOOL_TIMEOUT,
                )
                results.append(
                    ToolMessage(
                        content=(f"Error: {tool_name} timed out after {_TOOL_TIMEOUT}s"),
                        tool_call_id=tool_call["id"],
                    )
                )
            except Exception as exc:
                logger.error("%s: tool %s failed: %s", agent_name, tool_name, exc)
                results.append(
                    ToolMessage(
                        content=f"Error executing {tool_name}: {exc}",
                        tool_call_id=tool_call["id"],
                    )
                )

        return {"messages": results}

    # --- Edge: should we continue calling tools? ---
    def should_continue(state: dict) -> str:
        messages: list[AnyMessage] = state.get("messages", [])
        iteration: int = state.get("iteration_count", 0)

        # Enforce iteration limit to prevent infinite loops.
        if iteration >= max_iterations:
            logger.warning(
                "%s: hit max iterations (%d), stopping",
                agent_name,
                max_iterations,
            )
            return END

        last_message = messages[-1] if messages else None
        if (
            last_message is not None
            and hasattr(last_message, "tool_calls")
            and last_message.tool_calls
        ):
            return "tool_node"
        return END

    # --- Build the graph ---
    builder = StateGraph(AgentState)
    builder.add_node("llm_call", llm_call)
    builder.add_node("tool_node", tool_node)
    builder.add_edge(START, "llm_call")
    builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    builder.add_edge("tool_node", "llm_call")

    agent = builder.compile()
    logger.info("Built %s agent with %d tools", agent_name, len(tools))
    return agent


async def run_tool_agent(
    agent: Any,
    query: str,
    agent_name: str = "tool_agent",
) -> dict[str, Any] | None:
    """Run a compiled tool agent and extract results.

    Args:
        agent: Compiled LangGraph StateGraph agent.
        query: User query string.
        agent_name: Name for logging/action tracking.

    Returns:
        Dict with response text and tools called, or None on failure.
    """
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=query)]},
        )

        messages = result.get("messages", [])
        if not messages:
            return None

        # Get the final response text
        response_text = messages[-1].content if messages else ""

        # Extract tool calls from message history
        tools_called: list[str] = []
        for m in messages:
            if isinstance(m, ToolMessage):
                # The tool name is in the preceding AI message's tool_calls
                continue
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    tools_called.append(tc["name"])

        return {
            "response": response_text,
            "tools_called": tools_called,
        }

    except Exception as exc:
        logger.warning(
            "%s: LLM agent failed, falling back to keyword dispatch: %s",
            agent_name,
            exc,
        )
        return None
