"""Shared LLM analysis helper for domain agents.

Provides a reusable async function that takes raw tool results and generates
a natural-language analysis using the configured LLM provider. The LLM call
is strictly optional -- if anything fails (no LLM configured, Ollama not
running, timeout, etc.) the function returns None and the agent continues
with keyword-based results only.

Also provides ``stream_llm_analysis`` -- an async generator variant that
yields tokens as they arrive from the LLM, enabling real-time SSE streaming
to the dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# Maximum characters of serialized data to send to the LLM to avoid
# overwhelming context windows on smaller models.
_MAX_DATA_CHARS: int = settings.llm_analysis_max_data_chars

# Timeout in seconds for the LLM analysis call.
_LLM_TIMEOUT: int = settings.llm_analysis_timeout


def _build_messages(
    *,
    query: str,
    results: dict[str, Any],
    system_prompt: str,
) -> list[Any]:
    """Build the LangChain message list for LLM analysis.

    Shared helper used by both ``generate_llm_analysis`` and
    ``stream_llm_analysis`` to avoid duplicating serialization logic.

    Args:
        query: The original user query string.
        results: The dict of raw tool results collected by the agent.
        system_prompt: Domain-specific system prompt for the LLM.

    Returns:
        A list of LangChain message objects ready for LLM invocation.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    data_summary: str = json.dumps(results, indent=2, default=str)
    if len(data_summary) > _MAX_DATA_CHARS:
        data_summary = data_summary[:_MAX_DATA_CHARS] + "\n... (truncated)"

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"User query: {query}\n\n"
                f"Data collected:\n{data_summary}\n\n"
                "Provide a concise analysis with key findings "
                "and recommendations."
            )
        ),
    ]


async def generate_llm_analysis(
    *,
    query: str,
    results: dict[str, Any],
    system_prompt: str,
    agent_name: str,
) -> str | None:
    """Generate an LLM-powered analysis of the raw tool results.

    This function is intended to be called *after* keyword-based tool dispatch
    has already populated ``results``. It serializes the data, sends it to
    the configured LLM with the given system prompt, and returns the LLM's
    textual analysis.

    The call is wrapped in a timeout and a broad exception handler so that
    a failure here **never** breaks the existing keyword-based flow.

    Args:
        query: The original user query string.
        results: The dict of raw tool results collected by the agent.
        system_prompt: Domain-specific system prompt for the LLM.
        agent_name: Human-readable agent name for logging.

    Returns:
        The LLM analysis text, or None if the analysis was skipped or failed.
    """
    if not query or not results:
        return None

    try:
        from agents.llm_provider import get_llm

        llm = get_llm()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "%s: LLM provider unavailable, skipping analysis: %s",
            agent_name,
            exc,
        )
        return None

    try:
        messages = _build_messages(
            query=query, results=results, system_prompt=system_prompt
        )

        llm_response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=_LLM_TIMEOUT,
        )

        content: str = llm_response.content  # type: ignore[assignment]
        logger.info(
            "%s: LLM analysis generated (%d chars)",
            agent_name,
            len(content),
        )
        return content

    except TimeoutError:
        logger.debug(
            "%s: LLM analysis timed out after %ds",
            agent_name,
            _LLM_TIMEOUT,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s: LLM analysis skipped: %s", agent_name, exc)
        return None


async def stream_llm_analysis(
    *,
    query: str,
    results: dict[str, Any],
    system_prompt: str,
    agent_name: str,
) -> AsyncGenerator[str, None]:
    """Stream LLM analysis tokens as they are generated.

    Async generator variant of ``generate_llm_analysis``. Yields individual
    content chunks (tokens / token groups) from the LLM's ``astream``
    interface, enabling real-time Server-Sent Events streaming to the
    dashboard.

    If the LLM provider is unavailable or any error occurs, the generator
    silently ends (yields nothing) so the caller can fall back gracefully.

    Args:
        query: The original user query string.
        results: The dict of raw tool results collected by the agent.
        system_prompt: Domain-specific system prompt for the LLM.
        agent_name: Human-readable agent name for logging.

    Yields:
        String chunks of the LLM analysis as they arrive.
    """
    if not query or not results:
        return

    try:
        from agents.llm_provider import get_llm

        llm = get_llm()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "%s: LLM provider unavailable, skipping stream: %s",
            agent_name,
            exc,
        )
        return

    try:
        messages = _build_messages(
            query=query, results=results, system_prompt=system_prompt
        )

        total_chars = 0
        async for chunk in llm.astream(messages):
            token: str = chunk.content  # type: ignore[assignment]
            if token:
                total_chars += len(token)
                yield token

        logger.info(
            "%s: LLM stream completed (%d chars)",
            agent_name,
            total_chars,
        )

    except Exception as exc:  # noqa: BLE001
        logger.debug("%s: LLM stream failed: %s", agent_name, exc)
