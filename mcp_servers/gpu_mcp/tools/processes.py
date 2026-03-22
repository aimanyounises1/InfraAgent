"""GPU process management tools.

Provides MCP tools for listing processes running on GPU devices.
Auto-adapts to detected hardware — no mock data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.gpu_mcp.models import GpuDeviceIndexInput  # noqa: TC001
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import get_backend, get_gpu_count, get_processes

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2, default=str)


def _list_processes_sync(index: int) -> dict[str, Any]:
    """Get processes for a device (synchronous)."""
    procs = get_processes(index)
    return {
        "device_index": index,
        "process_count": len(procs),
        "processes": procs,
        "backend": get_backend(),
    }


@mcp.tool(
    name="gpu_list_processes",
    annotations={"title": "List GPU Processes", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_list_processes(params: GpuDeviceIndexInput) -> str:
    """List processes running on a GPU with PID, name, and memory usage.

    On NVIDIA: Shows CUDA compute processes via pynvml.
    On Apple Silicon: Shows top processes by CPU usage (proxy for GPU).
    """
    try:
        count = get_gpu_count()
        if count == 0:
            return _json({
                "device_index": params.device_index,
                "process_count": 0,
                "processes": [],
                "backend": get_backend(),
                "message": "No GPU hardware detected.",
            })

        if params.device_index < 0 or params.device_index >= count:
            return _json({
                "error": f"Device index {params.device_index} out of range. "
                f"Available: 0-{count - 1} ({count} total)",
            })

        result = await asyncio.to_thread(_list_processes_sync, params.device_index)
        return _json(result)
    except Exception as exc:
        logger.error("gpu_list_processes failed: %s", exc)
        return _json({"error": str(exc)})
