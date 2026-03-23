"""Main LangGraph orchestrator -- routes queries to specialized agents.

Uses LangGraph 1.0 StateGraph with Pydantic state and type-safe invoke.
Supports both the legacy keyword pipeline and the new ReAct engine
(controlled by ``settings.react_planning_enabled``).
"""

from __future__ import annotations

import json
import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.cluster_health import cluster_health_agent
from agents.formatters import format_gpu_data, format_incident_data, format_k8s_data
from agents.gpu_workload import gpu_workload_agent
from agents.incident_response import incident_response_agent
from agents.state import InfraState

logger = logging.getLogger(__name__)


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
        "slurm",
        "squeue",
        "srun",
        "sbatch",
        "job queue",
        "partition",
        "cordon",
        "drain",
        "rollout",
        "rollback",
        "hpa",
        "autoscal",
        "configmap",
        "quota",
        "event",
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
        "dcgm",
        "nvlink",
        "nvswitch",
        "nccl",
        "allreduce",
        "ecc",
        "xid",
        "topology",
        "hbm",
        "dgx",
        "h100",
        "a100",
        "b200",
        "tensor core",
        "interconnect",
        "collective",
        "infiniband",
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
        "postmortem",
        "correlat",
        "on-call",
        "oncall",
        "escalat",
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
    """Route to the appropriate agent based on classified intent."""
    return state.intent


# ---------------------------------------------------------------------------
# Synthesizer node
# ---------------------------------------------------------------------------


async def synthesize_response(state: InfraState) -> dict:
    """Synthesize a final human-readable response from agent outputs.

    Delegates to domain-specific formatters in ``agents.formatters``.
    """
    parts: list[str] = []
    actions: list[str] = state.actions_taken or []

    try:
        if state.k8s_data and state.k8s_data.get("raw"):
            parts.append(format_k8s_data(state.k8s_data))
        elif state.k8s_data:
            parts.append(f"## Kubernetes\n{json.dumps(state.k8s_data, indent=2, default=str)}")

        if state.gpu_data and state.gpu_data.get("raw"):
            parts.append(format_gpu_data(state.gpu_data))
        elif state.gpu_data:
            parts.append(f"## GPU\n{json.dumps(state.gpu_data, indent=2, default=str)}")

        if state.incident_data and state.incident_data.get("raw"):
            parts.append(format_incident_data(state.incident_data))
        elif state.incident_data:
            parts.append(f"## Incident\n{json.dumps(state.incident_data, indent=2, default=str)}")
    except Exception as exc:
        logger.error("Error formatting response: %s", exc)
        if state.k8s_data:
            parts.append(f"Kubernetes: {state.k8s_data}")
        if state.gpu_data:
            parts.append(f"GPU: {state.gpu_data}")
        if state.incident_data:
            parts.append(f"Incident: {state.incident_data}")

    if not parts:
        return {"response": "No data collected."}

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
