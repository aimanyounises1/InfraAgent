"""NCCL (NVIDIA Collective Communications Library) profiling tools.

Monitors multi-GPU collective operations: AllReduce, AllGather,
ReduceScatter, Broadcast. Reports bandwidth, latency, and algorithm
selection.

Requires nccl-tests installed on a system with multiple NVIDIA GPUs.
When not available, returns a clear error explaining the requirement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from typing import Any

from mcp_servers.gpu_mcp.models import NcclProfileInput
from mcp_servers.gpu_mcp.server import mcp
from mcp_servers.gpu_mcp.utils import get_backend, get_gpu_count

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# NCCL availability detection
# ---------------------------------------------------------------------------

_NCCL_TESTS_AVAILABLE = False
_NCCL_TEST_BINARIES: dict[str, str] = {}

for op, binary in [
    ("allreduce", "all_reduce_perf"),
    ("allgather", "all_gather_perf"),
    ("reduce_scatter", "reduce_scatter_perf"),
    ("broadcast", "broadcast_perf"),
]:
    path = shutil.which(binary)
    if path:
        _NCCL_TEST_BINARIES[op] = path
        _NCCL_TESTS_AVAILABLE = True

if _NCCL_TESTS_AVAILABLE:
    logger.info("NCCL tests found: %s", list(_NCCL_TEST_BINARIES.keys()))
else:
    logger.info("nccl-tests not found (all_reduce_perf etc. not in PATH)")


def _nccl_not_available_error(tool_name: str) -> str:
    """Standard error when NCCL tests aren't available."""
    backend = get_backend()
    gpu_count = get_gpu_count()

    if backend != "nvml":
        return _json({
            "error": f"{tool_name} requires NVIDIA GPUs with NCCL.",
            "detected_backend": backend,
            "hint": "NCCL is NVIDIA's collective communication library for multi-GPU systems.",
        })

    if gpu_count < 2:
        return _json({
            "error": f"{tool_name} requires at least 2 NVIDIA GPUs for collective profiling.",
            "detected_backend": backend,
            "gpu_count": gpu_count,
            "hint": "NCCL collectives operate across multiple GPUs.",
        })

    return _json({
        "error": f"{tool_name} requires nccl-tests to be installed.",
        "detected_backend": backend,
        "gpu_count": gpu_count,
        "hint": "Install nccl-tests: https://github.com/NVIDIA/nccl-tests",
        "install_cmd": "cd /tmp && git clone https://github.com/NVIDIA/nccl-tests && cd nccl-tests && make MPI=1",
    })


# ---------------------------------------------------------------------------
# Real NCCL profiling
# ---------------------------------------------------------------------------


def _run_nccl_test(operation: str, num_gpus: int, message_size_mb: int | None) -> dict[str, Any]:
    """Run an nccl-test binary and parse results."""
    binary = _NCCL_TEST_BINARIES.get(operation)
    if not binary:
        return {"error": f"No nccl-test binary found for operation: {operation}"}

    # Build command
    cmd = [binary, "-b", "1M", "-e", "1G", "-f", "2", "-g", str(num_gpus)]
    if message_size_mb:
        size_str = f"{message_size_mb}M"
        cmd = [binary, "-b", size_str, "-e", size_str, "-g", str(num_gpus)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return {
                "operation": operation,
                "error": f"nccl-test failed: {result.stderr.strip()}",
                "return_code": result.returncode,
            }

        # Parse nccl-test output
        parsed = _parse_nccl_output(result.stdout, operation, num_gpus)
        return parsed

    except subprocess.TimeoutExpired:
        return {"operation": operation, "error": "NCCL test timed out after 120s"}
    except Exception as exc:
        return {"operation": operation, "error": str(exc)}


def _parse_nccl_output(output: str, operation: str, num_gpus: int) -> dict[str, Any]:
    """Parse nccl-test output into structured data."""
    results: list[dict[str, Any]] = []

    for line in output.split("\n"):
        line = line.strip()
        # nccl-test output lines look like:
        # size  count  type  redop  time  algbw  busbw  error
        parts = line.split()
        if len(parts) >= 7:
            try:
                size = int(parts[0])
                time_us = float(parts[4])
                algbw = float(parts[5])
                busbw = float(parts[6])
                results.append({
                    "message_size_bytes": size,
                    "message_size_mb": round(size / (1024 * 1024), 2),
                    "time_us": time_us,
                    "algorithm_bandwidth_gb_s": algbw,
                    "bus_bandwidth_gb_s": busbw,
                })
            except (ValueError, IndexError):
                continue

    return {
        "operation": operation,
        "num_gpus": num_gpus,
        "backend": "nccl-tests",
        "results": results,
        "raw_output": output,
    }


# ---------------------------------------------------------------------------
# MCP Tool
# ---------------------------------------------------------------------------


@mcp.tool(
    name="gpu_nccl_profile",
    annotations={"title": "NCCL Collective Profile", "readOnlyHint": True, "destructiveHint": False},
)
async def gpu_nccl_profile(params: NcclProfileInput) -> str:
    """Profile NCCL collective operation performance.

    Measures bandwidth and latency for AllReduce, AllGather, ReduceScatter,
    or Broadcast across the specified number of GPUs.

    Requires nccl-tests installed on a system with multiple NVIDIA GPUs.
    """
    if not _NCCL_TESTS_AVAILABLE:
        return _nccl_not_available_error("gpu_nccl_profile")

    try:
        data = await asyncio.to_thread(
            _run_nccl_test,
            params.operation,
            params.num_gpus,
            params.message_size_mb,
        )
        return _json(data)
    except Exception as exc:
        logger.error("gpu_nccl_profile failed: %s", exc)
        return _json({"error": str(exc)})
