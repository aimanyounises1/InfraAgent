"""Pydantic input/output models for k8s_mcp tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Input Models — Pods
# ---------------------------------------------------------------------------


class K8sListPodsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    label_selector: str | None = Field(
        default=None, description="Label selector (e.g., 'app=nginx')"
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max pods to return")


class K8sDescribePodInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    pod_name: str = Field(..., min_length=1, description="Name of the pod")


class K8sGetPodLogsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    pod_name: str = Field(..., min_length=1, description="Name of the pod")
    container: str | None = Field(
        default=None,
        description="Container name (required for multi-container pods)",
    )
    tail_lines: int = Field(default=100, ge=1, le=5000, description="Number of lines from the end")
    since_seconds: int | None = Field(default=None, ge=1, description="Logs since N seconds ago")


# ---------------------------------------------------------------------------
# Input Models — Deployments
# ---------------------------------------------------------------------------


class K8sListDeploymentsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    label_selector: str | None = Field(default=None, description="Label selector")


class K8sScaleDeploymentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    deployment_name: str = Field(..., min_length=1, description="Deployment name")
    replicas: int = Field(..., ge=0, le=100, description="Desired replica count")


class K8sRestartDeploymentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    deployment_name: str = Field(..., min_length=1, description="Deployment name")


# ---------------------------------------------------------------------------
# Input Models — Services
# ---------------------------------------------------------------------------


class K8sListServicesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")


# ---------------------------------------------------------------------------
# Input Models — Events
# ---------------------------------------------------------------------------


class K8sListEventsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str | None = Field(default=None, description="Namespace (all if omitted)")
    event_type: str | None = Field(default=None, description="Filter: Normal | Warning")
    limit: int = Field(default=50, ge=1, le=200, description="Max events")


# ---------------------------------------------------------------------------
# Input Models — Namespace Summary
# ---------------------------------------------------------------------------


class K8sGetNamespaceSummaryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")


# ---------------------------------------------------------------------------
# Input Models — Exec
# ---------------------------------------------------------------------------


class K8sExecCommandInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    pod_name: str = Field(..., min_length=1, description="Pod name")
    container: str | None = Field(default=None, description="Container name")
    command: list[str] = Field(..., min_length=1, description="Command and arguments")


# ---------------------------------------------------------------------------
# Input Models — Node Management (Phase 5)
# ---------------------------------------------------------------------------


class K8sGetNodeStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    node_name: str | None = Field(default=None, description="Node name (all if omitted)")


class K8sCordonNodeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    node_name: str = Field(..., min_length=1, description="Node name")


class K8sDrainNodeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    node_name: str = Field(..., min_length=1, description="Node name")
    grace_period: int = Field(default=30, ge=0, le=600)
    force: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Input Models — Rollout / Rollback (Phase 5)
# ---------------------------------------------------------------------------


class K8sRolloutStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default")
    deployment_name: str = Field(..., min_length=1)


class K8sRollbackDeploymentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default")
    deployment_name: str = Field(..., min_length=1)
    revision: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Input Models — HPA / Namespaces / ConfigMaps / Quotas (Phase 5)
# ---------------------------------------------------------------------------


class K8sGetHPAInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default")


class K8sListNamespacesInput(BaseModel):
    pass


class K8sGetConfigMapInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default")
    name: str = Field(..., min_length=1)


class K8sGetResourceQuotasInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default")


# ---------------------------------------------------------------------------
# Input Models — Slurm Expansion (Phase 5)
# ---------------------------------------------------------------------------


class SlurmSubmitJobInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    job_name: str = Field(..., min_length=1, max_length=100)
    partition: str = Field(default="batch")
    num_nodes: int = Field(default=1, ge=1, le=128)
    gpus_per_node: int = Field(default=0, ge=0, le=8)
    time_limit: str = Field(default="01:00:00")
    command: str = Field(..., min_length=1)


class SlurmCancelJobInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    job_id: str = Field(..., min_length=1)


class SlurmJobDetailInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    job_id: str = Field(..., min_length=1)
