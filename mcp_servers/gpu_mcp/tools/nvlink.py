"""NVLink topology and interconnect monitoring tools.

Provides GPU-to-GPU interconnect visibility: NVLink status per pair,
bandwidth utilization, error counters, NVSwitch health, and topology
discovery.

Requires NVIDIA GPUs with NVLink support. On non-NVLink hardware,
returns a clear error explaining the requirement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Any

from mcp_servers.gpu_mcp.models import (
    GpuDeviceIndexInput,
    NvlinkTopologyInput,
)
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import get_backend, get_gpu_count, pynvml

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _nvlink_not_available_error(tool_name: str) -> str:
    """Standard error when NVLink isn't available."""
    backend = get_backend()
    if backend != "nvml":
        return _json({
            "error": f"{tool_name} requires NVIDIA GPUs with NVLink support.",
            "detected_backend": backend,
            "hint": "NVLink is available on multi-GPU NVIDIA systems (DGX, HGX, etc.)",
        })
    return _json({
        "error": f"{tool_name}: NVLink not detected on this NVIDIA GPU.",
        "detected_backend": backend,
        "hint": "NVLink requires compatible GPUs (A100, H100, etc.) and NVSwitch.",
    })


# ---------------------------------------------------------------------------
# Real NVLink queries
# ---------------------------------------------------------------------------


def _nvml_nvlink_status(device_index: int) -> dict[str, Any]:
    """Query NVLink status via pynvml."""
    if pynvml is None:
        return {"error": "pynvml not available"}

    count = get_gpu_count()
    if device_index < 0 or device_index >= count:
        return {"error": f"Device index {device_index} out of range (0-{count - 1})"}

    handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
    links: list[dict[str, Any]] = []
    active_links = 0

    for link_id in range(18):  # Max 18 links on H100
        try:
            state = pynvml.nvmlDeviceGetNvLinkState(handle, link_id)
            if not state:
                continue

            active_links += 1
            link_info: dict[str, Any] = {
                "link_id": link_id,
                "state": "active",
            }

            # Try to get remote device info
            try:
                remote = pynvml.nvmlDeviceGetNvLinkRemotePciInfo(handle, link_id)
                link_info["remote_pci_bus_id"] = remote.busId if hasattr(remote, "busId") else str(remote)
            except Exception:
                pass

            # Try to get error counters
            try:
                crc_flit = pynvml.nvmlDeviceGetNvLinkErrorCounter(
                    handle, link_id, pynvml.NVML_NVLINK_ERROR_DL_CRC_FLIT
                )
                crc_data = pynvml.nvmlDeviceGetNvLinkErrorCounter(
                    handle, link_id, pynvml.NVML_NVLINK_ERROR_DL_CRC_DATA
                )
                replay = pynvml.nvmlDeviceGetNvLinkErrorCounter(
                    handle, link_id, pynvml.NVML_NVLINK_ERROR_DL_REPLAY
                )
                link_info["crc_flit_errors"] = crc_flit
                link_info["crc_data_errors"] = crc_data
                link_info["replay_errors"] = replay
            except Exception:
                pass

            # Try to get throughput
            try:
                tx = pynvml.nvmlDeviceGetNvLinkUtilizationCounter(handle, link_id, 0)
                rx = pynvml.nvmlDeviceGetNvLinkUtilizationCounter(handle, link_id, 1)
                link_info["tx_bytes"] = tx
                link_info["rx_bytes"] = rx
            except Exception:
                pass

            links.append(link_info)
        except Exception:
            break  # No more links

    name = pynvml.nvmlDeviceGetName(handle)
    if isinstance(name, bytes):
        name = name.decode("utf-8")

    return {
        "device_index": device_index,
        "gpu_name": name,
        "total_links": active_links,
        "active_links": active_links,
        "backend": "nvml",
        "links": links,
    }


def _nvidia_smi_topo() -> dict[str, Any]:
    """Get topology via nvidia-smi topo -m."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "topo", "-m"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return {
                "topology_output": result.stdout.strip(),
                "backend": "nvidia-smi",
            }
        return {"error": f"nvidia-smi topo failed: {result.stderr.strip()}"}
    except FileNotFoundError:
        return {"error": "nvidia-smi not found"}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_nvlink_status",
    annotations={"title": "NVLink Status", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_nvlink_status(params: GpuDeviceIndexInput) -> str:
    """Get NVLink interconnect status for a GPU device.

    Reports per-link state, error counters, and throughput.
    Requires NVIDIA GPUs with NVLink support.
    """
    backend = get_backend()
    if backend != "nvml":
        return _nvlink_not_available_error("gpu_nvlink_status")

    try:
        data = await asyncio.to_thread(_nvml_nvlink_status, params.device_index)
        # Check if any NVLink was found
        if data.get("total_links", 0) == 0:
            return _json({
                "device_index": params.device_index,
                "nvlink_present": False,
                "message": "No NVLink connections detected on this GPU. "
                "NVLink requires compatible GPUs in a multi-GPU configuration.",
                "backend": backend,
            })
        return _json(data)
    except Exception as exc:
        logger.error("gpu_nvlink_status failed: %s", exc)
        return _json({"error": str(exc)})


@mcp.tool(
    name="gpu_nvlink_topology",
    annotations={"title": "GPU Topology", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_nvlink_topology(params: NvlinkTopologyInput) -> str:
    """Get GPU interconnect topology (equivalent to nvidia-smi topo -m).

    Shows connectivity between all GPUs: NVLink, PCIe, or cross-node.
    Requires NVIDIA GPUs.
    """
    backend = get_backend()
    if backend != "nvml":
        return _nvlink_not_available_error("gpu_nvlink_topology")

    try:
        data = await asyncio.to_thread(_nvidia_smi_topo)
        return _json(data)
    except Exception as exc:
        logger.error("gpu_nvlink_topology failed: %s", exc)
        return _json({"error": str(exc)})
