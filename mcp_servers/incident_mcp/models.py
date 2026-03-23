"""Pydantic input/output models for incident_mcp tools."""

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Jira Models
# ---------------------------------------------------------------------------


class JiraCreateTicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    project_key: str = Field(..., min_length=1, description="Jira project key (e.g., 'OPS')")
    summary: str = Field(..., min_length=1, max_length=255, description="Ticket summary")
    description: str = Field(default="", description="Ticket description (Markdown)")
    issue_type: str = Field(default="Bug", description="Issue type: Bug, Task, Incident")
    priority: str = Field(
        default="High",
        description="Priority: Highest, High, Medium, Low, Lowest",
    )
    labels: list[str] = Field(default_factory=list, description="Labels to apply")


class JiraSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    jql: str = Field(..., min_length=1, description="JQL query string")
    max_results: int = Field(default=20, ge=1, le=100, description="Max results")


class JiraUpdateTicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    issue_key: str = Field(..., min_length=1, description="Issue key (e.g., 'OPS-123')")
    status: str | None = Field(default=None, description="New status")
    assignee: str | None = Field(default=None, description="Assignee email")
    comment: str | None = Field(default=None, description="Comment to add")


# ---------------------------------------------------------------------------
# Grafana Models
# ---------------------------------------------------------------------------


class GrafanaQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(..., min_length=1, description="PromQL query")
    start: str | None = Field(default=None, description="Start time (ISO 8601 or relative)")
    end: str | None = Field(default=None, description="End time")
    step: str = Field(default="60s", description="Query resolution step")


class GrafanaGetAlertsInput(BaseModel):
    state: str | None = Field(default=None, description="Filter: alerting, pending, ok")


class GrafanaGetDashboardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    dashboard_uid: str = Field(..., min_length=1, description="Dashboard UID")


# ---------------------------------------------------------------------------
# PagerDuty Models
# ---------------------------------------------------------------------------


class PagerDutyListIncidentsInput(BaseModel):
    status: str | None = Field(default="triggered,acknowledged", description="Status filter")
    limit: int = Field(default=25, ge=1, le=100, description="Max incidents")


class PagerDutyAcknowledgeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    incident_id: str = Field(..., min_length=1, description="PagerDuty incident ID")


class PagerDutyResolveInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    incident_id: str = Field(..., min_length=1, description="PagerDuty incident ID")


# ---------------------------------------------------------------------------
# RCA Models
# ---------------------------------------------------------------------------


class GenerateRCAInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    incident_summary: str = Field(..., min_length=1, description="Brief incident description")
    metrics_data: str | None = Field(default=None, description="Grafana metrics JSON")
    related_tickets: str | None = Field(default=None, description="Related Jira tickets JSON")
    timeline: str | None = Field(default=None, description="Event timeline JSON")


# ---------------------------------------------------------------------------
# Alert Correlation Models (Phase 5)
# ---------------------------------------------------------------------------


class CorrelateAlertsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    time_window_minutes: int = Field(default=30, ge=5, le=1440)
    min_alerts: int = Field(default=2, ge=2, le=100)


class DetectChangesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    namespace: str = Field(default="default")
    lookback_minutes: int = Field(default=60, ge=5, le=1440)


class GeneratePostmortemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    incident_id: str = Field(..., min_length=1)
    include_metrics: bool = Field(default=True)
    include_timeline: bool = Field(default=True)
