"""GPU utilization monitoring tools.

Provides MCP tools for querying GPU device info, utilization, memory,
temperature, power, and cluster-wide summaries.

Auto-adapts to the detected hardware backend (NVIDIA, Apple Silicon, or none).
No mock data — all metrics come from real hardware queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.gpu_mcp.models import (
    GpuClusterSummaryInput,
    GpuDeviceIndexInput,
    GpuListDevicesInput,
)
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import get_backend, get_gpu_count, get_gpu_info

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2, default=str)


def _validate_device_index(index: int, count: int) -> None:
    """Validate that a device index is within the valid range."""
    if count == 0:
        raise RuntimeError(
            "No GPU hardware detected on this system. "
            "Install pynvml (NVIDIA) or psutil (Apple Silicon) for GPU monitoring."
        )
    if index < 0 or index >= count:
        raise ValueError(
            f"Device index {index} out of range. "
            f"Available devices: 0-{count - 1} ({count} total)"
        )


def _device_info_sync(index: int) -> dict[str, Any]:
    """Get device info (synchronous — run via to_thread for async)."""
    info = get_gpu_info(index)
    return {
        "device_index": index,
        "name": info.name,
        "total_memory_mb": info.total_memory_mb,
        "driver_version": info.driver_version,
        "backend": info.backend,
    }


def _utilization_sync(index: int) -> dict[str, Any]:
    """Get utilization (synchronous)."""
    info = get_gpu_info(index)
    return {
        "device_index": index,
        "gpu_utilization_pct": info.gpu_utilization,
        "memory_utilization_pct": info.memory_utilization,
        "backend": info.backend,
    }


def _memory_sync(index: int) -> dict[str, Any]:
    """Get memory (synchronous)."""
    info = get_gpu_info(index)
    used_mb = int(info.total_memory_mb * info.memory_utilization / 100)
    free_mb = info.total_memory_mb - used_mb
    return {
        "device_index": index,
        "total_mb": info.total_memory_mb,
        "used_mb": used_mb,
        "free_mb": free_mb,
        "used_pct": round(info.memory_utilization, 1),
        "backend": info.backend,
    }


def _temperature_sync(index: int) -> dict[str, Any]:
    """Get temperature (synchronous)."""
    info = get_gpu_info(index)
    temp = info.temperature
    return {
        "device_index": index,
        "temperature_c": temp,
        "throttle_warning": temp > 85,
        "status": "critical" if temp > 90 else ("warning" if temp > 85 else "normal"),
        "backend": info.backend,
    }


def _power_sync(index: int) -> dict[str, Any]:
    """Get power (synchronous)."""
    info = get_gpu_info(index)
    power_w = info.power_draw_w
    limit_w = info.power_limit_w
    return {
        "device_index": index,
        "power_draw_w": power_w,
        "power_limit_w": limit_w,
        "power_usage_pct": round(power_w / limit_w * 100, 1) if limit_w > 0 else 0.0,
        "backend": info.backend,
    }


def _cluster_data_sync() -> list[dict[str, Any]]:
    """Gather per-device stats for cluster summary (synchronous)."""
    count = get_gpu_count()
    devices: list[dict[str, Any]] = []
    for i in range(count):
        info = get_gpu_info(i)
        used_mb = int(info.total_memory_mb * info.memory_utilization / 100)
        devices.append({
            "device_index": i,
            "name": info.name,
            "gpu_utilization_pct": info.gpu_utilization,
            "memory_total_mb": info.total_memory_mb,
            "memory_used_mb": used_mb,
            "temperature_c": info.temperature,
            "power_draw_w": info.power_draw_w,
            "backend": info.backend,
        })
    return devices


# ---------------------------------------------------------------------------
# MCP Tool: gpu_list_devices
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_list_devices",
    annotations={"title": "List GPU Devices", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_list_devices(params: GpuListDevicesInput) -> str:
    """List all GPUs with name, memory, and driver version.

    Auto-detects hardware: NVIDIA GPUs via pynvml, Apple Silicon via psutil.
    Returns an error message if no GPU hardware is found.
    """
    try:
        count = get_gpu_count()
        if count == 0:
            return _json({
                "device_count": 0,
                "backend": get_backend(),
                "message": "No GPU hardware detected on this system.",
            })

        devices = await asyncio.to_thread(
            lambda: [_device_info_sync(i) for i in range(count)]
        )
        return _json(devices)
    except Exception as exc:
        logger.error("gpu_list_devices failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_utilization
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_utilization",
    annotations={"title": "Get GPU Utilization", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_get_utilization(params: GpuDeviceIndexInput) -> str:
    """Get real-time GPU and memory utilization for a specific device."""
    try:
        count = get_gpu_count()
        _validate_device_index(params.device_index, count)
        result = await asyncio.to_thread(_utilization_sync, params.device_index)
        return _json(result)
    except (ValueError, RuntimeError) as exc:
        logger.warning("gpu_get_utilization: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_get_utilization failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_memory
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_memory",
    annotations={"title": "Get GPU Memory", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_get_memory(params: GpuDeviceIndexInput) -> str:
    """Get free/used/total memory for a GPU device."""
    try:
        count = get_gpu_count()
        _validate_device_index(params.device_index, count)
        result = await asyncio.to_thread(_memory_sync, params.device_index)
        return _json(result)
    except (ValueError, RuntimeError) as exc:
        logger.warning("gpu_get_memory: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_get_memory failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_temperature
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_temperature",
    annotations={"title": "Get GPU Temperature", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_get_temperature(params: GpuDeviceIndexInput) -> str:
    """Get temperature and thermal throttle status for a GPU device."""
    try:
        count = get_gpu_count()
        _validate_device_index(params.device_index, count)
        result = await asyncio.to_thread(_temperature_sync, params.device_index)
        return _json(result)
    except (ValueError, RuntimeError) as exc:
        logger.warning("gpu_get_temperature: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_get_temperature failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_power
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_power",
    annotations={"title": "Get GPU Power", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_get_power(params: GpuDeviceIndexInput) -> str:
    """Get power draw and power limit for a GPU device."""
    try:
        count = get_gpu_count()
        _validate_device_index(params.device_index, count)
        result = await asyncio.to_thread(_power_sync, params.device_index)
        return _json(result)
    except (ValueError, RuntimeError) as exc:
        logger.warning("gpu_get_power: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_get_power failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_cluster_summary
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_cluster_summary",
    annotations={"title": "GPU Cluster Summary", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_get_cluster_summary(params: GpuClusterSummaryInput) -> str:
    """Aggregate GPU stats across all devices.

    Returns device count, average utilization, total/used memory,
    hottest device, and most loaded device.
    """
    try:
        devices = await asyncio.to_thread(_cluster_data_sync)

        if not devices:
            return _json({
                "device_count": 0,
                "backend": get_backend(),
                "message": "No GPU devices found on this system.",
            })

        total_mem = sum(d["memory_total_mb"] for d in devices)
        total_used = sum(d["memory_used_mb"] for d in devices)
        avg_util = round(sum(d["gpu_utilization_pct"] for d in devices) / len(devices), 1)
        hottest = max(devices, key=lambda d: d["temperature_c"])
        most_loaded = max(devices, key=lambda d: d["gpu_utilization_pct"])

        summary: dict[str, Any] = {
            "device_count": len(devices),
            "backend": get_backend(),
            "avg_gpu_utilization_pct": avg_util,
            "total_memory_mb": total_mem,
            "used_memory_mb": total_used,
            "free_memory_mb": total_mem - total_used,
            "memory_used_pct": round(total_used / total_mem * 100, 1) if total_mem > 0 else 0.0,
            "hottest_device": {
                "device_index": hottest["device_index"],
                "temperature_c": hottest["temperature_c"],
            },
            "most_loaded_device": {
                "device_index": most_loaded["device_index"],
                "gpu_utilization_pct": most_loaded["gpu_utilization_pct"],
            },
            "devices": devices,
        }
        return _json(summary)
    except Exception as exc:
        logger.error("gpu_get_cluster_summary failed: %s", exc)
        return _json({"error": str(exc)})
