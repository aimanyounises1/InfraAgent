"""Pydantic input/output models for k8s_mcp tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Input Models
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
    tail_lines: int = Field(
        default=100, ge=1, le=5000, description="Number of lines from the end"
    )
    since_seconds: int | None = Field(
        default=None, ge=1, description="Logs since N seconds ago"
    )


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


class K8sListServicesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")


class K8sListEventsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str | None = Field(
        default=None, description="Namespace (all if omitted)"
    )
    event_type: str | None = Field(
        default=None, description="Filter: Normal | Warning"
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max events")


class K8sGetNamespaceSummaryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")


class K8sExecCommandInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default", description="Kubernetes namespace")
    pod_name: str = Field(..., min_length=1, description="Pod name")
    container: str | None = Field(default=None, description="Container name")
    command: list[str] = Field(..., min_length=1, description="Command and arguments")
