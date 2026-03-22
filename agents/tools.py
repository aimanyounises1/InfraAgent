"""LangChain @tool wrappers for all MCP tool functions.

Each wrapper delegates to the underlying MCP tool function, translating
simple Python arguments into the Pydantic input models the MCP tools expect.
These wrappers are used by the LangGraph StateGraph agent (via
model.bind_tools()) so the LLM can call tools via LangChain's standard
tool-calling protocol.

All tools are async, matching the async MCP tool implementations.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kubernetes Tools
# ---------------------------------------------------------------------------


@tool
async def list_pods(namespace: str = "default") -> str:
    """List all Kubernetes pods in a namespace with their status, node, and restart counts.

    Use this to check cluster health, find failing pods, or get an overview of
    what is running. Returns JSON with pod_count and a list of pods.

    Args:
        namespace: Kubernetes namespace to query (default: "default").
    """
    from mcp_servers.k8s_mcp.models import K8sListPodsInput
    from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods

    return await k8s_list_pods(K8sListPodsInput(namespace=namespace))


@tool
async def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Get detailed information about a specific Kubernetes pod including events and conditions.

    Use this when you need to investigate a specific pod -- for example when
    it is in CrashLoopBackOff or has high restart counts.

    Args:
        pod_name: Name of the pod to describe.
        namespace: Kubernetes namespace (default: "default").
    """
    from mcp_servers.k8s_mcp.models import K8sDescribePodInput
    from mcp_servers.k8s_mcp.tools.pods import k8s_describe_pod

    return await k8s_describe_pod(
        K8sDescribePodInput(pod_name=pod_name, namespace=namespace)
    )


@tool
async def get_pod_logs(
    pod_name: str,
    namespace: str = "default",
    tail_lines: int = 100,
) -> str:
    """Retrieve the most recent log lines from a Kubernetes pod.

    Use this to diagnose errors, check startup messages, or investigate
    application behavior.

    Args:
        pod_name: Name of the pod whose logs to fetch.
        namespace: Kubernetes namespace (default: "default").
        tail_lines: Number of log lines from the end (default: 100, max: 5000).
    """
    from mcp_servers.k8s_mcp.models import K8sGetPodLogsInput
    from mcp_servers.k8s_mcp.tools.logs import k8s_get_pod_logs

    return await k8s_get_pod_logs(
        K8sGetPodLogsInput(
            pod_name=pod_name,
            namespace=namespace,
            tail_lines=min(tail_lines, 5000),
        )
    )


@tool
async def list_deployments(namespace: str = "default") -> str:
    """List all Kubernetes deployments in a namespace with replica counts and rollout status.

    Use this to see which deployments exist, how many replicas are ready,
    and whether any deployments are degraded.

    Args:
        namespace: Kubernetes namespace to query (default: "default").
    """
    from mcp_servers.k8s_mcp.models import K8sListDeploymentsInput
    from mcp_servers.k8s_mcp.tools.deployments import k8s_list_deployments

    return await k8s_list_deployments(
        K8sListDeploymentsInput(namespace=namespace)
    )


@tool
async def scale_deployment(
    deployment_name: str,
    replicas: int,
    namespace: str = "default",
) -> str:
    """Scale a Kubernetes deployment to the specified number of replicas.

    WARNING: This is a mutating action. Only call this when the user explicitly
    asks to scale a deployment.

    Args:
        deployment_name: Name of the deployment to scale.
        replicas: Desired replica count (0-100).
        namespace: Kubernetes namespace (default: "default").
    """
    from mcp_servers.k8s_mcp.models import K8sScaleDeploymentInput
    from mcp_servers.k8s_mcp.tools.deployments import k8s_scale_deployment

    return await k8s_scale_deployment(
        K8sScaleDeploymentInput(
            deployment_name=deployment_name,
            replicas=replicas,
            namespace=namespace,
        )
    )


@tool
async def restart_deployment(
    deployment_name: str,
    namespace: str = "default",
) -> str:
    """Perform a rolling restart of a Kubernetes deployment.

    WARNING: This is a mutating action. Only call this when the user explicitly
    asks to restart a deployment.

    Args:
        deployment_name: Name of the deployment to restart.
        namespace: Kubernetes namespace (default: "default").
    """
    from mcp_servers.k8s_mcp.models import K8sRestartDeploymentInput
    from mcp_servers.k8s_mcp.tools.deployments import k8s_restart_deployment

    return await k8s_restart_deployment(
        K8sRestartDeploymentInput(
            deployment_name=deployment_name,
            namespace=namespace,
        )
    )


