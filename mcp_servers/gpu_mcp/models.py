"""Pydantic input/output models for gpu_mcp tools."""

from pydantic import BaseModel, Field


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
