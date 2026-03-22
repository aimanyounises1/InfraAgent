"""Tests for k8s_mcp server tools.

All tests run with INFRA_AGENT_MOCK_K8S=true (the default) so they exercise
the mock-data code paths without needing a real Kubernetes cluster.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from mcp_servers.k8s_mcp.models import (
    K8sDescribePodInput,
    K8sExecCommandInput,
    K8sGetPodLogsInput,
    K8sListDeploymentsInput,
    K8sListPodsInput,
    K8sListServicesInput,
    K8sRestartDeploymentInput,
    K8sScaleDeploymentInput,
)

# ---------------------------------------------------------------------------
# Ensure mock mode is enabled for all tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _force_mock_k8s():
    """Ensure settings.mock_k8s is True for every test."""
    with patch("config.settings.mock_k8s", True):
        yield


# ===========================================================================
# Pod Tools
# ===========================================================================


class TestK8sListPods:
    """Tests for k8s_list_pods tool."""

    @pytest.mark.asyncio
    async def test_list_pods_default_namespace(self) -> None:
        """Should list pods in the default namespace."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

        params = K8sListPodsInput()
        result_str = await k8s_list_pods(params)
        result = json.loads(result_str)

        assert result["namespace"] == "default"
        assert result["pod_count"] > 0
        assert isinstance(result["pods"], list)

        # Check that known mock pods are present
        pod_names = [p["name"] for p in result["pods"]]
        assert any("nginx" in name for name in pod_names)
        assert any("redis" in name for name in pod_names)

    @pytest.mark.asyncio
    async def test_list_pods_with_label_selector(self) -> None:
        """Should filter pods by label selector."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

        params = K8sListPodsInput(label_selector="app=nginx")
        result_str = await k8s_list_pods(params)
        result = json.loads(result_str)

        assert result["pod_count"] >= 1
        for pod in result["pods"]:
            assert pod["labels"].get("app") == "nginx"

    @pytest.mark.asyncio
    async def test_list_pods_empty_namespace(self) -> None:
        """Should return empty list for namespace with no pods."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

        params = K8sListPodsInput(namespace="nonexistent-ns")
        result_str = await k8s_list_pods(params)
        result = json.loads(result_str)

        assert result["pod_count"] == 0
        assert result["pods"] == []

    @pytest.mark.asyncio
    async def test_list_pods_with_limit(self) -> None:
        """Should respect the limit parameter."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

        params = K8sListPodsInput(limit=2)
        result_str = await k8s_list_pods(params)
        result = json.loads(result_str)

        assert result["pod_count"] <= 2

    def test_list_pods_input_validation(self) -> None:
        """Should reject invalid input (e.g., limit < 1)."""
        with pytest.raises(ValidationError):
            K8sListPodsInput(limit=0)

    def test_list_pods_input_validation_limit_too_high(self) -> None:
        """Should reject limit > 200."""
        with pytest.raises(ValidationError):
            K8sListPodsInput(limit=201)


class TestK8sDescribePod:
    """Tests for k8s_describe_pod tool."""

    @pytest.mark.asyncio
    async def test_describe_existing_pod(self) -> None:
        """Should return Markdown detail for existing pod."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_describe_pod

        params = K8sDescribePodInput(
            pod_name="nginx-deployment-7c79c4bf97-abc12",
            namespace="default",
        )
        result_str = await k8s_describe_pod(params)

        # Markdown output should contain the pod name as a heading
        assert "# Pod: nginx-deployment-7c79c4bf97-abc12" in result_str
        assert "**Status:** Running" in result_str
        assert "## Containers" in result_str
        assert "nginx" in result_str

    @pytest.mark.asyncio
    async def test_describe_pod_with_events(self) -> None:
        """Should include events section for pods with events."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_describe_pod

        params = K8sDescribePodInput(
            pod_name="worker-batch-job-ghi01",
            namespace="default",
        )
        result_str = await k8s_describe_pod(params)

        assert "## Events" in result_str
        assert "BackOff" in result_str or "Warning" in result_str

    @pytest.mark.asyncio
    async def test_describe_nonexistent_pod(self) -> None:
        """Should return error JSON for pod that doesn't exist."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_describe_pod

        params = K8sDescribePodInput(
            pod_name="no-such-pod",
            namespace="default",
        )
        result_str = await k8s_describe_pod(params)
        result = json.loads(result_str)

        assert result["error"] == "Pod not found"
        assert result["pod_name"] == "no-such-pod"

    def test_describe_pod_input_validation(self) -> None:
        """Should reject empty pod_name."""
        with pytest.raises(ValidationError):
            K8sDescribePodInput(pod_name="")


