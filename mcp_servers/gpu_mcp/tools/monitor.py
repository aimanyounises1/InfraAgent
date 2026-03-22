"""GPU utilization monitoring tools.

Provides MCP tools for querying GPU device info, utilization, memory,
temperature, power, and cluster-wide summaries. Supports both real
NVML hardware queries and a mock mode for development/demo.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.gpu_mcp.models import (  # noqa: TC001
    GpuClusterSummaryInput,
    GpuDeviceIndexInput,
    GpuListDevicesInput,
)
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import (
    MOCK_MODE,
    get_mock_gpu_count,
    get_mock_gpu_info,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional pynvml import.
# In mock mode, pynvml may not be installed; set to None so the attribute
# exists at module level (required for test patching via conftest.py).
# ---------------------------------------------------------------------------
pynvml: Any = None

if not MOCK_MODE:
    try:
        import pynvml as _pynvml

        pynvml = _pynvml
        pynvml.nvmlInit()
        logger.info("pynvml initialized successfully")
    except Exception as exc:
        logger.error("Failed to initialize pynvml: %s", exc)
        raise


def _json(data: Any) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2, default=str)


def _validate_device_index(index: int, count: int) -> None:
    """Validate that a device index is within the valid range.

    Args:
        index: The device index to validate.
        count: Total number of available GPU devices.

    Raises:
        ValueError: If the index is out of range.
    """
    if index < 0 or index >= count:
        raise ValueError(
            f"Device index {index} out of range. Available devices: 0-{count - 1} ({count} total)"
        )


# ---------------------------------------------------------------------------
# Real-mode NVML helper functions (run via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _real_list_devices() -> list[dict[str, Any]]:
    """Query NVML for all GPU device info (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    devices: list[dict[str, Any]] = []
    for i in range(count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        driver = pynvml.nvmlSystemGetDriverVersion()
        devices.append(
            {
                "device_index": i,
                "name": name if isinstance(name, str) else name.decode("utf-8"),
                "total_memory_mb": round(mem_info.total / (1024 * 1024)),
                "driver_version": (driver if isinstance(driver, str) else driver.decode("utf-8")),
            }
        )
    return devices


def _real_get_utilization(index: int) -> dict[str, Any]:
    """Query NVML for GPU utilization rates (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    _validate_device_index(index, count)
    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
    return {
        "device_index": index,
        "gpu_utilization_pct": rates.gpu,
        "memory_utilization_pct": rates.memory,
    }


def _real_get_memory(index: int) -> dict[str, Any]:
    """Query NVML for GPU memory info (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    _validate_device_index(index, count)
    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
    return {
        "device_index": index,
        "total_mb": round(mem.total / (1024 * 1024)),
        "used_mb": round(mem.used / (1024 * 1024)),
        "free_mb": round(mem.free / (1024 * 1024)),
        "used_pct": round(mem.used / mem.total * 100, 1) if mem.total > 0 else 0.0,
    }


def _real_get_temperature(index: int) -> dict[str, Any]:
    """Query NVML for GPU temperature (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    _validate_device_index(index, count)
    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
    return {
        "device_index": index,
        "temperature_c": temp,
        "throttle_warning": temp > 85,
        "status": "critical" if temp > 90 else ("warning" if temp > 85 else "normal"),
    }


def _real_get_power(index: int) -> dict[str, Any]:
    """Query NVML for GPU power draw and limit (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    _validate_device_index(index, count)
    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    # pynvml returns milliwatts
    power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
    limit_mw = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle)
    power_w = round(power_mw / 1000, 1)
    limit_w = round(limit_mw / 1000, 1)
    return {
        "device_index": index,
        "power_draw_w": power_w,
        "power_limit_w": limit_w,
        "power_usage_pct": round(power_w / limit_w * 100, 1) if limit_w > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# MCP Tool: gpu_list_devices
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_list_devices",
    annotations={"title": "List GPU Devices", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_list_devices(params: GpuListDevicesInput) -> str:
    """List all GPUs with name, memory, and driver version."""
    try:
        if MOCK_MODE:
            logger.debug("gpu_list_devices: using mock mode")
            count = get_mock_gpu_count()
            devices: list[dict[str, Any]] = []
            for i in range(count):
                info = get_mock_gpu_info(i)
                devices.append(
                    {
                        "device_index": i,
                        "name": info.name,
                        "total_memory_mb": info.total_memory_mb,
                        "driver_version": "535.129.03 (mock)",
                    }
                )
            return _json(devices)
        else:
            logger.debug("gpu_list_devices: querying NVML")
            devices = await asyncio.to_thread(_real_list_devices)
            return _json(devices)
    except Exception as exc:
        logger.error("gpu_list_devices failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_utilization
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_utilization",
    annotations={
        "title": "Get GPU Utilization",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_get_utilization(params: GpuDeviceIndexInput) -> str:
    """Get real-time GPU and memory utilization for a specific device."""
    try:
        if MOCK_MODE:
            logger.debug("gpu_get_utilization: mock mode, device=%d", params.device_index)
            count = get_mock_gpu_count()
            _validate_device_index(params.device_index, count)
            info = get_mock_gpu_info(params.device_index)
            return _json(
                {
                    "device_index": params.device_index,
                    "gpu_utilization_pct": info.gpu_utilization,
                    "memory_utilization_pct": info.memory_utilization,
                }
            )
        else:
            logger.debug("gpu_get_utilization: NVML, device=%d", params.device_index)
            result = await asyncio.to_thread(_real_get_utilization, params.device_index)
            return _json(result)
    except ValueError as exc:
        logger.warning("gpu_get_utilization validation error: %s", exc)
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
        if MOCK_MODE:
            logger.debug("gpu_get_memory: mock mode, device=%d", params.device_index)
            count = get_mock_gpu_count()
            _validate_device_index(params.device_index, count)
            info = get_mock_gpu_info(params.device_index)
            used_mb = int(info.total_memory_mb * info.memory_utilization / 100)
            free_mb = info.total_memory_mb - used_mb
            return _json(
                {
                    "device_index": params.device_index,
                    "total_mb": info.total_memory_mb,
                    "used_mb": used_mb,
                    "free_mb": free_mb,
                    "used_pct": round(info.memory_utilization, 1),
                }
            )
        else:
            logger.debug("gpu_get_memory: NVML, device=%d", params.device_index)
            result = await asyncio.to_thread(_real_get_memory, params.device_index)
            return _json(result)
    except ValueError as exc:
        logger.warning("gpu_get_memory validation error: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_get_memory failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_temperature
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_temperature",
    annotations={
        "title": "Get GPU Temperature",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_get_temperature(params: GpuDeviceIndexInput) -> str:
    """Get temperature and thermal throttle status for a GPU device."""
    try:
        if MOCK_MODE:
            logger.debug("gpu_get_temperature: mock mode, device=%d", params.device_index)
            count = get_mock_gpu_count()
            _validate_device_index(params.device_index, count)
            info = get_mock_gpu_info(params.device_index)
            temp = info.temperature
            return _json(
                {
                    "device_index": params.device_index,
                    "temperature_c": temp,
                    "throttle_warning": temp > 85,
                    "status": ("critical" if temp > 90 else ("warning" if temp > 85 else "normal")),
                }
            )
        else:
            logger.debug("gpu_get_temperature: NVML, device=%d", params.device_index)
            result = await asyncio.to_thread(_real_get_temperature, params.device_index)
            return _json(result)
    except ValueError as exc:
        logger.warning("gpu_get_temperature validation error: %s", exc)
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
        if MOCK_MODE:
            logger.debug("gpu_get_power: mock mode, device=%d", params.device_index)
            count = get_mock_gpu_count()
            _validate_device_index(params.device_index, count)
            info = get_mock_gpu_info(params.device_index)
            power_w = float(info.power_draw_w)
            limit_w = float(info.power_limit_w)
            return _json(
                {
                    "device_index": params.device_index,
                    "power_draw_w": power_w,
                    "power_limit_w": limit_w,
                    "power_usage_pct": (round(power_w / limit_w * 100, 1) if limit_w > 0 else 0.0),
                }
            )
        else:
            logger.debug("gpu_get_power: NVML, device=%d", params.device_index)
            result = await asyncio.to_thread(_real_get_power, params.device_index)
            return _json(result)
    except ValueError as exc:
        logger.warning("gpu_get_power validation error: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_get_power failed: %s", exc)
        return _json({"error": str(exc)})


# ---------------------------------------------------------------------------
# MCP Tool: gpu_get_cluster_summary
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_get_cluster_summary",
    annotations={
        "title": "GPU Cluster Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_get_cluster_summary(params: GpuClusterSummaryInput) -> str:
    """Aggregate GPU stats across all devices.

    Returns device count, average utilization, total/used memory,
    hottest device, and most loaded device.
    """
    try:
        if MOCK_MODE:
            logger.debug("gpu_get_cluster_summary: mock mode")
            count = get_mock_gpu_count()
            devices: list[dict[str, Any]] = []
            for i in range(count):
                info = get_mock_gpu_info(i)
                used_mb = int(info.total_memory_mb * info.memory_utilization / 100)
                devices.append(
                    {
                        "device_index": i,
                        "name": info.name,
                        "gpu_utilization_pct": info.gpu_utilization,
                        "memory_total_mb": info.total_memory_mb,
                        "memory_used_mb": used_mb,
                        "temperature_c": info.temperature,
                        "power_draw_w": info.power_draw_w,
                    }
                )
        else:
            logger.debug("gpu_get_cluster_summary: querying NVML")
            devices = await asyncio.to_thread(_real_cluster_data)

        if not devices:
            return _json({"error": "No GPU devices found"})

        total_mem = sum(d["memory_total_mb"] for d in devices)
        total_used = sum(d["memory_used_mb"] for d in devices)
        avg_util = round(sum(d["gpu_utilization_pct"] for d in devices) / len(devices), 1)
        hottest = max(devices, key=lambda d: d["temperature_c"])
        most_loaded = max(devices, key=lambda d: d["gpu_utilization_pct"])

        summary: dict[str, Any] = {
            "device_count": len(devices),
            "avg_gpu_utilization_pct": avg_util,
            "total_memory_mb": total_mem,
            "used_memory_mb": total_used,
            "free_memory_mb": total_mem - total_used,
            "memory_used_pct": (round(total_used / total_mem * 100, 1) if total_mem > 0 else 0.0),
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


def _real_cluster_data() -> list[dict[str, Any]]:
    """Gather per-device stats from NVML for cluster summary (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    devices: list[dict[str, Any]] = []
    for i in range(count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
        devices.append(
            {
                "device_index": i,
                "name": name if isinstance(name, str) else name.decode("utf-8"),
                "gpu_utilization_pct": rates.gpu,
                "memory_total_mb": round(mem.total / (1024 * 1024)),
                "memory_used_mb": round(mem.used / (1024 * 1024)),
                "temperature_c": temp,
                "power_draw_w": round(power_mw / 1000, 1),
            }
        )
    return devices
