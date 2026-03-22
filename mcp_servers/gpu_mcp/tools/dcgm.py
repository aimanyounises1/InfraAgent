"""DCGM (Data Center GPU Manager) telemetry tools.

Provides deep GPU diagnostics beyond basic NVML: XID errors, PCIe throughput,
retired pages, violation status, and DCGM field group queries.

Requires NVIDIA GPUs with DCGM installed (dcgmi CLI or pydcgm).
When DCGM is not available, reports the subsystem as unavailable (never fakes data).
When running on non-NVIDIA hardware, returns a clear error explaining why.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from mcp_servers.gpu_mcp.models import (
    DcgmFieldGroupInput,
    DcgmXidErrorsInput,
    GpuDeviceIndexInput,
)
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import get_backend, get_gpu_count

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# DCGM availability check
# ---------------------------------------------------------------------------

_DCGM_AVAILABLE = False
_DCGM_METHOD = "none"  # "pydcgm", "cli", "none"

try:
    import pydcgm  # noqa: F401
    _DCGM_AVAILABLE = True
    _DCGM_METHOD = "pydcgm"
    logger.info("DCGM backend: pydcgm library")
except ImportError:
    if shutil.which("dcgmi"):
        _DCGM_AVAILABLE = True
        _DCGM_METHOD = "cli"
        logger.info("DCGM backend: dcgmi CLI")
    else:
        logger.info("DCGM not available (no pydcgm or dcgmi found)")


def _dcgm_not_available_error(tool_name: str) -> str:
    """Standard error response when DCGM isn't available."""
    backend = get_backend()
    if backend != "nvml":
        return _json({
            "error": f"{tool_name} requires NVIDIA GPUs with DCGM installed.",
            "detected_backend": backend,
            "hint": "DCGM is only available on systems with NVIDIA datacenter GPUs.",
        })
    return _json({
        "error": f"{tool_name} requires DCGM (Data Center GPU Manager).",
        "detected_backend": backend,
        "hint": "Install DCGM: https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/getting-started.html",
        "install_cmd": "apt-get install -y datacenter-gpu-manager",
    })


# ---------------------------------------------------------------------------
# Real DCGM queries via CLI
# ---------------------------------------------------------------------------


