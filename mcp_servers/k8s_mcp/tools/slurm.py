"""Slurm HPC job scheduler tools for k8s_mcp.

Integrates with Slurm via CLI commands (squeue, sinfo, scontrol, sbatch,
scancel, sacct) to provide:
- Job queue status and GPU allocation visibility
- Node state and GPU resource tracking
- Job submission, cancellation, and detailed accounting

Requires Slurm to be installed and accessible. When not available,
returns a clear error explaining the requirement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

from mcp_servers.k8s_mcp.models import (  # noqa: TCH001
    SlurmCancelJobInput,
    SlurmJobDetailInput,
    SlurmSubmitJobInput,
)
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
_SBATCH = shutil.which("sbatch")
_SCANCEL = shutil.which("scancel")
_SACCT = shutil.which("sacct")
_SLURM_AVAILABLE = bool(_SQUEUE and _SINFO)

if _SLURM_AVAILABLE:
    logger.info("Slurm detected: squeue=%s sinfo=%s", _SQUEUE, _SINFO)
    if _SBATCH:
        logger.info("Slurm sbatch detected: %s", _SBATCH)
    if _SCANCEL:
        logger.info("Slurm scancel detected: %s", _SCANCEL)
    if _SACCT:
        logger.info("Slurm sacct detected: %s", _SACCT)
else:
    logger.info("Slurm not detected (squeue/sinfo not in PATH)")


def _slurm_not_available_error(tool_name: str) -> str:
    """Standard error when Slurm isn't available."""
    return _json(
        {
            "error": f"{tool_name} requires Slurm job scheduler.",
            "slurm_available": False,
            "hint": "Slurm commands (squeue, sinfo) must be in PATH. "
            "This tool is designed for HPC clusters with Slurm installed.",
        }
    )


def _slurm_command_not_available_error(tool_name: str, command: str) -> str:
    """Standard error when a specific Slurm command isn't available."""
    return _json(
        {
            "error": f"{tool_name} requires '{command}' which is not in PATH.",
            "slurm_available": _SLURM_AVAILABLE,
            "hint": f"Ensure '{command}' is installed and in PATH. "
            "This tool is designed for HPC clusters with full Slurm installation.",
        }
    )


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
                jobs.append(
                    {
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
                    }
                )

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
                nodes.append(
                    {
                        "node_name": parts[0].strip(),
                        "state": parts[1].strip(),
                        "cpus_total": parts[2].strip(),
                        "memory_total_mb": parts[3].strip(),
                        "gres": parts[4].strip(),
                        "partitions": parts[5].strip(),
                        "features": parts[6].strip(),
                        "cpu_load": parts[7].strip(),
                    }
                )

        return {
            "total_nodes": len(nodes),
            "nodes": nodes,
        }
    except subprocess.TimeoutExpired:
        return {"error": "sinfo timed out after 30s"}
    except Exception as exc:
        return {"error": str(exc)}


