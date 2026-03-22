"""Main LangGraph orchestrator -- routes queries to specialized agents.

Uses LangGraph 1.0 StateGraph with Pydantic state and type-safe invoke.
"""

from __future__ import annotations

import json
import logging
from operator import add
from typing import Annotated, Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agents.cluster_health import cluster_health_agent
from agents.gpu_workload import gpu_workload_agent
from agents.incident_response import incident_response_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class InfraState(BaseModel):
    """Type-safe state with Pydantic -- auto-coerced with version='v2'."""

    query: str = ""
    intent: str = ""
    k8s_data: dict = {}
    gpu_data: dict = {}
    incident_data: dict = {}
    response: str = ""
    actions_taken: Annotated[list, add] = []


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def classify_intent(state: InfraState) -> dict:
    """Classify the user query into an intent category.

    Uses keyword matching to route queries to the correct agent.
    Each keyword set corresponds to a domain-specific agent.

    Args:
        state: The current InfraState with the user query.

    Returns:
        Dict with "intent" key set to "kubernetes", "gpu", or "incident".
    """
    query_lower = state.query.lower()

    k8s_keywords = {
        "pod",
        "deploy",
        "service",
        "node",
        "namespace",
        "kubectl",
        "kubernetes",
        "k8s",
        "replica",
        "scale",
    }
    gpu_keywords = {
        "gpu",
        "cuda",
        "nvidia",
        "utilization",
        "vram",
        "memory",
        "temperature",
        "power",
    }
    incident_keywords = {
        "incident",
        "alert",
        "pagerduty",
        "jira",
        "grafana",
        "rca",
        "outage",
        "ticket",
    }

    if any(kw in query_lower for kw in k8s_keywords):
        return {"intent": "kubernetes"}
    elif any(kw in query_lower for kw in gpu_keywords):
        return {"intent": "gpu"}
    elif any(kw in query_lower for kw in incident_keywords):
        return {"intent": "incident"}
    else:
        return {"intent": "kubernetes"}  # default


def route_to_agent(state: InfraState) -> str:
    """Route to the appropriate agent based on classified intent.

    Args:
        state: The current InfraState with the classified intent.

    Returns:
        The string key for the next agent node.
    """
    return state.intent


# ---------------------------------------------------------------------------
# Response synthesis helpers
# ---------------------------------------------------------------------------


