"""Tests for k8s_mcp server tools.

All tests mock the Kubernetes client via ``get_clients`` so they can run
without a real cluster.  Two paths are tested for every tool:

1. **Happy path** -- ``get_clients`` returns mock API objects that
   simulate real Kubernetes responses.
2. **Unavailable path** -- ``get_clients`` raises ``K8sUnavailableError``
   and the tool returns a structured JSON error.

Input-validation tests exercise the Pydantic models directly.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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
from mcp_servers.k8s_mcp.utils import K8sUnavailableError

# ---------------------------------------------------------------------------
# Patch targets -- patch where get_clients is USED, not where defined
# ---------------------------------------------------------------------------

_PODS_GC = "mcp_servers.k8s_mcp.tools.pods.get_clients"
_DEPLOYS_GC = "mcp_servers.k8s_mcp.tools.deployments.get_clients"
_SERVICES_GC = "mcp_servers.k8s_mcp.tools.services.get_clients"
_LOGS_GC = "mcp_servers.k8s_mcp.tools.logs.get_clients"


# ---------------------------------------------------------------------------
# Helpers -- build realistic MagicMock K8s objects
# ---------------------------------------------------------------------------


def _mock_pod(
    name: str = "test-pod-abc123",
    namespace: str = "default",
    phase: str = "Running",
    pod_ip: str = "10.0.0.1",
    node: str = "node-1",
    labels: dict | None = None,
) -> MagicMock:
    """Create a realistic V1Pod MagicMock."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = namespace
    pod.metadata.labels = labels or {"app": "test"}
    pod.status.phase = phase
    pod.status.pod_ip = pod_ip
    pod.status.start_time = "2026-03-22T07:00:00Z"
    pod.status.conditions = []
    pod.spec.node_name = node

    # Container status
    cs = MagicMock()
    cs.name = "main"
    cs.image = "test-image:latest"
    cs.ready = True
    cs.restart_count = 0
    cs.state.running.started_at = "2026-03-22T07:00:00Z"
    cs.state.waiting = None
    cs.state.terminated = None
    pod.status.container_statuses = [cs]
    return pod


def _mock_deployment(
    name: str = "test-deploy",
    namespace: str = "default",
    replicas: int = 3,
    labels: dict | None = None,
) -> MagicMock:
    """Create a realistic V1Deployment MagicMock."""
    deploy = MagicMock()
    deploy.metadata.name = name
    deploy.metadata.namespace = namespace
    deploy.metadata.labels = labels or {"app": "test"}
    deploy.spec.replicas = replicas
    deploy.spec.strategy.type = "RollingUpdate"
    deploy.status.ready_replicas = replicas
    deploy.status.available_replicas = replicas
    deploy.status.updated_replicas = replicas
    deploy.status.conditions = []
    return deploy


def _mock_service(
    name: str = "test-svc",
    namespace: str = "default",
    svc_type: str = "ClusterIP",
    cluster_ip: str = "10.96.0.1",
) -> MagicMock:
    """Create a realistic V1Service MagicMock."""
    svc = MagicMock()
    svc.metadata.name = name
    svc.metadata.namespace = namespace
    svc.spec.type = svc_type
    svc.spec.cluster_ip = cluster_ip
    svc.spec.selector = {"app": "test"}

    port = MagicMock()
    port.port = 80
    port.target_port = 8080
    port.protocol = "TCP"
    port.name = "http"
    port.node_port = None
    svc.spec.ports = [port]

    svc.status.load_balancer.ingress = None
    return svc


# ===========================================================================
# Pod Tools
# ===========================================================================


