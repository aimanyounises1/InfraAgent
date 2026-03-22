"""Pydantic input/output models for gpu_mcp tools."""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Basic GPU queries (NVML)
# ---------------------------------------------------------------------------


class GpuDeviceIndexInput(BaseModel):
    device_index: int = Field(default=0, ge=0, description="GPU device index")


class GpuListDevicesInput(BaseModel):
    """No parameters needed — lists all devices."""

    pass


class GpuHealthCheckInput(BaseModel):
    """No parameters needed — checks all devices."""

    pass


class GpuClusterSummaryInput(BaseModel):
    """No parameters needed — aggregates across all devices."""

    pass


# ---------------------------------------------------------------------------
# DCGM (Data Center GPU Manager) queries
# ---------------------------------------------------------------------------


class DcgmFieldGroupInput(BaseModel):
    """Query DCGM field group data for deep GPU telemetry."""

    device_index: int = Field(default=0, ge=0, description="GPU device index")
    field_group: str = Field(
        default="health",
        description="DCGM field group: 'health', 'performance', 'power', 'memory'",
    )


class DcgmXidErrorsInput(BaseModel):
    """Query XID error history from DCGM."""

    device_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="GPU device index (None for all devices)",
    )
    hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Look back period in hours (1-720)",
    )


# ---------------------------------------------------------------------------
# NVLink / NVSwitch topology
# ---------------------------------------------------------------------------


class NvlinkTopologyInput(BaseModel):
    """Query NVLink topology for a DGX node."""

    node_index: int = Field(
        default=0,
        ge=0,
        description="DGX node index (0-based)",
    )


# ---------------------------------------------------------------------------
# NCCL collective profiling
# ---------------------------------------------------------------------------


class NcclProfileInput(BaseModel):
    """Profile NCCL collective operation performance."""

    operation: str = Field(
        default="allreduce",
        description="NCCL operation: 'allreduce', 'allgather', 'reduce_scatter', 'broadcast'",
    )
    num_gpus: int = Field(
        default=8,
        ge=2,
        le=256,
        description="Number of GPUs for the collective (2-256)",
    )
    message_size_mb: Optional[int] = Field(
        default=None,
        ge=1,
        le=4096,
        description="Message size in MB (None to profile across standard sizes)",
    )
