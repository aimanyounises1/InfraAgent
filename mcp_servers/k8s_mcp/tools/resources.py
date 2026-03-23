"""Kubernetes resource management tools for k8s_mcp.

Provides node management (status, cordon/uncordon, drain), rollout status,
rollback, HPA inspection, and namespace listing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp_servers.k8s_mcp.models import (  # noqa: TCH001
    K8sCordonNodeInput,
    K8sDrainNodeInput,
    K8sGetHPAInput,
    K8sGetNodeStatusInput,
    K8sListEventsInput,
    K8sListNamespacesInput,
    K8sRollbackDeploymentInput,
    K8sRolloutStatusInput,
)
from mcp_servers.k8s_mcp.server import mcp
from mcp_servers.k8s_mcp.utils import (
    K8sUnavailableError,
    get_autoscaling_client,
    get_clients,
)

logger = logging.getLogger(__name__)


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
# Serializers
# ---------------------------------------------------------------------------


def _serialize_node(node: Any) -> dict[str, Any]:
    """Extract relevant fields from a V1Node object.

    Args:
        node: A kubernetes.client.V1Node object.

    Returns:
        Dictionary with node summary fields.
    """
    conditions: list[dict[str, Any]] = []
    if node.status and node.status.conditions:
        for c in node.status.conditions:
            conditions.append(
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason or "",
                    "message": c.message or "",
                    "last_transition": str(c.last_transition_time),
                }
            )

    allocatable: dict[str, str] = {}
    if node.status and node.status.allocatable:
        allocatable = {k: str(v) for k, v in node.status.allocatable.items()}

    capacity: dict[str, str] = {}
    if node.status and node.status.capacity:
        capacity = {k: str(v) for k, v in node.status.capacity.items()}

    taints: list[dict[str, str]] = []
    if node.spec and node.spec.taints:
        for t in node.spec.taints:
            taints.append(
                {
                    "key": t.key or "",
                    "value": t.value or "",
                    "effect": t.effect or "",
                }
            )

    return {
        "name": node.metadata.name,
        "labels": node.metadata.labels or {},
        "unschedulable": bool(node.spec.unschedulable) if node.spec else False,
        "conditions": conditions,
        "allocatable": allocatable,
        "capacity": capacity,
        "taints": taints,
        "creation_timestamp": str(node.metadata.creation_timestamp),
    }


def _serialize_event(ev: Any) -> dict[str, Any]:
    """Extract relevant fields from a V1Event object.

    Args:
        ev: A kubernetes.client.V1Event object.

    Returns:
        Dictionary with event summary fields.
    """
    return {
        "type": ev.type,
        "reason": ev.reason,
        "message": ev.message,
        "count": ev.count,
        "source_component": ev.source.component if ev.source else None,
        "involved_object": (
            f"{ev.involved_object.kind}/{ev.involved_object.name}" if ev.involved_object else None
        ),
        "namespace": ev.metadata.namespace,
        "first_seen": str(ev.first_timestamp),
        "last_seen": str(ev.last_timestamp),
    }


# ---------------------------------------------------------------------------
# Tool 1: k8s_list_events
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_list_events",
    annotations={
        "title": "List Kubernetes Events",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_list_events(params: K8sListEventsInput) -> str:
    """List cluster events with optional namespace and type filtering."""
    logger.debug(
        "k8s_list_events called",
        extra={
            "namespace": params.namespace,
            "event_type": params.event_type,
            "limit": params.limit,
        },
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_list_events: cluster unavailable")
        return _k8s_error(e)

    try:
        kwargs: dict[str, Any] = {"limit": params.limit}
        if params.event_type:
            kwargs["field_selector"] = f"type={params.event_type}"

        if params.namespace:
            event_list = await asyncio.to_thread(
                v1.list_namespaced_event,
                namespace=params.namespace,
                **kwargs,
            )
        else:
            event_list = await asyncio.to_thread(
                v1.list_event_for_all_namespaces,
                **kwargs,
            )

        events = [_serialize_event(ev) for ev in event_list.items]
        result = {
            "namespace": params.namespace or "all",
            "event_type_filter": params.event_type,
            "event_count": len(events),
            "events": events,
        }
        logger.info("k8s_list_events completed", extra={"event_count": len(events)})
        return _json(result)

    except Exception as e:
        logger.error("k8s_list_events error", extra={"error": str(e)})
        return _api_error("k8s_list_events", e, f"namespace={params.namespace}")


# ---------------------------------------------------------------------------
# Tool 2: k8s_get_node_status
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_get_node_status",
    annotations={
        "title": "Get Kubernetes Node Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_node_status(params: K8sGetNodeStatusInput) -> str:
    """Get node conditions, allocatable resources, and taints."""
    logger.debug(
        "k8s_get_node_status called",
        extra={"node_name": params.node_name},
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_get_node_status: cluster unavailable")
        return _k8s_error(e)

    try:
        if params.node_name:
            node = await asyncio.to_thread(
                v1.read_node,
                name=params.node_name,
            )
            nodes = [_serialize_node(node)]
        else:
            node_list = await asyncio.to_thread(v1.list_node)
            nodes = [_serialize_node(n) for n in node_list.items]

        result = {
            "node_count": len(nodes),
            "nodes": nodes,
        }
        logger.info(
            "k8s_get_node_status completed",
            extra={"node_count": len(nodes)},
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_get_node_status error", extra={"error": str(e)})
        return _api_error("k8s_get_node_status", e, f"node={params.node_name or 'all'}")


# ---------------------------------------------------------------------------
# Tool 3: k8s_cordon_node
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_cordon_node",
    annotations={
        "title": "Cordon Kubernetes Node",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_cordon_node(params: K8sCordonNodeInput) -> str:
    """Mark a node as unschedulable (cordon)."""
    logger.debug("k8s_cordon_node called", extra={"node_name": params.node_name})

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_cordon_node: cluster unavailable")
        return _k8s_error(e)

    try:
        body = {"spec": {"unschedulable": True}}
        await asyncio.to_thread(
            v1.patch_node,
            name=params.node_name,
            body=body,
        )

        result = {
            "action": "cordon",
            "node": params.node_name,
            "unschedulable": True,
            "status": "cordoned",
        }
        logger.info("k8s_cordon_node completed", extra={"node": params.node_name})
        return _json(result)

    except Exception as e:
        logger.error("k8s_cordon_node error", extra={"error": str(e)})
        return _api_error("k8s_cordon_node", e, f"node={params.node_name}")


# ---------------------------------------------------------------------------
# Tool 4: k8s_uncordon_node
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_uncordon_node",
    annotations={
        "title": "Uncordon Kubernetes Node",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_uncordon_node(params: K8sCordonNodeInput) -> str:
    """Mark a node as schedulable again (uncordon)."""
    logger.debug("k8s_uncordon_node called", extra={"node_name": params.node_name})

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_uncordon_node: cluster unavailable")
        return _k8s_error(e)

    try:
        body = {"spec": {"unschedulable": False}}
        await asyncio.to_thread(
            v1.patch_node,
            name=params.node_name,
            body=body,
        )

        result = {
            "action": "uncordon",
            "node": params.node_name,
            "unschedulable": False,
            "status": "uncordoned",
        }
        logger.info("k8s_uncordon_node completed", extra={"node": params.node_name})
        return _json(result)

    except Exception as e:
        logger.error("k8s_uncordon_node error", extra={"error": str(e)})
        return _api_error("k8s_uncordon_node", e, f"node={params.node_name}")


# ---------------------------------------------------------------------------
# Tool 5: k8s_drain_node
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_drain_node",
    annotations={
        "title": "Drain Kubernetes Node",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def k8s_drain_node(params: K8sDrainNodeInput) -> str:
    """Drain a node by evicting all non-DaemonSet pods.

    Cordons the node first, then evicts pods via the Eviction API.
    DaemonSet-managed pods and mirror pods are skipped.
    """
    logger.debug(
        "k8s_drain_node called",
        extra={
            "node_name": params.node_name,
            "grace_period": params.grace_period,
            "force": params.force,
        },
    )

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_drain_node: cluster unavailable")
        return _k8s_error(e)

    try:
        # Step 1: Cordon the node
        cordon_body = {"spec": {"unschedulable": True}}
        await asyncio.to_thread(
            v1.patch_node,
            name=params.node_name,
            body=cordon_body,
        )

        # Step 2: List pods on the node
        pod_list = await asyncio.to_thread(
            v1.list_pod_for_all_namespaces,
            field_selector=f"spec.nodeName={params.node_name}",
        )

        evicted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for pod in pod_list.items:
            pod_name = pod.metadata.name
            pod_ns = pod.metadata.namespace

            # Skip DaemonSet-managed pods
            if pod.metadata.owner_references:
                is_daemonset = any(ref.kind == "DaemonSet" for ref in pod.metadata.owner_references)
                if is_daemonset:
                    skipped.append(f"{pod_ns}/{pod_name} (DaemonSet)")
                    continue

            # Skip mirror pods (static pods managed by kubelet)
            annotations = pod.metadata.annotations or {}
            if "kubernetes.io/config.mirror" in annotations:
                skipped.append(f"{pod_ns}/{pod_name} (mirror)")
                continue

            # Create eviction
            try:
                from kubernetes.client import V1Eviction, V1ObjectMeta

                eviction = V1Eviction(
                    metadata=V1ObjectMeta(
                        name=pod_name,
                        namespace=pod_ns,
                    ),
                    delete_options={
                        "gracePeriodSeconds": params.grace_period,
                    },
                )
                await asyncio.to_thread(
                    v1.create_namespaced_pod_eviction,
                    name=pod_name,
                    namespace=pod_ns,
                    body=eviction,
                )
                evicted.append(f"{pod_ns}/{pod_name}")
            except Exception as evict_err:
                if params.force:
                    # Force delete the pod
                    try:
                        await asyncio.to_thread(
                            v1.delete_namespaced_pod,
                            name=pod_name,
                            namespace=pod_ns,
                            grace_period_seconds=params.grace_period,
                        )
                        evicted.append(f"{pod_ns}/{pod_name} (force-deleted)")
                    except Exception as del_err:
                        errors.append(f"{pod_ns}/{pod_name}: {del_err}")
                else:
                    errors.append(f"{pod_ns}/{pod_name}: {evict_err}")

        result = {
            "action": "drain",
            "node": params.node_name,
            "cordoned": True,
            "evicted_count": len(evicted),
            "evicted": evicted,
            "skipped_count": len(skipped),
            "skipped": skipped,
            "error_count": len(errors),
            "errors": errors,
            "status": "drained" if not errors else "partial_drain",
        }
        logger.info(
            "k8s_drain_node completed",
            extra={
                "node": params.node_name,
                "evicted": len(evicted),
                "errors": len(errors),
            },
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_drain_node error", extra={"error": str(e)})
        return _api_error("k8s_drain_node", e, f"node={params.node_name}")


# ---------------------------------------------------------------------------
# Tool 6: k8s_rollout_status
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_rollout_status",
    annotations={
        "title": "Deployment Rollout Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_rollout_status(params: K8sRolloutStatusInput) -> str:
    """Check the rollout status of a deployment.

    Compares spec.replicas with status.readyReplicas, updatedReplicas,
    and availableReplicas to determine rollout progress.
    """
    logger.debug(
        "k8s_rollout_status called",
        extra={
            "namespace": params.namespace,
            "deployment_name": params.deployment_name,
        },
    )

    try:
        _, apps_v1 = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_rollout_status: cluster unavailable")
        return _k8s_error(e)

    try:
        deploy = await asyncio.to_thread(
            apps_v1.read_namespaced_deployment,
            name=params.deployment_name,
            namespace=params.namespace,
        )

        desired = deploy.spec.replicas if deploy.spec else 0
        status = deploy.status
        ready = status.ready_replicas if status and status.ready_replicas else 0
        updated = status.updated_replicas if status and status.updated_replicas else 0
        available = status.available_replicas if status and status.available_replicas else 0
        unavailable = status.unavailable_replicas if status and status.unavailable_replicas else 0
        observed_gen = status.observed_generation if status and status.observed_generation else 0
        spec_gen = deploy.metadata.generation or 0

        # Determine rollout state
        if observed_gen < spec_gen or updated < desired or available < updated:
            rollout_state = "progressing"
        elif ready >= desired and updated >= desired:
            rollout_state = "complete"
        else:
            rollout_state = "progressing"

        conditions: list[dict[str, Any]] = []
        if status and status.conditions:
            for c in status.conditions:
                conditions.append(
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason or "",
                        "message": c.message or "",
                        "last_update": str(c.last_update_time),
                    }
                )

        result = {
            "deployment": params.deployment_name,
            "namespace": params.namespace,
            "rollout_state": rollout_state,
            "desired_replicas": desired,
            "ready_replicas": ready,
            "updated_replicas": updated,
            "available_replicas": available,
            "unavailable_replicas": unavailable,
            "observed_generation": observed_gen,
            "spec_generation": spec_gen,
            "conditions": conditions,
        }
        logger.info(
            "k8s_rollout_status completed",
            extra={
                "deployment": params.deployment_name,
                "state": rollout_state,
            },
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_rollout_status error", extra={"error": str(e)})
        return _api_error("k8s_rollout_status", e, f"deployment={params.deployment_name}")


# ---------------------------------------------------------------------------
# Tool 7: k8s_rollback_deployment
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_rollback_deployment",
    annotations={
        "title": "Rollback Deployment",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def k8s_rollback_deployment(params: K8sRollbackDeploymentInput) -> str:
    """Rollback a deployment to a previous revision.

    Finds the ReplicaSet matching the target revision (or the previous one
    if no revision is specified) and patches the deployment's pod template
    to match, triggering a rollback.
    """
    logger.debug(
        "k8s_rollback_deployment called",
        extra={
            "namespace": params.namespace,
            "deployment_name": params.deployment_name,
            "revision": params.revision,
        },
    )

    try:
        v1, apps_v1 = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_rollback_deployment: cluster unavailable")
        return _k8s_error(e)

    try:
        # Read current deployment to get the label selector
        deploy = await asyncio.to_thread(
            apps_v1.read_namespaced_deployment,
            name=params.deployment_name,
            namespace=params.namespace,
        )

        # Build label selector from the deployment's match labels
        match_labels = {}
        if deploy.spec and deploy.spec.selector and deploy.spec.selector.match_labels:
            match_labels = deploy.spec.selector.match_labels

        if not match_labels:
            return _json(
                {
                    "error": "Cannot determine deployment selector",
                    "deployment": params.deployment_name,
                }
            )

        label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())

        # List all ReplicaSets for this deployment
        rs_list = await asyncio.to_thread(
            apps_v1.list_namespaced_replica_set,
            namespace=params.namespace,
            label_selector=label_selector,
        )

        if not rs_list.items:
            return _json(
                {
                    "error": "No ReplicaSets found for deployment",
                    "deployment": params.deployment_name,
                }
            )

        # Filter ReplicaSets owned by this deployment
        owned_rs = []
        for rs in rs_list.items:
            if rs.metadata.owner_references:
                for ref in rs.metadata.owner_references:
                    if ref.kind == "Deployment" and ref.name == params.deployment_name:
                        revision_str = (rs.metadata.annotations or {}).get(
                            "deployment.kubernetes.io/revision", "0"
                        )
                        try:
                            revision_num = int(revision_str)
                        except ValueError:
                            revision_num = 0
                        owned_rs.append((revision_num, rs))
                        break

        if not owned_rs:
            return _json(
                {
                    "error": "No owned ReplicaSets found",
                    "deployment": params.deployment_name,
                }
            )

        # Sort by revision (descending)
        owned_rs.sort(key=lambda x: x[0], reverse=True)

        # Find target ReplicaSet
        target_rs = None
        if params.revision is not None:
            for rev, rs in owned_rs:
                if rev == params.revision:
                    target_rs = rs
                    break
            if target_rs is None:
                available_revisions = [rev for rev, _ in owned_rs]
                return _json(
                    {
                        "error": f"Revision {params.revision} not found",
                        "available_revisions": available_revisions,
                        "deployment": params.deployment_name,
                    }
                )
        else:
            # Use previous revision (second highest)
            if len(owned_rs) < 2:
                return _json(
                    {
                        "error": "No previous revision available to rollback to",
                        "deployment": params.deployment_name,
                    }
                )
            _, target_rs = owned_rs[1]

        # Patch the deployment with the target ReplicaSet's pod template
        target_revision = (target_rs.metadata.annotations or {}).get(
            "deployment.kubernetes.io/revision", "unknown"
        )
        patch_body = {
            "spec": {
                "template": target_rs.spec.template.to_dict()
                if hasattr(target_rs.spec.template, "to_dict")
                else target_rs.spec.template
            }
        }

        await asyncio.to_thread(
            apps_v1.patch_namespaced_deployment,
            name=params.deployment_name,
            namespace=params.namespace,
            body=patch_body,
        )

        result = {
            "action": "rollback",
            "deployment": params.deployment_name,
            "namespace": params.namespace,
            "rolled_back_to_revision": target_revision,
            "status": "rollback_initiated",
        }
        logger.info(
            "k8s_rollback_deployment completed",
            extra={
                "deployment": params.deployment_name,
                "revision": target_revision,
            },
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_rollback_deployment error", extra={"error": str(e)})
        return _api_error("k8s_rollback_deployment", e, f"deployment={params.deployment_name}")


# ---------------------------------------------------------------------------
# Tool 8: k8s_get_hpa
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_get_hpa",
    annotations={
        "title": "Get Horizontal Pod Autoscalers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_get_hpa(params: K8sGetHPAInput) -> str:
    """List HorizontalPodAutoscalers in a namespace with current/target metrics."""
    logger.debug(
        "k8s_get_hpa called",
        extra={"namespace": params.namespace},
    )

    try:
        autoscaling = get_autoscaling_client()
    except K8sUnavailableError as e:
        logger.warning("k8s_get_hpa: cluster unavailable")
        return _k8s_error(e)

    try:
        hpa_list = await asyncio.to_thread(
            autoscaling.list_namespaced_horizontal_pod_autoscaler,
            namespace=params.namespace,
        )

        hpas: list[dict[str, Any]] = []
        for hpa in hpa_list.items:
            metrics_info: list[dict[str, Any]] = []
            if hpa.spec and hpa.spec.metrics:
                for m in hpa.spec.metrics:
                    metric_entry: dict[str, Any] = {"type": m.type}
                    if m.resource:
                        metric_entry["resource_name"] = m.resource.name
                        if m.resource.target:
                            metric_entry["target_type"] = m.resource.target.type
                            if m.resource.target.average_utilization is not None:
                                metric_entry["target_average_utilization"] = (
                                    m.resource.target.average_utilization
                                )
                            if m.resource.target.average_value is not None:
                                metric_entry["target_average_value"] = str(
                                    m.resource.target.average_value
                                )
                    metrics_info.append(metric_entry)

            current_metrics: list[dict[str, Any]] = []
            if hpa.status and hpa.status.current_metrics:
                for cm in hpa.status.current_metrics:
                    cm_entry: dict[str, Any] = {"type": cm.type}
                    if cm.resource:
                        cm_entry["resource_name"] = cm.resource.name
                        if cm.resource.current:
                            if cm.resource.current.average_utilization is not None:
                                cm_entry["current_average_utilization"] = (
                                    cm.resource.current.average_utilization
                                )
                            if cm.resource.current.average_value is not None:
                                cm_entry["current_average_value"] = str(
                                    cm.resource.current.average_value
                                )
                    current_metrics.append(cm_entry)

            conditions: list[dict[str, str]] = []
            if hpa.status and hpa.status.conditions:
                for c in hpa.status.conditions:
                    conditions.append(
                        {
                            "type": c.type,
                            "status": c.status,
                            "reason": c.reason or "",
                            "message": c.message or "",
                        }
                    )

            hpas.append(
                {
                    "name": hpa.metadata.name,
                    "namespace": hpa.metadata.namespace,
                    "target_ref": (
                        f"{hpa.spec.scale_target_ref.kind}/{hpa.spec.scale_target_ref.name}"
                        if hpa.spec and hpa.spec.scale_target_ref
                        else "unknown"
                    ),
                    "min_replicas": hpa.spec.min_replicas if hpa.spec else None,
                    "max_replicas": hpa.spec.max_replicas if hpa.spec else None,
                    "current_replicas": (hpa.status.current_replicas if hpa.status else None),
                    "desired_replicas": (hpa.status.desired_replicas if hpa.status else None),
                    "metrics": metrics_info,
                    "current_metrics": current_metrics,
                    "conditions": conditions,
                }
            )

        result = {
            "namespace": params.namespace,
            "hpa_count": len(hpas),
            "hpas": hpas,
        }
        logger.info(
            "k8s_get_hpa completed",
            extra={"hpa_count": len(hpas)},
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_get_hpa error", extra={"error": str(e)})
        return _api_error("k8s_get_hpa", e, f"namespace={params.namespace}")


# ---------------------------------------------------------------------------
# Tool 9: k8s_list_namespaces
# ---------------------------------------------------------------------------


@mcp.tool(
    name="k8s_list_namespaces",
    annotations={
        "title": "List Kubernetes Namespaces",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_list_namespaces(params: K8sListNamespacesInput) -> str:
    """List all namespaces in the cluster with their status and labels."""
    logger.debug("k8s_list_namespaces called")

    try:
        v1, _ = get_clients()
    except K8sUnavailableError as e:
        logger.warning("k8s_list_namespaces: cluster unavailable")
        return _k8s_error(e)

    try:
        ns_list = await asyncio.to_thread(v1.list_namespace)

        namespaces: list[dict[str, Any]] = []
        for ns in ns_list.items:
            namespaces.append(
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase if ns.status else "Unknown",
                    "labels": ns.metadata.labels or {},
                    "creation_timestamp": str(ns.metadata.creation_timestamp),
                }
            )

        result = {
            "namespace_count": len(namespaces),
            "namespaces": namespaces,
        }
        logger.info(
            "k8s_list_namespaces completed",
            extra={"namespace_count": len(namespaces)},
        )
        return _json(result)

    except Exception as e:
        logger.error("k8s_list_namespaces error", extra={"error": str(e)})
        return _api_error("k8s_list_namespaces", e)