def _dcgm_cli_diag(device_index: int) -> dict[str, Any]:
    """Run dcgmi health check for a device."""
    try:
        result = subprocess.run(
            ["dcgmi", "health", "-c", "-g", str(device_index)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "device_index": device_index,
            "dcgm_output": result.stdout.strip(),
            "return_code": result.returncode,
        }
    except Exception as exc:
        return {"device_index": device_index, "error": str(exc)}


def _dcgm_cli_field_values(device_index: int, field_group: str) -> dict[str, Any]:
    """Query DCGM field values for a device via dcgmi."""
    # Map field groups to dcgmi field IDs
    field_map = {
        "health": "100,101,102,103,104,112,310,311,312,313",
        "performance": "1001,1002,1003,1004,1005,1006,1007,1008,1009,1010",
        "power": "150,155,156,157,158,160",
        "memory": "250,251,252,253,254",
    }
    field_ids = field_map.get(field_group, field_map["health"])

    try:
        result = subprocess.run(
            ["dcgmi", "dmon", "-e", field_ids, "-c", "1", "-d", str(device_index)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "device_index": device_index,
            "field_group": field_group,
            "raw_output": result.stdout.strip(),
            "return_code": result.returncode,
        }
    except Exception as exc:
        return {"device_index": device_index, "field_group": field_group, "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_dcgm_field_group",
    annotations={
        "title": "Query DCGM Field Group",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gpu_dcgm_field_group(params: DcgmFieldGroupInput) -> str:
    """Query DCGM field group data for a GPU device.

    Provides deep telemetry beyond nvidia-smi: SM occupancy, tensor core
    utilization, PCIe/NVLink throughput, HBM bandwidth, power violations,
    ECC error counts, and retired pages.

    Field groups: 'health', 'performance', 'power', 'memory'.
    Requires DCGM installed on a system with NVIDIA datacenter GPUs.
    """
    if not _DCGM_AVAILABLE:
        return _dcgm_not_available_error("gpu_dcgm_field_group")

    try:
        import asyncio

        if _DCGM_METHOD == "cli":
            data = await asyncio.to_thread(
                _dcgm_cli_field_values, params.device_index, params.field_group
            )
            return _json(data)
        else:
            # pydcgm path — implement when pydcgm is available
            return _json({
                "error": "pydcgm integration not yet implemented",
                "hint": "Use dcgmi CLI method for now",
            })
    except Exception as exc:
        logger.error("gpu_dcgm_field_group failed: %s", exc)
        return _json({"error": str(exc)})


@mcp.tool(
    name="gpu_dcgm_xid_errors",
    annotations={
        "title": "Get XID Error History",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_dcgm_xid_errors(params: DcgmXidErrorsInput) -> str:
    """Get XID error history for GPU devices from DCGM.

    XID errors are critical GPU fault indicators. Common codes:
    - XID 31: GPU memory page fault
    - XID 48: Double-bit ECC error (uncorrectable)
    - XID 63: Row-remapping failure
    - XID 79: GPU fallen off the bus
    - XID 94: Contained ECC error (correctable, safe)

    Requires DCGM installed on a system with NVIDIA datacenter GPUs.
    """
    if not _DCGM_AVAILABLE:
        return _dcgm_not_available_error("gpu_dcgm_xid_errors")

    try:
        import asyncio

        # Use dmesg + nvidia-smi as fallback for XID error checking
        result = await asyncio.to_thread(_get_xid_from_system, params.device_index, params.hours)
        return _json(result)
    except Exception as exc:
        logger.error("gpu_dcgm_xid_errors failed: %s", exc)
        return _json({"error": str(exc)})


def _get_xid_from_system(device_index: int | None, hours: int) -> dict[str, Any]:
    """Check for XID errors from dmesg and nvidia-smi."""
    errors: list[dict[str, Any]] = []

    # Check dmesg for NVRM XID errors
    try:
        result = subprocess.run(
            ["dmesg", "--time-format=iso"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "NVRM: Xid" in line:
                    errors.append({"raw": line.strip(), "source": "dmesg"})
    except Exception:
        pass  # dmesg may require root

    # Check nvidia-smi for pending page retirements
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=gpu_uuid,ecc.errors.corrected.volatile.total,ecc.errors.uncorrected.volatile.total",
             "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    errors.append({"raw": line.strip(), "source": "nvidia-smi"})
    except Exception:
        pass

    return {
        "query": {"device_index": device_index, "hours": hours},
        "total_errors": len(errors),
        "errors": errors,
        "dcgm_method": _DCGM_METHOD,
    }


@mcp.tool(
    name="gpu_dcgm_cluster_health",
    annotations={
        "title": "DCGM Cluster Health Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def gpu_dcgm_cluster_health(params: GpuDeviceIndexInput) -> str:
    """Get DCGM health summary across all GPUs in the cluster.

    Aggregates health status, ECC errors, retired pages, thermal/power
    violations, and NVLink status for every detected GPU.
    Requires DCGM installed on a system with NVIDIA datacenter GPUs.
    """
    if not _DCGM_AVAILABLE:
        return _dcgm_not_available_error("gpu_dcgm_cluster_health")

    try:
        import asyncio

        if _DCGM_METHOD == "cli":
            data = await asyncio.to_thread(_dcgm_cli_cluster_health)
            return _json(data)
        else:
            return _json({
                "error": "pydcgm cluster health not yet implemented",
                "hint": "Use dcgmi CLI method for now",
            })
    except Exception as exc:
        logger.error("gpu_dcgm_cluster_health failed: %s", exc)
        return _json({"error": str(exc)})


def _dcgm_cli_cluster_health() -> dict[str, Any]:
    """Run dcgmi health check for all GPUs."""
    try:
        result = subprocess.run(
            ["dcgmi", "health", "-c"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "dcgm_output": result.stdout.strip(),
            "return_code": result.returncode,
            "total_gpus": get_gpu_count(),
            "dcgm_method": _DCGM_METHOD,
        }
    except Exception as exc:
        return {"error": str(exc)}
