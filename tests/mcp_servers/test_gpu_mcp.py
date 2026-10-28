"""Hardware-independent tests for normalized GPU utilities and MCP adapters.

NVIDIA and Apple backends use controlled readings at the hardware boundary.
Explicit no-GPU cases verify disconnected responses. No test requires a driver,
GPU, live process inspection, or collection-time skip.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from mcp_servers.gpu_mcp import utils
from mcp_servers.gpu_mcp.models import (
    GpuClusterSummaryInput,
    GpuDeviceIndexInput,
    GpuHealthCheckInput,
    GpuListDevicesInput,
)
from mcp_servers.gpu_mcp.utils import (
    GpuInfo,
    get_backend,
    get_gpu_count,
    get_gpu_info,
    get_health,
    get_processes,
)


@pytest.fixture(autouse=True, params=["nvml", "apple_metal"])
def controlled_gpu_backend(request):
    """Exercise real normalization/adapter logic without touching GPU hardware.

    Stub only hardware-specific count/info/process operations. Public validation,
    health classification, serialization, and asynchronous adapter code stay real.
    """
    backend = request.param
    readings = [
        GpuInfo(
            name="Controlled device A",
            total_memory_mb=8192,
            temperature=60,
            gpu_utilization=40,
            memory_utilization=25,
            power_draw_w=50.0,
            power_limit_w=100.0,
            driver_version="unit-test",
            backend=backend,
        ),
        GpuInfo(
            name="Controlled device B",
            total_memory_mb=16384,
            temperature=86,
            gpu_utilization=70,
            memory_utilization=50,
            power_draw_w=75.0,
            power_limit_w=150.0,
            driver_version="unit-test",
            backend=backend,
        ),
    ]
    processes = [{"pid": 123, "name": "controlled-worker", "memory_mb": 128, "type": "Compute"}]
    nvml = MagicMock()
    nvml.nvmlDeviceGetCurrentEccMode.return_value = 0
    with ExitStack() as stack:
        stack.enter_context(patch.object(utils, "_BACKEND", backend))
        stack.enter_context(patch.object(utils, "_pynvml", nvml))
        for prefix in ("_nvml", "_apple"):
            stack.enter_context(
                patch.object(utils, f"{prefix}_device_count", return_value=len(readings))
            )
            stack.enter_context(
                patch.object(utils, f"{prefix}_gpu_info", side_effect=readings.__getitem__)
            )
            stack.enter_context(patch.object(utils, f"{prefix}_processes", return_value=processes))
        yield


# ---------------------------------------------------------------------------
# Utils tests (controlled backend)
# ---------------------------------------------------------------------------


class TestGpuUtils:
    """Tests for GPU utility dispatch and validation with controlled backends."""

    def test_get_backend_returns_valid_string(self) -> None:
        """Backend should be one of the known values."""
        backend = get_backend()
        assert backend in ("nvml", "apple_metal", "none")

    def test_get_gpu_count_non_negative(self) -> None:
        """GPU count should be >= 0."""
        count = get_gpu_count()
        assert count >= 0

    def test_get_gpu_info_returns_gpu_info(self) -> None:
        """get_gpu_info(0) should return a valid GpuInfo dataclass."""
        info = get_gpu_info(0)
        assert isinstance(info, GpuInfo)
        assert 0 <= info.gpu_utilization <= 100
        assert info.total_memory_mb > 0
        assert info.power_limit_w > 0
        assert info.backend == get_backend()

    def test_get_gpu_info_has_name(self) -> None:
        """Device should have a non-empty name string."""
        info = get_gpu_info(0)
        assert isinstance(info.name, str)
        assert len(info.name) > 0

    def test_get_gpu_info_out_of_range(self) -> None:
        """Out-of-range index should raise ValueError."""
        with pytest.raises(ValueError, match="out of range"):
            get_gpu_info(999)

    def test_get_gpu_info_no_gpu_raises_runtime(self) -> None:
        """When backend is 'none', get_gpu_info should raise RuntimeError."""
        with (
            patch("mcp_servers.gpu_mcp.utils._BACKEND", "none"),
            patch("mcp_servers.gpu_mcp.utils.get_gpu_count", return_value=0),
        ):
            from mcp_servers.gpu_mcp.utils import get_gpu_info as _get_info

            with pytest.raises(RuntimeError, match="No GPU hardware"):
                _get_info(0)

    def test_get_processes_returns_list(self) -> None:
        """get_processes should return a list of process dicts."""
        procs = get_processes(0)
        assert isinstance(procs, list)
        for proc in procs:
            assert "pid" in proc
            assert "name" in proc
            assert "memory_mb" in proc
            assert "type" in proc

    def test_get_health_returns_dict(self) -> None:
        """get_health should return a valid health dict."""
        health = get_health(0)
        assert isinstance(health, dict)
        assert health["device_index"] == 0
        assert health["status"] in ("healthy", "warning", "critical")
        assert "temperature_c" in health
        assert "gpu_utilization_pct" in health
        assert "memory_total_mb" in health
        assert health["backend"] == get_backend()

    def test_get_health_throttle_flag(self) -> None:
        """throttle_warning should be True only when temp > 85."""
        health = get_health(0)
        if health["temperature_c"] > 85:
            assert health["throttle_warning"] is True
        else:
            assert health["throttle_warning"] is False


# ---------------------------------------------------------------------------
# Monitor tool tests (controlled backend)
# ---------------------------------------------------------------------------


class TestGpuListDevices:
    """Tests for gpu_list_devices tool."""

    @pytest.mark.asyncio
    async def test_list_devices_returns_data(self) -> None:
        """Should return device data matching the controlled backend."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_list_devices

        result = await gpu_list_devices(GpuListDevicesInput())
        data = json.loads(result)

        count = get_gpu_count()
        if count == 0:
            # No-GPU path returns a dict with device_count: 0
            assert isinstance(data, dict)
            assert data["device_count"] == 0
        else:
            assert isinstance(data, list)
            assert len(data) == count
            for device in data:
                assert "device_index" in device
                assert "name" in device
                assert "total_memory_mb" in device
                assert "driver_version" in device
                assert "backend" in device

    @pytest.mark.asyncio
    async def test_list_devices_backend_field(self) -> None:
        """Each device should report the correct backend."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_list_devices

        result = await gpu_list_devices(GpuListDevicesInput())
        data = json.loads(result)
        assert isinstance(data, list)
        for device in data:
            assert device["backend"] == get_backend()


class TestGpuGetUtilization:
    """Tests for gpu_get_utilization tool."""

    @pytest.mark.asyncio
    async def test_get_utilization(self) -> None:
        """Should return utilization percentage."""
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

        result = await gpu_get_utilization(GpuDeviceIndexInput(device_index=0))
        data = json.loads(result)
        assert data["device_index"] == 0


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
        count = get_gpu_count()
        assert "device_count" in data
        assert data["device_count"] == count
        assert "avg_gpu_utilization_pct" in data
        assert "total_memory_mb" in data
        assert "used_memory_mb" in data
        assert "free_memory_mb" in data
        assert "hottest_device" in data
        assert "most_loaded_device" in data
        assert "devices" in data
        assert len(data["devices"]) == count

    @pytest.mark.asyncio
    async def test_cluster_summary_memory_consistency(self) -> None:
        """Total memory should equal used + free."""
        from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary

        result = await gpu_get_cluster_summary(GpuClusterSummaryInput())
        data = json.loads(result)
        assert data["total_memory_mb"] == data["used_memory_mb"] + data["free_memory_mb"]

    @pytest.mark.asyncio
    async def test_cluster_summary_no_gpu(self) -> None:
        """With no GPU backend, should return zero-device summary."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.monitor.get_backend", return_value="none"),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary

            result = await gpu_get_cluster_summary(GpuClusterSummaryInput())
            data = json.loads(result)
            assert data["device_count"] == 0
            assert data["backend"] == "none"


