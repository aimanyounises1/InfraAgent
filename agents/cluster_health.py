"""Cluster Health Agent -- monitors K8s cluster health.

Responsibilities:
- Identify failing pods and CrashLoopBackOff containers
- Suggest scaling actions based on resource pressure
- Detect resource bottlenecks (CPU/memory)
- Report on node health and capacity

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

from mcp_servers.k8s_mcp.models import (
    K8sDescribePodInput,
    K8sGetPodLogsInput,
    K8sListDeploymentsInput,
    K8sListPodsInput,
    K8sListServicesInput,
    K8sRestartDeploymentInput,
    K8sScaleDeploymentInput,
)
from mcp_servers.k8s_mcp.tools.deployments import (
    k8s_list_deployments,
    k8s_restart_deployment,
    k8s_scale_deployment,
)
from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs
from mcp_servers.k8s_mcp.tools.pods import k8s_describe_pod, k8s_list_pods
from mcp_servers.k8s_mcp.tools.services import k8s_list_services

logger = logging.getLogger(__name__)

# System prompt for the LLM-powered create_agent path.
K8S_SYSTEM_PROMPT: str = (
    "You are a Kubernetes cluster health specialist. "
    "You have tools to inspect pods, deployments, services, and logs. "
    "When the user asks about cluster status, use the appropriate tools to gather data. "
    "Always provide concise, actionable analysis of what you find. "
    "If you see failing pods or CrashLoopBackOff, highlight them as issues."
)

# System prompt for the legacy LLM analysis (post-keyword-dispatch).
_K8S_LLM_SYSTEM_PROMPT: str = (
    "You are a Kubernetes cluster health specialist. "
    "Analyze the cluster data and highlight any issues, failing pods, "
    "resource pressure, or recommendations. "
    "Be concise and actionable."
)


# ---------------------------------------------------------------------------
# Keyword-based parsing helpers (used by fallback path)
# ---------------------------------------------------------------------------


def _parse_namespace(query: str) -> str:
    """Extract a Kubernetes namespace from the query string.

    Looks for patterns like "in namespace production", "namespace=staging",
    "ns kube-system", or "-n monitoring". Falls back to "default".

    Args:
        query: The raw user query string.

    Returns:
        The parsed namespace or "default".
    """
    patterns: list[str] = [
        r"(?:in\s+)?namespace[\s=]+([a-z0-9][-a-z0-9]*)",
        r"\bns\s+([a-z0-9][-a-z0-9]*)",
        r"-n\s+([a-z0-9][-a-z0-9]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)
    return "default"


def _parse_pod_name(query: str) -> str | None:
    """Extract a pod name from the query string.

    Looks for patterns like "pod my-pod-abc", "describe my-pod",
    or "logs for my-pod-xyz".

    Args:
        query: The raw user query string.

    Returns:
        The parsed pod name or None if not found.
    """
    patterns: list[str] = [
        r"(?:describe|logs?\s+(?:for|from)?)\s+(?:pod\s+)?([a-z0-9][-a-z0-9.]*)",
        r"pod\s+([a-z0-9][-a-z0-9.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            candidate = match.group(1)
            # Exclude bare keywords
            if candidate.lower() not in {"pod", "pods", "log", "logs", "describe"}:
                return candidate
    return None


def _parse_deployment_name(query: str) -> str | None:
    """Extract a deployment name from the query string.

    Looks for patterns like "scale my-deploy to 5", "restart my-deploy",
    or "deployment my-deploy".

    Args:
        query: The raw user query string.

    Returns:
        The parsed deployment name or None if not found.
    """
    patterns: list[str] = [
        r"(?:scale|restart)\s+(?:deployment\s+)?([a-z0-9][-a-z0-9.]*)",
        r"deployment\s+([a-z0-9][-a-z0-9.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            candidate = match.group(1)
            if candidate.lower() not in {
                "deployment",
                "deployments",
                "to",
                "in",
            }:
                return candidate
    return None


def _parse_replicas(query: str) -> int | None:
    """Extract a replica count from scale commands.

    Looks for patterns like "to 5", "to 5 replicas", "replicas 5",
    or "replicas=3".

    Args:
        query: The raw user query string.

    Returns:
        The parsed replica count or None if not found.
    """
    patterns: list[str] = [
        r"to\s+(\d+)\s*(?:replicas?)?",
        r"replicas?\s*[=:]?\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


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
        Dict with "k8s_data" and "actions_taken" keys, or None on failure.
    """
    try:
        from langchain.agents import create_agent
        from langgraph.checkpoint.memory import MemorySaver

        from agents.llm_provider import get_llm
        from agents.tools import K8S_TOOLS

        llm = get_llm()
        agent = create_agent(
            model=llm,
            tools=K8S_TOOLS,
            prompt=K8S_SYSTEM_PROMPT,
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

        namespace: str = _parse_namespace(query)

        return {
            "k8s_data": {
                "raw": {"llm_response": response_text},
                "tools_called": tools_called,
                "namespace": namespace,
            },
            "actions_taken": [
                f"cluster_health_agent: {t}" for t in tools_called
            ]
            or ["cluster_health_agent: analyzed query via LLM agent"],
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
        Dict with "k8s_data" and "actions_taken" keys.
    """
    query_lower: str = query.lower()
    namespace: str = _parse_namespace(query)
    results: dict[str, Any] = {}
    tools_called: list[str] = []
    actions: list[str] = []

    # --- Scale deployment ---
    if "scale" in query_lower:
        deploy_name = _parse_deployment_name(query)
        replicas = _parse_replicas(query)
        if deploy_name and replicas is not None:
            result_str = await _safe_call(
                k8s_scale_deployment,
                K8sScaleDeploymentInput(
                    namespace=namespace,
                    deployment_name=deploy_name,
                    replicas=replicas,
                ),
                "k8s_scale_deployment",
            )
            results["scale_deployment"] = result_str
            tools_called.append("k8s_scale_deployment")
            actions.append(
                f"cluster_health_agent: scaled {deploy_name} to {replicas} replicas"
            )
        else:
            actions.append(
                "cluster_health_agent: scale requested but could not parse "
                "deployment name or replica count"
            )
            # Fall back to listing deployments
            result_str = await _safe_call(
                k8s_list_deployments,
                K8sListDeploymentsInput(namespace=namespace),
                "k8s_list_deployments",
            )
            results["deployments"] = result_str
            tools_called.append("k8s_list_deployments")
            actions.append(
                "cluster_health_agent: listed deployments (fallback for scale)"
            )

    # --- Restart deployment ---
    elif "restart" in query_lower:
        deploy_name = _parse_deployment_name(query)
        if deploy_name:
            result_str = await _safe_call(
                k8s_restart_deployment,
                K8sRestartDeploymentInput(
                    namespace=namespace,
                    deployment_name=deploy_name,
                ),
                "k8s_restart_deployment",
            )
            results["restart_deployment"] = result_str
            tools_called.append("k8s_restart_deployment")
            actions.append(
                f"cluster_health_agent: restarted deployment {deploy_name}"
            )
        else:
            actions.append(
                "cluster_health_agent: restart requested but could not parse "
                "deployment name"
            )
            result_str = await _safe_call(
                k8s_list_deployments,
                K8sListDeploymentsInput(namespace=namespace),
                "k8s_list_deployments",
            )
            results["deployments"] = result_str
            tools_called.append("k8s_list_deployments")
            actions.append(
                "cluster_health_agent: listed deployments (fallback for restart)"
            )

    # --- Describe pod ---
    elif "describe" in query_lower:
        pod_name = _parse_pod_name(query)
        if pod_name:
            result_str = await _safe_call(
                k8s_describe_pod,
                K8sDescribePodInput(namespace=namespace, pod_name=pod_name),
                "k8s_describe_pod",
            )
            results["describe_pod"] = result_str
            tools_called.append("k8s_describe_pod")
            actions.append(
                f"cluster_health_agent: described pod {pod_name} in {namespace}"
            )
        else:
            actions.append(
                "cluster_health_agent: describe requested but no pod name found"
            )
            result_str = await _safe_call(
                k8s_list_pods,
                K8sListPodsInput(namespace=namespace),
                "k8s_list_pods",
            )
            results["pods"] = result_str
            tools_called.append("k8s_list_pods")
            actions.append(
                "cluster_health_agent: listed pods (fallback for describe)"
            )

    # --- Pod logs ---
    elif any(kw in query_lower for kw in ("log", "logs")):
        pod_name = _parse_pod_name(query)
        if pod_name:
            # Try to parse tail_lines from query
            tail_lines = 100
            tail_match = re.search(r"(\d+)\s*lines?", query, re.IGNORECASE)
            if tail_match:
                tail_lines = min(int(tail_match.group(1)), 5000)

            result_str = await _safe_call(
                k8s_get_pod_logs,
                K8sGetPodLogsInput(
                    namespace=namespace,
                    pod_name=pod_name,
                    tail_lines=tail_lines,
                ),
                "k8s_get_pod_logs",
            )
            results["pod_logs"] = result_str
            tools_called.append("k8s_get_pod_logs")
            actions.append(
                f"cluster_health_agent: fetched logs for pod {pod_name}"
            )
        else:
            actions.append(
                "cluster_health_agent: logs requested but no pod name found"
            )
            result_str = await _safe_call(
                k8s_list_pods,
                K8sListPodsInput(namespace=namespace),
                "k8s_list_pods",
            )
            results["pods"] = result_str
            tools_called.append("k8s_list_pods")
            actions.append(
                "cluster_health_agent: listed pods (fallback for logs)"
            )

    # --- List services ---
    elif any(kw in query_lower for kw in ("service", "svc")):
        result_str = await _safe_call(
            k8s_list_services,
            K8sListServicesInput(namespace=namespace),
            "k8s_list_services",
        )
        results["services"] = result_str
        tools_called.append("k8s_list_services")
        actions.append(f"cluster_health_agent: listed services in {namespace}")

    # --- List deployments ---
    elif any(kw in query_lower for kw in ("deploy", "deployment", "deployments")):
        result_str = await _safe_call(
            k8s_list_deployments,
            K8sListDeploymentsInput(namespace=namespace),
            "k8s_list_deployments",
        )
        results["deployments"] = result_str
        tools_called.append("k8s_list_deployments")
        actions.append(
            f"cluster_health_agent: listed deployments in {namespace}"
        )

    # --- List pods (explicit) ---
    elif any(
        kw in query_lower for kw in ("pod", "pods", "list pods", "show pods")
    ):
        result_str = await _safe_call(
            k8s_list_pods,
            K8sListPodsInput(namespace=namespace),
            "k8s_list_pods",
        )
        results["pods"] = result_str
        tools_called.append("k8s_list_pods")
        actions.append(f"cluster_health_agent: listed pods in {namespace}")

    # --- Default: cluster overview ---
    else:
        pods_str = await _safe_call(
            k8s_list_pods,
            K8sListPodsInput(namespace=namespace),
            "k8s_list_pods",
        )
        results["pods"] = pods_str
        tools_called.append("k8s_list_pods")

        deploy_str = await _safe_call(
            k8s_list_deployments,
            K8sListDeploymentsInput(namespace=namespace),
            "k8s_list_deployments",
        )
        results["deployments"] = deploy_str
        tools_called.append("k8s_list_deployments")
        actions.append(
            f"cluster_health_agent: fetched cluster overview for {namespace}"
        )

    # --- LLM-powered analysis (optional enhancement) ---
    from agents.llm_analysis import generate_llm_analysis

    llm_text: str | None = await generate_llm_analysis(
        query=query,
        results=results,
        system_prompt=_K8S_LLM_SYSTEM_PROMPT,
        agent_name="cluster_health_agent",
    )
    if llm_text is not None:
        results["llm_analysis"] = llm_text
        actions.append("cluster_health_agent: LLM analysis generated")

    logger.info(
        "cluster_health_agent completed (keyword dispatch)",
        extra={"tools_called": tools_called, "namespace": namespace},
    )

    return {
        "k8s_data": {
            "raw": results,
            "tools_called": tools_called,
            "namespace": namespace,
        },
        "actions_taken": actions
        or [
            f"cluster_health_agent: processed query in namespace {namespace}"
        ],
    }


# ---------------------------------------------------------------------------
# Public entry point (used by the orchestrator StateGraph)
# ---------------------------------------------------------------------------


async def cluster_health_agent(state: dict) -> dict:
    """Process Kubernetes-related queries using k8s_mcp tools.

    Tries the LLM-powered ``create_agent()`` path first. If the LLM is
    unavailable, falls back to deterministic keyword-based dispatch.

    The function signature is unchanged from the original so the orchestrator
    StateGraph continues to work without modification.

    Args:
        state: The current InfraState as a dict (includes "query" key).

    Returns:
        Dict with "k8s_data" containing raw results and tools called,
        plus "actions_taken" list.
    """
    query: str = state.query if hasattr(state, "query") else state.get("query", "")
    if not query:
        logger.warning("cluster_health_agent called with empty query")
        return {
            "k8s_data": {"raw": {}, "tools_called": [], "error": "Empty query"},
            "actions_taken": ["cluster_health_agent: received empty query"],
        }

    # Try LLM agent path first
    llm_result: dict[str, Any] | None = await _run_llm_agent(query)
    if llm_result is not None:
        return llm_result

    # Fallback to keyword dispatch
    return await _run_keyword_dispatch(query)
