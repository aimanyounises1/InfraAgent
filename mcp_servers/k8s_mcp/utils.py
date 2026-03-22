"""Kubernetes client helpers -- handles in-cluster and local kubeconfig.

When INFRA_AGENT_MOCK_K8S=true, provides realistic simulated Kubernetes data
reflecting a local development environment on a MacBook Pro M4 Max.
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime
from typing import Any

from kubernetes import client
from kubernetes import config as k8s_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Real K8s client helpers
# ---------------------------------------------------------------------------


def load_k8s_clients() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    """Load kubeconfig and return (CoreV1Api, AppsV1Api).

    Tries in-cluster config first, falls back to local kubeconfig.
    """
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()

    return client.CoreV1Api(), client.AppsV1Api()


# Module-level clients (lazy-initialised in tool modules)
v1: client.CoreV1Api | None = None
apps_v1: client.AppsV1Api | None = None


def get_clients() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    """Get or create cached K8s API clients."""
    global v1, apps_v1
    if v1 is None or apps_v1 is None:
        v1, apps_v1 = load_k8s_clients()
    return v1, apps_v1


# ---------------------------------------------------------------------------
# Mock Data -- Pods (local dev environment on MacBook Pro M4 Max)
# ---------------------------------------------------------------------------

MOCK_PODS: list[dict[str, Any]] = [
    {
        "name": "ollama-server-0",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.0.10",
        "node": "macbook-m4-max",
        "labels": {"app": "ollama", "tier": "inference"},
        "containers": [
            {
                "name": "ollama",
                "image": "ollama/ollama:0.6.2",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T07:00:00Z",
            }
        ],
        "start_time": "2026-03-21T07:00:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "infra-agent-api-7b9d4f6c8a-xk2p1",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.0.11",
        "node": "macbook-m4-max",
        "labels": {"app": "infra-agent-api", "tier": "backend"},
        "containers": [
            {
                "name": "api",
                "image": "infra-agent/api:latest",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T07:05:00Z",
            }
        ],
        "start_time": "2026-03-21T07:05:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "vite-dashboard-5c8e3a7d9b-mv4n8",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.0.12",
        "node": "macbook-m4-max",
        "labels": {"app": "dashboard", "tier": "frontend"},
        "containers": [
            {
                "name": "dashboard",
                "image": "infra-agent/dashboard:latest",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T07:10:00Z",
            }
        ],
        "start_time": "2026-03-21T07:10:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "redis-cache-0",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.0.13",
        "node": "macbook-m4-max",
        "labels": {"app": "redis", "tier": "cache"},
        "containers": [
            {
                "name": "redis",
                "image": "redis:7.2-alpine",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T06:55:00Z",
            }
        ],
        "start_time": "2026-03-21T06:55:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "langgraph-worker-3f7a2b8c1d-qz9w5",
        "namespace": "default",
        "status": "CrashLoopBackOff",
        "pod_ip": "10.244.0.14",
        "node": "macbook-m4-max",
        "labels": {"app": "langgraph-worker", "tier": "backend"},
        "containers": [
            {
                "name": "worker",
                "image": "infra-agent/langgraph-worker:latest",
                "ready": False,
                "restart_count": 3,
                "state": "waiting",
                "reason": "CrashLoopBackOff",
                "started_at": "2026-03-22T01:00:00Z",
            }
        ],
        "start_time": "2026-03-22T01:00:00Z",
        "conditions": [
            {"type": "Ready", "status": "False"},
            {"type": "ContainersReady", "status": "False"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Deployments
# ---------------------------------------------------------------------------

MOCK_DEPLOYMENTS: list[dict[str, Any]] = [
    {
        "name": "ollama-deployment",
        "namespace": "default",
        "replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "labels": {"app": "ollama"},
        "strategy": "Recreate",
        "conditions": [
            {
                "type": "Available",
                "status": "True",
                "reason": "MinimumReplicasAvailable",
                "message": "Deployment has minimum availability.",
            },
        ],
        "image": "ollama/ollama:0.6.2",
        "created_at": "2026-03-18T10:00:00Z",
    },
    {
        "name": "infra-agent-api",
        "namespace": "default",
        "replicas": 2,
        "ready_replicas": 2,
        "available_replicas": 2,
        "updated_replicas": 2,
        "labels": {"app": "infra-agent-api"},
        "strategy": "RollingUpdate",
        "conditions": [
            {
                "type": "Available",
                "status": "True",
                "reason": "MinimumReplicasAvailable",
                "message": "Deployment has minimum availability.",
            },
            {
                "type": "Progressing",
                "status": "True",
                "reason": "NewReplicaSetAvailable",
                "message": "ReplicaSet has successfully progressed.",
            },
        ],
        "image": "infra-agent/api:latest",
        "created_at": "2026-03-19T14:00:00Z",
    },
    {
        "name": "dashboard-frontend",
        "namespace": "default",
        "replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "labels": {"app": "dashboard"},
        "strategy": "RollingUpdate",
        "conditions": [
            {
                "type": "Available",
                "status": "True",
                "reason": "MinimumReplicasAvailable",
                "message": "Deployment has minimum availability.",
            },
        ],
        "image": "infra-agent/dashboard:latest",
        "created_at": "2026-03-19T14:30:00Z",
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Services
# ---------------------------------------------------------------------------

MOCK_SERVICES: list[dict[str, Any]] = [
    {
        "name": "kubernetes",
        "namespace": "default",
        "type": "ClusterIP",
        "cluster_ip": "10.96.0.1",
        "ports": [{"port": 443, "target_port": 6443, "protocol": "TCP"}],
        "selector": None,
    },
    {
        "name": "ollama-svc",
        "namespace": "default",
        "type": "ClusterIP",
        "cluster_ip": "10.96.10.50",
        "ports": [
            {"port": 11434, "target_port": 11434, "protocol": "TCP"},
        ],
        "selector": {"app": "ollama"},
    },
    {
        "name": "infra-agent-api-svc",
        "namespace": "default",
        "type": "NodePort",
        "cluster_ip": "10.96.20.100",
        "ports": [
            {
                "name": "http",
                "port": 8000,
                "target_port": 8000,
                "node_port": 30080,
                "protocol": "TCP",
            }
        ],
        "selector": {"app": "infra-agent-api"},
    },
    {
        "name": "dashboard-svc",
        "namespace": "default",
        "type": "LoadBalancer",
        "cluster_ip": "10.96.30.150",
        "external_ip": "127.0.0.1",
        "ports": [
            {"name": "http", "port": 3000, "target_port": 3000, "protocol": "TCP"},
        ],
        "selector": {"app": "dashboard"},
    },
    {
        "name": "redis-svc",
        "namespace": "default",
        "type": "ClusterIP",
        "cluster_ip": "10.96.45.200",
        "ports": [{"port": 6379, "target_port": 6379, "protocol": "TCP"}],
        "selector": {"app": "redis"},
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Nodes (single MacBook Pro M4 Max)
# ---------------------------------------------------------------------------

MOCK_NODES: list[dict[str, Any]] = [
    {
        "name": "macbook-m4-max",
        "status": "Ready",
        "roles": ["control-plane", "worker"],
        "cpu_capacity": "16",
        "memory_capacity": "64Gi",
        "cpu_allocatable": "15500m",
        "memory_allocatable": "62Gi",
        "os_image": "macOS 26.3.0 (Tahoe)",
        "kubelet_version": "v1.31.0",
        "architecture": "arm64",
        "container_runtime": "containerd://1.7.14",
        "disk_capacity": "1Ti",
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Events
# ---------------------------------------------------------------------------

MOCK_EVENTS: list[dict[str, Any]] = [
    {
        "type": "Normal",
        "reason": "Scheduled",
        "object": "Pod/ollama-server-0",
        "message": (
            "Successfully assigned default/ollama-server-0 to macbook-m4-max"
        ),
        "first_seen": "2026-03-21T07:00:00Z",
        "last_seen": "2026-03-21T07:00:00Z",
        "count": 1,
        "namespace": "default",
    },
    {
        "type": "Normal",
        "reason": "Pulled",
        "object": "Pod/ollama-server-0",
        "message": "Container image 'ollama/ollama:0.6.2' already present on machine",
        "first_seen": "2026-03-21T07:00:01Z",
        "last_seen": "2026-03-21T07:00:01Z",
        "count": 1,
        "namespace": "default",
    },
    {
        "type": "Normal",
        "reason": "Started",
        "object": "Pod/ollama-server-0",
        "message": "Started container ollama",
        "first_seen": "2026-03-21T07:00:02Z",
        "last_seen": "2026-03-21T07:00:02Z",
        "count": 1,
        "namespace": "default",
    },
    {
        "type": "Warning",
        "reason": "BackOff",
        "object": "Pod/langgraph-worker-3f7a2b8c1d-qz9w5",
        "message": (
            "Back-off restarting failed container worker "
            "in pod langgraph-worker-3f7a2b8c1d-qz9w5"
        ),
        "first_seen": "2026-03-22T01:05:00Z",
        "last_seen": "2026-03-22T06:30:00Z",
        "count": 12,
        "namespace": "default",
    },
    {
        "type": "Warning",
        "reason": "Unhealthy",
        "object": "Pod/langgraph-worker-3f7a2b8c1d-qz9w5",
        "message": "Liveness probe failed: connection refused",
        "first_seen": "2026-03-22T01:02:00Z",
        "last_seen": "2026-03-22T06:28:00Z",
        "count": 9,
        "namespace": "default",
    },
    {
        "type": "Normal",
        "reason": "ScalingReplicaSet",
        "object": "Deployment/infra-agent-api",
        "message": (
            "Scaled up replica set infra-agent-api-7b9d4f6c8a to 2"
        ),
        "first_seen": "2026-03-19T14:00:00Z",
        "last_seen": "2026-03-19T14:00:00Z",
        "count": 1,
        "namespace": "default",
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Pod Logs
# ---------------------------------------------------------------------------

_MOCK_LOG_LINES: dict[str, list[str]] = {
    "ollama": [
        "time=2026-03-22T08:00:00Z level=INFO msg=\"Listening on 0.0.0.0:11434\"",
        "time=2026-03-22T08:00:01Z level=INFO msg=\"Loading model qwen2.5-coder:14b\"",
        "time=2026-03-22T08:00:05Z level=INFO msg=\"Model loaded in 4.2s\"",
        "time=2026-03-22T08:15:00Z level=INFO msg=\"Inference request\" model=qwen2.5-coder:14b",
        "time=2026-03-22T08:15:02Z level=INFO msg=\"Generation complete\" tokens=342 time=1.8s",
        "time=2026-03-22T08:15:10Z level=INFO msg=\"Health check OK\"",
        "time=2026-03-22T08:15:30Z level=INFO msg=\"Inference request\" model=qwen2.5-coder:14b",
    ],
    "infra-agent-api": [
        "2026-03-22 08:05:00 INFO  [uvicorn] Application startup complete",
        "2026-03-22 08:05:01 INFO  [main] Connected to Redis at redis-svc:6379",
        "2026-03-22 08:05:01 INFO  [main] MCP servers registered: k8s, gpu, incident",
        "2026-03-22 08:05:02 INFO  [main] LangGraph agent initialised (ollama backend)",
        "2026-03-22 08:15:10 INFO  [http] GET /healthz 200 1ms",
        "2026-03-22 08:15:15 INFO  [http] POST /api/chat 200 1842ms",
        "2026-03-22 08:15:20 INFO  [http] GET /api/gpu/status 200 45ms",
        "2026-03-22 08:15:25 INFO  [http] GET /api/k8s/pods 200 12ms",
    ],
    "dashboard": [
        "  VITE v6.2.0  ready in 320 ms",
        "",
        "  -> Local:   http://localhost:3000/",
        "  -> Network: http://10.244.0.12:3000/",
        "",
        "08:10:05 [vite] page reload src/App.tsx",
        "08:15:00 [vite] hmr update /src/components/GpuPanel.tsx",
    ],
    "redis": [
        "1:C 22 Mar 2026 06:55:00.000 # oO0OoO0OoO0Oo Redis is starting oO0OoO0OoO0Oo",
        "1:C 22 Mar 2026 06:55:00.001 # Redis version=7.2.4, bits=64, commit=00000000",
        "1:M 22 Mar 2026 06:55:00.002 * Running mode=standalone, port=6379.",
        "1:M 22 Mar 2026 06:55:00.003 # Server initialized",
        "1:M 22 Mar 2026 06:55:00.004 * Ready to accept connections tcp",
        "1:M 22 Mar 2026 08:15:00.000 * 1 changes in 900 seconds. Saving...",
        "1:M 22 Mar 2026 08:15:00.050 * Background saving started by pid 42",
        "42:C 22 Mar 2026 08:15:00.100 * DB saved on disk",
        "1:M 22 Mar 2026 08:15:00.150 * Background saving terminated with success",
    ],
    "langgraph-worker": [
        "2026-03-22 01:00:00 INFO  Starting LangGraph worker process...",
        "2026-03-22 01:00:01 INFO  Connecting to Redis at redis-svc:6379...",
        "2026-03-22 01:00:02 ERROR Failed to initialise LangGraph checkpoint store",
        "2026-03-22 01:00:02 ERROR RuntimeError: Missing INFRA_AGENT_LLM_PROVIDER config",
        "2026-03-22 01:00:02 FATAL Unrecoverable error, shutting down",
        "2026-03-22 01:00:03 INFO  Worker process exited with code 1",
    ],
}


# ---------------------------------------------------------------------------
# Mock data generator functions
# ---------------------------------------------------------------------------


def get_mock_pods(
    namespace: str = "default",
    label_selector: str | None = None,
) -> list[dict[str, Any]]:
    """Return mock pod data filtered by namespace and optional label selector.

    Args:
        namespace: Kubernetes namespace to filter by.
        label_selector: Optional label selector string (e.g., 'app=ollama').

    Returns:
        List of pod dictionaries matching the filter criteria.
    """
    filtered = [p for p in MOCK_PODS if p["namespace"] == namespace]

    if label_selector:
        # Parse simple key=value selectors
        for selector_part in label_selector.split(","):
            selector_part = selector_part.strip()
            if "=" in selector_part:
                key, value = selector_part.split("=", 1)
                key = key.strip()
                value = value.strip()
                filtered = [
                    p
                    for p in filtered
                    if p.get("labels", {}).get(key) == value
                ]

    return filtered


def get_mock_deployments(
    namespace: str = "default",
    label_selector: str | None = None,
) -> list[dict[str, Any]]:
    """Return mock deployment data filtered by namespace.

    Args:
        namespace: Kubernetes namespace to filter by.
        label_selector: Optional label selector string.

    Returns:
        List of deployment dictionaries matching the filter criteria.
    """
    filtered = [d for d in MOCK_DEPLOYMENTS if d["namespace"] == namespace]

    if label_selector:
        for selector_part in label_selector.split(","):
            selector_part = selector_part.strip()
            if "=" in selector_part:
                key, value = selector_part.split("=", 1)
                key = key.strip()
                value = value.strip()
                filtered = [
                    d
                    for d in filtered
                    if d.get("labels", {}).get(key) == value
                ]

    return filtered


def get_mock_services(namespace: str = "default") -> list[dict[str, Any]]:
    """Return mock service data filtered by namespace.

    Args:
        namespace: Kubernetes namespace to filter by.

    Returns:
        List of service dictionaries matching the namespace.
    """
    return [s for s in MOCK_SERVICES if s["namespace"] == namespace]


def get_mock_pod_detail(
    name: str,
    namespace: str = "default",
) -> dict[str, Any] | None:
    """Return detailed mock pod information including events.

    Args:
        name: Pod name to look up.
        namespace: Kubernetes namespace.

    Returns:
        Detailed pod dictionary with events, or None if not found.
    """
    for pod in MOCK_PODS:
        if pod["name"] == name and pod["namespace"] == namespace:
            # Enrich with relevant events
            pod_events = [
                e
                for e in MOCK_EVENTS
                if name in e.get("object", "") and e["namespace"] == namespace
            ]
            return {**pod, "events": pod_events}

    return None


def get_mock_pod_logs(
    name: str,
    tail_lines: int = 100,
    since_seconds: int | None = None,
) -> str:
    """Return mock log output for a pod.

    Matches the pod name against known log templates. Adds slight
    variation to simulate real log output.

    Args:
        name: Pod name.
        tail_lines: Number of trailing lines to return.
        since_seconds: Ignored in mock mode (included for API compatibility).

    Returns:
        Multi-line log string.
    """
    _ = since_seconds  # Unused in mock mode, kept for API parity

    # Match pod name to a log template
    for key, lines in _MOCK_LOG_LINES.items():
        if key in name.lower():
            selected = lines[-tail_lines:]
            return "\n".join(selected)

    # Fallback generic logs
    fallback_lines = [
        f"2026-03-22 08:15:{i:02d} INFO  Heartbeat check OK "
        f"(seq={random.randint(1000, 9999)})"
        for i in range(min(tail_lines, 10))
    ]
    return "\n".join(fallback_lines)


def get_mock_events(
    namespace: str | None = None,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return mock events filtered by namespace and type.

    Args:
        namespace: Filter events by namespace (all namespaces if None).
        event_type: Filter by event type ('Normal' or 'Warning').

    Returns:
        List of event dictionaries.
    """
    filtered = list(MOCK_EVENTS)

    if namespace is not None:
        filtered = [e for e in filtered if e["namespace"] == namespace]

    if event_type is not None:
        filtered = [e for e in filtered if e["type"] == event_type]

    return filtered


