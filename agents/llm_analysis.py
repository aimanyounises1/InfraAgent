"""Shared LLM analysis helper for domain agents.

Provides a reusable async function that takes raw tool results and generates
a natural-language analysis using the configured LLM provider. The LLM call
is strictly optional -- if anything fails (no LLM configured, Ollama not
running, timeout, etc.) the function returns None and the agent continues
with keyword-based results only.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# Maximum characters of serialized data to send to the LLM to avoid
# overwhelming context windows on smaller models.
_MAX_DATA_CHARS: int = settings.llm_analysis_max_data_chars

# Timeout in seconds for the LLM analysis call.
_LLM_TIMEOUT: int = settings.llm_analysis_timeout


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
        # Serialize results to JSON, truncating to avoid overwhelming the LLM
        data_summary: str = json.dumps(results, indent=2, default=str)
        if len(data_summary) > _MAX_DATA_CHARS:
            data_summary = (
                data_summary[:_MAX_DATA_CHARS] + "\n... (truncated)"
            )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
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
