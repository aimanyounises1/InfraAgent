"""Pod management tools for k8s_mcp."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from kubernetes import client

from config import settings
from mcp_servers.k8s_mcp.models import (  # noqa: TCH001
    K8sDescribePodInput,
    K8sExecCommandInput,
    K8sListPodsInput,
)
from mcp_servers.k8s_mcp.server import mcp
from mcp_servers.k8s_mcp.utils import (
    get_clients,
    get_mock_exec_output,
    get_mock_pod_detail,
    get_mock_pods,
)

logger = logging.getLogger(__name__)


def _serialize_pod(pod: Any) -> dict[str, Any]:
    """Extract relevant fields from a V1Pod object into a plain dict.

    Args:
        pod: A kubernetes.client.V1Pod object.

    Returns:
        Dictionary with pod summary fields.
    """
    containers: list[dict[str, Any]] = []
    if pod.status and pod.status.container_statuses:
        for cs in pod.status.container_statuses:
            container_info: dict[str, Any] = {
                "name": cs.name,
                "image": cs.image,
                "ready": cs.ready,
                "restart_count": cs.restart_count,
            }
            if cs.state:
                if cs.state.running:
                    container_info["state"] = "running"
                    container_info["started_at"] = str(
                        cs.state.running.started_at
                    )
                elif cs.state.waiting:
                    container_info["state"] = "waiting"
                    container_info["reason"] = cs.state.waiting.reason or ""
                elif cs.state.terminated:
                    container_info["state"] = "terminated"
                    container_info["reason"] = (
                        cs.state.terminated.reason or ""
                    )
                    container_info["exit_code"] = (
                        cs.state.terminated.exit_code
                    )
            containers.append(container_info)

    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "status": pod.status.phase if pod.status else "Unknown",
        "pod_ip": pod.status.pod_ip if pod.status else None,
        "node": pod.spec.node_name if pod.spec else None,
        "labels": pod.metadata.labels or {},
        "containers": containers,
        "start_time": (
            str(pod.status.start_time)
            if pod.status and pod.status.start_time
            else None
        ),
    }


@mcp.tool(
    name="k8s_list_pods",
    annotations={
        "title": "List Kubernetes Pods",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_list_pods(params: K8sListPodsInput) -> str:
    """List all pods in a namespace with their status, IP, and node assignment."""
    logger.debug(
        "k8s_list_pods called",
        extra={
            "namespace": params.namespace,
            "label_selector": params.label_selector,
            "limit": params.limit,
        },
    )

    if settings.mock_k8s:
        logger.info("k8s_list_pods using mock data")
        pods = get_mock_pods(
            namespace=params.namespace,
            label_selector=params.label_selector,
        )
        result = {
            "namespace": params.namespace,
            "pod_count": len(pods[: params.limit]),
            "pods": pods[: params.limit],
        }
        return json.dumps(result, indent=2, default=str)

    try:
        v1, _ = get_clients()

        kwargs: dict[str, Any] = {
            "namespace": params.namespace,
            "limit": params.limit,
        }
        if params.label_selector:
            kwargs["label_selector"] = params.label_selector

        pod_list = await asyncio.to_thread(
            v1.list_namespaced_pod,
            **kwargs,
        )

        pods = [_serialize_pod(p) for p in pod_list.items]
        result = {
            "namespace": params.namespace,
            "pod_count": len(pods),
            "pods": pods,
        }
        logger.info(
            "k8s_list_pods completed", extra={"pod_count": len(pods)}
        )
        return json.dumps(result, indent=2, default=str)

    except client.ApiException as e:
        logger.error(
            "k8s_list_pods API error",
            extra={"status": e.status, "reason": e.reason},
        )
        error = {
            "error": "Kubernetes API error",
            "status": e.status,
            "reason": e.reason,
            "details": (
                f"Failed to list pods in namespace '{params.namespace}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)
    except Exception as e:
        logger.error(
            "k8s_list_pods unexpected error", extra={"error": str(e)}
        )
        error = {
            "error": "Unexpected error",
            "message": str(e),
            "details": (
                f"Failed to list pods in namespace '{params.namespace}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)


@mcp.tool(
    name="k8s_describe_pod",
    annotations={
        "title": "Describe Kubernetes Pod",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def k8s_describe_pod(params: K8sDescribePodInput) -> str:
    """Get detailed pod info including events, conditions, and container statuses."""
    logger.debug(
        "k8s_describe_pod called",
        extra={
            "pod_name": params.pod_name,
            "namespace": params.namespace,
        },
    )

    if settings.mock_k8s:
        logger.info("k8s_describe_pod using mock data")
        detail = get_mock_pod_detail(
            name=params.pod_name, namespace=params.namespace
        )
        if detail is None:
            error = {
                "error": "Pod not found",
                "pod_name": params.pod_name,
                "namespace": params.namespace,
            }
            return json.dumps(error, indent=2, default=str)
        return _format_pod_detail_markdown(detail)

    try:
        v1, _ = get_clients()

        pod = await asyncio.to_thread(
            v1.read_namespaced_pod,
            name=params.pod_name,
            namespace=params.namespace,
        )

        events_response = await asyncio.to_thread(
            v1.list_namespaced_event,
            namespace=params.namespace,
            field_selector=f"involvedObject.name={params.pod_name}",
        )

        pod_data = _serialize_pod(pod)

        # Add conditions
        conditions: list[dict[str, Any]] = []
        if pod.status and pod.status.conditions:
            for c in pod.status.conditions:
                conditions.append({
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason or "",
                    "message": c.message or "",
                    "last_transition": str(c.last_transition_time),
                })
        pod_data["conditions"] = conditions

        # Add events
        events: list[dict[str, Any]] = []
        for ev in events_response.items:
            events.append({
                "type": ev.type,
                "reason": ev.reason,
                "message": ev.message,
                "count": ev.count,
                "first_seen": str(ev.first_timestamp),
                "last_seen": str(ev.last_timestamp),
            })
        pod_data["events"] = events

        logger.info(
            "k8s_describe_pod completed",
            extra={"pod_name": params.pod_name},
        )
        return _format_pod_detail_markdown(pod_data)

    except client.ApiException as e:
        logger.error(
            "k8s_describe_pod API error",
            extra={"status": e.status, "reason": e.reason},
        )
        if e.status == 404:
            error = {
                "error": "Pod not found",
                "pod_name": params.pod_name,
                "namespace": params.namespace,
            }
        else:
            error = {
                "error": "Kubernetes API error",
                "status": e.status,
                "reason": e.reason,
            }
        return json.dumps(error, indent=2, default=str)
    except Exception as e:
        logger.error(
            "k8s_describe_pod unexpected error", extra={"error": str(e)}
        )
        error = {
            "error": "Unexpected error",
            "message": str(e),
            "details": f"Failed to describe pod '{params.pod_name}'",
        }
        return json.dumps(error, indent=2, default=str)


def _format_pod_detail_markdown(pod: dict[str, Any]) -> str:
    """Format pod detail data as a Markdown string.

    Args:
        pod: Pod detail dictionary (from mock or real API).

    Returns:
        Markdown-formatted string with pod information.
    """
    lines: list[str] = []
    lines.append(f"# Pod: {pod['name']}")
    lines.append("")
    lines.append(f"**Namespace:** {pod['namespace']}")
    lines.append(f"**Status:** {pod['status']}")
    lines.append(f"**Pod IP:** {pod.get('pod_ip', 'N/A')}")
    lines.append(f"**Node:** {pod.get('node', 'N/A')}")
    lines.append(f"**Start Time:** {pod.get('start_time', 'N/A')}")

    # Labels
    labels = pod.get("labels", {})
    if labels:
        lines.append("")
        lines.append("## Labels")
        for k, v in labels.items():
            lines.append(f"- `{k}={v}`")

    # Containers
    containers = pod.get("containers", [])
    if containers:
        lines.append("")
        lines.append("## Containers")
        for c in containers:
            lines.append(f"### {c['name']}")
            lines.append(f"- **Image:** {c.get('image', 'N/A')}")
            lines.append(f"- **Ready:** {c.get('ready', 'N/A')}")
            lines.append(f"- **State:** {c.get('state', 'N/A')}")
            lines.append(f"- **Restart Count:** {c.get('restart_count', 0)}")
            if c.get("reason"):
                lines.append(f"- **Reason:** {c['reason']}")
            if c.get("started_at"):
                lines.append(f"- **Started At:** {c['started_at']}")

    # Conditions
    conditions = pod.get("conditions", [])
    if conditions:
        lines.append("")
        lines.append("## Conditions")
        lines.append("| Type | Status |")
        lines.append("|------|--------|")
        for cond in conditions:
            lines.append(f"| {cond['type']} | {cond['status']} |")

    # Events
    events = pod.get("events", [])
    if events:
        lines.append("")
        lines.append("## Events")
        for ev in events:
            count = ev.get("count", 1)
            ev_type = ev.get("type", "Normal")
            reason = ev.get("reason", "")
            message = ev.get("message", "")
            lines.append(
                f"- **[{ev_type}]** {reason}: {message} (x{count})"
            )

    return "\n".join(lines)


@mcp.tool(
    name="k8s_exec_command",
    annotations={
        "title": "Execute Command in Pod",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def k8s_exec_command(params: K8sExecCommandInput) -> str:
    """Execute a command inside a pod container."""
    logger.debug(
        "k8s_exec_command called",
        extra={
            "pod_name": params.pod_name,
            "namespace": params.namespace,
            "command": params.command,
        },
    )

    if settings.mock_k8s:
        logger.info("k8s_exec_command using mock data")
        output = get_mock_exec_output(params.command)
        result = {
            "pod": params.pod_name,
            "namespace": params.namespace,
            "command": params.command,
            "output": output,
            "exit_code": 0,
        }
        return json.dumps(result, indent=2, default=str)

    try:
        from kubernetes.stream import stream

        v1, _ = get_clients()

        kwargs: dict[str, Any] = {
            "name": params.pod_name,
            "namespace": params.namespace,
            "command": params.command,
            "stderr": True,
            "stdin": False,
            "stdout": True,
            "tty": False,
        }
        if params.container:
            kwargs["container"] = params.container

        output = await asyncio.to_thread(
            stream,
            v1.connect_get_namespaced_pod_exec,
            **kwargs,
        )

        result = {
            "pod": params.pod_name,
            "namespace": params.namespace,
            "command": params.command,
            "output": output,
            "exit_code": 0,
        }
        logger.info(
            "k8s_exec_command completed",
            extra={"pod_name": params.pod_name},
        )
        return json.dumps(result, indent=2, default=str)

    except client.ApiException as e:
        logger.error(
            "k8s_exec_command API error",
            extra={"status": e.status, "reason": e.reason},
        )
        error = {
            "error": "Kubernetes API error",
            "status": e.status,
            "reason": e.reason,
            "details": f"Failed to exec in pod '{params.pod_name}'",
        }
        return json.dumps(error, indent=2, default=str)
    except Exception as e:
        logger.error(
            "k8s_exec_command unexpected error", extra={"error": str(e)}
        )
        error = {
            "error": "Unexpected error",
            "message": str(e),
            "details": (
                f"Failed to exec command in pod '{params.pod_name}'"
            ),
        }
        return json.dumps(error, indent=2, default=str)
