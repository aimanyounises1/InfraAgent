"""Deployment management tools for k8s_mcp."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from kubernetes import client

from config import settings
from mcp_servers.k8s_mcp.models import (  # noqa: TCH001
    K8sListDeploymentsInput,
    K8sRestartDeploymentInput,
    K8sScaleDeploymentInput,
)
from mcp_servers.k8s_mcp.server import mcp
from mcp_servers.k8s_mcp.utils import get_clients, get_mock_deployments

logger = logging.getLogger(__name__)


def _serialize_deployment(deploy: Any) -> dict[str, Any]:
    """Extract relevant fields from a V1Deployment object into a plain dict.

    Args:
        deploy: A kubernetes.client.V1Deployment object.

    Returns:
        Dictionary with deployment summary fields.
    """
    conditions: list[dict[str, Any]] = []
    if deploy.status and deploy.status.conditions:
        for c in deploy.status.conditions:
            conditions.append({
                "type": c.type,
                "status": c.status,
                "reason": c.reason or "",
                "message": c.message or "",
            })

    return {
        "name": deploy.metadata.name,
        "namespace": deploy.metadata.namespace,
        "replicas": deploy.spec.replicas if deploy.spec else 0,
        "ready_replicas": (
            deploy.status.ready_replicas
            if deploy.status and deploy.status.ready_replicas
            else 0
        ),
        "available_replicas": (
            deploy.status.available_replicas
            if deploy.status and deploy.status.available_replicas
            else 0
        ),
        "updated_replicas": (
            deploy.status.updated_replicas
            if deploy.status and deploy.status.updated_replicas
            else 0
        ),
        "labels": deploy.metadata.labels or {},
        "strategy": (
            deploy.spec.strategy.type
            if deploy.spec and deploy.spec.strategy
            else "Unknown"
        ),
        "conditions": conditions,
    }


@mcp.tool(
    name="k8s_list_deployments",
    annotations={
        "title": "List Kubernetes Deployments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_list_deployments(params: K8sListDeploymentsInput) -> str:
    """List deployments in a namespace with replica counts and rollout status."""
    logger.debug(
        "k8s_list_deployments called",
        extra={
            "namespace": params.namespace,
            "label_selector": params.label_selector,
        },
    )

    if settings.mock_k8s:
        logger.info("k8s_list_deployments using mock data")
        deployments = get_mock_deployments(
            namespace=params.namespace,
            label_selector=params.label_selector,
        )
        result = {
            "namespace": params.namespace,
            "deployment_count": len(deployments),
            "deployments": deployments,
        }
        return json.dumps(result, indent=2, default=str)

    try:
        _, apps_v1 = get_clients()

        kwargs: dict[str, Any] = {"namespace": params.namespace}
        if params.label_selector:
            kwargs["label_selector"] = params.label_selector

        deploy_list = await asyncio.to_thread(
            apps_v1.list_namespaced_deployment,
            **kwargs,
        )

        deployments = [_serialize_deployment(d) for d in deploy_list.items]
        result = {
            "namespace": params.namespace,
            "deployment_count": len(deployments),
            "deployments": deployments,
        }
        logger.info(
            "k8s_list_deployments completed",
            extra={"deployment_count": len(deployments)},
        )
        return json.dumps(result, indent=2, default=str)

    except client.ApiException as e:
        logger.error(
            "k8s_list_deployments API error",
            extra={"status": e.status, "reason": e.reason},
        )
        error = {
            "error": "Kubernetes API error",
            "status": e.status,
            "reason": e.reason,
            "details": (
                f"Failed to list deployments in namespace '{params.namespace}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)
    except Exception as e:
        logger.error(
            "k8s_list_deployments unexpected error",
            extra={"error": str(e)},
        )
        error = {
            "error": "Unexpected error",
            "message": str(e),
            "details": (
                f"Failed to list deployments in namespace '{params.namespace}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)


@mcp.tool(
    name="k8s_scale_deployment",
    annotations={
        "title": "Scale Kubernetes Deployment",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_scale_deployment(params: K8sScaleDeploymentInput) -> str:
    """Scale a deployment to the specified number of replicas."""
    logger.debug(
        "k8s_scale_deployment called",
        extra={
            "deployment_name": params.deployment_name,
            "namespace": params.namespace,
            "replicas": params.replicas,
        },
    )

    if settings.mock_k8s:
        logger.info("k8s_scale_deployment using mock data")
        # Find the mock deployment to report old replicas
        deployments = get_mock_deployments(namespace=params.namespace)
        old_replicas = 0
        found = False
        for d in deployments:
            if d["name"] == params.deployment_name:
                old_replicas = d["replicas"]
                found = True
                break

        if not found:
            error = {
                "error": "Deployment not found",
                "deployment_name": params.deployment_name,
                "namespace": params.namespace,
            }
            return json.dumps(error, indent=2, default=str)

        result = {
            "action": "scale",
            "deployment": params.deployment_name,
            "namespace": params.namespace,
            "previous_replicas": old_replicas,
            "new_replicas": params.replicas,
            "status": "scaled",
        }
        return json.dumps(result, indent=2, default=str)

    try:
        _, apps_v1 = get_clients()

        # Read current state for reporting
        current = await asyncio.to_thread(
            apps_v1.read_namespaced_deployment,
            name=params.deployment_name,
            namespace=params.namespace,
        )
        old_replicas = current.spec.replicas if current.spec else 0

        # Patch the scale
        body = {"spec": {"replicas": params.replicas}}
        await asyncio.to_thread(
            apps_v1.patch_namespaced_deployment_scale,
            name=params.deployment_name,
            namespace=params.namespace,
            body=body,
        )

        result = {
            "action": "scale",
            "deployment": params.deployment_name,
            "namespace": params.namespace,
            "previous_replicas": old_replicas,
            "new_replicas": params.replicas,
            "status": "scaled",
        }
        logger.info(
            "k8s_scale_deployment completed",
            extra={
                "deployment": params.deployment_name,
                "old": old_replicas,
                "new": params.replicas,
            },
        )
        return json.dumps(result, indent=2, default=str)

    except client.ApiException as e:
        logger.error(
            "k8s_scale_deployment API error",
            extra={"status": e.status, "reason": e.reason},
        )
        if e.status == 404:
            error = {
                "error": "Deployment not found",
                "deployment_name": params.deployment_name,
                "namespace": params.namespace,
            }
        else:
            error = {
                "error": "Kubernetes API error",
                "status": e.status,
                "reason": e.reason,
                "details": (
                    f"Failed to scale deployment '{params.deployment_name}'"
                ),
            }
        return json.dumps(error, indent=2, default=str)
    except Exception as e:
        logger.error(
            "k8s_scale_deployment unexpected error",
            extra={"error": str(e)},
        )
        error = {
            "error": "Unexpected error",
            "message": str(e),
            "details": (
                f"Failed to scale deployment '{params.deployment_name}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)


@mcp.tool(
    name="k8s_restart_deployment",
    annotations={
        "title": "Rolling Restart Deployment",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_restart_deployment(params: K8sRestartDeploymentInput) -> str:
    """Perform a rolling restart of a deployment."""
    logger.debug(
        "k8s_restart_deployment called",
        extra={
            "deployment_name": params.deployment_name,
            "namespace": params.namespace,
        },
    )

    restart_time = datetime.now(tz=UTC).isoformat()

    if settings.mock_k8s:
        logger.info("k8s_restart_deployment using mock data")
        deployments = get_mock_deployments(namespace=params.namespace)
        found = any(
            d["name"] == params.deployment_name for d in deployments
        )

        if not found:
            error = {
                "error": "Deployment not found",
                "deployment_name": params.deployment_name,
                "namespace": params.namespace,
            }
            return json.dumps(error, indent=2, default=str)

        result = {
            "action": "rolling_restart",
            "deployment": params.deployment_name,
            "namespace": params.namespace,
            "restart_triggered_at": restart_time,
            "status": "restarting",
        }
        return json.dumps(result, indent=2, default=str)

    try:
        _, apps_v1 = get_clients()

        # Trigger rolling restart by patching the pod template annotation
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": restart_time,
                        }
                    }
                }
            }
        }

        await asyncio.to_thread(
            apps_v1.patch_namespaced_deployment,
            name=params.deployment_name,
            namespace=params.namespace,
            body=body,
        )

        result = {
            "action": "rolling_restart",
            "deployment": params.deployment_name,
            "namespace": params.namespace,
            "restart_triggered_at": restart_time,
            "status": "restarting",
        }
        logger.info(
            "k8s_restart_deployment completed",
            extra={
                "deployment": params.deployment_name,
                "restart_at": restart_time,
            },
        )
        return json.dumps(result, indent=2, default=str)

    except client.ApiException as e:
        logger.error(
            "k8s_restart_deployment API error",
            extra={"status": e.status, "reason": e.reason},
        )
        if e.status == 404:
            error = {
                "error": "Deployment not found",
                "deployment_name": params.deployment_name,
                "namespace": params.namespace,
            }
        else:
            error = {
                "error": "Kubernetes API error",
                "status": e.status,
                "reason": e.reason,
                "details": (
                    f"Failed to restart deployment "
                    f"'{params.deployment_name}'"
                ),
            }
        return json.dumps(error, indent=2, default=str)
    except Exception as e:
        logger.error(
            "k8s_restart_deployment unexpected error",
            extra={"error": str(e)},
        )
        error = {
            "error": "Unexpected error",
            "message": str(e),
            "details": (
                f"Failed to restart deployment '{params.deployment_name}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)
