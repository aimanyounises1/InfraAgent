"""Service management tools for k8s_mcp."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.k8s_mcp.models import K8sListServicesInput  # noqa: TCH001
from mcp_servers.k8s_mcp.server import mcp
from mcp_servers.k8s_mcp.utils import K8sUnavailableError, get_clients

logger = logging.getLogger(__name__)


def _serialize_service(svc: Any) -> dict[str, Any]:
    """Extract relevant fields from a V1Service object into a plain dict.

    Args:
        svc: A kubernetes.client.V1Service object.

    Returns:
        Dictionary with service summary fields.
    """
    ports: list[dict[str, Any]] = []
    if svc.spec and svc.spec.ports:
        for p in svc.spec.ports:
            port_info: dict[str, Any] = {
                "port": p.port,
                "target_port": p.target_port,
                "protocol": p.protocol or "TCP",
            }
            if p.name:
                port_info["name"] = p.name
            if p.node_port:
                port_info["node_port"] = p.node_port
            ports.append(port_info)

    external_ips: list[str] = []
    if svc.status and svc.status.load_balancer and svc.status.load_balancer.ingress:
        for ing in svc.status.load_balancer.ingress:
            if ing.ip:
                external_ips.append(ing.ip)
            elif ing.hostname:
                external_ips.append(ing.hostname)

    result: dict[str, Any] = {
        "name": svc.metadata.name,
        "namespace": svc.metadata.namespace,
        "type": svc.spec.type if svc.spec else "ClusterIP",
        "cluster_ip": svc.spec.cluster_ip if svc.spec else None,
        "ports": ports,
        "selector": svc.spec.selector if svc.spec else None,
    }

    if external_ips:
        result["external_ips"] = external_ips

    return result


@mcp.tool(
    name="k8s_list_services",
    annotations={
        "title": "List Kubernetes Services",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_list_services(params: K8sListServicesInput) -> str:
    """List services in a namespace with type, cluster IP, and ports."""
    logger.debug(
        "k8s_list_services called",
        extra={"namespace": params.namespace},
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_list_services: cluster unavailable")
        return json.dumps(
            {
                "error": "Kubernetes not available",
                "detail": str(e),
                "hint": ("Install kubectl and configure cluster access."),
            },
            indent=2,
        )

    try:
        svc_list = await asyncio.to_thread(
            v1.list_namespaced_service,
            namespace=params.namespace,
        )

        services = [_serialize_service(s) for s in svc_list.items]
        result = {
            "namespace": params.namespace,
            "service_count": len(services),
            "services": services,
        }
        logger.info(
            "k8s_list_services completed",
            extra={"service_count": len(services)},
        )
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error("k8s_list_services error", extra={"error": str(e)})
        return json.dumps(
            {
                "error": f"K8s API error: {e}",
                "details": (f"Failed to list services in namespace '{params.namespace}'"),
            },
            indent=2,
        )
