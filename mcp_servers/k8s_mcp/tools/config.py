"""ConfigMap and ResourceQuota tools for k8s_mcp.

Provides read-only access to ConfigMaps (with value truncation for safety)
and ResourceQuotas (hard vs used comparison).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.k8s_mcp.models import (  # noqa: TCH001
    K8sGetConfigMapInput,
    K8sGetResourceQuotasInput,
)
from mcp_servers.k8s_mcp.server import mcp
from mcp_servers.k8s_mcp.utils import K8sUnavailableError, get_clients

logger = logging.getLogger(__name__)

# Maximum characters per ConfigMap value to return
_MAX_VALUE_LENGTH = 500


def _json(data: Any) -> str:
    """Serialize data to a JSON string with indentation."""
    return json.dumps(data, indent=2, default=str)


def _k8s_error(detail: str | Exception) -> str:
    """Return a standardised K8s unavailability error as JSON."""
    return _json(
        {
            "error": "Kubernetes not available",
            "detail": str(detail),
            "hint": "Install kubectl and configure cluster access.",
        }
    )


def _api_error(tool: str, exc: Exception, context: str = "") -> str:
    """Return a standardised K8s API error as JSON."""
    return _json(
        {
            "error": f"K8s API error: {exc}",
            "details": f"Failed in {tool}: {context}" if context else f"Failed in {tool}",
        }
    )


# ---------------------------------------------------------------------------
# Tool 1: k8s_get_configmap
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_get_configmap",
    annotations={
        "title": "Get Kubernetes ConfigMap",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_configmap(params: K8sGetConfigMapInput) -> str:
    """Get a ConfigMap by name, truncating values to 500 chars for safety."""
    logger.debug(
        "k8s_get_configmap called",
        extra={"namespace": params.namespace, "name": params.name},
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_get_configmap: cluster unavailable")
        return _k8s_error(e)

    try:
        cm = await asyncio.to_thread(
            v1.read_namespaced_config_map,
            name=params.name,
            namespace=params.namespace,
        )

        # Truncate large values
        data: dict[str, str] = {}
        if cm.data:
            for key, value in cm.data.items():
                if len(value) > _MAX_VALUE_LENGTH:
                    data[key] = (
                        value[:_MAX_VALUE_LENGTH] + f"... [truncated, total {len(value)} chars]"
                    )
                else:
                    data[key] = value

        binary_data_keys: list[str] = []
        if cm.binary_data:
            binary_data_keys = list(cm.binary_data.keys())

        result = {
            "name": cm.metadata.name,
            "namespace": cm.metadata.namespace,
            "labels": cm.metadata.labels or {},
            "annotations": cm.metadata.annotations or {},
            "data_keys": list(data.keys()),
            "data": data,
            "binary_data_keys": binary_data_keys,
            "creation_timestamp": str(cm.metadata.creation_timestamp),
        }
        logger.info(
            "k8s_get_configmap completed",
            extra={"name": params.name, "keys": len(data)},
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_get_configmap error", extra={"error": str(e)})
        return _api_error("k8s_get_configmap", e, f"name={params.name}")


# ---------------------------------------------------------------------------
# Tool 2: k8s_get_resource_quotas
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_get_resource_quotas",
    annotations={
        "title": "Get Kubernetes Resource Quotas",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_resource_quotas(params: K8sGetResourceQuotasInput) -> str:
    """List ResourceQuotas in a namespace showing hard limits vs current usage."""
    logger.debug(
        "k8s_get_resource_quotas called",
        extra={"namespace": params.namespace},
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_get_resource_quotas: cluster unavailable")
        return _k8s_error(e)

    try:
        quota_list = await asyncio.to_thread(
            v1.list_namespaced_resource_quota,
            namespace=params.namespace,
        )

        quotas: list[dict[str, Any]] = []
        for q in quota_list.items:
            hard: dict[str, str] = {}
            used: dict[str, str] = {}

            if q.status and q.status.hard:
                hard = {k: str(v) for k, v in q.status.hard.items()}
            if q.status and q.status.used:
                used = {k: str(v) for k, v in q.status.used.items()}

            # Build a comparison view
            resources: list[dict[str, str]] = []
            all_keys = set(list(hard.keys()) + list(used.keys()))
            for key in sorted(all_keys):
                resources.append(
                    {
                        "resource": key,
                        "hard": hard.get(key, "N/A"),
                        "used": used.get(key, "0"),
                    }
                )

            scopes: list[str] = []
            if q.spec and q.spec.scopes:
                scopes = [str(s) for s in q.spec.scopes]

            quotas.append(
                {
                    "name": q.metadata.name,
                    "namespace": q.metadata.namespace,
                    "hard": hard,
                    "used": used,
                    "resources": resources,
                    "scopes": scopes,
                    "creation_timestamp": str(q.metadata.creation_timestamp),
                }
            )

        result = {
            "namespace": params.namespace,
            "quota_count": len(quotas),
            "quotas": quotas,
        }
        logger.info(
            "k8s_get_resource_quotas completed",
            extra={"quota_count": len(quotas)},
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_get_resource_quotas error", extra={"error": str(e)})
        return _api_error("k8s_get_resource_quotas", e, f"namespace={params.namespace}")
