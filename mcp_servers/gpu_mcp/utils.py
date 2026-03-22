"""NVML helpers and mock GPU data generator.

When INFRA_AGENT_MOCK_GPU=true, provides realistic simulated GPU data
so the project can demo without physical NVIDIA hardware.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

MOCK_MODE = os.getenv("INFRA_AGENT_MOCK_GPU", "true").lower() == "true"


@dataclass
class MockGpuInfo:
    name: str
    total_memory_mb: int
    temperature: int
    gpu_utilization: int
    memory_utilization: int
    power_draw_w: int
    power_limit_w: int


MOCK_GPUS = [
    MockGpuInfo("NVIDIA A100-SXM4-80GB", 81920, 62, 78, 65, 285, 400),
    MockGpuInfo("NVIDIA A100-SXM4-80GB", 81920, 58, 42, 38, 195, 400),
    MockGpuInfo("NVIDIA A100-SXM4-80GB", 81920, 71, 95, 88, 350, 400),
    MockGpuInfo("NVIDIA A100-SXM4-80GB", 81920, 45, 12, 10, 85, 400),
]

_MOCK_PROCESS_TEMPLATES: list[list[dict[str, str | int]]] = [
    [
        {"pid": 12001, "name": "python3", "memory_mb": 24576, "type": "Compute"},
        {"pid": 12002, "name": "torch_trainer", "memory_mb": 18432, "type": "Compute"},
    ],
    [
        {"pid": 13001, "name": "inference_server", "memory_mb": 12288, "type": "Compute"},
    ],
    [
        {"pid": 14001, "name": "python3", "memory_mb": 32768, "type": "Compute"},
        {"pid": 14002, "name": "nccl_allreduce", "memory_mb": 16384, "type": "Compute"},
        {"pid": 14003, "name": "data_loader", "memory_mb": 8192, "type": "Compute"},
    ],
    [],
]


def get_mock_gpu_count() -> int:
    """Return the number of mock GPU devices."""
    return len(MOCK_GPUS)


def get_mock_gpu_info(index: int) -> MockGpuInfo:
    """Return mock GPU data with slight randomization for realism."""
    base = MOCK_GPUS[index % len(MOCK_GPUS)]
    return MockGpuInfo(
        name=base.name,
        total_memory_mb=base.total_memory_mb,
        temperature=base.temperature + random.randint(-3, 3),
        gpu_utilization=max(0, min(100, base.gpu_utilization + random.randint(-5, 5))),
        memory_utilization=max(0, min(100, base.memory_utilization + random.randint(-5, 5))),
        power_draw_w=max(50, base.power_draw_w + random.randint(-15, 15)),
        power_limit_w=base.power_limit_w,
    )


def get_mock_processes(index: int) -> list[dict[str, str | int]]:
    """Return a list of fake GPU processes for the given device index.

    Each process dict contains: pid, name, memory_mb, type.
    Memory values are slightly randomized for realism.
    """
    templates = _MOCK_PROCESS_TEMPLATES[index % len(_MOCK_PROCESS_TEMPLATES)]
    processes: list[dict[str, str | int]] = []
    for tmpl in templates:
        proc = dict(tmpl)
        # Add slight memory jitter (+/- 512 MB)
        base_mem = int(tmpl["memory_mb"])
        proc["memory_mb"] = max(256, base_mem + random.randint(-512, 512))
        processes.append(proc)
    return processes


def get_mock_health(index: int) -> dict[str, str | int | float | bool]:
    """Return a health status dict for the given mock GPU device.

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

    # Determine status
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
