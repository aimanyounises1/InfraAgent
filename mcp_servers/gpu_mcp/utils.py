"""System resource helpers for Apple Silicon Macs.

When INFRA_AGENT_MOCK_GPU=true (the default), provides real macOS system
metrics from psutil — reframed as GPU-like device data for the dashboard.
Since there are no NVIDIA GPUs on Apple Silicon, the four "devices" represent:
  0: M4 Max Performance Cores
  1: M4 Max Efficiency Cores
  2: M4 Max 40-core GPU (unified memory)
  3: M4 Max Neural Engine
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)

MOCK_MODE = os.getenv("INFRA_AGENT_MOCK_GPU", "true").lower() == "true"

# Number of virtual "devices" exposed to the dashboard.
_DEVICE_COUNT = 4


@dataclass
class MockGpuInfo:
    """GPU-like data container — backed by real psutil metrics on macOS."""

    name: str
    total_memory_mb: int
    temperature: int
    gpu_utilization: int
    memory_utilization: int
    power_draw_w: int
    power_limit_w: int


# ---------------------------------------------------------------------------
# Internal helpers — real metric collection
# ---------------------------------------------------------------------------


def _get_cpu_temp() -> int:
    """Estimate CPU temperature from load.

    Real temperature requires ``sudo powermetrics`` on macOS, which is not
    practical for a dashboard.  Instead, use a linear model:
    idle ~35 C, full load ~85 C.
    """
    try:
        cpu = psutil.cpu_percent(interval=0)
    except Exception:
        cpu = 20.0
    return int(35 + (cpu / 100) * 50)


def _estimate_power() -> int:
    """Estimate system power draw (watts) from CPU utilization.

    M4 Max TDP is ~92 W.  Idle draws roughly 8-12 W.
    """
    try:
        cpu = psutil.cpu_percent(interval=0)
    except Exception:
        cpu = 15.0
    return max(8, int(10 + (cpu / 100) * 82))


def _get_gpu_util() -> int:
    """Estimate Apple GPU utilization.

    Checks for known GPU-heavy macOS processes (WindowServer,
    MTLCompilerService) and uses their CPU share as a proxy.
    Falls back to a small random baseline.
    """
    try:
        gpu_proc_names = {"WindowServer", "MTLCompilerService"}
        for proc in psutil.process_iter(["name", "cpu_percent"]):
            info = proc.info
            if info and info.get("name") in gpu_proc_names:
                cpu_pct = info.get("cpu_percent")
                if cpu_pct is not None and cpu_pct > 0:
                    return min(100, int(cpu_pct))
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    except Exception as exc:
        logger.debug("_get_gpu_util failed: %s", exc)
    return random.randint(5, 20)


def _get_neural_util() -> int:
    """Estimate Neural Engine utilization.

    On macOS the Neural Engine is used by CoreML / ANE processes.
    Without private APIs we return a low baseline with jitter.
    """
    return random.randint(2, 15)


# ---------------------------------------------------------------------------
# Public API — used by tool modules (monitor, health, processes)
# ---------------------------------------------------------------------------


def get_mock_gpu_count() -> int:
    """Return number of virtual devices (CPU perf, CPU eff, GPU, Neural Engine)."""
    return _DEVICE_COUNT


def get_mock_gpu_info(index: int) -> MockGpuInfo:
    """Return real system metrics for a virtual Apple Silicon device.

    Args:
        index: Device index (0-3). Wraps with modulo.

    Returns:
        MockGpuInfo populated with live psutil data.
    """
    try:
        cpu = psutil.cpu_percent(interval=0.1)
    except Exception:
        cpu = 15.0

    try:
        mem = psutil.virtual_memory()
        total_mem_mb = int(mem.total / 1024 / 1024)
        mem_pct = int(mem.percent)
    except Exception:
        total_mem_mb = 65536
        mem_pct = 40

    temp = _get_cpu_temp()
    power = _estimate_power()

    devices = [
        MockGpuInfo(
            name="Apple M4 Max \u2014 Performance Cores",
            total_memory_mb=total_mem_mb,
            temperature=temp,
            gpu_utilization=max(0, min(100, int(cpu))),
            memory_utilization=mem_pct,
            power_draw_w=power,
            power_limit_w=92,
        ),
        MockGpuInfo(
            name="Apple M4 Max \u2014 Efficiency Cores",
            total_memory_mb=total_mem_mb,
            temperature=max(30, temp - 10),
            gpu_utilization=max(0, min(100, int(cpu) - 15)),
            memory_utilization=mem_pct,
            power_draw_w=max(5, power // 3),
            power_limit_w=30,
        ),
        MockGpuInfo(
            name="Apple M4 Max \u2014 40-core GPU",
            total_memory_mb=total_mem_mb,
            temperature=min(100, temp + 2),
            gpu_utilization=_get_gpu_util(),
            memory_utilization=mem_pct,
            power_draw_w=max(5, power // 2),
            power_limit_w=60,
        ),
        MockGpuInfo(
            name="Apple M4 Max \u2014 Neural Engine",
            total_memory_mb=total_mem_mb,
            temperature=max(30, temp - 5),
            gpu_utilization=_get_neural_util(),
            memory_utilization=mem_pct,
            power_draw_w=max(3, power // 6),
            power_limit_w=15,
        ),
    ]

    return devices[index % len(devices)]


def get_mock_processes(index: int) -> list[dict[str, str | int]]:
    """Return real top processes sorted by CPU usage.

    Args:
        index: Device index.  All devices share the same host process
               list; we return the top 5 for devices 0-2 and an empty
               list for device 3 (Neural Engine has no visible procs).

    Returns:
        List of process dicts with pid, name, memory_mb, type.
    """
    # Neural Engine (index 3) — no user-visible processes
    if index % _DEVICE_COUNT == 3:
        return []

    procs: list[dict[str, str | int]] = []
    try:
        all_procs = list(
            psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"])
        )
        sorted_procs = sorted(
            all_procs,
            key=lambda p: p.info.get("cpu_percent") or 0,
            reverse=True,
        )
        for proc in sorted_procs[:5]:
            info = proc.info
            if info is None:
                continue
            mem_info = info.get("memory_info")
            rss = mem_info.rss if mem_info else 0
            procs.append(
                {
                    "pid": info.get("pid", 0),
                    "name": info.get("name", "unknown") or "unknown",
                    "memory_mb": int(rss / 1024 / 1024),
                    "type": "Compute",
                }
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    except Exception as exc:
        logger.warning("get_mock_processes failed: %s", exc)

    return procs


def get_mock_health(index: int) -> dict[str, str | int | float | bool]:
    """Return a health status dict for the given virtual device.

    Evaluates temperature, utilization, and memory to determine status:
    - "healthy": temp < 80 and util < 95%
    - "warning": temp 80-90 or util >= 95%
    - "critical": temp > 90
    """
    info = get_mock_gpu_info(index)

    temp = info.temperature
    util = info.gpu_utilization
    mem_util = info.memory_utilization
    used_mb = int(info.total_memory_mb * mem_util / 100)
    free_mb = info.total_memory_mb - used_mb

    if temp > 90:
        status = "critical"
    elif temp >= 80 or util >= 95:
        status = "warning"
    else:
        status = "healthy"

    return {
        "device_index": index,
        "name": info.name,
        "status": status,
        "temperature_c": temp,
        "gpu_utilization_pct": util,
        "memory_utilization_pct": mem_util,
        "memory_used_mb": used_mb,
        "memory_free_mb": free_mb,
        "memory_total_mb": info.total_memory_mb,
        "power_draw_w": info.power_draw_w,
        "power_limit_w": info.power_limit_w,
        "throttle_warning": temp > 85,
        "ecc_errors": 0,
    }
