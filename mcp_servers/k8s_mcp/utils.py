"""Kubernetes client helpers -- auto-detects cluster availability.

Provides lazily-initialized, cached CoreV1Api and AppsV1Api clients.
Raises K8sUnavailableError when no kubeconfig or in-cluster config is found,
so every tool can return a clear error instead of crashing.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class K8sUnavailableError(Exception):
    """Raised when Kubernetes cluster is not reachable."""


@lru_cache(maxsize=1)
def get_clients() -> tuple[Any, Any]:
    """Get cached (CoreV1Api, AppsV1Api) clients.

    Tries in-cluster config first, then falls back to local kubeconfig.

    Returns:
        Tuple of (CoreV1Api, AppsV1Api) client instances.

    Raises:
        K8sUnavailableError: If no kubeconfig or in-cluster config is found.
    """
    try:
        from kubernetes import client
        from kubernetes import config as k8s_config

        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        logger.info("Kubernetes client initialized successfully")
        return v1, apps_v1
    except Exception as exc:
        raise K8sUnavailableError(
            f"Kubernetes not available: {exc}. "
            "Set KUBECONFIG or run inside a cluster. "
            "Install: pip install kubernetes && kubectl config view"
        ) from exc
