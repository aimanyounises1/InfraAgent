"""Tests for individual agents (cluster_health, gpu_workload, incident_response).

Tests verify keyword dispatch logic, parameter parsing, MCP tool invocation,
error handling, and structured output format for each agent.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Cluster Health Agent Tests
# ---------------------------------------------------------------------------


class TestClusterHealthAgent:
    """Tests for the cluster_health_agent keyword dispatch and tool calls."""

    @pytest.mark.asyncio
    async def test_list_pods_keyword(self) -> None:
        """Query with 'pods' keyword should call k8s_list_pods."""
        mock_result = json.dumps(
            {
                "namespace": "default",
                "pod_count": 1,
                "pods": [{"name": "test-pod", "status": "Running"}],
            }
        )
        with patch(
            "agents.cluster_health.k8s_list_pods",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "show me all pods"})

            mock_fn.assert_called_once()
            assert "k8s_list_pods" in result["k8s_data"]["tools_called"]
            assert "pods" in result["k8s_data"]["raw"]

    @pytest.mark.asyncio
    async def test_list_deployments_keyword(self) -> None:
        """Query with 'deployments' keyword should call k8s_list_deployments."""
        mock_result = json.dumps(
            {
                "namespace": "default",
                "deployment_count": 1,
                "deployments": [{"name": "nginx", "replicas": 3}],
            }
        )
        with patch(
            "agents.cluster_health.k8s_list_deployments",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "list deployments"})

            mock_fn.assert_called_once()
            assert "k8s_list_deployments" in result["k8s_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_list_services_keyword(self) -> None:
        """Query with 'service' keyword should call k8s_list_services."""
        mock_result = json.dumps(
            {
                "namespace": "default",
                "service_count": 1,
                "services": [{"name": "nginx-svc", "type": "ClusterIP"}],
            }
        )
        with patch(
            "agents.cluster_health.k8s_list_services",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "show services in namespace production"})

            mock_fn.assert_called_once()
            assert "k8s_list_services" in result["k8s_data"]["tools_called"]
            assert result["k8s_data"]["namespace"] == "production"

    @pytest.mark.asyncio
    async def test_describe_pod(self) -> None:
        """Query with 'describe pod X' should call k8s_describe_pod."""
        mock_result = "# Pod: my-pod\n**Status:** Running"
        with patch(
            "agents.cluster_health.k8s_describe_pod",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "describe pod my-pod"})

            mock_fn.assert_called_once()
            assert "k8s_describe_pod" in result["k8s_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_get_pod_logs(self) -> None:
        """Query with 'logs for X' should call k8s_get_pod_logs."""
        mock_result = json.dumps(
            {
                "pod": "api-server-abc",
                "logs": "INFO: started\nINFO: healthy",
                "log_lines": 2,
            }
        )
        with patch(
            "agents.cluster_health.k8s_get_pod_logs",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "get logs for api-server-abc"})

            mock_fn.assert_called_once()
            assert "k8s_get_pod_logs" in result["k8s_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_scale_deployment(self) -> None:
        """Query with 'scale X to N' should call k8s_scale_deployment."""
        mock_result = json.dumps(
            {
                "action": "scale",
                "deployment": "nginx",
                "previous_replicas": 3,
                "new_replicas": 5,
                "status": "scaled",
            }
        )
        with patch(
            "agents.cluster_health.k8s_scale_deployment",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "scale nginx to 5 replicas"})

            mock_fn.assert_called_once()
            assert "k8s_scale_deployment" in result["k8s_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_restart_deployment(self) -> None:
        """Query with 'restart X' should call k8s_restart_deployment."""
        mock_result = json.dumps(
            {
                "action": "rolling_restart",
                "deployment": "api-server",
                "status": "restarting",
            }
        )
        with patch(
            "agents.cluster_health.k8s_restart_deployment",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "restart api-server"})

            mock_fn.assert_called_once()
            assert "k8s_restart_deployment" in result["k8s_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_default_overview(self) -> None:
        """Default query should call both k8s_list_pods and k8s_list_deployments."""
        pods_result = json.dumps({"namespace": "default", "pod_count": 0, "pods": []})
        deploy_result = json.dumps(
            {"namespace": "default", "deployment_count": 0, "deployments": []}
        )
        with (
            patch(
                "agents.cluster_health.k8s_list_pods",
                new_callable=AsyncMock,
                return_value=pods_result,
            ),
            patch(
                "agents.cluster_health.k8s_list_deployments",
                new_callable=AsyncMock,
                return_value=deploy_result,
            ),
        ):
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "what is the cluster status"})

            assert "k8s_list_pods" in result["k8s_data"]["tools_called"]
            assert "k8s_list_deployments" in result["k8s_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_namespace_parsing(self) -> None:
        """Query mentioning 'namespace production' should use that namespace."""
        mock_result = json.dumps({"namespace": "production", "pod_count": 0, "pods": []})
        with patch(
            "agents.cluster_health.k8s_list_pods",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "list pods in namespace production"})

            assert result["k8s_data"]["namespace"] == "production"

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        """Empty query should return an error in k8s_data."""
        from agents.cluster_health import cluster_health_agent

        result = await cluster_health_agent({"query": ""})

        assert "error" in result["k8s_data"]

    @pytest.mark.asyncio
    async def test_tool_call_error_handling(self) -> None:
        """If a tool call raises an exception, the agent should handle it gracefully."""
        with patch(
            "agents.cluster_health.k8s_list_pods",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "list pods"})

            # Should not raise; should contain error info in the raw result
            raw_pods = result["k8s_data"]["raw"].get("pods", "")
            parsed = json.loads(raw_pods)
            assert "error" in parsed

    @pytest.mark.asyncio
    async def test_output_structure(self) -> None:
        """Agent output should contain k8s_data with raw, tools_called, namespace."""
        mock_result = json.dumps({"namespace": "default", "pod_count": 0, "pods": []})
        with (
            patch(
                "agents.cluster_health.k8s_list_pods",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "agents.cluster_health.k8s_list_deployments",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            from agents.cluster_health import cluster_health_agent

            result = await cluster_health_agent({"query": "cluster overview"})

            assert "k8s_data" in result
            assert "raw" in result["k8s_data"]
            assert "tools_called" in result["k8s_data"]
            assert "namespace" in result["k8s_data"]
            assert "actions_taken" in result
            assert isinstance(result["actions_taken"], list)


# ---------------------------------------------------------------------------
# GPU Workload Agent Tests
# ---------------------------------------------------------------------------


class TestGpuWorkloadAgent:
    """Tests for the gpu_workload_agent keyword dispatch and tool calls."""

    @pytest.mark.asyncio
    async def test_list_devices(self) -> None:
        """Query with 'list gpus' should call gpu_list_devices."""
        mock_result = json.dumps(
            [
                {"device_index": 0, "name": "A100", "total_memory_mb": 81920},
            ]
        )
        with patch(
            "agents.gpu_workload.gpu_list_devices",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "list all gpus"})

            mock_fn.assert_called_once()
            assert "gpu_list_devices" in result["gpu_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        """Query with 'health' should call gpu_health_check."""
        mock_result = json.dumps(
            {
                "overall_status": "healthy",
                "device_count": 4,
                "summary": {"healthy": 4, "warning": 0, "critical": 0},
                "devices": [],
            }
        )
        with patch(
            "agents.gpu_workload.gpu_health_check",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "gpu health check"})

            mock_fn.assert_called_once()
            assert "gpu_health_check" in result["gpu_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_cluster_summary(self) -> None:
        """Query with 'utilization' should call gpu_get_cluster_summary."""
        mock_result = json.dumps(
            {
                "device_count": 4,
                "avg_gpu_utilization_pct": 72.5,
            }
        )
        with patch(
            "agents.gpu_workload.gpu_get_cluster_summary",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "show gpu utilization"})

            mock_fn.assert_called_once()
            assert "gpu_get_cluster_summary" in result["gpu_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_temperature_all_devices(self) -> None:
        """Query about 'temperature' without device index should query all devices."""
        devices_result = json.dumps(
            [
                {"device_index": 0},
                {"device_index": 1},
            ]
        )
        temp_result = json.dumps({"device_index": 0, "temperature_c": 65})
        with (
            patch(
                "agents.gpu_workload.gpu_list_devices",
                new_callable=AsyncMock,
                return_value=devices_result,
            ),
            patch(
                "agents.gpu_workload.gpu_get_temperature",
                new_callable=AsyncMock,
                return_value=temp_result,
            ) as temp_mock,
        ):
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "check gpu temperature"})

            # Should be called for each device
            assert temp_mock.call_count == 2
            assert any("gpu_get_temperature" in t for t in result["gpu_data"]["tools_called"])

    @pytest.mark.asyncio
    async def test_temperature_specific_device(self) -> None:
        """Query about 'temperature gpu 1' should query only device 1."""
        temp_result = json.dumps(
            {
                "device_index": 1,
                "temperature_c": 72,
                "status": "normal",
            }
        )
        with patch(
            "agents.gpu_workload.gpu_get_temperature",
            new_callable=AsyncMock,
            return_value=temp_result,
        ) as temp_mock:
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "temperature for gpu 1"})

            temp_mock.assert_called_once()
            assert "gpu_get_temperature" in result["gpu_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_memory_keyword(self) -> None:
        """Query about 'memory' should call gpu_get_memory."""
        devices_result = json.dumps([{"device_index": 0}])
        mem_result = json.dumps(
            {
                "device_index": 0,
                "total_mb": 81920,
                "used_mb": 40960,
            }
        )
        with (
            patch(
                "agents.gpu_workload.gpu_list_devices",
                new_callable=AsyncMock,
                return_value=devices_result,
            ),
            patch(
                "agents.gpu_workload.gpu_get_memory",
                new_callable=AsyncMock,
                return_value=mem_result,
            ),
        ):
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "gpu memory usage"})

            assert any("gpu_get_memory" in t for t in result["gpu_data"]["tools_called"])

    @pytest.mark.asyncio
    async def test_power_keyword(self) -> None:
        """Query about 'power' should call gpu_get_power."""
        devices_result = json.dumps([{"device_index": 0}])
        power_result = json.dumps(
            {
                "device_index": 0,
                "power_draw_w": 250.0,
                "power_limit_w": 400.0,
            }
        )
        with (
            patch(
                "agents.gpu_workload.gpu_list_devices",
                new_callable=AsyncMock,
                return_value=devices_result,
            ),
            patch(
                "agents.gpu_workload.gpu_get_power",
                new_callable=AsyncMock,
                return_value=power_result,
            ),
        ):
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "gpu power draw"})

            assert any("gpu_get_power" in t for t in result["gpu_data"]["tools_called"])

    @pytest.mark.asyncio
    async def test_processes_keyword(self) -> None:
        """Query about 'processes' should call gpu_list_processes."""
        devices_result = json.dumps([{"device_index": 0}])
        proc_result = json.dumps(
            {
                "device_index": 0,
                "process_count": 1,
                "processes": [{"pid": 1234, "name": "python", "memory_mb": 4096}],
            }
        )
        with (
            patch(
                "agents.gpu_workload.gpu_list_devices",
                new_callable=AsyncMock,
                return_value=devices_result,
            ),
            patch(
                "agents.gpu_workload.gpu_list_processes",
                new_callable=AsyncMock,
                return_value=proc_result,
            ),
        ):
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "what processes are running on gpu"})

            assert any("gpu_list_processes" in t for t in result["gpu_data"]["tools_called"])

    @pytest.mark.asyncio
    async def test_default_overview(self) -> None:
        """Default GPU query should call cluster_summary + health_check."""
        summary_result = json.dumps({"device_count": 4, "avg_gpu_utilization_pct": 50})
        health_result = json.dumps(
            {"overall_status": "healthy", "device_count": 4, "summary": {}, "devices": []}
        )
        with (
            patch(
                "agents.gpu_workload.gpu_get_cluster_summary",
                new_callable=AsyncMock,
                return_value=summary_result,
            ),
            patch(
                "agents.gpu_workload.gpu_health_check",
                new_callable=AsyncMock,
                return_value=health_result,
            ),
        ):
            from agents.gpu_workload import gpu_workload_agent

            # Use a query that does not match any specific keyword branch
            result = await gpu_workload_agent(
                {"query": "give me an overview of the compute accelerators"}
            )

            assert "gpu_get_cluster_summary" in result["gpu_data"]["tools_called"]
            assert "gpu_health_check" in result["gpu_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        """Empty query should return an error in gpu_data."""
        from agents.gpu_workload import gpu_workload_agent

        result = await gpu_workload_agent({"query": ""})

        assert "error" in result["gpu_data"]

    @pytest.mark.asyncio
    async def test_output_structure(self) -> None:
        """Agent output should contain gpu_data with raw and tools_called."""
        mock_result = json.dumps(
            {"overall_status": "healthy", "device_count": 4, "summary": {}, "devices": []}
        )
        with patch(
            "agents.gpu_workload.gpu_health_check",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            from agents.gpu_workload import gpu_workload_agent

            result = await gpu_workload_agent({"query": "gpu health"})

            assert "gpu_data" in result
            assert "raw" in result["gpu_data"]
            assert "tools_called" in result["gpu_data"]
            assert "actions_taken" in result
            assert isinstance(result["actions_taken"], list)


# ---------------------------------------------------------------------------
# Incident Response Agent Tests
# ---------------------------------------------------------------------------


class TestIncidentResponseAgent:
    """Tests for the incident_response_agent keyword dispatch and tool calls."""

    @pytest.mark.asyncio
    async def test_create_jira_ticket(self) -> None:
        """Query with 'create ticket' should call incident_jira_create_ticket."""
        mock_result = json.dumps(
            {
                "key": "OPS-123",
                "fields": {"summary": "Test incident", "status": {"name": "Open"}},
            }
        )
        with patch(
            "agents.incident_response.incident_jira_create_ticket",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "create ticket for database outage"})

            mock_fn.assert_called_once()
            assert "incident_jira_create_ticket" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_search_jira(self) -> None:
        """Query with 'search' should call incident_jira_search."""
        mock_result = json.dumps(
            {
                "total": 1,
                "issues": [{"key": "OPS-100", "fields": {"summary": "Past incident"}}],
            }
        )
        with patch(
            "agents.incident_response.incident_jira_search",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent(
                {"query": "search for past incident about database"}
            )

            mock_fn.assert_called_once()
            assert "incident_jira_search" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_get_alerts(self) -> None:
        """Query with 'alerts' should call incident_grafana_get_alerts."""
        mock_result = json.dumps(
            {
                "alerts": [{"labels": {"alertname": "HighCPU"}}],
                "total": 1,
            }
        )
        with patch(
            "agents.incident_response.incident_grafana_get_alerts",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "show firing alerts"})

            mock_fn.assert_called_once()
            assert "incident_grafana_get_alerts" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_grafana_metrics(self) -> None:
        """Query with 'metric' should call incident_grafana_query."""
        mock_result = json.dumps({"status": "success", "data": {"result": []}})
        with patch(
            "agents.incident_response.incident_grafana_query",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "query grafana metric for cpu usage"})

            mock_fn.assert_called_once()
            assert "incident_grafana_query" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_pagerduty_list(self) -> None:
        """Query with 'pagerduty' should call incident_pagerduty_list_incidents."""
        mock_result = json.dumps(
            {
                "incidents": [{"id": "P1234", "title": "High CPU", "status": "triggered"}],
                "total": 1,
            }
        )
        with patch(
            "agents.incident_response.incident_pagerduty_list_incidents",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "list pagerduty incidents"})

            mock_fn.assert_called_once()
            assert "incident_pagerduty_list_incidents" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_acknowledge_incident(self) -> None:
        """Query with 'ack' and incident ID should call pagerduty_acknowledge."""
        mock_result = json.dumps(
            {
                "incident": {"id": "PABC123", "status": "acknowledged"},
            }
        )
        with patch(
            "agents.incident_response.incident_pagerduty_acknowledge",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "acknowledge incident PABC123"})

            mock_fn.assert_called_once()
            assert "incident_pagerduty_acknowledge" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_acknowledge_without_id_fallback(self) -> None:
        """Ack without incident ID should fall back to listing incidents."""
        mock_result = json.dumps({"incidents": [], "total": 0})
        with patch(
            "agents.incident_response.incident_pagerduty_list_incidents",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "ack the issue"})

            assert "incident_pagerduty_list_incidents" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_resolve_incident(self) -> None:
        """Query with 'resolve' and incident ID should call pagerduty_resolve."""
        mock_result = json.dumps(
            {
                "incident": {"id": "PXYZ789", "status": "resolved"},
            }
        )
        with patch(
            "agents.incident_response.incident_pagerduty_resolve",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "resolve incident PXYZ789"})

            mock_fn.assert_called_once()
            assert "incident_pagerduty_resolve" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_generate_rca(self) -> None:
        """Query with 'rca' should call incident_generate_rca."""
        mock_result = "# Root Cause Analysis\n\nReport content..."
        with patch(
            "agents.incident_response.incident_generate_rca",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_fn:
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent(
                {"query": "generate rca for the database outage last night"}
            )

            mock_fn.assert_called_once()
            assert "incident_generate_rca" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_default_overview(self) -> None:
        """Default incident query should call PD incidents + Grafana alerts."""
        pd_result = json.dumps({"incidents": [], "total": 0})
        alerts_result = json.dumps({"alerts": [], "total": 0})
        with (
            patch(
                "agents.incident_response.incident_pagerduty_list_incidents",
                new_callable=AsyncMock,
                return_value=pd_result,
            ),
            patch(
                "agents.incident_response.incident_grafana_get_alerts",
                new_callable=AsyncMock,
                return_value=alerts_result,
            ),
        ):
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "what incidents are happening"})

            assert "incident_pagerduty_list_incidents" in result["incident_data"]["tools_called"]
            assert "incident_grafana_get_alerts" in result["incident_data"]["tools_called"]

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        """Empty query should return an error in incident_data."""
        from agents.incident_response import incident_response_agent

        result = await incident_response_agent({"query": ""})

        assert "error" in result["incident_data"]

    @pytest.mark.asyncio
    async def test_output_structure(self) -> None:
        """Agent output should contain incident_data with raw and tools_called."""
        mock_result = json.dumps({"incidents": [], "total": 0})
        alerts_result = json.dumps({"alerts": [], "total": 0})
        with (
            patch(
                "agents.incident_response.incident_pagerduty_list_incidents",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "agents.incident_response.incident_grafana_get_alerts",
                new_callable=AsyncMock,
                return_value=alerts_result,
            ),
        ):
            from agents.incident_response import incident_response_agent

            result = await incident_response_agent({"query": "incident overview"})

            assert "incident_data" in result
            assert "raw" in result["incident_data"]
            assert "tools_called" in result["incident_data"]
            assert "actions_taken" in result
            assert isinstance(result["actions_taken"], list)


# ---------------------------------------------------------------------------
# Synthesizer / Orchestrator Tests
# ---------------------------------------------------------------------------


class TestSynthesizeResponse:
    """Tests for the synthesize_response function."""

    @pytest.mark.asyncio
    async def test_formats_k8s_data(self) -> None:
        """Synthesizer should format k8s_data into readable output."""
        from agents.orchestrator import InfraState, synthesize_response

        state = InfraState(
            query="list pods",
            k8s_data={
                "raw": {
                    "pods": json.dumps(
                        {
                            "namespace": "default",
                            "pod_count": 2,
                            "pods": [
                                {
                                    "name": "pod-a",
                                    "status": "Running",
                                    "node": "node-1",
                                    "containers": [],
                                },
                                {
                                    "name": "pod-b",
                                    "status": "CrashLoopBackOff",
                                    "node": "node-2",
                                    "containers": [{"restart_count": 5}],
                                },
                            ],
                        }
                    )
                },
                "tools_called": ["k8s_list_pods"],
                "namespace": "default",
            },
        )

        result = await synthesize_response(state)
        response = result["response"]

        assert "Kubernetes" in response
        assert "pod-a" in response
        assert "pod-b" in response
        assert "k8s_list_pods" in response

    @pytest.mark.asyncio
    async def test_formats_gpu_data(self) -> None:
        """Synthesizer should format gpu_data into readable output."""
        from agents.orchestrator import InfraState, synthesize_response

        state = InfraState(
            query="gpu status",
            gpu_data={
                "raw": {
                    "health": json.dumps(
                        {
                            "overall_status": "healthy",
                            "device_count": 2,
                            "summary": {"healthy": 2, "warning": 0, "critical": 0},
                            "devices": [
                                {
                                    "device_index": 0,
                                    "status": "healthy",
                                    "temperature_c": 65,
                                    "gpu_utilization_pct": 80,
                                    "memory_utilization_pct": 50,
                                },
                                {
                                    "device_index": 1,
                                    "status": "healthy",
                                    "temperature_c": 70,
                                    "gpu_utilization_pct": 60,
                                    "memory_utilization_pct": 40,
                                },
                            ],
                        }
                    )
                },
                "tools_called": ["gpu_health_check"],
            },
        )

        result = await synthesize_response(state)
        response = result["response"]

        assert "GPU" in response
        assert "healthy" in response.lower() or "HEALTHY" in response

    @pytest.mark.asyncio
    async def test_formats_incident_data(self) -> None:
        """Synthesizer should format incident_data into readable output."""
        from agents.orchestrator import InfraState, synthesize_response

        state = InfraState(
            query="show alerts",
            incident_data={
                "raw": {
                    "alerts": json.dumps(
                        {
                            "alerts": [
                                {
                                    "labels": {"alertname": "HighCPU", "severity": "critical"},
                                    "status": {"state": "firing"},
                                },
                            ],
                            "total": 1,
                        }
                    )
                },
                "tools_called": ["incident_grafana_get_alerts"],
            },
        )

        result = await synthesize_response(state)
        response = result["response"]

        assert "Incident" in response
        assert "HighCPU" in response

    @pytest.mark.asyncio
    async def test_no_data_collected(self) -> None:
        """Synthesizer with no agent data should return 'No data collected.'."""
        from agents.orchestrator import InfraState, synthesize_response

        state = InfraState(query="hello")
        result = await synthesize_response(state)

        assert result["response"] == "No data collected."

    @pytest.mark.asyncio
    async def test_actions_summary(self) -> None:
        """Synthesizer should include actions summary when actions_taken is populated."""
        from agents.orchestrator import InfraState, synthesize_response

        state = InfraState(
            query="list pods",
            k8s_data={
                "raw": {"pods": json.dumps({"namespace": "default", "pod_count": 0, "pods": []})},
                "tools_called": ["k8s_list_pods"],
                "namespace": "default",
            },
            actions_taken=["cluster_health_agent: listed pods in default"],
        )

        result = await synthesize_response(state)
        response = result["response"]

        assert "Actions taken" in response
        assert "listed pods" in response
