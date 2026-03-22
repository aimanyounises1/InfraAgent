"""GPU health check tools.

Provides MCP tools for comprehensive GPU health assessment across
all devices. Auto-adapts to detected hardware — no mock data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.gpu_mcp.models import GpuHealthCheckInput  # noqa: TC001
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import get_backend, get_gpu_count, get_health

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2, default=str)


def _health_check_sync() -> list[dict[str, Any]]:
    """Run health checks against all detected GPUs (synchronous)."""
    count = get_gpu_count()
    devices: list[dict[str, Any]] = []
    for i in range(count):
        devices.append(get_health(i))
    return devices


def _compute_overall_status(devices: list[dict[str, Any]]) -> str:
    """Determine overall cluster health from per-device statuses."""
    statuses = [d["status"] for d in devices]
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    return "healthy"


@mcp.tool(
    name="gpu_health_check",
    annotations={"title": "GPU Health Check", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_health_check(params: GpuHealthCheckInput) -> str:
    """Comprehensive health report across all GPU devices.

    Checks temperature, utilization, memory, and ECC errors for each device.
    Returns per-device breakdown and overall cluster status.
    Auto-detects hardware backend (NVIDIA, Apple Silicon, or none).
    """
    try:
        backend = get_backend()
        count = get_gpu_count()

        if count == 0:
            return _json({
                "overall_status": "unknown",
                "device_count": 0,
                "backend": backend,
                "message": "No GPU hardware detected on this system.",
            })

        devices = await asyncio.to_thread(_health_check_sync)
        overall = _compute_overall_status(devices)

        healthy_count = sum(1 for d in devices if d["status"] == "healthy")
        warning_count = sum(1 for d in devices if d["status"] == "warning")
        critical_count = sum(1 for d in devices if d["status"] == "critical")

        report: dict[str, Any] = {
            "overall_status": overall,
            "device_count": len(devices),
            "backend": backend,
            "summary": {
                "healthy": healthy_count,
                "warning": warning_count,
                "critical": critical_count,
            },
            "devices": devices,
        }

        logger.info(
            "gpu_health_check complete: overall=%s, devices=%d, backend=%s",
            overall,
            len(devices),
            backend,
        )
        return _json(report)
    except Exception as exc:
        logger.error("gpu_health_check failed: %s", exc)
        return _json({"error": str(exc)})