def _run_sbatch(
    job_name: str,
    partition: str,
    num_nodes: int,
    gpus_per_node: int,
    time_limit: str,
    command: str,
) -> dict[str, Any]:
    """Submit a job via sbatch using a temporary script file.

    Args:
        job_name: Name for the Slurm job.
        partition: Slurm partition to submit to.
        num_nodes: Number of nodes to request.
        gpus_per_node: Number of GPUs per node (0 for no GPUs).
        time_limit: Wall clock time limit (HH:MM:SS).
        command: The command to execute.

    Returns:
        Dictionary with submission result or error.
    """
    # Build the SBATCH script
    script_lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --partition={partition}",
        f"#SBATCH --nodes={num_nodes}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --output={job_name}_%j.out",
        f"#SBATCH --error={job_name}_%j.err",
    ]
    if gpus_per_node > 0:
        script_lines.append(f"#SBATCH --gres=gpu:{gpus_per_node}")

    script_lines.append("")
    script_lines.append(command)
    script_lines.append("")

    script_content = "\n".join(script_lines)

    # Write to a temp file and submit
    fd = -1
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".sh", prefix=f"slurm_{job_name}_")
        with os.fdopen(fd, "w") as f:
            fd = -1  # os.fdopen takes ownership
            f.write(script_content)

        result = subprocess.run(
            ["sbatch", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "error": f"sbatch failed: {result.stderr.strip()}",
                "script": script_content,
            }

        # Parse the job ID from sbatch output ("Submitted batch job 12345")
        stdout = result.stdout.strip()
        job_id = ""
        if "Submitted batch job" in stdout:
            parts = stdout.split()
            job_id = parts[-1] if parts else ""

        return {
            "action": "submit",
            "job_id": job_id,
            "job_name": job_name,
            "partition": partition,
            "num_nodes": num_nodes,
            "gpus_per_node": gpus_per_node,
            "time_limit": time_limit,
            "status": "submitted",
            "sbatch_output": stdout,
        }
    except subprocess.TimeoutExpired:
        return {"error": "sbatch timed out after 30s"}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _run_scancel(job_id: str) -> dict[str, Any]:
    """Cancel a Slurm job via scancel.

    Args:
        job_id: The Slurm job ID to cancel.

    Returns:
        Dictionary with cancellation result or error.
    """
    try:
        result = subprocess.run(
            ["scancel", job_id],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "error": f"scancel failed: {result.stderr.strip()}",
                "job_id": job_id,
            }

        return {
            "action": "cancel",
            "job_id": job_id,
            "status": "cancelled",
            "output": result.stdout.strip() or "Job cancellation signal sent",
        }
    except subprocess.TimeoutExpired:
        return {"error": "scancel timed out after 30s"}
    except Exception as exc:
        return {"error": str(exc)}


def _run_sacct(job_id: str) -> dict[str, Any]:
    """Get detailed job accounting info via sacct.

    Args:
        job_id: The Slurm job ID to query.

    Returns:
        Dictionary with job detail or error.
    """
    try:
        result = subprocess.run(
            [
                "sacct",
                "-j",
                job_id,
                "--format=JobID,JobName,Partition,Account,AllocCPUS,State,"
                "ExitCode,Elapsed,Start,End,NodeList,MaxRSS,MaxVMSize,"
                "ReqGRES,AllocGRES,TotalCPU",
                "--parsable2",
                "--noheader",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "error": f"sacct failed: {result.stderr.strip()}",
                "job_id": job_id,
            }

        steps: list[dict[str, str]] = []
        headers = [
            "job_id",
            "job_name",
            "partition",
            "account",
            "alloc_cpus",
            "state",
            "exit_code",
            "elapsed",
            "start",
            "end",
            "node_list",
            "max_rss",
            "max_vmsize",
            "req_gres",
            "alloc_gres",
            "total_cpu",
        ]

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            step: dict[str, str] = {}
            for i, header in enumerate(headers):
                step[header] = parts[i].strip() if i < len(parts) else ""
            steps.append(step)

        return {
            "job_id": job_id,
            "step_count": len(steps),
            "steps": steps,
        }
    except subprocess.TimeoutExpired:
        return {"error": "sacct timed out after 30s"}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools — Existing
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_slurm_queue",
    annotations={
        "title": "Slurm Job Queue",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    annotations={
        "title": "Slurm Node Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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


# ---------------------------------------------------------------------------
# MCP Tools — New (Phase 5)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_slurm_submit_job",
    annotations={
        "title": "Submit Slurm Job",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def k8s_slurm_submit_job(params: SlurmSubmitJobInput) -> str:
    """Submit a new job to the Slurm scheduler.

    Writes a temporary sbatch script and submits it. Returns the
    assigned job ID on success.
    Requires Slurm (sbatch) to be installed and accessible.
    """
    logger.debug(
        "k8s_slurm_submit_job called",
        extra={
            "job_name": params.job_name,
            "partition": params.partition,
            "num_nodes": params.num_nodes,
            "gpus_per_node": params.gpus_per_node,
        },
    )

    if not _SLURM_AVAILABLE:
        return _slurm_not_available_error("k8s_slurm_submit_job")

    if not _SBATCH:
        return _slurm_command_not_available_error("k8s_slurm_submit_job", "sbatch")

    try:
        data = await asyncio.to_thread(
            _run_sbatch,
            job_name=params.job_name,
            partition=params.partition,
            num_nodes=params.num_nodes,
            gpus_per_node=params.gpus_per_node,
            time_limit=params.time_limit,
            command=params.command,
        )
        logger.info(
            "k8s_slurm_submit_job completed",
            extra={"job_id": data.get("job_id", "unknown")},
        )
        return _json(data)
    except Exception as exc:
        logger.error("k8s_slurm_submit_job failed: %s", exc)
        return _json({"error": str(exc)})


@mcp.tool(
    name="k8s_slurm_cancel_job",
    annotations={
        "title": "Cancel Slurm Job",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_slurm_cancel_job(params: SlurmCancelJobInput) -> str:
    """Cancel a running or pending Slurm job by ID.

    Requires Slurm (scancel) to be installed and accessible.
    """
    logger.debug(
        "k8s_slurm_cancel_job called",
        extra={"job_id": params.job_id},
    )

    if not _SLURM_AVAILABLE:
        return _slurm_not_available_error("k8s_slurm_cancel_job")

    if not _SCANCEL:
        return _slurm_command_not_available_error("k8s_slurm_cancel_job", "scancel")

    try:
        data = await asyncio.to_thread(_run_scancel, job_id=params.job_id)
        logger.info(
            "k8s_slurm_cancel_job completed",
            extra={"job_id": params.job_id},
        )
        return _json(data)
    except Exception as exc:
        logger.error("k8s_slurm_cancel_job failed: %s", exc)
        return _json({"error": str(exc)})


@mcp.tool(
    name="k8s_slurm_job_detail",
    annotations={
        "title": "Slurm Job Detail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_slurm_job_detail(params: SlurmJobDetailInput) -> str:
    """Get detailed accounting information for a Slurm job.

    Uses sacct to retrieve CPU time, memory usage, exit code, start/end
    time, allocated GRES, and per-step details.
    Requires Slurm (sacct) to be installed and accessible.
    """
    logger.debug(
        "k8s_slurm_job_detail called",
        extra={"job_id": params.job_id},
    )

    if not _SLURM_AVAILABLE:
        return _slurm_not_available_error("k8s_slurm_job_detail")

    if not _SACCT:
        return _slurm_command_not_available_error("k8s_slurm_job_detail", "sacct")

    try:
        data = await asyncio.to_thread(_run_sacct, job_id=params.job_id)
        logger.info(
            "k8s_slurm_job_detail completed",
            extra={"job_id": params.job_id},
        )
        return _json(data)
    except Exception as exc:
        logger.error("k8s_slurm_job_detail failed: %s", exc)
        return _json({"error": str(exc)})