class TestK8sListPods:
    """Tests for k8s_list_pods tool."""

    @pytest.mark.asyncio
    async def test_list_pods_happy_path(self) -> None:
        """Should list pods from the mock K8s API."""
        mock_v1 = MagicMock()
        mock_v1.list_namespaced_pod.return_value.items = [
            _mock_pod("web-0", labels={"app": "web"}),
            _mock_pod("db-0", labels={"app": "db"}),
        ]
        with patch(_PODS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

            result_str = await k8s_list_pods(K8sListPodsInput())
            result = json.loads(result_str)

        assert result["namespace"] == "default"
        assert result["pod_count"] == 2
        names = [p["name"] for p in result["pods"]]
        assert "web-0" in names
        assert "db-0" in names

    @pytest.mark.asyncio
    async def test_list_pods_with_label_selector(self) -> None:
        """Should pass label_selector to the K8s API."""
        mock_v1 = MagicMock()
        mock_v1.list_namespaced_pod.return_value.items = [
            _mock_pod("web-0", labels={"app": "web"}),
        ]
        with patch(_PODS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

            params = K8sListPodsInput(label_selector="app=web")
            result_str = await k8s_list_pods(params)
            result = json.loads(result_str)

        assert result["pod_count"] == 1
        mock_v1.list_namespaced_pod.assert_called_once()
        call_kwargs = mock_v1.list_namespaced_pod.call_args
        assert call_kwargs.kwargs.get("label_selector") == "app=web"

    @pytest.mark.asyncio
    async def test_list_pods_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _PODS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

            result_str = await k8s_list_pods(K8sListPodsInput())
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"
        assert "hint" in result

    @pytest.mark.asyncio
    async def test_list_pods_api_error(self) -> None:
        """Should return error JSON when K8s API call fails."""
        mock_v1 = MagicMock()
        mock_v1.list_namespaced_pod.side_effect = RuntimeError(
            "connection refused"
        )
        with patch(_PODS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

            result_str = await k8s_list_pods(K8sListPodsInput())
            result = json.loads(result_str)

        assert "error" in result
        assert "connection refused" in result["error"]

    def test_list_pods_input_validation_limit_zero(self) -> None:
        """Should reject limit < 1."""
        with pytest.raises(ValidationError):
            K8sListPodsInput(limit=0)

    def test_list_pods_input_validation_limit_too_high(self) -> None:
        """Should reject limit > 200."""
        with pytest.raises(ValidationError):
            K8sListPodsInput(limit=201)


class TestK8sDescribePod:
    """Tests for k8s_describe_pod tool."""

    @pytest.mark.asyncio
    async def test_describe_pod_happy_path(self) -> None:
        """Should return Markdown detail for an existing pod."""
        mock_v1 = MagicMock()
        pod = _mock_pod("ollama-server-0")
        # Add a condition
        cond = MagicMock()
        cond.type = "Ready"
        cond.status = "True"
        cond.reason = ""
        cond.message = ""
        cond.last_transition_time = "2026-03-22T07:00:00Z"
        pod.status.conditions = [cond]
        mock_v1.read_namespaced_pod.return_value = pod

        # Events
        ev = MagicMock()
        ev.type = "Normal"
        ev.reason = "Scheduled"
        ev.message = "Successfully assigned"
        ev.count = 1
        ev.first_timestamp = "2026-03-22T07:00:00Z"
        ev.last_timestamp = "2026-03-22T07:00:00Z"
        mock_v1.list_namespaced_event.return_value.items = [ev]

        with patch(_PODS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.pods import (
                k8s_describe_pod,
            )

            params = K8sDescribePodInput(pod_name="ollama-server-0")
            result_str = await k8s_describe_pod(params)

        assert "# Pod: ollama-server-0" in result_str
        assert "## Containers" in result_str
        assert "## Events" in result_str
        assert "Scheduled" in result_str

    @pytest.mark.asyncio
    async def test_describe_pod_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _PODS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.pods import (
                k8s_describe_pod,
            )

            params = K8sDescribePodInput(pod_name="test-pod")
            result_str = await k8s_describe_pod(params)
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"

    def test_describe_pod_input_validation(self) -> None:
        """Should reject empty pod_name."""
        with pytest.raises(ValidationError):
            K8sDescribePodInput(pod_name="")


class TestK8sExecCommand:
    """Tests for k8s_exec_command tool."""

    @pytest.mark.asyncio
    async def test_exec_command_happy_path(self) -> None:
        """Should return command output from the mock API."""
        mock_v1 = MagicMock()
        with (
            patch(_PODS_GC, return_value=(mock_v1, MagicMock())),
            patch(
                "kubernetes.stream.stream",
                return_value="root\n",
            ),
        ):
            from mcp_servers.k8s_mcp.tools.pods import (
                k8s_exec_command,
            )

            params = K8sExecCommandInput(
                pod_name="test-pod", command=["whoami"]
            )
            result_str = await k8s_exec_command(params)
            result = json.loads(result_str)

        assert result["exit_code"] == 0
        assert "root" in result["output"]

    @pytest.mark.asyncio
    async def test_exec_command_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _PODS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.pods import (
                k8s_exec_command,
            )

            params = K8sExecCommandInput(
                pod_name="test-pod", command=["whoami"]
            )
            result_str = await k8s_exec_command(params)
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"

    def test_exec_input_validation_empty_command(self) -> None:
        """Should reject empty command list."""
        with pytest.raises(ValidationError):
            K8sExecCommandInput(pod_name="test-pod", command=[])


# ===========================================================================
# Deployment Tools
# ===========================================================================


class TestK8sListDeployments:
    """Tests for k8s_list_deployments tool."""

    @pytest.mark.asyncio
    async def test_list_deployments_happy_path(self) -> None:
        """Should list deployments from the mock K8s API."""
        mock_apps = MagicMock()
        mock_apps.list_namespaced_deployment.return_value.items = [
            _mock_deployment("nginx", replicas=3),
            _mock_deployment("redis", replicas=1),
        ]
        with patch(
            _DEPLOYS_GC,
            return_value=(MagicMock(), mock_apps),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_list_deployments,
            )

            result_str = await k8s_list_deployments(
                K8sListDeploymentsInput()
            )
            result = json.loads(result_str)

        assert result["namespace"] == "default"
        assert result["deployment_count"] == 2
        names = [d["name"] for d in result["deployments"]]
        assert "nginx" in names
        assert "redis" in names
        # Check replica fields
        for d in result["deployments"]:
            assert "replicas" in d
            assert "ready_replicas" in d
            assert "available_replicas" in d

    @pytest.mark.asyncio
    async def test_list_deployments_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _DEPLOYS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_list_deployments,
            )

            result_str = await k8s_list_deployments(
                K8sListDeploymentsInput()
            )
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"

    @pytest.mark.asyncio
    async def test_list_deployments_with_label_selector(
        self,
    ) -> None:
        """Should pass label_selector to the K8s API."""
        mock_apps = MagicMock()
        mock_apps.list_namespaced_deployment.return_value.items = [
            _mock_deployment("nginx", labels={"app": "nginx"}),
        ]
        with patch(
            _DEPLOYS_GC,
            return_value=(MagicMock(), mock_apps),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_list_deployments,
            )

            params = K8sListDeploymentsInput(
                label_selector="app=nginx"
            )
            result_str = await k8s_list_deployments(params)
            result = json.loads(result_str)

        assert result["deployment_count"] == 1
        call_kwargs = (
            mock_apps.list_namespaced_deployment.call_args
        )
        assert (
            call_kwargs.kwargs.get("label_selector") == "app=nginx"
        )


class TestK8sScaleDeployment:
    """Tests for k8s_scale_deployment tool."""

    @pytest.mark.asyncio
    async def test_scale_deployment_happy_path(self) -> None:
        """Should scale a deployment to the specified replicas."""
        mock_apps = MagicMock()
        current = _mock_deployment("nginx", replicas=1)
        mock_apps.read_namespaced_deployment.return_value = current

        with patch(
            _DEPLOYS_GC,
            return_value=(MagicMock(), mock_apps),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_scale_deployment,
            )

            params = K8sScaleDeploymentInput(
                deployment_name="nginx", replicas=5
            )
            result_str = await k8s_scale_deployment(params)
            result = json.loads(result_str)

        assert result["action"] == "scale"
        assert result["deployment"] == "nginx"
        assert result["previous_replicas"] == 1
        assert result["new_replicas"] == 5
        assert result["status"] == "scaled"
        mock_apps.patch_namespaced_deployment_scale.assert_called_once()

    @pytest.mark.asyncio
    async def test_scale_deployment_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _DEPLOYS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_scale_deployment,
            )

            params = K8sScaleDeploymentInput(
                deployment_name="nginx", replicas=3
            )
            result_str = await k8s_scale_deployment(params)
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"

    def test_scale_input_validation_too_high(self) -> None:
        """Should reject replicas > 100."""
        with pytest.raises(ValidationError):
            K8sScaleDeploymentInput(
                deployment_name="nginx", replicas=101
            )

    def test_scale_input_validation_negative(self) -> None:
        """Should reject replicas < 0."""
        with pytest.raises(ValidationError):
            K8sScaleDeploymentInput(
                deployment_name="nginx", replicas=-1
            )


class TestK8sRestartDeployment:
    """Tests for k8s_restart_deployment tool."""

    @pytest.mark.asyncio
    async def test_restart_deployment_happy_path(self) -> None:
        """Should trigger a rolling restart."""
        mock_apps = MagicMock()
        with patch(
            _DEPLOYS_GC,
            return_value=(MagicMock(), mock_apps),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_restart_deployment,
            )

            params = K8sRestartDeploymentInput(
                deployment_name="nginx"
            )
            result_str = await k8s_restart_deployment(params)
            result = json.loads(result_str)

        assert result["action"] == "rolling_restart"
        assert result["deployment"] == "nginx"
        assert result["status"] == "restarting"
        assert "restart_triggered_at" in result
        mock_apps.patch_namespaced_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_deployment_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _DEPLOYS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.deployments import (
                k8s_restart_deployment,
            )

            params = K8sRestartDeploymentInput(
                deployment_name="nginx"
            )
            result_str = await k8s_restart_deployment(params)
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"


# ===========================================================================
# Service Tools
# ===========================================================================


class TestK8sListServices:
    """Tests for k8s_list_services tool."""

    @pytest.mark.asyncio
    async def test_list_services_happy_path(self) -> None:
        """Should list services from the mock K8s API."""
        mock_v1 = MagicMock()
        mock_v1.list_namespaced_service.return_value.items = [
            _mock_service("kubernetes", svc_type="ClusterIP"),
            _mock_service(
                "web-svc",
                svc_type="LoadBalancer",
                cluster_ip="10.96.10.1",
            ),
        ]
        with patch(
            _SERVICES_GC, return_value=(mock_v1, MagicMock())
        ):
            from mcp_servers.k8s_mcp.tools.services import (
                k8s_list_services,
            )

            result_str = await k8s_list_services(
                K8sListServicesInput()
            )
            result = json.loads(result_str)

        assert result["namespace"] == "default"
        assert result["service_count"] == 2
        names = [s["name"] for s in result["services"]]
        assert "kubernetes" in names
        assert "web-svc" in names
        for svc in result["services"]:
            assert "ports" in svc
            assert "type" in svc
            assert "cluster_ip" in svc

    @pytest.mark.asyncio
    async def test_list_services_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _SERVICES_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.services import (
                k8s_list_services,
            )

            result_str = await k8s_list_services(
                K8sListServicesInput()
            )
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"

    @pytest.mark.asyncio
    async def test_list_services_api_error(self) -> None:
        """Should return error JSON when K8s API call fails."""
        mock_v1 = MagicMock()
        mock_v1.list_namespaced_service.side_effect = RuntimeError(
            "timeout"
        )
        with patch(
            _SERVICES_GC, return_value=(mock_v1, MagicMock())
        ):
            from mcp_servers.k8s_mcp.tools.services import (
                k8s_list_services,
            )

            result_str = await k8s_list_services(
                K8sListServicesInput()
            )
            result = json.loads(result_str)

        assert "error" in result
        assert "timeout" in result["error"]


# ===========================================================================
# Log Tools
# ===========================================================================


class TestK8sGetPodLogs:
    """Tests for k8s_get_pod_logs tool."""

    @pytest.mark.asyncio
    async def test_get_pod_logs_happy_path(self) -> None:
        """Should return log text from the mock K8s API."""
        mock_v1 = MagicMock()
        mock_v1.read_namespaced_pod_log.return_value = (
            "line1\nline2\nline3"
        )
        with patch(_LOGS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.logs import (
                k8s_get_pod_logs,
            )

            params = K8sGetPodLogsInput(pod_name="test-pod")
            result_str = await k8s_get_pod_logs(params)
            result = json.loads(result_str)

        assert result["pod"] == "test-pod"
        assert result["log_lines"] == 3
        assert "line1" in result["logs"]

    @pytest.mark.asyncio
    async def test_get_pod_logs_with_params(self) -> None:
        """Should pass tail_lines and since_seconds to the API."""
        mock_v1 = MagicMock()
        mock_v1.read_namespaced_pod_log.return_value = "log output"
        with patch(_LOGS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.logs import (
                k8s_get_pod_logs,
            )

            params = K8sGetPodLogsInput(
                pod_name="test-pod",
                container="main",
                tail_lines=50,
                since_seconds=3600,
            )
            result_str = await k8s_get_pod_logs(params)
            result = json.loads(result_str)

        assert result["tail_lines"] == 50
        assert result["since_seconds"] == 3600
        assert result["container"] == "main"

        call_kwargs = mock_v1.read_namespaced_pod_log.call_args
        assert call_kwargs.kwargs["tail_lines"] == 50
        assert call_kwargs.kwargs["since_seconds"] == 3600
        assert call_kwargs.kwargs["container"] == "main"

    @pytest.mark.asyncio
    async def test_get_pod_logs_unavailable(self) -> None:
        """Should return error JSON when K8s is unavailable."""
        with patch(
            _LOGS_GC,
            side_effect=K8sUnavailableError("no cluster"),
        ):
            from mcp_servers.k8s_mcp.tools.logs import (
                k8s_get_pod_logs,
            )

            params = K8sGetPodLogsInput(pod_name="test-pod")
            result_str = await k8s_get_pod_logs(params)
            result = json.loads(result_str)

        assert result["error"] == "Kubernetes not available"

    @pytest.mark.asyncio
    async def test_get_pod_logs_empty(self) -> None:
        """Should handle empty log output gracefully."""
        mock_v1 = MagicMock()
        mock_v1.read_namespaced_pod_log.return_value = ""
        with patch(_LOGS_GC, return_value=(mock_v1, MagicMock())):
            from mcp_servers.k8s_mcp.tools.logs import (
                k8s_get_pod_logs,
            )

            params = K8sGetPodLogsInput(pod_name="test-pod")
            result_str = await k8s_get_pod_logs(params)
            result = json.loads(result_str)

        assert result["log_lines"] == 0
        assert result["logs"] == ""

    def test_get_logs_input_validation_tail_zero(self) -> None:
        """Should reject tail_lines < 1."""
        with pytest.raises(ValidationError):
            K8sGetPodLogsInput(pod_name="test", tail_lines=0)

    def test_get_logs_input_validation_tail_too_high(self) -> None:
        """Should reject tail_lines > 5000."""
        with pytest.raises(ValidationError):
            K8sGetPodLogsInput(pod_name="test", tail_lines=5001)


# ===========================================================================
# Utils tests
# ===========================================================================


class TestGetClients:
    """Tests for get_clients utility function."""

    def test_raises_when_k8s_unavailable(self) -> None:
        """Should raise K8sUnavailableError when no config found."""
        from mcp_servers.k8s_mcp.utils import get_clients

        get_clients.cache_clear()

        with (
            patch(
                "mcp_servers.k8s_mcp.utils.get_clients",
                side_effect=K8sUnavailableError("test error"),
            ),
            pytest.raises(
                K8sUnavailableError, match="test error"
            ),
        ):
            from mcp_servers.k8s_mcp.utils import get_clients

            get_clients()
