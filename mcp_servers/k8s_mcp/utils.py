"""Kubernetes client helpers — handles in-cluster and local kubeconfig.

When INFRA_AGENT_MOCK_K8S=true, provides realistic simulated Kubernetes data
so the project can demo without a real cluster.
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
# Mock Data -- Pods
# ---------------------------------------------------------------------------

MOCK_PODS: list[dict[str, Any]] = [
    {
        "name": "nginx-deployment-7c79c4bf97-abc12",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.1.15",
        "node": "node-1",
        "labels": {"app": "nginx", "tier": "frontend"},
        "containers": [
            {
                "name": "nginx",
                "image": "nginx:1.25.3",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T08:00:00Z",
            }
        ],
        "start_time": "2026-03-21T08:00:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "redis-master-0",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.2.22",
        "node": "node-2",
        "labels": {"app": "redis", "role": "master"},
        "containers": [
            {
                "name": "redis",
                "image": "redis:7.2-alpine",
                "ready": True,
                "restart_count": 1,
                "state": "running",
                "started_at": "2026-03-20T12:30:00Z",
            }
        ],
        "start_time": "2026-03-20T12:30:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "api-server-deployment-5d8f9b6c4-def45",
        "namespace": "default",
        "status": "Running",
        "pod_ip": "10.244.1.30",
        "node": "node-1",
        "labels": {"app": "api-server", "tier": "backend"},
        "containers": [
            {
                "name": "api-server",
                "image": "myregistry/api-server:v2.1.0",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T09:15:00Z",
            },
            {
                "name": "sidecar-proxy",
                "image": "envoyproxy/envoy:v1.28.0",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-21T09:15:05Z",
            },
        ],
        "start_time": "2026-03-21T09:15:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
    {
        "name": "worker-batch-job-ghi01",
        "namespace": "default",
        "status": "CrashLoopBackOff",
        "pod_ip": "10.244.3.8",
        "node": "node-3",
        "labels": {"app": "worker", "tier": "backend"},
        "containers": [
            {
                "name": "worker",
                "image": "myregistry/worker:v1.5.2",
                "ready": False,
                "restart_count": 7,
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
    {
        "name": "monitoring-prometheus-0",
        "namespace": "monitoring",
        "status": "Running",
        "pod_ip": "10.244.2.50",
        "node": "node-2",
        "labels": {"app": "prometheus", "tier": "monitoring"},
        "containers": [
            {
                "name": "prometheus",
                "image": "prom/prometheus:v2.51.0",
                "ready": True,
                "restart_count": 0,
                "state": "running",
                "started_at": "2026-03-19T06:00:00Z",
            }
        ],
        "start_time": "2026-03-19T06:00:00Z",
        "conditions": [
            {"type": "Ready", "status": "True"},
            {"type": "ContainersReady", "status": "True"},
            {"type": "PodScheduled", "status": "True"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Deployments
# ---------------------------------------------------------------------------

MOCK_DEPLOYMENTS: list[dict[str, Any]] = [
    {
        "name": "nginx-deployment",
        "namespace": "default",
        "replicas": 3,
        "ready_replicas": 3,
        "available_replicas": 3,
        "updated_replicas": 3,
        "labels": {"app": "nginx"},
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
        "image": "nginx:1.25.3",
        "created_at": "2026-03-15T10:00:00Z",
    },
    {
        "name": "api-server-deployment",
        "namespace": "default",
        "replicas": 2,
        "ready_replicas": 2,
        "available_replicas": 2,
        "updated_replicas": 2,
        "labels": {"app": "api-server"},
        "strategy": "RollingUpdate",
        "conditions": [
            {
                "type": "Available",
                "status": "True",
                "reason": "MinimumReplicasAvailable",
                "message": "Deployment has minimum availability.",
            },
        ],
        "image": "myregistry/api-server:v2.1.0",
        "created_at": "2026-03-18T14:00:00Z",
    },
    {
        "name": "redis-deployment",
        "namespace": "default",
        "replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
        "labels": {"app": "redis"},
        "strategy": "Recreate",
        "conditions": [
            {
                "type": "Available",
                "status": "True",
                "reason": "MinimumReplicasAvailable",
                "message": "Deployment has minimum availability.",
            },
        ],
        "image": "redis:7.2-alpine",
        "created_at": "2026-03-10T08:00:00Z",
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
        "name": "nginx-svc",
        "namespace": "default",
        "type": "LoadBalancer",
        "cluster_ip": "10.96.12.100",
        "external_ip": "203.0.113.50",
        "ports": [
            {"name": "http", "port": 80, "target_port": 80, "protocol": "TCP"},
            {"name": "https", "port": 443, "target_port": 443, "protocol": "TCP"},
        ],
        "selector": {"app": "nginx"},
    },
    {
        "name": "redis-svc",
        "namespace": "default",
        "type": "ClusterIP",
        "cluster_ip": "10.96.45.200",
        "ports": [{"port": 6379, "target_port": 6379, "protocol": "TCP"}],
        "selector": {"app": "redis"},
    },
    {
        "name": "api-svc",
        "namespace": "default",
        "type": "NodePort",
        "cluster_ip": "10.96.78.150",
        "ports": [
            {
                "name": "http",
                "port": 8080,
                "target_port": 8080,
                "node_port": 30080,
                "protocol": "TCP",
            }
        ],
        "selector": {"app": "api-server"},
    },
    {
        "name": "prometheus-svc",
        "namespace": "monitoring",
        "type": "ClusterIP",
        "cluster_ip": "10.96.90.10",
        "ports": [{"port": 9090, "target_port": 9090, "protocol": "TCP"}],
        "selector": {"app": "prometheus"},
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Nodes
# ---------------------------------------------------------------------------

MOCK_NODES: list[dict[str, Any]] = [
    {
        "name": "node-1",
        "status": "Ready",
        "roles": ["control-plane", "worker"],
        "cpu_capacity": "8",
        "memory_capacity": "32Gi",
        "cpu_allocatable": "7500m",
        "memory_allocatable": "30Gi",
        "os_image": "Ubuntu 22.04.4 LTS",
        "kubelet_version": "v1.29.2",
    },
    {
        "name": "node-2",
        "status": "Ready",
        "roles": ["worker"],
        "cpu_capacity": "16",
        "memory_capacity": "64Gi",
        "cpu_allocatable": "15500m",
        "memory_allocatable": "62Gi",
        "os_image": "Ubuntu 22.04.4 LTS",
        "kubelet_version": "v1.29.2",
    },
    {
        "name": "node-3",
        "status": "Ready",
        "roles": ["worker"],
        "cpu_capacity": "16",
        "memory_capacity": "64Gi",
        "cpu_allocatable": "15500m",
        "memory_allocatable": "62Gi",
        "os_image": "Ubuntu 22.04.4 LTS",
        "kubelet_version": "v1.29.2",
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Events
# ---------------------------------------------------------------------------

MOCK_EVENTS: list[dict[str, Any]] = [
    {
        "type": "Normal",
        "reason": "Scheduled",
        "object": "Pod/nginx-deployment-7c79c4bf97-abc12",
        "message": (
            "Successfully assigned default/nginx-deployment-7c79c4bf97-abc12 to node-1"
        ),
        "first_seen": "2026-03-21T08:00:00Z",
        "last_seen": "2026-03-21T08:00:00Z",
        "count": 1,
        "namespace": "default",
    },
    {
        "type": "Normal",
        "reason": "Pulled",
        "object": "Pod/nginx-deployment-7c79c4bf97-abc12",
        "message": "Container image 'nginx:1.25.3' already present on machine",
        "first_seen": "2026-03-21T08:00:01Z",
        "last_seen": "2026-03-21T08:00:01Z",
        "count": 1,
        "namespace": "default",
    },
    {
        "type": "Normal",
        "reason": "Started",
        "object": "Pod/nginx-deployment-7c79c4bf97-abc12",
        "message": "Started container nginx",
        "first_seen": "2026-03-21T08:00:02Z",
        "last_seen": "2026-03-21T08:00:02Z",
        "count": 1,
        "namespace": "default",
    },
    {
        "type": "Warning",
        "reason": "BackOff",
        "object": "Pod/worker-batch-job-ghi01",
        "message": (
            "Back-off restarting failed container worker "
            "in pod worker-batch-job-ghi01"
        ),
        "first_seen": "2026-03-22T01:05:00Z",
        "last_seen": "2026-03-22T06:30:00Z",
        "count": 42,
        "namespace": "default",
    },
    {
        "type": "Warning",
        "reason": "Unhealthy",
        "object": "Pod/worker-batch-job-ghi01",
        "message": "Liveness probe failed: connection refused",
        "first_seen": "2026-03-22T01:02:00Z",
        "last_seen": "2026-03-22T06:28:00Z",
        "count": 38,
        "namespace": "default",
    },
    {
        "type": "Normal",
        "reason": "ScalingReplicaSet",
        "object": "Deployment/nginx-deployment",
        "message": "Scaled up replica set nginx-deployment-7c79c4bf97 to 3",
        "first_seen": "2026-03-15T10:00:00Z",
        "last_seen": "2026-03-15T10:00:00Z",
        "count": 1,
        "namespace": "default",
    },
]


# ---------------------------------------------------------------------------
# Mock Data -- Pod Logs
# ---------------------------------------------------------------------------

_MOCK_LOG_LINES: dict[str, list[str]] = {
    "nginx": [
        '10.244.0.1 - - [22/Mar/2026:08:15:01 +0000] "GET / HTTP/1.1" 200 615 "-" "curl/8.5.0"',
        (
            '10.244.0.1 - - [22/Mar/2026:08:15:02 +0000] "GET /healthz HTTP/1.1"'
            ' 200 2 "-" "kube-probe/1.29"'
        ),
        (
            '10.244.0.5 - - [22/Mar/2026:08:15:05 +0000] "GET /api/v1/status HTTP/1.1"'
            ' 200 128 "-" "python-requests/2.31"'
        ),
        (
            '10.244.0.1 - - [22/Mar/2026:08:15:10 +0000] "POST /api/v1/data HTTP/1.1"'
            ' 201 64 "-" "python-requests/2.31"'
        ),
        (
            '10.244.0.1 - - [22/Mar/2026:08:15:15 +0000] "GET /healthz HTTP/1.1"'
            ' 200 2 "-" "kube-probe/1.29"'
        ),
        (
            '10.244.0.8 - - [22/Mar/2026:08:15:20 +0000]'
            ' "GET /static/main.css HTTP/1.1" 304 0 "-" "Mozilla/5.0"'
        ),
        '10.244.0.1 - - [22/Mar/2026:08:15:25 +0000] "GET / HTTP/1.1" 200 615 "-" "curl/8.5.0"',
    ],
    "redis": [
        "1:C 22 Mar 2026 08:00:00.000 # oO0OoO0OoO0Oo Redis is starting oO0OoO0OoO0Oo",
        "1:C 22 Mar 2026 08:00:00.001 # Redis version=7.2.4, bits=64, commit=00000000",
        "1:M 22 Mar 2026 08:00:00.002 * Running mode=standalone, port=6379.",
        "1:M 22 Mar 2026 08:00:00.003 # Server initialized",
        "1:M 22 Mar 2026 08:00:00.004 * Ready to accept connections tcp",
        "1:M 22 Mar 2026 08:15:00.000 * 1 changes in 900 seconds. Saving...",
        "1:M 22 Mar 2026 08:15:00.050 * Background saving started by pid 42",
        "42:C 22 Mar 2026 08:15:00.100 * DB saved on disk",
        "1:M 22 Mar 2026 08:15:00.150 * Background saving terminated with success",
    ],
    "api-server": [
        "2026-03-22 08:15:00 INFO  [main] Application starting on port 8080",
        "2026-03-22 08:15:01 INFO  [main] Connected to database postgres://db:5432/app",
        "2026-03-22 08:15:01 INFO  [main] Redis cache connected at redis-svc:6379",
        "2026-03-22 08:15:02 INFO  [main] Application ready, accepting requests",
        "2026-03-22 08:15:10 INFO  [http] GET /health 200 1ms",
        "2026-03-22 08:15:15 INFO  [http] POST /api/v1/users 201 45ms",
        "2026-03-22 08:15:20 WARN  [http] GET /api/v1/orders?page=999 - empty result set",
        "2026-03-22 08:15:25 INFO  [http] GET /api/v1/products 200 12ms",
    ],
    "worker": [
        "2026-03-22 01:00:00 INFO  Starting worker process...",
        "2026-03-22 01:00:01 INFO  Connecting to message queue...",
        "2026-03-22 01:00:02 ERROR Failed to connect to rabbitmq://rabbitmq-svc:5672",
        "2026-03-22 01:00:02 ERROR ConnectionRefusedError: [Errno 111] Connection refused",
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
        label_selector: Optional label selector string (e.g., 'app=nginx').

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
        return "nginx-deployment-7c79c4bf97-abc12\n"

    if cmd == "date":
        return f"{now_str}\n"

    if cmd == "env":
        return (
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
            "HOSTNAME=nginx-deployment-7c79c4bf97-abc12\n"
            "KUBERNETES_SERVICE_HOST=10.96.0.1\n"
            "KUBERNETES_SERVICE_PORT=443\n"
            "HOME=/root\n"
        )

    if cmd in ("ps", "ps aux"):
        return (
            "PID   USER     TIME  COMMAND\n"
            "    1 root      0:00 /entrypoint.sh\n"
            "   12 root      0:05 nginx: master process\n"
            "   13 nginx     0:12 nginx: worker process\n"
            "   14 nginx     0:11 nginx: worker process\n"
        )

    # Generic fallback
    full_cmd = " ".join(command)
    return f"$ {full_cmd}\n(mock output for command: {full_cmd})\n"