class TestK8sExecCommand:
    """Tests for k8s_exec_command tool."""

    @pytest.mark.asyncio
    async def test_exec_simple_command(self) -> None:
        """Should return mock output for a simple command."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_exec_command

        params = K8sExecCommandInput(
            pod_name="nginx-deployment-7c79c4bf97-abc12",
            namespace="default",
            command=["whoami"],
        )
        result_str = await k8s_exec_command(params)
        result = json.loads(result_str)

        assert result["pod"] == "nginx-deployment-7c79c4bf97-abc12"
        assert result["exit_code"] == 0
        assert "root" in result["output"]

    @pytest.mark.asyncio
    async def test_exec_ls_command(self) -> None:
        """Should return file listing for ls command."""
        from mcp_servers.k8s_mcp.tools.pods import k8s_exec_command

        params = K8sExecCommandInput(
            pod_name="nginx-deployment-7c79c4bf97-abc12",
            namespace="default",
            command=["ls", "-la"],
        )
        result_str = await k8s_exec_command(params)
        result = json.loads(result_str)

        assert result["exit_code"] == 0
        assert "total" in result["output"]

    def test_exec_input_validation_empty_command(self) -> None:
        """Should reject empty command list."""
        with pytest.raises(ValidationError):
            K8sExecCommandInput(
                pod_name="test-pod",
                command=[],
            )


# ===========================================================================
# Deployment Tools
# ===========================================================================


class TestK8sListDeployments:
    """Tests for k8s_list_deployments tool."""

    @pytest.mark.asyncio
    async def test_list_deployments_default_namespace(self) -> None:
        """Should list deployments in the default namespace."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_list_deployments

        params = K8sListDeploymentsInput()
        result_str = await k8s_list_deployments(params)
        result = json.loads(result_str)

        assert result["namespace"] == "default"
        assert result["deployment_count"] > 0

        deploy_names = [d["name"] for d in result["deployments"]]
        assert "nginx-deployment" in deploy_names

    @pytest.mark.asyncio
    async def test_list_deployments_with_label_selector(self) -> None:
        """Should filter deployments by label selector."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_list_deployments

        params = K8sListDeploymentsInput(label_selector="app=redis")
        result_str = await k8s_list_deployments(params)
        result = json.loads(result_str)

        assert result["deployment_count"] >= 1
        for d in result["deployments"]:
            assert d["labels"].get("app") == "redis"

    @pytest.mark.asyncio
    async def test_list_deployments_empty_namespace(self) -> None:
        """Should return empty list for namespace with no deployments."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_list_deployments

        params = K8sListDeploymentsInput(namespace="nonexistent-ns")
        result_str = await k8s_list_deployments(params)
        result = json.loads(result_str)

        assert result["deployment_count"] == 0
        assert result["deployments"] == []

    @pytest.mark.asyncio
    async def test_list_deployments_replica_counts(self) -> None:
        """Should include replica counts in deployment data."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_list_deployments

        params = K8sListDeploymentsInput()
        result_str = await k8s_list_deployments(params)
        result = json.loads(result_str)

        for d in result["deployments"]:
            assert "replicas" in d
            assert "ready_replicas" in d
            assert "available_replicas" in d


class TestK8sScaleDeployment:
    """Tests for k8s_scale_deployment tool."""

    @pytest.mark.asyncio
    async def test_scale_deployment(self) -> None:
        """Should scale a deployment to specified replicas."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_scale_deployment

        params = K8sScaleDeploymentInput(
            deployment_name="nginx-deployment",
            namespace="default",
            replicas=5,
        )
        result_str = await k8s_scale_deployment(params)
        result = json.loads(result_str)

        assert result["action"] == "scale"
        assert result["deployment"] == "nginx-deployment"
        assert result["new_replicas"] == 5
        assert result["previous_replicas"] == 3  # nginx mock has 3
        assert result["status"] == "scaled"

    @pytest.mark.asyncio
    async def test_scale_nonexistent_deployment(self) -> None:
        """Should return error for deployment that doesn't exist."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_scale_deployment

        params = K8sScaleDeploymentInput(
            deployment_name="no-such-deploy",
            namespace="default",
            replicas=2,
        )
        result_str = await k8s_scale_deployment(params)
        result = json.loads(result_str)

        assert result["error"] == "Deployment not found"

    def test_scale_input_validation(self) -> None:
        """Should reject replicas > 100."""
        with pytest.raises(ValidationError):
            K8sScaleDeploymentInput(deployment_name="nginx", replicas=101)

    def test_scale_input_validation_negative(self) -> None:
        """Should reject replicas < 0."""
        with pytest.raises(ValidationError):
            K8sScaleDeploymentInput(deployment_name="nginx", replicas=-1)


class TestK8sRestartDeployment:
    """Tests for k8s_restart_deployment tool."""

    @pytest.mark.asyncio
    async def test_restart_deployment(self) -> None:
        """Should trigger a rolling restart."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_restart_deployment

        params = K8sRestartDeploymentInput(
            deployment_name="nginx-deployment",
            namespace="default",
        )
        result_str = await k8s_restart_deployment(params)
        result = json.loads(result_str)

        assert result["action"] == "rolling_restart"
        assert result["deployment"] == "nginx-deployment"
        assert result["status"] == "restarting"
        assert "restart_triggered_at" in result

    @pytest.mark.asyncio
    async def test_restart_nonexistent_deployment(self) -> None:
        """Should return error for deployment that doesn't exist."""
        from mcp_servers.k8s_mcp.tools.deployments import k8s_restart_deployment

        params = K8sRestartDeploymentInput(
            deployment_name="no-such-deploy",
            namespace="default",
        )
        result_str = await k8s_restart_deployment(params)
        result = json.loads(result_str)

        assert result["error"] == "Deployment not found"


