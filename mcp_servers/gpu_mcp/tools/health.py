"""GPU health check tools.

Provides MCP tools for comprehensive GPU health assessment across
all devices. Supports both real NVML hardware queries and mock mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.gpu_mcp.models import GpuHealthCheckInput  # noqa: TC001
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import (
    MOCK_MODE,
    get_mock_gpu_count,
    get_mock_health,
)

logger = logging.getLogger(__name__)

# Conditional pynvml import — mirrors monitor.py pattern.
pynvml: Any = None

if not MOCK_MODE:
    try:
        import pynvml as _pynvml

        pynvml = _pynvml
        pynvml.nvmlInit()
    except Exception as exc:
        logger.error("Failed to initialize pynvml in health module: %s", exc)
        raise


def _json(data: Any) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2, default=str)


def _real_health_check() -> list[dict[str, Any]]:
    """Run health checks against all GPUs via NVML (synchronous).

    Returns a list of per-device health reports.
    """
    count = pynvml.nvmlDeviceGetCount()
    devices: list[dict[str, Any]] = []

    for i in range(count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")

        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
        limit_mw = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle)

        # Check for ECC errors (non-fatal)
        ecc_errors = 0
        try:
            ecc_errors = pynvml.nvmlDeviceGetTotalEccErrors(
                handle,
                pynvml.NVML_MEMORY_ERROR_TYPE_UNCORRECTED,
                pynvml.NVML_VOLATILE_ECC,
            )
        except Exception:
            # ECC may not be supported on all devices
            ecc_errors = 0

        util = rates.gpu
        mem_util = round(mem.used / mem.total * 100, 1) if mem.total > 0 else 0.0

        # Determine status
        if temp > 90:
            status = "critical"
        elif temp >= 80 or util >= 95:
            status = "warning"
        else:
            status = "healthy"

        devices.append(
            {
                "device_index": i,
                "name": name,
                "status": status,
                "temperature_c": temp,
                "gpu_utilization_pct": util,
                "memory_utilization_pct": mem_util,
                "memory_used_mb": round(mem.used / (1024 * 1024)),
                "memory_free_mb": round(mem.free / (1024 * 1024)),
                "memory_total_mb": round(mem.total / (1024 * 1024)),
                "power_draw_w": round(power_mw / 1000, 1),
                "power_limit_w": round(limit_mw / 1000, 1),
                "throttle_warning": temp > 85,
                "ecc_errors": ecc_errors,
            }
        )

    return devices


def _compute_overall_status(devices: list[dict[str, Any]]) -> str:
    """Determine overall cluster health from per-device statuses.

    Returns "critical" if any device is critical, "warning" if any
    device has a warning, otherwise "healthy".
    """
    statuses = [d["status"] for d in devices]
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    return "healthy"


@mcp.tool(
    name="gpu_health_check",
    annotations={
        "title": "GPU Health Check",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_health_check(params: GpuHealthCheckInput) -> str:
    """Comprehensive health report across all GPU devices.

    Checks temperature, utilization, memory, and ECC errors for each device.
    Returns per-device breakdown and overall cluster status.
    """
    try:
        if MOCK_MODE:
            logger.debug("gpu_health_check: mock mode")
            count = get_mock_gpu_count()
            devices: list[dict[str, Any]] = []
            for i in range(count):
                devices.append(get_mock_health(i))
        else:
            logger.debug("gpu_health_check: querying NVML")
            devices = await asyncio.to_thread(_real_health_check)

        overall = _compute_overall_status(devices)

        # Count devices by status
        healthy_count = sum(1 for d in devices if d["status"] == "healthy")
        warning_count = sum(1 for d in devices if d["status"] == "warning")
        critical_count = sum(1 for d in devices if d["status"] == "critical")

        report: dict[str, Any] = {
            "overall_status": overall,
            "device_count": len(devices),
            "summary": {
                "healthy": healthy_count,
                "warning": warning_count,
                "critical": critical_count,
            },
            "devices": devices,
        }

        logger.info(
            "gpu_health_check complete: overall=%s, devices=%d",
            overall,
            len(devices),
        )
        return _json(report)
    except Exception as exc:
        logger.error("gpu_health_check failed: %s", exc)
        return _json({"error": str(exc)})