def get_mock_exec_output(command: list[str]) -> str:
    """Return mock command execution output.

    Provides realistic output for common diagnostic commands.

    Args:
        command: Command and its arguments as a list.

    Returns:
        Simulated command output string.
    """
    if not command:
        return ""

    cmd = command[0]
    now_str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    if cmd in ("ls", "ls -la", "ls -l"):
        return (
            "total 32\n"
            "drwxr-xr-x 1 root root 4096 Mar 21 08:00 .\n"
            "drwxr-xr-x 1 root root 4096 Mar 21 08:00 ..\n"
            "-rw-r--r-- 1 root root 1024 Mar 21 08:00 app.conf\n"
            "drwxr-xr-x 2 root root 4096 Mar 21 08:00 logs\n"
            "-rwxr-xr-x 1 root root 8192 Mar 21 08:00 entrypoint.sh\n"
        )

    if cmd == "cat" and len(command) > 1:
        return (
            f"# Configuration file\n# Generated at {now_str}\n"
            "workers=4\ntimeout=30\n"
        )

    if cmd == "whoami":
        return "root\n"

    if cmd == "hostname":
        return "infra-agent-api-7b9d4f6c8a-xk2p1\n"

    if cmd == "date":
        return f"{now_str}\n"

    if cmd == "env":
        return (
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
            "HOSTNAME=infra-agent-api-7b9d4f6c8a-xk2p1\n"
            "KUBERNETES_SERVICE_HOST=10.96.0.1\n"
            "KUBERNETES_SERVICE_PORT=443\n"
            "HOME=/root\n"
        )

    if cmd in ("ps", "ps aux"):
        return (
            "PID   USER     TIME  COMMAND\n"
            "    1 root      0:00 /entrypoint.sh\n"
            "   12 root      0:05 uvicorn api.main:app --host 0.0.0.0\n"
            "   13 root      0:12 python -m mcp_servers.gpu_mcp.server\n"
            "   14 root      0:11 python -m mcp_servers.k8s_mcp.server\n"
        )

    # Generic fallback
    full_cmd = " ".join(command)
    return f"$ {full_cmd}\n(mock output for command: {full_cmd})\n"