# ===========================================================================
# Service Tools
# ===========================================================================


class TestK8sListServices:
    """Tests for k8s_list_services tool."""

    @pytest.mark.asyncio
    async def test_list_services_default_namespace(self) -> None:
        """Should list services in the default namespace."""
        from mcp_servers.k8s_mcp.tools.services import k8s_list_services

        params = K8sListServicesInput()
        result_str = await k8s_list_services(params)
        result = json.loads(result_str)

        assert result["namespace"] == "default"
        assert result["service_count"] > 0

        svc_names = [s["name"] for s in result["services"]]
        assert "kubernetes" in svc_names
        assert "nginx-svc" in svc_names
        assert "redis-svc" in svc_names

    @pytest.mark.asyncio
    async def test_list_services_includes_ports(self) -> None:
        """Should include port information in service data."""
        from mcp_servers.k8s_mcp.tools.services import k8s_list_services

        params = K8sListServicesInput()
        result_str = await k8s_list_services(params)
        result = json.loads(result_str)

        for svc in result["services"]:
            assert "ports" in svc
            assert "type" in svc
            assert "cluster_ip" in svc

    @pytest.mark.asyncio
    async def test_list_services_includes_types(self) -> None:
        """Should include various service types."""
        from mcp_servers.k8s_mcp.tools.services import k8s_list_services

        params = K8sListServicesInput()
        result_str = await k8s_list_services(params)
        result = json.loads(result_str)

        types = {s["type"] for s in result["services"]}
        assert "ClusterIP" in types
        assert "LoadBalancer" in types

    @pytest.mark.asyncio
    async def test_list_services_empty_namespace(self) -> None:
        """Should return empty list for namespace with no services."""
        from mcp_servers.k8s_mcp.tools.services import k8s_list_services

        params = K8sListServicesInput(namespace="nonexistent-ns")
        result_str = await k8s_list_services(params)
        result = json.loads(result_str)

        assert result["service_count"] == 0
        assert result["services"] == []


# ===========================================================================
# Log Tools
# ===========================================================================


class TestK8sGetPodLogs:
    """Tests for k8s_get_pod_logs tool."""

    @pytest.mark.asyncio
    async def test_get_nginx_logs(self) -> None:
        """Should return nginx-style log output."""
        from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs

        params = K8sGetPodLogsInput(
            pod_name="nginx-deployment-7c79c4bf97-abc12",
            namespace="default",
        )
        result_str = await k8s_get_pod_logs(params)
        result = json.loads(result_str)

        assert result["pod"] == "nginx-deployment-7c79c4bf97-abc12"
        assert result["log_lines"] > 0
        assert "GET" in result["logs"]  # nginx access log pattern

    @pytest.mark.asyncio
    async def test_get_worker_logs_shows_errors(self) -> None:
        """Should return error logs for crashing worker pod."""
        from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs

        params = K8sGetPodLogsInput(
            pod_name="worker-batch-job-ghi01",
            namespace="default",
        )
        result_str = await k8s_get_pod_logs(params)
        result = json.loads(result_str)

        assert "ERROR" in result["logs"] or "FATAL" in result["logs"]

    @pytest.mark.asyncio
    async def test_get_logs_with_tail_lines(self) -> None:
        """Should respect tail_lines parameter."""
        from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs

        params = K8sGetPodLogsInput(
            pod_name="nginx-deployment-7c79c4bf97-abc12",
            namespace="default",
            tail_lines=3,
        )
        result_str = await k8s_get_pod_logs(params)
        result = json.loads(result_str)

        assert result["tail_lines"] == 3
        assert result["log_lines"] <= 3

    @pytest.mark.asyncio
    async def test_get_logs_with_since_seconds(self) -> None:
        """Should accept since_seconds parameter."""
        from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs

        params = K8sGetPodLogsInput(
            pod_name="redis-master-0",
            namespace="default",
            since_seconds=3600,
        )
        result_str = await k8s_get_pod_logs(params)
        result = json.loads(result_str)

        assert result["since_seconds"] == 3600
        assert result["log_lines"] > 0

    @pytest.mark.asyncio
    async def test_get_logs_unknown_pod_returns_fallback(self) -> None:
        """Should return fallback logs for unknown pod name."""
        from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs

        params = K8sGetPodLogsInput(
            pod_name="unknown-pod-xyz",
            namespace="default",
        )
        result_str = await k8s_get_pod_logs(params)
        result = json.loads(result_str)

        # Fallback logs should still have content
        assert result["log_lines"] > 0
        assert "Heartbeat" in result["logs"]

    def test_get_logs_input_validation(self) -> None:
        """Should reject tail_lines < 1."""
        with pytest.raises(ValidationError):
            K8sGetPodLogsInput(pod_name="test", tail_lines=0)

    def test_get_logs_input_validation_too_many_lines(self) -> None:
        """Should reject tail_lines > 5000."""
        with pytest.raises(ValidationError):
            K8sGetPodLogsInput(pod_name="test", tail_lines=5001)