# ---------------------------------------------------------------------------
# Process tool tests (controlled backend)
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
        assert "backend" in data

    @pytest.mark.parametrize("device_index", [2, 99])
    @pytest.mark.asyncio
    async def test_list_processes_invalid_device(self, device_index: int) -> None:
        """A known device count rejects its first invalid index and larger indices."""
        from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

        with patch("mcp_servers.gpu_mcp.tools.processes.get_processes") as query_processes:
            result = await gpu_list_processes(GpuDeviceIndexInput(device_index=device_index))
        query_processes.assert_not_called()
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.parametrize("device_index", [0, 99])
    @pytest.mark.asyncio
    async def test_list_processes_no_gpu(self, device_index: int) -> None:
        """Absent hardware returns a labeled empty list, independent of requested index."""
        with (
            patch("mcp_servers.gpu_mcp.tools.processes.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.processes.get_backend", return_value="none"),
            patch("mcp_servers.gpu_mcp.tools.processes.get_processes") as query_processes,
        ):
            from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

            result = await gpu_list_processes(GpuDeviceIndexInput(device_index=device_index))
            data = json.loads(result)
            assert data["process_count"] == 0
            assert data["processes"] == []
            assert data["backend"] == "none"
            assert data["device_index"] == device_index
            assert data["message"] == "No GPU hardware detected."
            query_processes.assert_not_called()


