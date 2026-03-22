"""Incident Response Agent -- automated incident management.

Responsibilities:
- Receive alerts and pull relevant metrics from Grafana
- Search Jira for related past incidents
- Generate Root Cause Analysis reports
- Create/update Jira tickets
- Acknowledge/resolve PagerDuty incidents

Primary path: Uses ``create_agent()`` with LangChain ``@tool``-decorated
functions so the LLM can decide which tools to call.

Fallback path: If the LLM is unavailable (e.g. Ollama not running), falls
back to the original keyword-based dispatch for deterministic operation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mcp_servers.incident_mcp.models import (
    GenerateRCAInput,
    GrafanaGetAlertsInput,
    GrafanaQueryInput,
    JiraCreateTicketInput,
    JiraSearchInput,
    PagerDutyAcknowledgeInput,
    PagerDutyListIncidentsInput,
    PagerDutyResolveInput,
)
from mcp_servers.incident_mcp.tools.grafana_tools import (
    incident_grafana_get_alerts,
    incident_grafana_query,
)
from mcp_servers.incident_mcp.tools.jira_tools import (
    incident_jira_create_ticket,
    incident_jira_search,
)
from mcp_servers.incident_mcp.tools.pagerduty_tools import (
    incident_pagerduty_acknowledge,
    incident_pagerduty_list_incidents,
    incident_pagerduty_resolve,
)
from mcp_servers.incident_mcp.tools.rca import incident_generate_rca

logger = logging.getLogger(__name__)

# System prompt for the LLM-powered create_agent path.
INCIDENT_SYSTEM_PROMPT: str = (
    "You are an incident response specialist. "
    "You have tools to manage PagerDuty incidents, query Grafana alerts and metrics, "
    "search and create Jira tickets, and generate Root Cause Analysis reports. "
    "When the user asks about incidents, use the appropriate tools to gather data. "
    "Provide severity assessment, correlation between alerts, recommended next steps, "
    "and escalation guidance. Be concise and actionable."
)

# System prompt for the legacy LLM analysis (post-keyword-dispatch).
_INCIDENT_LLM_SYSTEM_PROMPT: str = (
    "You are an incident response specialist. "
    "Analyze the incident data and provide: severity assessment, "
    "correlation between alerts, recommended next steps, "
    "and escalation guidance. "
    "Be concise and actionable."
)


# ---------------------------------------------------------------------------
# Keyword-based parsing helpers (used by fallback path)
# ---------------------------------------------------------------------------


def _parse_incident_id(query: str) -> str | None:
    """Extract a PagerDuty incident ID from the query string.

    Looks for patterns like "incident P123ABC", "id P456DEF",
    or bare PagerDuty-style IDs.

    Args:
        query: The raw user query string.

    Returns:
        The parsed incident ID or None if not found.
    """
    patterns: list[str] = [
        r"(?:incident|id)\s+([A-Z0-9]{6,})",
        r"\b(P[A-Z0-9]{5,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _parse_project_key(query: str) -> str:
    """Extract a Jira project key from the query string.

    Looks for patterns like "project OPS", "in OPS", or "project=INFRA".
    Falls back to "OPS".

    Args:
        query: The raw user query string.

    Returns:
        The parsed project key or "OPS" as default.
    """
    patterns: list[str] = [
        r"project[\s=]+([A-Z]{2,10})",
        r"in\s+([A-Z]{2,10})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return match.group(1)
    return "OPS"


def _parse_ticket_summary(query: str) -> str:
    """Extract a ticket summary from a create ticket query.

    Strips the command portion and uses the remainder as the summary.
    Falls back to a generic summary.

    Args:
        query: The raw user query string.

    Returns:
        The parsed summary text.
    """
    # Remove the command prefix to extract the summary part
    cleaned = re.sub(
        r"^(?:create|open)\s+(?:a\s+)?(?:jira\s+)?(?:ticket|issue)\s*(?:for|about|:)?\s*",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    if cleaned and len(cleaned) > 3:
        # Capitalize first letter
        return cleaned[0].upper() + cleaned[1:]
    return "Incident reported via InfraAgent"


def _parse_jql(query: str) -> str:
    """Build a JQL query from the user's search terms.

    If the query contains quoted text, uses that as the search term.
    Otherwise strips command prefixes and builds a text search.

    Args:
        query: The raw user query string.

    Returns:
        A JQL query string.
    """
    # Check for quoted search terms
    quoted = re.search(r'"([^"]+)"', query)
    if quoted:
        return f'text ~ "{quoted.group(1)}" ORDER BY created DESC'

    # Strip command prefixes
    cleaned = re.sub(
        r"^(?:search|find)\s+(?:jira\s+)?(?:ticket|tickets|issue|issues)?\s*(?:for|about|:)?\s*",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()

    if cleaned and len(cleaned) > 2:
        return f'text ~ "{cleaned}" ORDER BY created DESC'

    return "type = Bug AND status != Done ORDER BY created DESC"


def _parse_promql(query: str) -> str:
    """Extract a PromQL expression from the query or generate a default.

    Looks for common metric patterns or quoted queries.

    Args:
        query: The raw user query string.

    Returns:
        A PromQL query string.
    """
    # Check for a quoted PromQL query
    quoted = re.search(r'"([^"]+)"', query)
    if quoted:
        return quoted.group(1)

    # Check for known metric name patterns
    metric_match = re.search(
        r"\b((?:node|container|kube|http|process)_[a-z_]+(?:\{[^}]*\})?)",
        query,
    )
    if metric_match:
        return metric_match.group(1)

    return 'rate(http_requests_total{status=~"5.."}[5m])'


async def _safe_call(tool_fn: Any, params: Any, tool_name: str) -> str:
    """Safely call an MCP tool function with error handling.

    Args:
        tool_fn: The async MCP tool function to call.
        params: The Pydantic model input for the tool.
        tool_name: Human-readable name for logging.

    Returns:
        The JSON string result from the tool, or an error JSON string.
    """
    try:
        logger.debug("Calling %s with params: %s", tool_name, params)
        result: str = await tool_fn(params)
        return result
    except Exception as exc:
        logger.error("Error calling %s: %s", tool_name, exc)
        return json.dumps(
            {"error": f"Failed to call {tool_name}", "detail": str(exc)},
            indent=2,
        )


# ---------------------------------------------------------------------------
# LLM-powered agent path (create_agent)
# ---------------------------------------------------------------------------


async def _run_llm_agent(query: str) -> dict[str, Any] | None:
    """Attempt to process the query using a ``create_agent()`` LLM agent.

    Returns the structured agent result dict, or None if the LLM agent
    cannot be created or invoked (so the caller should fall back to
    keyword dispatch).

    Args:
        query: The user query string.

    Returns:
        Dict with "incident_data" and "actions_taken" keys, or None on failure.
    """
    try:
        from langchain.agents import create_agent
        from langgraph.checkpoint.memory import MemorySaver

        from agents.llm_provider import get_llm
        from agents.tools import INCIDENT_TOOLS

        llm = get_llm()
        agent = create_agent(
            model=llm,
            tools=INCIDENT_TOOLS,
            prompt=INCIDENT_SYSTEM_PROMPT,
            checkpointer=MemorySaver(),
        )

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            config={"recursion_limit": 10},
        )

        response_text: str = result["messages"][-1].content

        # Extract which tools were called from the message history
        tools_called: list[str] = [
            m.name
            for m in result["messages"]
            if hasattr(m, "name") and m.name
        ]

        return {
            "incident_data": {
                "raw": {"llm_response": response_text},
                "tools_called": tools_called,
            },
            "actions_taken": [
                f"incident_response_agent: {t}" for t in tools_called
            ]
            or ["incident_response_agent: analyzed query via LLM agent"],
        }

    except Exception as exc:
        logger.warning(
            "LLM agent path unavailable, falling back to keyword dispatch: %s",
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Keyword-based fallback dispatch
# ---------------------------------------------------------------------------


async def _run_keyword_dispatch(query: str) -> dict[str, Any]:
    """Process the query using keyword-based dispatch to MCP tools.

    This is the deterministic fallback when the LLM agent is unavailable.

    Args:
        query: The user query string.

    Returns:
        Dict with "incident_data" and "actions_taken" keys.
    """
    query_lower: str = query.lower()
    results: dict[str, Any] = {}
    tools_called: list[str] = []
    actions: list[str] = []

    # --- Create Jira ticket ---
    if any(
        phrase in query_lower
        for phrase in (
            "create ticket",
            "create jira",
            "open ticket",
            "open issue",
        )
    ):
        project_key = _parse_project_key(query)
        summary = _parse_ticket_summary(query)
        result_str = await _safe_call(
            incident_jira_create_ticket,
            JiraCreateTicketInput(
                project_key=project_key,
                summary=summary,
                description=f"Auto-created from query: {query}",
                issue_type="Incident",
                priority="High",
                labels=["infraagent", "auto-created"],
            ),
            "incident_jira_create_ticket",
        )
        results["create_ticket"] = result_str
        tools_called.append("incident_jira_create_ticket")
        actions.append(
            f"incident_response_agent: created Jira ticket in {project_key}"
        )

    # --- Search Jira ---
    elif any(
        phrase in query_lower
        for phrase in (
            "search",
            "find ticket",
            "find issue",
            "past incident",
        )
    ):
        jql = _parse_jql(query)
        result_str = await _safe_call(
            incident_jira_search,
            JiraSearchInput(jql=jql),
            "incident_jira_search",
        )
        results["search_tickets"] = result_str
        tools_called.append("incident_jira_search")
        actions.append("incident_response_agent: searched Jira with JQL")

    # --- RCA ---
    elif any(
        phrase in query_lower
        for phrase in ("rca", "root cause", "analysis")
    ):
        # Extract incident summary for RCA from the query itself
        rca_summary = re.sub(
            r"\b(?:generate|create|run)\s+(?:an?\s+)?"
            r"(?:rca|root\s+cause\s+analysis)\s*(?:for|about|:)?\s*",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if not rca_summary or len(rca_summary) < 5:
            rca_summary = query

        result_str = await _safe_call(
            incident_generate_rca,
            GenerateRCAInput(incident_summary=rca_summary),
            "incident_generate_rca",
        )
        results["rca"] = result_str
        tools_called.append("incident_generate_rca")
        actions.append("incident_response_agent: generated RCA report")

    # --- Acknowledge PagerDuty ---
    elif any(kw in query_lower for kw in ("acknowledge", "ack")):
        incident_id = _parse_incident_id(query)
        if incident_id:
            result_str = await _safe_call(
                incident_pagerduty_acknowledge,
                PagerDutyAcknowledgeInput(incident_id=incident_id),
                "incident_pagerduty_acknowledge",
            )
            results["acknowledge"] = result_str
            tools_called.append("incident_pagerduty_acknowledge")
            actions.append(
                f"incident_response_agent: acknowledged incident "
                f"{incident_id}"
            )
        else:
            actions.append(
                "incident_response_agent: acknowledge requested "
                "but no incident ID found"
            )
            # Fall back to listing incidents
            result_str = await _safe_call(
                incident_pagerduty_list_incidents,
                PagerDutyListIncidentsInput(),
                "incident_pagerduty_list_incidents",
            )
            results["incidents"] = result_str
            tools_called.append("incident_pagerduty_list_incidents")
            actions.append(
                "incident_response_agent: listed incidents "
                "(fallback for ack)"
            )

    # --- Resolve PagerDuty ---
    elif "resolve" in query_lower:
        incident_id = _parse_incident_id(query)
        if incident_id:
            result_str = await _safe_call(
                incident_pagerduty_resolve,
                PagerDutyResolveInput(incident_id=incident_id),
                "incident_pagerduty_resolve",
            )
            results["resolve"] = result_str
            tools_called.append("incident_pagerduty_resolve")
            actions.append(
                f"incident_response_agent: resolved incident {incident_id}"
            )
        else:
            actions.append(
                "incident_response_agent: resolve requested "
                "but no incident ID found"
            )
            result_str = await _safe_call(
                incident_pagerduty_list_incidents,
                PagerDutyListIncidentsInput(),
                "incident_pagerduty_list_incidents",
            )
            results["incidents"] = result_str
            tools_called.append("incident_pagerduty_list_incidents")
            actions.append(
                "incident_response_agent: listed incidents "
                "(fallback for resolve)"
            )

    # --- Grafana alerts ---
    elif any(kw in query_lower for kw in ("alert", "alerts", "firing")):
        # Determine state filter
        state_filter: str | None = None
        if "firing" in query_lower:
            state_filter = "alerting"
        elif "pending" in query_lower:
            state_filter = "pending"

        result_str = await _safe_call(
            incident_grafana_get_alerts,
            GrafanaGetAlertsInput(state=state_filter),
            "incident_grafana_get_alerts",
        )
        results["alerts"] = result_str
        tools_called.append("incident_grafana_get_alerts")
        actions.append("incident_response_agent: fetched Grafana alerts")

    # --- Grafana metric query ---
    elif any(kw in query_lower for kw in ("metric", "grafana", "promql")):
        promql = _parse_promql(query)
        result_str = await _safe_call(
            incident_grafana_query,
            GrafanaQueryInput(query=promql),
            "incident_grafana_query",
        )
        results["metrics"] = result_str
        tools_called.append("incident_grafana_query")
        actions.append("incident_response_agent: queried Grafana metrics")

    # --- PagerDuty incidents ---
    elif any(
        kw in query_lower
        for kw in ("pagerduty", "pd", "on-call", "active incident", "oncall")
    ):
        result_str = await _safe_call(
            incident_pagerduty_list_incidents,
            PagerDutyListIncidentsInput(),
            "incident_pagerduty_list_incidents",
        )
        results["incidents"] = result_str
        tools_called.append("incident_pagerduty_list_incidents")
        actions.append(
            "incident_response_agent: listed PagerDuty incidents"
        )

    # --- Default: overview (PD incidents + Grafana alerts) ---
    else:
        pd_str = await _safe_call(
            incident_pagerduty_list_incidents,
            PagerDutyListIncidentsInput(),
            "incident_pagerduty_list_incidents",
        )
        results["incidents"] = pd_str
        tools_called.append("incident_pagerduty_list_incidents")

        alerts_str = await _safe_call(
            incident_grafana_get_alerts,
            GrafanaGetAlertsInput(),
            "incident_grafana_get_alerts",
        )
        results["alerts"] = alerts_str
        tools_called.append("incident_grafana_get_alerts")
        actions.append(
            "incident_response_agent: fetched incident overview "
            "(PagerDuty incidents + Grafana alerts)"
        )

    # --- LLM-powered analysis (optional enhancement) ---
    from agents.llm_analysis import generate_llm_analysis

    llm_text: str | None = await generate_llm_analysis(
        query=query,
        results=results,
        system_prompt=_INCIDENT_LLM_SYSTEM_PROMPT,
        agent_name="incident_response_agent",
    )
    if llm_text is not None:
        results["llm_analysis"] = llm_text
        actions.append("incident_response_agent: LLM analysis generated")

    logger.info(
        "incident_response_agent completed (keyword dispatch)",
        extra={"tools_called": tools_called},
    )

    return {
        "incident_data": {
            "raw": results,
            "tools_called": tools_called,
        },
        "actions_taken": actions
        or ["incident_response_agent: processed incident query"],
    }


# ---------------------------------------------------------------------------
# Public entry point (used by the orchestrator StateGraph)
# ---------------------------------------------------------------------------


async def incident_response_agent(state: dict) -> dict:
    """Process incident-related queries using incident_mcp tools.

    Tries the LLM-powered ``create_agent()`` path first. If the LLM is
    unavailable, falls back to deterministic keyword-based dispatch.

    The function signature is unchanged from the original so the orchestrator
    StateGraph continues to work without modification.

    Args:
        state: The current InfraState as a dict (includes "query" key).

    Returns:
        Dict with "incident_data" containing raw results and tools called,
        plus "actions_taken" list.
    """
    query: str = (
        state.query if hasattr(state, "query") else state.get("query", "")
    )
    if not query:
        logger.warning("incident_response_agent called with empty query")
        return {
            "incident_data": {
                "raw": {},
                "tools_called": [],
                "error": "Empty query",
            },
            "actions_taken": [
                "incident_response_agent: received empty query"
            ],
        }

    # Try LLM agent path first
    llm_result: dict[str, Any] | None = await _run_llm_agent(query)
    if llm_result is not None:
        return llm_result

    # Fallback to keyword dispatch
    return await _run_keyword_dispatch(query)
