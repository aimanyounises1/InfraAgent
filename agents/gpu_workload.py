"""GPU Workload Agent -- monitors GPU utilization across devices.

Responsibilities:
- Monitor GPU utilization, temperature, and memory across all devices
- Detect stuck jobs (high memory but low utilization)
- Suggest workload rebalancing across GPUs
- Report on cluster-wide GPU efficiency

Dispatches queries to the appropriate gpu MCP tools via keyword matching.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mcp_servers.gpu_mcp.models import (
    GpuClusterSummaryInput,
    GpuDeviceIndexInput,
    GpuHealthCheckInput,
    GpuListDevicesInput,
)
from mcp_servers.gpu_mcp.tools.health import gpu_health_check
from mcp_servers.gpu_mcp.tools.monitor import (
    gpu_get_cluster_summary,
    gpu_get_memory,
    gpu_get_power,
    gpu_get_temperature,
    gpu_list_devices,
)
from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

logger = logging.getLogger(__name__)


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


async def gpu_workload_agent(state: dict) -> dict:
    """Process GPU-related queries using gpu_mcp tools.

    Parses the user query to determine which GPU tools to invoke,
    calls them with appropriate parameters, and returns structured results.

    Keyword dispatch rules:
    - "list" / "devices" / "gpus" -> gpu_list_devices
    - "utilization" / "usage" / "load" -> gpu_get_cluster_summary
    - "temperature" / "temp" / "thermal" -> gpu_get_temperature per device
    - "memory" / "vram" -> gpu_get_memory per device
    - "power" -> gpu_get_power per device
    - "health" / "status" -> gpu_health_check
    - "process" / "job" / "running" -> gpu_list_processes
    - Default: gpu_get_cluster_summary + gpu_health_check

    Args:
        state: The current InfraState as a dict (includes "query" key).

    Returns:
        Dict with "gpu_data" containing raw results and tools called,
        plus "actions_taken" list.
    """
    query: str = state.query if hasattr(state, "query") else state.get("query", "")
    if not query:
        logger.warning("gpu_workload_agent called with empty query")
        return {
            "gpu_data": {"raw": {}, "tools_called": [], "error": "Empty query"},
            "actions_taken": ["gpu_workload_agent: received empty query"],
        }

    query_lower: str = query.lower()
    device_index: int | None = _parse_device_index(query)
    results: dict[str, Any] = {}
    tools_called: list[str] = []
    actions: list[str] = []

    # --- List devices ---
    if any(kw in query_lower for kw in ("list", "devices", "gpus", "all gpu")):
        result_str = await _safe_call(
            gpu_list_devices,
            GpuListDevicesInput(),
            "gpu_list_devices",
        )
        results["devices"] = result_str
        tools_called.append("gpu_list_devices")
        actions.append("gpu_workload_agent: listed all GPU devices")

    # --- Temperature ---
    elif any(kw in query_lower for kw in ("temperature", "temp", "thermal", "heat")):
        result_str, names = await _per_device_call(
            gpu_get_temperature, "gpu_get_temperature", device_index
        )
        results["temperature"] = result_str
        tools_called.extend(names)
        target = f"device {device_index}" if device_index is not None else "all devices"
        actions.append(f"gpu_workload_agent: checked temperature for {target}")

    # --- Memory ---
    elif any(kw in query_lower for kw in ("memory", "vram", "mem")):
        result_str, names = await _per_device_call(gpu_get_memory, "gpu_get_memory", device_index)
        results["memory"] = result_str
        tools_called.extend(names)
        target = f"device {device_index}" if device_index is not None else "all devices"
        actions.append(f"gpu_workload_agent: checked memory for {target}")

    # --- Power ---
    elif "power" in query_lower:
        result_str, names = await _per_device_call(gpu_get_power, "gpu_get_power", device_index)
        results["power"] = result_str
        tools_called.extend(names)
        target = f"device {device_index}" if device_index is not None else "all devices"
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
    elif any(kw in query_lower for kw in ("process", "job", "running", "pid")):
        result_str, names = await _per_device_call(
            gpu_list_processes, "gpu_list_processes", device_index
        )
        results["processes"] = result_str
        tools_called.extend(names)
        target = f"device {device_index}" if device_index is not None else "all devices"
        actions.append(f"gpu_workload_agent: listed processes for {target}")

    # --- Utilization / usage / load ---
    elif any(kw in query_lower for kw in ("utilization", "usage", "load", "util")):
        result_str = await _safe_call(
            gpu_get_cluster_summary,
            GpuClusterSummaryInput(),
            "gpu_get_cluster_summary",
        )
        results["cluster_summary"] = result_str
        tools_called.append("gpu_get_cluster_summary")
        actions.append("gpu_workload_agent: fetched cluster utilization summary")

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
        actions.append("gpu_workload_agent: fetched GPU overview (summary + health)")

    logger.info(
        "gpu_workload_agent completed",
        extra={"tools_called": tools_called},
    )

    return {
        "gpu_data": {
            "raw": results,
            "tools_called": tools_called,
        },
        "actions_taken": actions or ["gpu_workload_agent: processed GPU query"],
    }
