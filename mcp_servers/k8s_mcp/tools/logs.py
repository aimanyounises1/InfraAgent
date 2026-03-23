"""Log retrieval tools for k8s_mcp."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.k8s_mcp.models import K8sGetPodLogsInput  # noqa: TCH001
from mcp_servers.k8s_mcp.server import mcp
from mcp_servers.k8s_mcp.utils import K8sUnavailableError, get_clients

logger = logging.getLogger(__name__)


@mcp.tool(
    name="k8s_get_pod_logs",
    annotations={
        "title": "Get Pod Logs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_pod_logs(params: K8sGetPodLogsInput) -> str:
    """Retrieve container logs with tail and time-based filtering."""
    logger.debug(
        "k8s_get_pod_logs called",
        extra={
            "pod_name": params.pod_name,
            "namespace": params.namespace,
            "container": params.container,
            "tail_lines": params.tail_lines,
            "since_seconds": params.since_seconds,
        },
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_get_pod_logs: cluster unavailable")
        return json.dumps(
            {
                "error": "Kubernetes not available",
                "detail": str(e),
                "hint": ("Install kubectl and configure cluster access."),
            },
            indent=2,
        )

    try:
        kwargs: dict[str, Any] = {
            "name": params.pod_name,
            "namespace": params.namespace,
            "tail_lines": params.tail_lines,
        }
        if params.container:
            kwargs["container"] = params.container
        if params.since_seconds:
            kwargs["since_seconds"] = params.since_seconds

        log_text = await asyncio.to_thread(
            v1.read_namespaced_pod_log,
            **kwargs,
        )

        result = {
            "pod": params.pod_name,
            "namespace": params.namespace,
            "container": params.container,
            "tail_lines": params.tail_lines,
            "since_seconds": params.since_seconds,
            "log_lines": (log_text.count("\n") + 1 if log_text else 0),
            "logs": log_text or "",
        }
        logger.info(
            "k8s_get_pod_logs completed",
            extra={
                "pod_name": params.pod_name,
                "lines": result["log_lines"],
            },
        )
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error("k8s_get_pod_logs error", extra={"error": str(e)})
        return json.dumps(
            {
                "error": f"K8s API error: {e}",
                "details": (f"Failed to get logs for pod '{params.pod_name}'"),
            },
            indent=2,
        )