# ---------------------------------------------------------------------------
# Health check tool tests (controlled backend)
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
        assert data["device_count"] == get_gpu_count()
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
            assert "backend" in device

    @pytest.mark.asyncio
    async def test_health_check_no_gpu(self) -> None:
        """With no GPU backend, should return unknown status and zero devices."""
        with (
            patch("mcp_servers.gpu_mcp.tools.health.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.health.get_backend", return_value="none"),
        ):
            from mcp_servers.gpu_mcp.tools.health import gpu_health_check

            result = await gpu_health_check(GpuHealthCheckInput())
            data = json.loads(result)
            assert data["overall_status"] == "unknown"
            assert data["device_count"] == 0
            assert data["backend"] == "none"


# ---------------------------------------------------------------------------
# No-GPU error path tests (patched backend)
# ---------------------------------------------------------------------------


class TestNoGpuErrorPaths:
    """Verify that tools handle the 'no GPU' case gracefully."""

    @pytest.mark.asyncio
    async def test_list_devices_no_gpu(self) -> None:
        """gpu_list_devices should return device_count: 0 when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.monitor.get_backend", return_value="none"),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_list_devices

            result = await gpu_list_devices(GpuListDevicesInput())
            data = json.loads(result)
            assert data["device_count"] == 0
            assert data["backend"] == "none"
            assert "message" in data

    @pytest.mark.asyncio
    async def test_utilization_no_gpu(self) -> None:
        """gpu_get_utilization should return error JSON when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_get_utilization

            result = await gpu_get_utilization(GpuDeviceIndexInput(device_index=0))
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_memory_no_gpu(self) -> None:
        """gpu_get_memory should return error JSON when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_get_memory

            result = await gpu_get_memory(GpuDeviceIndexInput(device_index=0))
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_temperature_no_gpu(self) -> None:
        """gpu_get_temperature should return error JSON when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_get_temperature

            result = await gpu_get_temperature(GpuDeviceIndexInput(device_index=0))
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_power_no_gpu(self) -> None:
        """gpu_get_power should return error JSON when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_get_power

            result = await gpu_get_power(GpuDeviceIndexInput(device_index=0))
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_processes_no_gpu(self) -> None:
        """gpu_list_processes should return empty list when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.processes.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.processes.get_backend", return_value="none"),
        ):
            from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

            result = await gpu_list_processes(GpuDeviceIndexInput(device_index=0))
            data = json.loads(result)
            assert data["process_count"] == 0

    @pytest.mark.asyncio
    async def test_health_no_gpu(self) -> None:
        """gpu_health_check should return unknown status when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.health.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.health.get_backend", return_value="none"),
        ):
            from mcp_servers.gpu_mcp.tools.health import gpu_health_check

            result = await gpu_health_check(GpuHealthCheckInput())
            data = json.loads(result)
            assert data["overall_status"] == "unknown"
            assert data["device_count"] == 0

    @pytest.mark.asyncio
    async def test_cluster_summary_no_gpu(self) -> None:
        """gpu_get_cluster_summary should return zero devices when no GPU."""
        with (
            patch("mcp_servers.gpu_mcp.tools.monitor.get_gpu_count", return_value=0),
            patch("mcp_servers.gpu_mcp.tools.monitor.get_backend", return_value="none"),
        ):
            from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary

            result = await gpu_get_cluster_summary(GpuClusterSummaryInput())
            data = json.loads(result)
            assert data["device_count"] == 0


# ---------------------------------------------------------------------------
# Backward compatibility aliases
# ---------------------------------------------------------------------------


class TestBackwardCompatAliases:
    """Verify backward-compat aliases still resolve to the real functions."""

    def test_mock_gpu_info_alias(self) -> None:
        """MockGpuInfo should be an alias for GpuInfo."""
        from mcp_servers.gpu_mcp.utils import MockGpuInfo

        assert issubclass(MockGpuInfo, GpuInfo)

    def test_get_mock_gpu_count_alias(self) -> None:
        """get_mock_gpu_count should point to get_gpu_count."""
        from mcp_servers.gpu_mcp.utils import get_mock_gpu_count

        assert get_mock_gpu_count is get_gpu_count

    def test_get_mock_gpu_info_alias(self) -> None:
        """get_mock_gpu_info should point to get_gpu_info."""
        from mcp_servers.gpu_mcp.utils import get_mock_gpu_info

        assert get_mock_gpu_info is get_gpu_info

    def test_get_mock_processes_alias(self) -> None:
        """get_mock_processes should point to get_processes."""
        from mcp_servers.gpu_mcp.utils import get_mock_processes

        assert get_mock_processes is get_processes

    def test_get_mock_health_alias(self) -> None:
        """get_mock_health should point to get_health."""
        from mcp_servers.gpu_mcp.utils import get_mock_health

        assert get_mock_health is get_health

    def test_mock_mode_flag_is_false(self) -> None:
        """MOCK_MODE should be False (no longer used)."""
        from mcp_servers.gpu_mcp.utils import MOCK_MODE

        assert MOCK_MODE is False
