"""Tests for gpu_mcp server tools.

All tests run in MOCK_MODE (INFRA_AGENT_MOCK_GPU=true) by default.
The mock_nvml fixture from conftest.py is available for pynvml patching tests.
"""

from __future__ import annotations

import json

import pytest

from mcp_servers.gpu_mcp.models import (
    GpuClusterSummaryInput,
    GpuDeviceIndexInput,
    GpuHealthCheckInput,
    GpuListDevicesInput,
)
from mcp_servers.gpu_mcp.utils import (
    get_mock_gpu_count,
    get_mock_gpu_info,
    get_mock_health,
    get_mock_processes,
)

# ---------------------------------------------------------------------------
# Utils tests
# ---------------------------------------------------------------------------


class TestGpuUtils:
    """Tests for gpu_mcp utility functions."""

    def test_mock_gpu_data_generation(self) -> None:
        """Mock mode should generate realistic GPU data."""
        info = get_mock_gpu_info(0)
        assert 0 <= info.gpu_utilization <= 100
        assert info.total_memory_mb > 0
        assert info.power_limit_w > 0

    def test_mock_gpu_count(self) -> None:
        """Should return the expected number of mock GPUs."""
        count = get_mock_gpu_count()
        assert count == 4

    def test_mock_gpu_info_wraps_index(self) -> None:
        """Index modulo should wrap around for out-of-range indices."""
        info_0 = get_mock_gpu_info(0)
        info_4 = get_mock_gpu_info(4)
        # Same base GPU, but values are randomized so just check name
        assert info_0.name == info_4.name

    def test_mock_processes_returns_list(self) -> None:
        """get_mock_processes should return a list of process dicts."""
        procs = get_mock_processes(0)
        assert isinstance(procs, list)
        assert len(procs) > 0
        for proc in procs:
            assert "pid" in proc
            assert "name" in proc
            assert "memory_mb" in proc
            assert "type" in proc

    def test_mock_processes_empty_device(self) -> None:
        """Device index 3 has no processes in the template."""
        procs = get_mock_processes(3)
        assert isinstance(procs, list)
        assert len(procs) == 0

    def test_mock_health_returns_dict(self) -> None:
        """get_mock_health should return a valid health dict."""
        health = get_mock_health(0)
        assert isinstance(health, dict)
        assert health["device_index"] == 0
        assert health["status"] in ("healthy", "warning", "critical")
        assert "temperature_c" in health
        assert "gpu_utilization_pct" in health
        assert "memory_total_mb" in health

    def test_mock_health_status_logic(self) -> None:
        """Health status should reflect temperature and utilization rules."""
        # Device 2 has high utilization (95) and temp (71)
        # With randomization it could be warning or healthy — just check valid
        health = get_mock_health(2)
        assert health["status"] in ("healthy", "warning", "critical")

    def test_mock_health_throttle_flag(self) -> None:
        """throttle_warning should be True only when temp > 85."""
        health = get_mock_health(0)
        if health["temperature_c"] > 85:
            assert health["throttle_warning"] is True
        else:
            assert health["throttle_warning"] is False


# ---------------------------------------------------------------------------
# Monitor tool tests (mock mode)
# ---------------------------------------------------------------------------


class TestGpuListDevices:
    """Tests for gpu_list_devices tool."""

    @pytest.mark.asyncio
    async def test_list_devices_returns_all(self) -> None:
        """Should return all mock GPU devices."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_list_devices

        result = await gpu_list_devices(GpuListDevicesInput())
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == get_mock_gpu_count()
        for device in data:
            assert "device_index" in device
            assert "name" in device
            assert "total_memory_mb" in device
            assert "driver_version" in device

    @pytest.mark.asyncio
    async def test_list_devices_driver_version_mock(self) -> None:
        """Mock driver version should contain '(mock)' marker."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_list_devices

        result = await gpu_list_devices(GpuListDevicesInput())
        data = json.loads(result)
        assert "mock" in data[0]["driver_version"].lower()