@tool
async def list_services(namespace: str = "default") -> str:
    """List all Kubernetes services in a namespace with type, cluster IP, and ports.

    Use this to see the networking layer -- which services expose which ports,
    their types (ClusterIP, NodePort, LoadBalancer), and selectors.

    Args:
        namespace: Kubernetes namespace to query (default: "default").
    """
    from mcp_servers.k8s_mcp.models import K8sListServicesInput
    from mcp_servers.k8s_mcp.tools.services import k8s_list_services

    return await k8s_list_services(
        K8sListServicesInput(namespace=namespace)
    )


# ---------------------------------------------------------------------------
# GPU Tools
# ---------------------------------------------------------------------------


@tool
async def list_gpu_devices() -> str:
    """List all GPU devices with name, total memory, and driver version.

    Use this to discover what GPUs are available in the cluster.
    """
    from mcp_servers.gpu_mcp.models import GpuListDevicesInput
    from mcp_servers.gpu_mcp.tools.monitor import gpu_list_devices

    return await gpu_list_devices(GpuListDevicesInput())


@tool
async def get_gpu_utilization(device_index: int = 0) -> str:
    """Get real-time GPU and memory utilization percentages for a specific device.

    Args:
        device_index: GPU device index (default: 0).
    """
    from mcp_servers.gpu_mcp.models import GpuDeviceIndexInput
    from mcp_servers.gpu_mcp.tools.monitor import gpu_get_utilization

    return await gpu_get_utilization(
        GpuDeviceIndexInput(device_index=device_index)
    )


@tool
async def get_gpu_memory(device_index: int = 0) -> str:
    """Get free, used, and total memory for a specific GPU device.

    Args:
        device_index: GPU device index (default: 0).
    """
    from mcp_servers.gpu_mcp.models import GpuDeviceIndexInput
    from mcp_servers.gpu_mcp.tools.monitor import gpu_get_memory

    return await gpu_get_memory(
        GpuDeviceIndexInput(device_index=device_index)
    )


@tool
async def get_gpu_temperature(device_index: int = 0) -> str:
    """Get temperature and thermal throttle status for a specific GPU device.

    Args:
        device_index: GPU device index (default: 0).
    """
    from mcp_servers.gpu_mcp.models import GpuDeviceIndexInput
    from mcp_servers.gpu_mcp.tools.monitor import gpu_get_temperature

    return await gpu_get_temperature(
        GpuDeviceIndexInput(device_index=device_index)
    )


@tool
async def get_gpu_cluster_summary() -> str:
    """Get an aggregate summary of GPU stats across all devices.

    Returns device count, average utilization, total/used memory,
    hottest device, and most loaded device. Use this for a quick
    overview of the entire GPU cluster.
    """
    from mcp_servers.gpu_mcp.models import GpuClusterSummaryInput
    from mcp_servers.gpu_mcp.tools.monitor import gpu_get_cluster_summary

    return await gpu_get_cluster_summary(GpuClusterSummaryInput())


@tool
async def gpu_health_check() -> str:
    """Run a comprehensive health check across all GPU devices.

    Checks temperature, utilization, memory, and ECC errors for each device.
    Returns per-device breakdown and overall cluster health status
    (healthy, warning, or critical).
    """
    from mcp_servers.gpu_mcp.models import GpuHealthCheckInput
    from mcp_servers.gpu_mcp.tools.health import gpu_health_check as _gpu_health_check

    return await _gpu_health_check(GpuHealthCheckInput())


@tool
async def list_gpu_processes(device_index: int = 0) -> str:
    """List processes running on a GPU with PID, name, and memory usage.

    Use this to find what workloads are consuming GPU resources.

    Args:
        device_index: GPU device index (default: 0).
    """
    from mcp_servers.gpu_mcp.models import GpuDeviceIndexInput
    from mcp_servers.gpu_mcp.tools.processes import gpu_list_processes

    return await gpu_list_processes(
        GpuDeviceIndexInput(device_index=device_index)
    )


# ---------------------------------------------------------------------------
# Incident Tools
# ---------------------------------------------------------------------------


@tool
async def create_jira_ticket(
    project_key: str = "OPS",
    summary: str = "Incident reported via InfraAgent",
    description: str = "",
    priority: str = "High",
) -> str:
    """Create a Jira incident ticket with summary, description, and priority.

    WARNING: This creates a real ticket. Only call when the user explicitly
    asks to create a ticket.

    Args:
        project_key: Jira project key (default: "OPS").
        summary: Ticket summary/title.
        description: Ticket description in Markdown.
        priority: Priority level: Highest, High, Medium, Low, Lowest.
    """
    from mcp_servers.incident_mcp.models import JiraCreateTicketInput
    from mcp_servers.incident_mcp.tools.jira_tools import incident_jira_create_ticket

    return await incident_jira_create_ticket(
        JiraCreateTicketInput(
            project_key=project_key,
            summary=summary,
            description=description,
            issue_type="Incident",
            priority=priority,
            labels=["infraagent", "auto-created"],
        )
    )