# ===========================================================================
# Mock Data Unit Tests
# ===========================================================================


class TestMockDataGenerators:
    """Tests for the mock data generator functions in utils.py."""

    def test_get_mock_pods_filters_by_namespace(self) -> None:
        """Should only return pods from the specified namespace."""
        from mcp_servers.k8s_mcp.utils import get_mock_pods

        default_pods = get_mock_pods(namespace="default")
        monitoring_pods = get_mock_pods(namespace="monitoring")

        assert all(p["namespace"] == "default" for p in default_pods)
        assert all(p["namespace"] == "monitoring" for p in monitoring_pods)
        assert len(monitoring_pods) >= 1

    def test_get_mock_pods_filters_by_label(self) -> None:
        """Should filter by label selector."""
        from mcp_servers.k8s_mcp.utils import get_mock_pods

        redis_pods = get_mock_pods(namespace="default", label_selector="app=redis")
        assert len(redis_pods) >= 1
        assert all(p["labels"].get("app") == "redis" for p in redis_pods)

    def test_get_mock_deployments_returns_data(self) -> None:
        """Should return deployments with expected fields."""
        from mcp_servers.k8s_mcp.utils import get_mock_deployments

        deploys = get_mock_deployments(namespace="default")
        assert len(deploys) >= 1
        for d in deploys:
            assert "name" in d
            assert "replicas" in d
            assert "ready_replicas" in d

    def test_get_mock_services_returns_data(self) -> None:
        """Should return services with expected fields."""
        from mcp_servers.k8s_mcp.utils import get_mock_services

        svcs = get_mock_services(namespace="default")
        assert len(svcs) >= 1
        for s in svcs:
            assert "name" in s
            assert "type" in s
            assert "ports" in s

    def test_get_mock_pod_detail_returns_events(self) -> None:
        """Should return pod detail with events attached."""
        from mcp_servers.k8s_mcp.utils import get_mock_pod_detail

        detail = get_mock_pod_detail(
            name="nginx-deployment-7c79c4bf97-abc12",
            namespace="default",
        )
        assert detail is not None
        assert "events" in detail
        assert len(detail["events"]) >= 1

    def test_get_mock_pod_detail_returns_none_for_missing(self) -> None:
        """Should return None when pod is not found."""
        from mcp_servers.k8s_mcp.utils import get_mock_pod_detail

        detail = get_mock_pod_detail(name="no-such-pod", namespace="default")
        assert detail is None

    def test_get_mock_pod_logs_returns_matching_content(self) -> None:
        """Should return logs matching the pod name prefix."""
        from mcp_servers.k8s_mcp.utils import get_mock_pod_logs

        nginx_logs = get_mock_pod_logs(name="nginx-abc123")
        assert "GET" in nginx_logs

        redis_logs = get_mock_pod_logs(name="redis-master-0")
        assert "Redis" in redis_logs

    def test_get_mock_exec_output(self) -> None:
        """Should return realistic output for known commands."""
        from mcp_servers.k8s_mcp.utils import get_mock_exec_output

        assert "root" in get_mock_exec_output(["whoami"])
        assert "total" in get_mock_exec_output(["ls", "-la"])
        assert "PID" in get_mock_exec_output(["ps", "aux"])

    def test_get_mock_events_filters_by_type(self) -> None:
        """Should filter events by type."""
        from mcp_servers.k8s_mcp.utils import get_mock_events

        warnings = get_mock_events(event_type="Warning")
        assert all(e["type"] == "Warning" for e in warnings)
        assert len(warnings) >= 1

        normals = get_mock_events(event_type="Normal")
        assert all(e["type"] == "Normal" for e in normals)
