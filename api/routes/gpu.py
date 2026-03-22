"""GPU monitoring API routes -- wired to gpu_mcp tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter

from mcp_servers.gpu_mcp.models import (
    GpuClusterSummaryInput,
    GpuHealthCheckInput,
    GpuListDevicesInput,
)
from mcp_servers.gpu_mcp.tools.health import gpu_health_check
from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary, gpu_list_devices

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def gpu_status() -> dict[str, Any]:
    """Get GPU cluster status including cluster summary and per-device listing.

    Calls both the cluster summary and device listing tools, combines
    the results into a single response payload.

    Returns:
        Dictionary with status, cluster summary, and device list.
    """
    logger.info("gpu_status route called")

    try:
        summary_raw: str = await gpu_get_cluster_summary(GpuClusterSummaryInput())
        devices_raw: str = await gpu_list_devices(GpuListDevicesInput())

        summary_parsed: dict[str, Any] = json.loads(summary_raw)
        devices_parsed: Any = json.loads(devices_raw)

        # Check for errors in either response
        if isinstance(summary_parsed, dict) and "error" in summary_parsed:
            logger.warning(
                "gpu_status cluster summary returned error",
                extra={"error": summary_parsed["error"]},
            )
            return {"status": "error", "message": summary_parsed["error"]}

        if isinstance(devices_parsed, dict) and "error" in devices_parsed:
            logger.warning(
                "gpu_status device list returned error",
                extra={"error": devices_parsed["error"]},
            )
            return {"status": "error", "message": devices_parsed["error"]}

        return {
            "status": "ok",
            "cluster_summary": summary_parsed,
            "devices": devices_parsed,
        }

    except json.JSONDecodeError as e:
        logger.error("gpu_status JSON parse failed", extra={"error": str(e)})
        return {"status": "error", "message": f"Failed to parse tool response: {e}"}
    except Exception as e:
        logger.error("gpu_status failed", extra={"error": str(e)})
        return {"status": "error", "message": str(e)}


@router.get("/health")
async def gpu_health() -> dict[str, Any]:
    """Run a comprehensive GPU health check across all devices.

    Returns per-device health reports and an overall cluster health status.

    Returns:
        Dictionary with status and health check data.
    """
    logger.info("gpu_health route called")

    try:
        raw_result: str = await gpu_health_check(GpuHealthCheckInput())
        parsed: dict[str, Any] = json.loads(raw_result)

        if "error" in parsed:
            logger.warning(
                "gpu_health returned error from tool",
                extra={"error": parsed["error"]},
            )
            return {"status": "error", "message": parsed["error"]}

        return {"status": "ok", "data": parsed}

    except json.JSONDecodeError as e:
        logger.error("gpu_health JSON parse failed", extra={"error": str(e)})
        return {"status": "error", "message": f"Failed to parse tool response: {e}"}
    except Exception as e:
        logger.error("gpu_health failed", extra={"error": str(e)})
        return {"status": "error", "message": str(e)}