def _safe_parse_json(raw: str) -> Any:
    """Attempt to parse a JSON string, returning the raw string on failure.

    Args:
        raw: A string that may contain JSON data.

    Returns:
        Parsed JSON object or the original string.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _format_llm_analysis(raw: dict[str, Any]) -> str:
    """Extract and format the LLM analysis section if present.

    Checks the raw results dict for an ``llm_analysis`` key and returns
    it formatted as a Markdown section. Returns an empty string if no
    LLM analysis is present.

    Args:
        raw: The raw results dict from an agent.

    Returns:
        A formatted "## AI Analysis" Markdown section, or empty string.
    """
    llm_analysis: Any = raw.get("llm_analysis")
    if not llm_analysis:
        return ""
    return f"\n## AI Analysis\n\n{llm_analysis}\n"


def _format_llm_agent_response(
    agent_data: dict[str, Any],
    heading: str,
) -> str | None:
    """Format a response from the create_agent() LLM path.

    When the LLM agent path is active, the raw dict contains a single
    ``llm_response`` key with the full natural-language response from the
    agent. This helper detects that case and returns a formatted section,
    or None if the data did not come from the LLM agent path.

    Args:
        agent_data: The agent output dict (e.g. k8s_data, gpu_data).
        heading: Markdown heading for the section (e.g. "Kubernetes Cluster").

    Returns:
        Formatted string if llm_response is present, or None.
    """
    raw: dict[str, Any] = agent_data.get("raw", {})
    llm_response: str | None = raw.get("llm_response")
    if llm_response is None:
        return None

    lines: list[str] = []
    lines.append(f"## {heading}")
    lines.append("")

    tools: list[str] = agent_data.get("tools_called", [])
    if tools:
        lines.append(f"**Tools used:** {', '.join(tools)}")
        lines.append("")

    lines.append(llm_response)
    return "\n".join(lines)


def _format_k8s_data(k8s_data: dict[str, Any]) -> str:
    """Format Kubernetes agent results into a human-readable string.

    Parses the raw tool outputs and presents pod lists, deployment
    info, service details, logs, and action results in a structured way.

    If the data came from the create_agent() LLM path (contains
    ``llm_response`` key), the LLM's response is used directly.

    Args:
        k8s_data: The k8s_data dict from the agent with "raw" and
                  "tools_called" keys.

    Returns:
        Formatted multi-line string summarizing K8s results.
    """
    # Check for LLM agent response first
    llm_formatted: str | None = _format_llm_agent_response(
        k8s_data, "Kubernetes Cluster"
    )
    if llm_formatted is not None:
        return llm_formatted

    lines: list[str] = []
    lines.append("## Kubernetes Cluster")
    lines.append("")

    raw: dict[str, Any] = k8s_data.get("raw", {})
    namespace: str = k8s_data.get("namespace", "default")
    tools: list[str] = k8s_data.get("tools_called", [])

    if tools:
        lines.append(f"**Namespace:** {namespace}")
        lines.append(f"**Tools used:** {', '.join(tools)}")
        lines.append("")

    for key, value_str in raw.items():
        # Skip llm_analysis -- handled separately at the end
        if key == "llm_analysis":
            continue

        parsed = (
            _safe_parse_json(value_str)
            if isinstance(value_str, str)
            else value_str
        )

        if key == "pods" and isinstance(parsed, dict):
            pod_count = parsed.get("pod_count", 0)
            lines.append(f"### Pods ({pod_count} found)")
            pods = parsed.get("pods", [])
            for pod in pods:
                name = pod.get("name", "unknown")
                status = pod.get("status", "Unknown")
                node = pod.get("node", "N/A")
                restarts = sum(
                    c.get("restart_count", 0)
                    for c in pod.get("containers", [])
                )
                status_icon = "OK" if status == "Running" else "WARN"
                lines.append(
                    f"  [{status_icon}] {name} -- Status: {status}, "
                    f"Node: {node}, Restarts: {restarts}"
                )
            lines.append("")

        elif key == "deployments" and isinstance(parsed, dict):
            deploy_count = parsed.get("deployment_count", 0)
            lines.append(f"### Deployments ({deploy_count} found)")
            deploys = parsed.get("deployments", [])
            for dep in deploys:
                name = dep.get("name", "unknown")
                ready = dep.get("ready_replicas", 0)
                desired = dep.get("replicas", 0)
                lines.append(f"  {name} -- Ready: {ready}/{desired}")
            lines.append("")

        elif key == "services" and isinstance(parsed, dict):
            svc_count = parsed.get("service_count", 0)
            lines.append(f"### Services ({svc_count} found)")
            svcs = parsed.get("services", [])
            for svc in svcs:
                name = svc.get("name", "unknown")
                svc_type = svc.get("type", "ClusterIP")
                cluster_ip = svc.get("cluster_ip", "N/A")
                ports = svc.get("ports", [])
                port_str = ", ".join(
                    f"{p.get('port', '?')}/{p.get('protocol', 'TCP')}"
                    for p in ports
                )
                lines.append(
                    f"  {name} -- Type: {svc_type}, "
                    f"IP: {cluster_ip}, Ports: {port_str}"
                )
            lines.append("")

        elif key == "pod_logs" and isinstance(parsed, dict):
            pod_name = parsed.get("pod", "unknown")
            log_lines_count = parsed.get("log_lines", 0)
            lines.append(
                f"### Logs for {pod_name} ({log_lines_count} lines)"
            )
            logs_text = parsed.get("logs", "")
            if logs_text:
                # Show last 20 lines max in summary
                log_lines_list = logs_text.strip().split("\n")
                shown = log_lines_list[-20:]
                for line in shown:
                    lines.append(f"  {line}")
                if len(log_lines_list) > 20:
                    lines.append(
                        f"  ... ({len(log_lines_list) - 20} more lines)"
                    )
            lines.append("")

        elif key == "describe_pod":
            # describe_pod returns Markdown directly
            if isinstance(parsed, str):
                lines.append(parsed)
            else:
                lines.append("### Pod Details")
                lines.append(json.dumps(parsed, indent=2, default=str))
            lines.append("")

        elif key in ("scale_deployment", "restart_deployment"):
            if isinstance(parsed, dict):
                action = parsed.get("action", key)
                deploy_name = parsed.get("deployment", "unknown")
                status = parsed.get("status", "unknown")
                lines.append(f"### Action: {action}")
                lines.append(f"  Deployment: {deploy_name}")
                lines.append(f"  Status: {status}")
                if "previous_replicas" in parsed:
                    lines.append(
                        f"  Replicas: {parsed['previous_replicas']} -> "
                        f"{parsed.get('new_replicas', '?')}"
                    )
            else:
                lines.append("### Action Result")
                lines.append(f"  {parsed}")
            lines.append("")

        elif isinstance(parsed, dict) and "error" in parsed:
            lines.append(f"### Error in {key}")
            lines.append(f"  {parsed.get('error', 'Unknown error')}")
            if parsed.get("detail"):
                lines.append(f"  Detail: {parsed['detail']}")
            lines.append("")

        else:
            lines.append(f"### {key}")
            if isinstance(parsed, (dict, list)):
                lines.append(json.dumps(parsed, indent=2, default=str))
            else:
                lines.append(str(parsed))
            lines.append("")

    # Append LLM analysis section if available
    llm_section: str = _format_llm_analysis(raw)
    if llm_section:
        lines.append(llm_section)

    return "\n".join(lines)


def _format_gpu_data(gpu_data: dict[str, Any]) -> str:
    """Format GPU agent results into a human-readable string.

    Parses the raw tool outputs and presents device lists, cluster
    summaries, health reports, and per-device metrics in a structured way.

    If the data came from the create_agent() LLM path (contains
    ``llm_response`` key), the LLM's response is used directly.

    Args:
        gpu_data: The gpu_data dict from the agent with "raw" and
                  "tools_called" keys.

    Returns:
        Formatted multi-line string summarizing GPU results.
    """
    # Check for LLM agent response first
    llm_formatted: str | None = _format_llm_agent_response(
        gpu_data, "GPU Cluster"
    )
    if llm_formatted is not None:
        return llm_formatted

    lines: list[str] = []
    lines.append("## GPU Cluster")
    lines.append("")

    raw: dict[str, Any] = gpu_data.get("raw", {})
    tools: list[str] = gpu_data.get("tools_called", [])

    if tools:
        lines.append(f"**Tools used:** {', '.join(tools)}")
        lines.append("")

    for key, value_str in raw.items():
        # Skip llm_analysis -- handled separately at the end
        if key == "llm_analysis":
            continue

        parsed = (
            _safe_parse_json(value_str)
            if isinstance(value_str, str)
            else value_str
        )

        if key == "devices" and isinstance(parsed, list):
            lines.append(f"### GPU Devices ({len(parsed)} found)")
            for dev in parsed:
                idx = dev.get("device_index", "?")
                name = dev.get("name", "Unknown")
                mem = dev.get("total_memory_mb", 0)
                driver = dev.get("driver_version", "N/A")
                lines.append(
                    f"  GPU {idx}: {name} -- {mem} MB, Driver: {driver}"
                )
            lines.append("")

        elif key == "cluster_summary" and isinstance(parsed, dict):
            count = parsed.get("device_count", 0)
            avg_util = parsed.get("avg_gpu_utilization_pct", 0)
            total_mem = parsed.get("total_memory_mb", 0)
            used_mem = parsed.get("used_memory_mb", 0)
            free_mem = parsed.get("free_memory_mb", 0)
            mem_pct = parsed.get("memory_used_pct", 0)
            lines.append(f"### Cluster Summary ({count} devices)")
            lines.append(f"  Average GPU Utilization: {avg_util}%")
            lines.append(
                f"  Memory: {used_mem} MB / {total_mem} MB "
                f"({mem_pct}% used, {free_mem} MB free)"
            )
            hottest = parsed.get("hottest_device", {})
            if hottest:
                lines.append(
                    f"  Hottest Device: GPU {hottest.get('device_index', '?')} "
                    f"at {hottest.get('temperature_c', '?')}C"
                )
            most_loaded = parsed.get("most_loaded_device", {})
            if most_loaded:
                lines.append(
                    f"  Most Loaded: GPU "
                    f"{most_loaded.get('device_index', '?')} "
                    f"at {most_loaded.get('gpu_utilization_pct', '?')}%"
                )
            lines.append("")

        elif key == "health" and isinstance(parsed, dict):
            overall = parsed.get("overall_status", "unknown")
            summary = parsed.get("summary", {})
            lines.append(
                f"### Health Report (Overall: {overall.upper()})"
            )
            lines.append(
                f"  Healthy: {summary.get('healthy', 0)}, "
                f"Warning: {summary.get('warning', 0)}, "
                f"Critical: {summary.get('critical', 0)}"
            )
            devices = parsed.get("devices", [])
            for dev in devices:
                idx = dev.get("device_index", "?")
                status = dev.get("status", "unknown")
                temp = dev.get("temperature_c", "?")
                util = dev.get("gpu_utilization_pct", "?")
                mem_util = dev.get("memory_utilization_pct", "?")
                status_tag = status.upper()
                lines.append(
                    f"  GPU {idx} [{status_tag}]: "
                    f"Temp: {temp}C, Util: {util}%, Mem: {mem_util}%"
                )
            lines.append("")

        elif key == "temperature" and isinstance(parsed, list):
            lines.append("### Temperature")
            for dev in parsed:
                idx = dev.get("device_index", "?")
                temp = dev.get("temperature_c", "?")
                status = dev.get("status", "normal")
                throttle = dev.get("throttle_warning", False)
                warning = " [THROTTLE WARNING]" if throttle else ""
                lines.append(
                    f"  GPU {idx}: {temp}C ({status}){warning}"
                )
            lines.append("")

        elif key == "memory" and isinstance(parsed, list):
            lines.append("### Memory")
            for dev in parsed:
                idx = dev.get("device_index", "?")
                total = dev.get("total_mb", 0)
                used = dev.get("used_mb", 0)
                free = dev.get("free_mb", 0)
                pct = dev.get("used_pct", 0)
                lines.append(
                    f"  GPU {idx}: {used} MB / {total} MB "
                    f"({pct}% used, {free} MB free)"
                )
            lines.append("")

        elif key == "power" and isinstance(parsed, list):
            lines.append("### Power")
            for dev in parsed:
                idx = dev.get("device_index", "?")
                draw = dev.get("power_draw_w", 0)
                limit = dev.get("power_limit_w", 0)
                pct = dev.get("power_usage_pct", 0)
                lines.append(
                    f"  GPU {idx}: {draw}W / {limit}W ({pct}%)"
                )
            lines.append("")

        elif key == "processes" and isinstance(parsed, (list, dict)):
            lines.append("### GPU Processes")
            if isinstance(parsed, dict):
                procs = parsed.get("processes", [])
                idx = parsed.get("device_index", "?")
                lines.append(
                    f"  Device {idx}: {len(procs)} process(es)"
                )
                for proc in procs:
                    pid = proc.get("pid", "?")
                    name = proc.get("name", "unknown")
                    mem = proc.get("memory_mb", 0)
                    lines.append(
                        f"    PID {pid}: {name} ({mem} MB)"
                    )
            elif isinstance(parsed, list):
                for device_data in parsed:
                    if isinstance(device_data, dict):
                        idx = device_data.get("device_index", "?")
                        procs = device_data.get("processes", [])
                        lines.append(
                            f"  Device {idx}: "
                            f"{len(procs)} process(es)"
                        )
                        for proc in procs:
                            pid = proc.get("pid", "?")
                            name = proc.get("name", "unknown")
                            mem = proc.get("memory_mb", 0)
                            lines.append(
                                f"    PID {pid}: {name} ({mem} MB)"
                            )
            lines.append("")

        # Single-device result (not list)
        elif key in ("temperature", "memory", "power") and isinstance(
            parsed, dict
        ):
            idx = parsed.get("device_index", "?")
            lines.append(f"### {key.capitalize()} (GPU {idx})")
            for k, v in parsed.items():
                if k != "device_index":
                    lines.append(f"  {k}: {v}")
            lines.append("")

        elif isinstance(parsed, dict) and "error" in parsed:
            lines.append(f"### Error in {key}")
            lines.append(f"  {parsed.get('error', 'Unknown error')}")
            lines.append("")

        else:
            lines.append(f"### {key}")
            if isinstance(parsed, (dict, list)):
                lines.append(json.dumps(parsed, indent=2, default=str))
            else:
                lines.append(str(parsed))
            lines.append("")

    # Append LLM analysis section if available
    llm_section: str = _format_llm_analysis(raw)
    if llm_section:
        lines.append(llm_section)

    return "\n".join(lines)


def _format_incident_data(incident_data: dict[str, Any]) -> str:
    """Format Incident agent results into a human-readable string.

    Parses the raw tool outputs and presents PagerDuty incidents,
    Grafana alerts, Jira tickets, and RCA reports in a structured way.

    If the data came from the create_agent() LLM path (contains
    ``llm_response`` key), the LLM's response is used directly.

    Args:
        incident_data: The incident_data dict from the agent with "raw" and
                       "tools_called" keys.

    Returns:
        Formatted multi-line string summarizing incident results.
    """
    # Check for LLM agent response first
    llm_formatted: str | None = _format_llm_agent_response(
        incident_data, "Incident Management"
    )
    if llm_formatted is not None:
        return llm_formatted

    lines: list[str] = []
    lines.append("## Incident Management")
    lines.append("")

    raw: dict[str, Any] = incident_data.get("raw", {})
    tools: list[str] = incident_data.get("tools_called", [])

    if tools:
        lines.append(f"**Tools used:** {', '.join(tools)}")
        lines.append("")

    for key, value_str in raw.items():
        # Skip llm_analysis -- handled separately at the end
        if key == "llm_analysis":
            continue

        parsed = (
            _safe_parse_json(value_str)
            if isinstance(value_str, str)
            else value_str
        )

        if key == "incidents" and isinstance(parsed, dict):
            total = parsed.get("total", 0)
            lines.append(f"### PagerDuty Incidents ({total} found)")
            incidents = parsed.get("incidents", [])
            for inc in incidents:
                inc_id = inc.get("id", "?")
                title = inc.get(
                    "title", inc.get("summary", "No title")
                )
                status = inc.get("status", "unknown")
                urgency = inc.get("urgency", "N/A")
                lines.append(
                    f"  [{status.upper()}] {inc_id}: {title} "
                    f"(Urgency: {urgency})"
                )
            lines.append("")

        elif key == "alerts" and isinstance(parsed, dict):
            total = parsed.get("total", 0)
            lines.append(f"### Grafana Alerts ({total} active)")
            alerts = parsed.get("alerts", [])
            for alert in alerts:
                if isinstance(alert, dict):
                    name = alert.get("labels", {}).get(
                        "alertname", alert.get("name", "Unknown")
                    )
                    severity = alert.get("labels", {}).get(
                        "severity", "N/A"
                    )
                    state = alert.get("status", {}).get(
                        "state", alert.get("state", "unknown")
                    )
                    summary = alert.get("annotations", {}).get(
                        "summary", ""
                    )
                    lines.append(
                        f"  [{state.upper()}] {name} "
                        f"(Severity: {severity})"
                    )
                    if summary:
                        lines.append(f"    {summary}")
            lines.append("")

        elif key == "create_ticket" and isinstance(parsed, dict):
            ticket_key = parsed.get("key", "?")
            fields = parsed.get("fields", {})
            summary = fields.get("summary", "N/A")
            status = fields.get("status", {}).get("name", "Open")
            priority = fields.get("priority", {}).get("name", "N/A")
            lines.append("### Jira Ticket Created")
            lines.append(f"  Key: {ticket_key}")
            lines.append(f"  Summary: {summary}")
            lines.append(f"  Status: {status}")
            lines.append(f"  Priority: {priority}")
            lines.append("")

        elif key == "search_tickets" and isinstance(parsed, dict):
            total = parsed.get("total", 0)
            lines.append(f"### Jira Search Results ({total} found)")
            issues = parsed.get("issues", [])
            for issue in issues:
                issue_key = issue.get("key", "?")
                fields = issue.get("fields", {})
                summary = fields.get("summary", "No summary")
                status = fields.get("status", {}).get("name", "Unknown")
                lines.append(
                    f"  {issue_key}: {summary} (Status: {status})"
                )
            lines.append("")

        elif key == "acknowledge" and isinstance(parsed, dict):
            inc = parsed.get("incident", {})
            inc_id = inc.get("id", "?")
            status = inc.get("status", "acknowledged")
            message = inc.get("message", "")
            lines.append("### Incident Acknowledged")
            lines.append(f"  ID: {inc_id}")
            lines.append(f"  Status: {status}")
            if message:
                lines.append(f"  {message}")
            lines.append("")

        elif key == "resolve" and isinstance(parsed, dict):
            inc = parsed.get("incident", {})
            inc_id = inc.get("id", "?")
            status = inc.get("status", "resolved")
            message = inc.get("message", "")
            lines.append("### Incident Resolved")
            lines.append(f"  ID: {inc_id}")
            lines.append(f"  Status: {status}")
            if message:
                lines.append(f"  {message}")
            lines.append("")

        elif key == "metrics" and isinstance(parsed, dict):
            lines.append("### Grafana Metrics")
            lines.append(json.dumps(parsed, indent=2, default=str))
            lines.append("")

        elif key == "rca":
            # RCA returns a full Markdown report
            lines.append("### Root Cause Analysis")
            if isinstance(parsed, str):
                lines.append(parsed)
            else:
                lines.append(json.dumps(parsed, indent=2, default=str))
            lines.append("")

        elif isinstance(parsed, dict) and "error" in parsed:
            lines.append(f"### Error in {key}")
            lines.append(f"  {parsed.get('error', 'Unknown error')}")
            if parsed.get("detail"):
                lines.append(f"  Detail: {parsed['detail']}")
            lines.append("")

        else:
            lines.append(f"### {key}")
            if isinstance(parsed, (dict, list)):
                lines.append(json.dumps(parsed, indent=2, default=str))
            else:
                lines.append(str(parsed))
            lines.append("")

    # Append LLM analysis section if available
    llm_section: str = _format_llm_analysis(raw)
    if llm_section:
        lines.append(llm_section)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthesizer node
# ---------------------------------------------------------------------------


async def synthesize_response(state: InfraState) -> dict:
    """Synthesize a final human-readable response from agent outputs.

    Parses the raw JSON strings returned by each agent's MCP tool calls
    and formats them into structured, readable output. Each domain
    (K8s, GPU, Incident) has its own formatter that understands the
    data shapes returned by the corresponding MCP tools.

    Also handles the create_agent() LLM path where agents return a
    ``llm_response`` key containing the full natural-language response.

    Args:
        state: The current InfraState containing agent output dicts.

    Returns:
        Dict with a "response" key containing the formatted string.
    """
    parts: list[str] = []
    actions: list[str] = state.actions_taken or []

    try:
        if state.k8s_data and state.k8s_data.get("raw"):
            parts.append(_format_k8s_data(state.k8s_data))
        elif state.k8s_data:
            # Fallback for unexpected k8s_data format
            parts.append(
                f"## Kubernetes\n"
                f"{json.dumps(state.k8s_data, indent=2, default=str)}"
            )

        if state.gpu_data and state.gpu_data.get("raw"):
            parts.append(_format_gpu_data(state.gpu_data))
        elif state.gpu_data:
            parts.append(
                f"## GPU\n"
                f"{json.dumps(state.gpu_data, indent=2, default=str)}"
            )

        if state.incident_data and state.incident_data.get("raw"):
            parts.append(_format_incident_data(state.incident_data))
        elif state.incident_data:
            parts.append(
                f"## Incident\n"
                f"{json.dumps(state.incident_data, indent=2, default=str)}"
            )
    except Exception as exc:
        logger.error("Error formatting response: %s", exc)
        # Fallback to raw dict representation
        if state.k8s_data:
            parts.append(f"Kubernetes: {state.k8s_data}")
        if state.gpu_data:
            parts.append(f"GPU: {state.gpu_data}")
        if state.incident_data:
            parts.append(f"Incident: {state.incident_data}")

    if not parts:
        return {"response": "No data collected."}

    # Add actions summary at the bottom
    response = "\n\n".join(parts)
    if actions:
        actions_text = "\n".join(f"  - {a}" for a in actions)
        response += f"\n\n---\n**Actions taken:**\n{actions_text}"

    return {"response": response}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Build and compile the InfraAgent orchestration graph.

    Creates a LangGraph StateGraph with:
    - classifier: routes queries by intent
    - k8s_agent, gpu_agent, incident_agent: domain-specific agents
    - synthesizer: formats and combines all agent outputs

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    graph = StateGraph(InfraState)

    graph.add_node("classifier", classify_intent)
    graph.add_node("k8s_agent", cluster_health_agent)
    graph.add_node("gpu_agent", gpu_workload_agent)
    graph.add_node("incident_agent", incident_response_agent)
    graph.add_node("synthesizer", synthesize_response)

    graph.add_edge(START, "classifier")
    graph.add_conditional_edges(
        "classifier",
        route_to_agent,
        {
            "kubernetes": "k8s_agent",
            "gpu": "gpu_agent",
            "incident": "incident_agent",
        },
    )
    graph.add_edge("k8s_agent", "synthesizer")
    graph.add_edge("gpu_agent", "synthesizer")
    graph.add_edge("incident_agent", "synthesizer")
    graph.add_edge("synthesizer", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Compiled app -- import this to invoke the orchestrator.
app = build_graph()