@tool
async def search_jira(jql: str) -> str:
    """Search Jira for related incidents using a JQL query string.

    Use this to find past incidents, related tickets, or check if a similar
    issue has been reported before.

    Args:
        jql: JQL query string (e.g., 'text ~ "database outage" ORDER BY created DESC').
    """
    from mcp_servers.incident_mcp.models import JiraSearchInput
    from mcp_servers.incident_mcp.tools.jira_tools import incident_jira_search

    return await incident_jira_search(JiraSearchInput(jql=jql))


@tool
async def get_grafana_alerts(state: str = "") -> str:
    """Get active Grafana alerts with optional state filter.

    Use this to check what alerts are currently firing or pending.

    Args:
        state: Optional filter: "alerting", "pending", "ok", or empty for all.
    """
    from mcp_servers.incident_mcp.models import GrafanaGetAlertsInput
    from mcp_servers.incident_mcp.tools.grafana_tools import incident_grafana_get_alerts

    return await incident_grafana_get_alerts(
        GrafanaGetAlertsInput(state=state or None)
    )


@tool
async def query_grafana_metrics(query: str) -> str:
    """Query Grafana for metrics using a PromQL expression.

    Use this to pull specific metrics data for investigation.

    Args:
        query: PromQL query string (e.g., 'rate(http_requests_total{status=~"5.."}[5m])').
    """
    from mcp_servers.incident_mcp.models import GrafanaQueryInput
    from mcp_servers.incident_mcp.tools.grafana_tools import incident_grafana_query

    return await incident_grafana_query(GrafanaQueryInput(query=query))


@tool
async def list_pagerduty_incidents(status: str = "triggered,acknowledged") -> str:
    """List active PagerDuty incidents with optional status filter.

    Use this to see what incidents are currently open and need attention.

    Args:
        status: Status filter (default: "triggered,acknowledged").
    """
    from mcp_servers.incident_mcp.models import PagerDutyListIncidentsInput
    from mcp_servers.incident_mcp.tools.pagerduty_tools import (
        incident_pagerduty_list_incidents,
    )

    return await incident_pagerduty_list_incidents(
        PagerDutyListIncidentsInput(status=status)
    )


@tool
async def acknowledge_incident(incident_id: str) -> str:
    """Acknowledge a PagerDuty incident to signal that someone is working on it.

    WARNING: This is a mutating action. Only call when the user explicitly
    asks to acknowledge an incident.

    Args:
        incident_id: PagerDuty incident ID (e.g., "PABC123").
    """
    from mcp_servers.incident_mcp.models import PagerDutyAcknowledgeInput
    from mcp_servers.incident_mcp.tools.pagerduty_tools import (
        incident_pagerduty_acknowledge,
    )

    return await incident_pagerduty_acknowledge(
        PagerDutyAcknowledgeInput(incident_id=incident_id)
    )


@tool
async def resolve_incident(incident_id: str) -> str:
    """Resolve a PagerDuty incident to mark it as fixed.

    WARNING: This is a mutating action. Only call when the user explicitly
    asks to resolve an incident.

    Args:
        incident_id: PagerDuty incident ID (e.g., "PXYZ789").
    """
    from mcp_servers.incident_mcp.models import PagerDutyResolveInput
    from mcp_servers.incident_mcp.tools.pagerduty_tools import (
        incident_pagerduty_resolve,
    )

    return await incident_pagerduty_resolve(
        PagerDutyResolveInput(incident_id=incident_id)
    )


@tool
async def generate_rca(incident_summary: str) -> str:
    """Generate a Root Cause Analysis report from an incident description.

    Produces a structured Markdown report with investigation findings,
    impact assessment, and remediation steps.

    Args:
        incident_summary: Brief description of the incident to analyze.
    """
    from mcp_servers.incident_mcp.models import GenerateRCAInput
    from mcp_servers.incident_mcp.tools.rca import incident_generate_rca

    return await incident_generate_rca(
        GenerateRCAInput(incident_summary=incident_summary)
    )


# ---------------------------------------------------------------------------
# Tool groups for each agent
# ---------------------------------------------------------------------------

K8S_TOOLS: list = [
    list_pods,
    describe_pod,
    get_pod_logs,
    list_deployments,
    scale_deployment,
    restart_deployment,
    list_services,
]

GPU_TOOLS: list = [
    list_gpu_devices,
    get_gpu_utilization,
    get_gpu_memory,
    get_gpu_temperature,
    get_gpu_cluster_summary,
    gpu_health_check,
    list_gpu_processes,
]

INCIDENT_TOOLS: list = [
    create_jira_ticket,
    search_jira,
    get_grafana_alerts,
    query_grafana_metrics,
    list_pagerduty_incidents,
    acknowledge_incident,
    resolve_incident,
    generate_rca,
]
