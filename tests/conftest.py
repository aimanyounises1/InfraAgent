"""Shared pytest fixtures and mock configurations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# LLM Analysis Mock (autouse -- prevents real Ollama calls in tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_llm_analysis():
    """Disable LLM analysis in all tests to avoid hitting real Ollama.

    The LLM analysis is an optional enhancement that runs after keyword-based
    tool dispatch. In tests we mock MCP tools, so the LLM analysis would
    either time out or produce irrelevant results. This fixture patches
    ``generate_llm_analysis`` to always return None, keeping tests fast and
    deterministic.
    """
    with patch(
        "agents.llm_analysis.generate_llm_analysis",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


# ---------------------------------------------------------------------------
# Kubernetes Mocks -- patches get_clients() where it is used (in tool modules)
# ---------------------------------------------------------------------------

# Patch targets: must patch where get_clients is USED, not where defined,
# because `from mcp_servers.k8s_mcp.utils import get_clients` creates a
# local name binding that is not affected by patching the utils module.
_K8S_TOOL_MODULES = [
    "mcp_servers.k8s_mcp.tools.pods.get_clients",
    "mcp_servers.k8s_mcp.tools.deployments.get_clients",
    "mcp_servers.k8s_mcp.tools.services.get_clients",
    "mcp_servers.k8s_mcp.tools.logs.get_clients",
]


@pytest.fixture
def mock_k8s_core_v1():
    """Mock kubernetes CoreV1Api via get_clients.

    Returns the mock CoreV1Api instance so tests can configure
    return values on its methods (list_namespaced_pod, etc.).
    """
    mock_v1 = MagicMock()

    # Default: return one healthy pod
    mock_pod = MagicMock()
    mock_pod.metadata.name = "test-pod-abc123"
    mock_pod.metadata.namespace = "default"
    mock_pod.metadata.labels = {"app": "test"}
    mock_pod.status.phase = "Running"
    mock_pod.status.pod_ip = "10.0.0.1"
    mock_pod.status.start_time = "2026-03-22T07:00:00Z"
    mock_pod.status.conditions = []
    mock_pod.status.container_statuses = []
    mock_pod.spec.node_name = "node-1"
    mock_v1.list_namespaced_pod.return_value.items = [mock_pod]

    mock_apps = MagicMock()
    patches = [
        patch(target, return_value=(mock_v1, mock_apps))
        for target in _K8S_TOOL_MODULES
    ]
    for p in patches:
        p.start()
    yield mock_v1
    for p in patches:
        p.stop()


@pytest.fixture
def mock_k8s_apps_v1():
    """Mock kubernetes AppsV1Api via get_clients.

    Returns the mock AppsV1Api instance so tests can configure
    return values on its methods (list_namespaced_deployment, etc.).
    """
    mock_v1 = MagicMock()
    mock_apps = MagicMock()

    mock_deploy = MagicMock()
    mock_deploy.metadata.name = "nginx"
    mock_deploy.metadata.namespace = "default"
    mock_deploy.metadata.labels = {"app": "nginx"}
    mock_deploy.spec.replicas = 3
    mock_deploy.spec.strategy.type = "RollingUpdate"
    mock_deploy.status.ready_replicas = 3
    mock_deploy.status.available_replicas = 3
    mock_deploy.status.updated_replicas = 3
    mock_deploy.status.conditions = []
    mock_apps.list_namespaced_deployment.return_value.items = [
        mock_deploy
    ]

    patches = [
        patch(target, return_value=(mock_v1, mock_apps))
        for target in _K8S_TOOL_MODULES
    ]
    for p in patches:
        p.start()
    yield mock_apps
    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# GPU Mocks (pynvml)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_nvml():
    """Mock pynvml for GPU tests."""
    with patch("mcp_servers.gpu_mcp.tools.monitor.pynvml") as mock:
        mock.nvmlDeviceGetCount.return_value = 2
        handle = MagicMock()
        mock.nvmlDeviceGetHandleByIndex.return_value = handle
        mock.nvmlDeviceGetUtilizationRates.return_value = MagicMock(
            gpu=75, memory=60
        )
        mock.nvmlDeviceGetMemoryInfo.return_value = MagicMock(
            total=80 * 1024**3,
            used=48 * 1024**3,
            free=32 * 1024**3,
        )
        mock.nvmlDeviceGetTemperature.return_value = 62
        mock.nvmlDeviceGetPowerUsage.return_value = 285_000
        mock.nvmlDeviceGetEnforcedPowerLimit.return_value = 400_000
        yield mock


# ---------------------------------------------------------------------------
# HTTP Mocks (for incident_mcp)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for external API calls."""
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        yield mock_client


# ---------------------------------------------------------------------------
# FastAPI Test Client
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """FastAPI TestClient fixture.

    Usage: response = api_client.get("/healthz")
    """
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)
