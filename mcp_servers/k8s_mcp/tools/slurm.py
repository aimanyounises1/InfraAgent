"""Slurm HPC job scheduler tools for k8s_mcp.

Integrates with Slurm via CLI commands (squeue, sinfo, scontrol) to provide:
- Job queue status and GPU allocation visibility
- Node state and GPU resource tracking

Requires Slurm to be installed and accessible. When not available,
returns a clear error explaining the requirement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from typing import Any

from mcp_servers.k8s_mcp.server import mcp

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Slurm availability detection
# ---------------------------------------------------------------------------

_SQUEUE = shutil.which("squeue")
_SINFO = shutil.which("sinfo")
_SCONTROL = shutil.which("scontrol")
_SLURM_AVAILABLE = bool(_SQUEUE and _SINFO)

if _SLURM_AVAILABLE:
    logger.info("Slurm detected: squeue=%s sinfo=%s", _SQUEUE, _SINFO)
else:
    logger.info("Slurm not detected (squeue/sinfo not in PATH)")


def _slurm_not_available_error(tool_name: str) -> str:
    """Standard error when Slurm isn't available."""
    return _json({
        "error": f"{tool_name} requires Slurm job scheduler.",
        "slurm_available": False,
        "hint": "Slurm commands (squeue, sinfo) must be in PATH. "
        "This tool is designed for HPC clusters with Slurm installed.",
    })


# ---------------------------------------------------------------------------
# Real Slurm queries
# ---------------------------------------------------------------------------


def _run_squeue() -> dict[str, Any]:
    """Get job queue via squeue."""
    try:
        result = subprocess.run(
            [
                "squeue",
                "--format=%i|%j|%u|%P|%T|%D|%b|%N|%V|%S|%M|%l|%Q",
                "--noheader",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {"error": f"squeue failed: {result.stderr.strip()}"}

        jobs: list[dict[str, Any]] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            if len(parts) >= 13:
                jobs.append({
                    "job_id": parts[0].strip(),
                    "name": parts[1].strip(),
                    "user": parts[2].strip(),
                    "partition": parts[3].strip(),
                    "state": parts[4].strip(),
                    "num_nodes": parts[5].strip(),
                    "gres": parts[6].strip(),
                    "nodes": parts[7].strip(),
                    "submit_time": parts[8].strip(),
                    "start_time": parts[9].strip(),
                    "elapsed": parts[10].strip(),
                    "time_limit": parts[11].strip(),
                    "priority": parts[12].strip(),
                })

        running = [j for j in jobs if j["state"] == "RUNNING"]
        pending = [j for j in jobs if j["state"] == "PENDING"]

        return {
            "total_jobs": len(jobs),
            "running": len(running),
            "pending": len(pending),
            "jobs": jobs,
        }
    except subprocess.TimeoutExpired:
        return {"error": "squeue timed out after 30s"}
    except Exception as exc:
        return {"error": str(exc)}


def _run_sinfo() -> dict[str, Any]:
    """Get node status via sinfo."""
    try:
        result = subprocess.run(
            [
                "sinfo",
                "--format=%n|%T|%c|%m|%G|%P|%f|%O",
                "--noheader",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {"error": f"sinfo failed: {result.stderr.strip()}"}

        nodes: list[dict[str, Any]] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            if len(parts) >= 8:
                nodes.append({
                    "node_name": parts[0].strip(),
                    "state": parts[1].strip(),
                    "cpus_total": parts[2].strip(),
                    "memory_total_mb": parts[3].strip(),
                    "gres": parts[4].strip(),
                    "partitions": parts[5].strip(),
                    "features": parts[6].strip(),
                    "cpu_load": parts[7].strip(),
                })

        return {
            "total_nodes": len(nodes),
            "nodes": nodes,
        }
    except subprocess.TimeoutExpired:
        return {"error": "sinfo timed out after 30s"}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_slurm_queue",
    annotations={"title": "Slurm Job Queue", "readOnlyHint": True, "destructiveHint": False},
)
async def k8s_slurm_queue() -> str:
    """List Slurm job queue showing running and pending jobs.

    Returns job IDs, names, users, GPU allocations, node assignments,
    elapsed time, and pending reasons.
    Requires Slurm (squeue) to be installed and accessible.
    """
    if not _SLURM_AVAILABLE:
        return _slurm_not_available_error("k8s_slurm_queue")

    try:
        data = await asyncio.to_thread(_run_squeue)
        return _json(data)
    except Exception as exc:
        logger.error("k8s_slurm_queue failed: %s", exc)
        return _json({"error": str(exc)})


@mcp.tool(
    name="k8s_slurm_nodes",
    annotations={"title": "Slurm Node Status", "readOnlyHint": True, "destructiveHint": False},
)
async def k8s_slurm_nodes() -> str:
    """List Slurm node status showing resource allocation and availability.

    Returns per-node CPU, memory, GPU allocation, node state, and features.
    Requires Slurm (sinfo) to be installed and accessible.
    """
    if not _SLURM_AVAILABLE:
        return _slurm_not_available_error("k8s_slurm_nodes")

    try:
        data = await asyncio.to_thread(_run_sinfo)
        return _json(data)
    except Exception as exc:
        logger.error("k8s_slurm_nodes failed: %s", exc)
        return _json({"error": str(exc)})
