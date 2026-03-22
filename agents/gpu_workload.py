"""GPU Workload Agent -- monitors GPU utilization across devices.

Responsibilities:
- Monitor GPU utilization, temperature, and memory across all devices
- Detect stuck jobs (high memory but low utilization)
- Suggest workload rebalancing across GPUs
- Report on cluster-wide GPU efficiency

Primary path: Uses LangGraph StateGraph with model.bind_tools() for
LLM-driven tool selection (modern LangGraph 1.0 pattern).

Fallback path: If the LLM is unavailable (e.g. Ollama not running), falls
back to deterministic keyword-based dispatch.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mcp_servers.gpu_mcp.models import (
    DcgmFieldGroupInput,
    DcgmXidErrorsInput,
    GpuClusterSummaryInput,
    GpuDeviceIndexInput,
    GpuHealthCheckInput,
    GpuListDevicesInput,
    NcclProfileInput,
    NvlinkTopologyInput,
)
from mcp_servers.gpu_mcp.tools.dcgm import (
    gpu_dcgm_cluster_health,
    gpu_dcgm_field_group,
    gpu_dcgm_xid_errors,
)
from mcp_servers.gpu_mcp.tools.health import gpu_health_check
from mcp_servers.gpu_mcp.tools.monitor import (
    gpu_get_cluster_summary,
    gpu_get_memory,
    gpu_get_power,
    gpu_get_temperature,
    gpu_list_devices,
)
from mcp_servers.gpu_mcp.tools.nccl import gpu_nccl_profile
from mcp_servers.gpu_mcp.tools.nvlink import gpu_nvlink_status, gpu_nvlink_topology
from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

logger = logging.getLogger(__name__)

# System prompt for the LLM-powered agent path (LangGraph StateGraph).
GPU_SYSTEM_PROMPT: str = (
    "You are an HPC GPU infrastructure specialist managing DGX H100 clusters. "
    "You have tools for: basic GPU telemetry (NVML), deep diagnostics (DCGM field groups, "
    "XID errors, ECC), NVLink topology and interconnect health, NCCL collective profiling, "
    "and cluster-wide health scoring. "
    "When the user asks about GPU status, use the appropriate tools to gather data. "
    "Identify: overloaded devices, thermal concerns, stuck training jobs, memory pressure, "
    "NVLink degradation, NCCL bandwidth bottlenecks, or workload imbalance across DGX nodes. "
    "Be concise and actionable."
)

# System prompt for the legacy LLM analysis (post-keyword-dispatch).
_GPU_LLM_SYSTEM_PROMPT: str = (
    "You are a GPU workload monitoring specialist. "
    "Analyze GPU metrics and identify: overloaded devices, thermal concerns, "
    "stuck jobs, memory pressure, or workload imbalance recommendations. "
    "Be concise and actionable."
)


# ---------------------------------------------------------------------------
# Keyword-based parsing helpers (used by fallback path)
# ---------------------------------------------------------------------------


def _parse_device_index(query: str) -> int | None:
    """Extract a GPU device index from the query string.

    Looks for patterns like "gpu 0", "device 2", "gpu:1", "#3".

    Args:
        query: The raw user query string.

    Returns:
        The parsed device index or None to operate on all devices.
    """
    patterns: list[str] = [
        r"(?:gpu|device)\s*[:#]?\s*(\d+)",
        r"#(\d+)",
        r"index\s+(\d+)",
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


async def _get_device_count() -> int:
    """Retrieve the number of GPU devices available.

    Calls gpu_list_devices and parses the result to count devices.

    Returns:
        Number of GPU devices, defaults to 4 on parse failure.
    """
    try:
        devices_str = await gpu_list_devices(GpuListDevicesInput())
        devices_data = json.loads(devices_str)
        if isinstance(devices_data, list):
            return len(devices_data)
        return devices_data.get("device_count", 4)
    except Exception as exc:
        logger.warning("Could not determine device count: %s", exc)
        return 4


async def _per_device_call(
    tool_fn: Any,
    tool_name: str,
    device_index: int | None,
) -> tuple[str, list[str]]:
    """Call a per-device tool for one or all devices.

    If device_index is specified, calls for that single device.
    Otherwise, retrieves the device count and calls for each one.

    Args:
        tool_fn: The async MCP tool function expecting GpuDeviceIndexInput.
        tool_name: Human-readable name for logging.
        device_index: Specific device, or None for all.

    Returns:
        Tuple of (JSON results string, list of tool names called).
    """
    if device_index is not None:
        result = await _safe_call(
            tool_fn,
            GpuDeviceIndexInput(device_index=device_index),
            tool_name,
        )
        return result, [tool_name]

    # Call for all devices
    count = await _get_device_count()
    all_results: list[Any] = []
    for i in range(count):
        result = await _safe_call(
            tool_fn,
            GpuDeviceIndexInput(device_index=i),
            tool_name,
        )
        try:
            all_results.append(json.loads(result))
        except (json.JSONDecodeError, TypeError):
            all_results.append({"device_index": i, "raw": result})

    return json.dumps(all_results, indent=2), [f"{tool_name}(x{count})"]


# ---------------------------------------------------------------------------
# LLM-powered agent path (LangGraph StateGraph)
# ---------------------------------------------------------------------------


async def _run_llm_agent(query: str) -> dict[str, Any] | None:
    """Process the query using LangGraph StateGraph with tool binding.

    Uses build_tool_agent from agent_factory to create a StateGraph with
    model.bind_tools() (modern LangGraph 1.0 pattern).

    Returns the structured agent result dict, or None if the LLM agent
    cannot be created or invoked (so the caller should fall back to
    keyword dispatch).

    Args:
        query: The user query string.

    Returns:
        Dict with "gpu_data" and "actions_taken" keys, or None on failure.
    """
    try:
        from agents.agent_factory import build_tool_agent, run_tool_agent
        from agents.tools import GPU_TOOLS

        agent = build_tool_agent(
            tools=GPU_TOOLS,
            system_prompt=GPU_SYSTEM_PROMPT,
            agent_name="gpu_workload_agent",
        )

        result = await run_tool_agent(agent, query, "gpu_workload_agent")
        if result is None:
            return None

        return {
            "gpu_data": {
                "raw": {"llm_response": result["response"]},
                "tools_called": result["tools_called"],
            },
            "actions_taken": [
                f"gpu_workload_agent: {t}" for t in result["tools_called"]
            ]
            or ["gpu_workload_agent: analyzed query via LLM agent"],
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
        Dict with "gpu_data" and "actions_taken" keys.
    """
    query_lower: str = query.lower()
    device_index: int | None = _parse_device_index(query)
    results: dict[str, Any] = {}
    tools_called: list[str] = []
    actions: list[str] = []

    # --- DCGM diagnostics ---
    if any(
        kw in query_lower for kw in ("dcgm", "xid", "ecc", "retired page", "field group")
    ):
        if "xid" in query_lower or "error" in query_lower:
            result_str = await _safe_call(
                gpu_dcgm_xid_errors,
                DcgmXidErrorsInput(device_index=device_index),
                "gpu_dcgm_xid_errors",
            )
            results["xid_errors"] = result_str
            tools_called.append("gpu_dcgm_xid_errors")
            actions.append("gpu_workload_agent: queried DCGM XID error history")
        elif "cluster" in query_lower or "fleet" in query_lower:
            result_str = await _safe_call(
                gpu_dcgm_cluster_health,
                GpuDeviceIndexInput(device_index=0),
                "gpu_dcgm_cluster_health",
            )
            results["dcgm_cluster"] = result_str
            tools_called.append("gpu_dcgm_cluster_health")
            actions.append("gpu_workload_agent: ran DCGM cluster health check")
        else:
            field_group = "health"
            if "perf" in query_lower:
                field_group = "performance"
            elif "power" in query_lower:
                field_group = "power"
            elif "mem" in query_lower:
                field_group = "memory"
            result_str = await _safe_call(
                gpu_dcgm_field_group,
                DcgmFieldGroupInput(device_index=device_index or 0, field_group=field_group),
                "gpu_dcgm_field_group",
            )
            results["dcgm_fields"] = result_str
            tools_called.append("gpu_dcgm_field_group")
            actions.append(f"gpu_workload_agent: queried DCGM {field_group} fields")

    # --- NVLink / topology ---
    elif any(
        kw in query_lower for kw in ("nvlink", "nvswitch", "topology", "topo", "interconnect")
    ):
        if "topo" in query_lower or "nvswitch" in query_lower:
            node_idx = device_index // 8 if device_index is not None else 0
            result_str = await _safe_call(
                gpu_nvlink_topology,
                NvlinkTopologyInput(node_index=node_idx),
                "gpu_nvlink_topology",
            )
            results["topology"] = result_str
            tools_called.append("gpu_nvlink_topology")
            actions.append("gpu_workload_agent: retrieved NVLink/NVSwitch topology")
        else:
            result_str = await _safe_call(
                gpu_nvlink_status,
                GpuDeviceIndexInput(device_index=device_index or 0),
                "gpu_nvlink_status",
            )
            results["nvlink"] = result_str
            tools_called.append("gpu_nvlink_status")
            actions.append("gpu_workload_agent: checked NVLink status")

    # --- NCCL profiling ---
    elif any(
        kw in query_lower for kw in ("nccl", "allreduce", "allgather", "collective", "bandwidth")
    ):
        operation = "allreduce"
        if "allgather" in query_lower:
            operation = "allgather"
        elif "reduce_scatter" in query_lower or "reducescatter" in query_lower:
            operation = "reduce_scatter"
        elif "broadcast" in query_lower:
            operation = "broadcast"

        num_gpus = 8
        if "32" in query_lower or "multi" in query_lower or "cross" in query_lower:
            num_gpus = 32

        result_str = await _safe_call(
            gpu_nccl_profile,
            NcclProfileInput(operation=operation, num_gpus=num_gpus),
            "gpu_nccl_profile",
        )
        results["nccl"] = result_str
        tools_called.append("gpu_nccl_profile")
        actions.append(f"gpu_workload_agent: profiled NCCL {operation} ({num_gpus} GPUs)")

    # --- List devices ---
    elif any(
        kw in query_lower for kw in ("list", "devices", "gpus", "all gpu")
    ):
        result_str = await _safe_call(
            gpu_list_devices,
            GpuListDevicesInput(),
            "gpu_list_devices",
        )
        results["devices"] = result_str
        tools_called.append("gpu_list_devices")
        actions.append("gpu_workload_agent: listed all GPU devices")

    # --- Temperature ---
    elif any(
        kw in query_lower
        for kw in ("temperature", "temp", "thermal", "heat")
    ):
        result_str, names = await _per_device_call(
            gpu_get_temperature, "gpu_get_temperature", device_index
        )
        results["temperature"] = result_str
        tools_called.extend(names)
        target = (
            f"device {device_index}"
            if device_index is not None
            else "all devices"
        )
        actions.append(
            f"gpu_workload_agent: checked temperature for {target}"
        )

    # --- Memory ---
    elif any(kw in query_lower for kw in ("memory", "vram", "mem")):
        result_str, names = await _per_device_call(
            gpu_get_memory, "gpu_get_memory", device_index
        )
        results["memory"] = result_str
        tools_called.extend(names)
        target = (
            f"device {device_index}"
            if device_index is not None
            else "all devices"
        )
        actions.append(f"gpu_workload_agent: checked memory for {target}")

    # --- Power ---
    elif "power" in query_lower:
        result_str, names = await _per_device_call(
            gpu_get_power, "gpu_get_power", device_index
        )
        results["power"] = result_str
        tools_called.extend(names)
        target = (
            f"device {device_index}"
            if device_index is not None
            else "all devices"
        )
        actions.append(f"gpu_workload_agent: checked power for {target}")

    # --- Health check ---
    elif any(kw in query_lower for kw in ("health", "status", "check")):
        result_str = await _safe_call(
            gpu_health_check,
            GpuHealthCheckInput(),
            "gpu_health_check",
        )
        results["health"] = result_str
        tools_called.append("gpu_health_check")
        actions.append("gpu_workload_agent: ran GPU health check")

    # --- Processes / jobs ---
    elif any(
        kw in query_lower for kw in ("process", "job", "running", "pid")
    ):
        result_str, names = await _per_device_call(
            gpu_list_processes, "gpu_list_processes", device_index
        )
        results["processes"] = result_str
        tools_called.extend(names)
        target = (
            f"device {device_index}"
            if device_index is not None
            else "all devices"
        )
        actions.append(
            f"gpu_workload_agent: listed processes for {target}"
        )

    # --- Utilization / usage / load ---
    elif any(
        kw in query_lower for kw in ("utilization", "usage", "load", "util")
    ):
        result_str = await _safe_call(
            gpu_get_cluster_summary,
            GpuClusterSummaryInput(),
            "gpu_get_cluster_summary",
        )
        results["cluster_summary"] = result_str
        tools_called.append("gpu_get_cluster_summary")
        actions.append(
            "gpu_workload_agent: fetched cluster utilization summary"
        )

    # --- Default: overview ---
    else:
        summary_str = await _safe_call(
            gpu_get_cluster_summary,
            GpuClusterSummaryInput(),
            "gpu_get_cluster_summary",
        )
        results["cluster_summary"] = summary_str
        tools_called.append("gpu_get_cluster_summary")

        health_str = await _safe_call(
            gpu_health_check,
            GpuHealthCheckInput(),
            "gpu_health_check",
        )
        results["health"] = health_str
        tools_called.append("gpu_health_check")
        actions.append(
            "gpu_workload_agent: fetched GPU overview (summary + health)"
        )

    # --- LLM-powered analysis (optional enhancement) ---
    from agents.llm_analysis import generate_llm_analysis

    llm_text: str | None = await generate_llm_analysis(
        query=query,
        results=results,
        system_prompt=_GPU_LLM_SYSTEM_PROMPT,
        agent_name="gpu_workload_agent",
    )
    if llm_text is not None:
        results["llm_analysis"] = llm_text
        actions.append("gpu_workload_agent: LLM analysis generated")

    logger.info(
        "gpu_workload_agent completed (keyword dispatch)",
        extra={"tools_called": tools_called},
    )

    return {
        "gpu_data": {
            "raw": results,
            "tools_called": tools_called,
        },
        "actions_taken": actions
        or ["gpu_workload_agent: processed GPU query"],
    }


# ---------------------------------------------------------------------------
# Public entry point (used by the orchestrator StateGraph)
# ---------------------------------------------------------------------------


async def gpu_workload_agent(state: dict) -> dict:
    """Process GPU-related queries using gpu_mcp tools.

    Tries the LLM-powered LangGraph agent path first. If the LLM is
    unavailable, falls back to deterministic keyword-based dispatch.

    The function signature is unchanged from the original so the orchestrator
    StateGraph continues to work without modification.

    Args:
        state: The current InfraState as a dict (includes "query" key).

    Returns:
        Dict with "gpu_data" containing raw results and tools called,
        plus "actions_taken" list.
    """
    query: str = (
        state.query if hasattr(state, "query") else state.get("query", "")
    )
    if not query:
        logger.warning("gpu_workload_agent called with empty query")
        return {
            "gpu_data": {
                "raw": {},
                "tools_called": [],
                "error": "Empty query",
            },
            "actions_taken": ["gpu_workload_agent: received empty query"],
        }

    # Try LLM agent path first
    llm_result: dict[str, Any] | None = await _run_llm_agent(query)
    if llm_result is not None:
        return llm_result

    # Fallback to keyword dispatch
    return await _run_keyword_dispatch(query)