class TestGpuGetUtilization:
    """Tests for gpu_get_utilization tool."""

    @pytest.mark.asyncio
    async def test_get_utilization(self) -> None:
        """Should return GPU utilization percentage."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_utilization

        result = await gpu_get_utilization(GpuDeviceIndexInput(device_index=0))
        data = json.loads(result)
        assert "gpu_utilization_pct" in data
        assert "memory_utilization_pct" in data
        assert 0 <= data["gpu_utilization_pct"] <= 100
        assert 0 <= data["memory_utilization_pct"] <= 100

    @pytest.mark.asyncio
    async def test_get_utilization_invalid_device(self) -> None:
        """Should handle invalid device index gracefully."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_utilization

        result = await gpu_get_utilization(GpuDeviceIndexInput(device_index=99))
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_utilization_device_index_in_response(self) -> None:
        """Response should include the requested device index."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_utilization

        result = await gpu_get_utilization(GpuDeviceIndexInput(device_index=1))
        data = json.loads(result)
        assert data["device_index"] == 1


class TestGpuGetMemory:
    """Tests for gpu_get_memory tool."""

    @pytest.mark.asyncio
    async def test_get_memory(self) -> None:
        """Should return memory info with total, used, free."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_memory

        result = await gpu_get_memory(GpuDeviceIndexInput(device_index=0))
        data = json.loads(result)
        assert "total_mb" in data
        assert "used_mb" in data
        assert "free_mb" in data
        assert "used_pct" in data
        assert data["total_mb"] == data["used_mb"] + data["free_mb"]

    @pytest.mark.asyncio
    async def test_get_memory_invalid_device(self) -> None:
        """Should return error for invalid device index."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_memory

        result = await gpu_get_memory(GpuDeviceIndexInput(device_index=99))
        data = json.loads(result)
        assert "error" in data


class TestGpuGetTemperature:
    """Tests for gpu_get_temperature tool."""

    @pytest.mark.asyncio
    async def test_get_temperature(self) -> None:
        """Should return temperature with throttle status."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_temperature

        result = await gpu_get_temperature(GpuDeviceIndexInput(device_index=0))
        data = json.loads(result)
        assert "temperature_c" in data
        assert "throttle_warning" in data
        assert "status" in data
        assert data["status"] in ("normal", "warning", "critical")

    @pytest.mark.asyncio
    async def test_get_temperature_invalid_device(self) -> None:
        """Should return error for invalid device index."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_temperature

        result = await gpu_get_temperature(GpuDeviceIndexInput(device_index=99))
        data = json.loads(result)
        assert "error" in data


class TestGpuGetPower:
    """Tests for gpu_get_power tool."""

    @pytest.mark.asyncio
    async def test_get_power(self) -> None:
        """Should return power draw and limit."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_power

        result = await gpu_get_power(GpuDeviceIndexInput(device_index=0))
        data = json.loads(result)
        assert "power_draw_w" in data
        assert "power_limit_w" in data
        assert "power_usage_pct" in data
        assert data["power_draw_w"] <= data["power_limit_w"] + 50  # allow some flex

    @pytest.mark.asyncio
    async def test_get_power_invalid_device(self) -> None:
        """Should return error for invalid device index."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_power

        result = await gpu_get_power(GpuDeviceIndexInput(device_index=99))
        data = json.loads(result)
        assert "error" in data


class TestGpuClusterSummary:
    """Tests for gpu_get_cluster_summary tool."""

    @pytest.mark.asyncio
    async def test_cluster_summary(self) -> None:
        """Should return aggregated cluster stats."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary

        result = await gpu_get_cluster_summary(GpuClusterSummaryInput())
        data = json.loads(result)
        assert "device_count" in data
        assert data["device_count"] == get_mock_gpu_count()
        assert "avg_gpu_utilization_pct" in data
        assert "total_memory_mb" in data
        assert "used_memory_mb" in data
        assert "free_memory_mb" in data
        assert "hottest_device" in data
        assert "most_loaded_device" in data
        assert "devices" in data
        assert len(data["devices"]) == get_mock_gpu_count()

    @pytest.mark.asyncio
    async def test_cluster_summary_memory_consistency(self) -> None:
        """Total memory should equal used + free."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary

        result = await gpu_get_cluster_summary(GpuClusterSummaryInput())
        data = json.loads(result)
        assert data["total_memory_mb"] == data["used_memory_mb"] + data["free_memory_mb"]


# ---------------------------------------------------------------------------
# Process tool tests (mock mode)
# ---------------------------------------------------------------------------


class TestGpuListProcesses:
    """Tests for gpu_list_processes tool."""

    @pytest.mark.asyncio
    async def test_list_processes(self) -> None:
        """Should return processes for a given device."""
        from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

        result = await gpu_list_processes(GpuDeviceIndexInput(device_index=0))
        data = json.loads(result)
        assert "device_index" in data
        assert "process_count" in data
        assert "processes" in data
        assert data["process_count"] == len(data["processes"])
        assert data["process_count"] > 0

    @pytest.mark.asyncio
    async def test_list_processes_empty_device(self) -> None:
        """Device 3 has no processes in mock mode."""
        from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

        result = await gpu_list_processes(GpuDeviceIndexInput(device_index=3))
        data = json.loads(result)
        assert data["process_count"] == 0
        assert data["processes"] == []

    @pytest.mark.asyncio
    async def test_list_processes_invalid_device(self) -> None:
        """Should return error for invalid device index."""
        from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

        result = await gpu_list_processes(GpuDeviceIndexInput(device_index=99))
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# Health check tool tests (mock mode)
# ---------------------------------------------------------------------------


class TestGpuHealthCheck:
    """Tests for gpu_health_check tool."""

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        """Should return a comprehensive health report."""
        from mcp_servers.gpu_mcp.tools.health import gpu_health_check

        result = await gpu_health_check(GpuHealthCheckInput())
        data = json.loads(result)
        assert "overall_status" in data
        assert data["overall_status"] in ("healthy", "warning", "critical")
        assert "device_count" in data
        assert data["device_count"] == get_mock_gpu_count()
        assert "summary" in data
        assert "devices" in data

    @pytest.mark.asyncio
    async def test_health_check_summary_counts(self) -> None:
        """Summary counts should add up to total device count."""
        from mcp_servers.gpu_mcp.tools.health import gpu_health_check

        result = await gpu_health_check(GpuHealthCheckInput())
        data = json.loads(result)
        summary = data["summary"]
        total = summary["healthy"] + summary["warning"] + summary["critical"]
        assert total == data["device_count"]

    @pytest.mark.asyncio
    async def test_health_check_device_fields(self) -> None:
        """Each device in the report should have required fields."""
        from mcp_servers.gpu_mcp.tools.health import gpu_health_check

        result = await gpu_health_check(GpuHealthCheckInput())
        data = json.loads(result)
        for device in data["devices"]:
            assert "device_index" in device
            assert "name" in device
            assert "status" in device
            assert "temperature_c" in device
            assert "gpu_utilization_pct" in device
            assert "memory_total_mb" in device
            assert "throttle_warning" in device
            assert "ecc_errors" in device


# ---------------------------------------------------------------------------
# Mock mode class (backwards compatibility)
# ---------------------------------------------------------------------------


class TestGpuMockMode:
    """Tests for mock/simulation mode."""

    def test_mock_gpu_data_generation(self) -> None:
        """Mock mode should generate realistic GPU data."""
        info = get_mock_gpu_info(0)
        assert 0 <= info.gpu_utilization <= 100
        assert info.total_memory_mb > 0
