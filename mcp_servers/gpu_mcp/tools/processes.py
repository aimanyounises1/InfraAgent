"""GPU process management tools.

Provides MCP tools for listing processes running on GPU devices.
Supports both real NVML hardware queries and mock mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.gpu_mcp.models import GpuDeviceIndexInput  # noqa: TC001
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import (
    MOCK_MODE,
    get_mock_gpu_count,
    get_mock_processes,
)

logger = logging.getLogger(__name__)

# Conditional pynvml import — mirrors monitor.py pattern.
pynvml: Any = None

if not MOCK_MODE:
    try:
        import pynvml as _pynvml

        pynvml = _pynvml
        # nvmlInit is already called in monitor.py; safe to call again (idempotent)
        pynvml.nvmlInit()
    except Exception as exc:
        logger.error("Failed to initialize pynvml in processes module: %s", exc)
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


def _real_list_processes(index: int) -> dict[str, Any]:
    """Query NVML for running compute processes on a GPU (synchronous)."""
    count = pynvml.nvmlDeviceGetCount()
    _validate_device_index(index, count)
    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
    procs = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)

    processes: list[dict[str, Any]] = []
    for proc in procs:
        pid = proc.pid
        mem_bytes = proc.usedGpuMemory if proc.usedGpuMemory else 0
        # Try to get process name; may fail for permission reasons
        try:
            name = pynvml.nvmlSystemGetProcessName(pid)
            if isinstance(name, bytes):
                name = name.decode("utf-8")
        except Exception:
            name = "unknown"
        processes.append(
            {
                "pid": pid,
                "name": name,
                "memory_mb": round(mem_bytes / (1024 * 1024)),
                "type": "Compute",
            }
        )

    return {
        "device_index": index,
        "process_count": len(processes),
        "processes": processes,
    }


@mcp.tool(
    name="gpu_list_processes",
    annotations={
        "title": "List GPU Processes",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_list_processes(params: GpuDeviceIndexInput) -> str:
    """List processes running on a GPU with PID, name, and memory usage."""
    try:
        if MOCK_MODE:
            logger.debug("gpu_list_processes: mock mode, device=%d", params.device_index)
            count = get_mock_gpu_count()
            _validate_device_index(params.device_index, count)
            processes = get_mock_processes(params.device_index)
            return _json(
                {
                    "device_index": params.device_index,
                    "process_count": len(processes),
                    "processes": processes,
                }
            )
        else:
            logger.debug("gpu_list_processes: NVML, device=%d", params.device_index)
            result = await asyncio.to_thread(_real_list_processes, params.device_index)
            return _json(result)
    except ValueError as exc:
        logger.warning("gpu_list_processes validation error: %s", exc)
        return _json({"error": str(exc)})
    except Exception as exc:
        logger.error("gpu_list_processes failed: %s", exc)
        return _json({"error": str(exc)})
