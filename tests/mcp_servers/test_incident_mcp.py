"""Tests for incident_mcp server tools.

All tests run in mock mode (settings.mock_* = True by default).
"""

import json

import pytest
from pydantic import ValidationError

from mcp_servers.incident_mcp.models import (
    GenerateRCAInput,
    GrafanaGetAlertsInput,
    GrafanaGetDashboardInput,
    GrafanaQueryInput,
    JiraCreateTicketInput,
    JiraSearchInput,
    JiraUpdateTicketInput,
    PagerDutyAcknowledgeInput,
    PagerDutyListIncidentsInput,
    PagerDutyResolveInput,
)
from mcp_servers.incident_mcp.tools.grafana_tools import (
    incident_grafana_get_alerts,
    incident_grafana_get_dashboard,
    incident_grafana_query,
)
from mcp_servers.incident_mcp.tools.jira_tools import (
    incident_jira_create_ticket,
    incident_jira_search,
    incident_jira_update_ticket,
)
from mcp_servers.incident_mcp.tools.pagerduty_tools import (
    incident_pagerduty_acknowledge,
    incident_pagerduty_list_incidents,
    incident_pagerduty_resolve,
)
from mcp_servers.incident_mcp.tools.rca import incident_generate_rca
from mcp_servers.incident_mcp.utils import (
    get_mock_grafana_alerts,
    get_mock_grafana_dashboard,
    get_mock_grafana_metrics,
    get_mock_jira_tickets,
    get_mock_pd_incidents,
)

# ---------------------------------------------------------------------------
# Mock Data Generator Tests
# ---------------------------------------------------------------------------


class TestMockDataGenerators:
    """Verify the mock data helpers return well-structured data."""

    def test_mock_jira_tickets_returns_list(self) -> None:
        tickets = get_mock_jira_tickets()
        assert isinstance(tickets, list)
        assert len(tickets) >= 3

    def test_mock_jira_tickets_have_required_fields(self) -> None:
        tickets = get_mock_jira_tickets()
        for t in tickets:
            assert "key" in t
            assert "fields" in t
            assert "summary" in t["fields"]
            assert "status" in t["fields"]

    def test_mock_jira_tickets_jql_filter(self) -> None:
        tickets = get_mock_jira_tickets(jql="redis")
        assert any("redis" in t["fields"]["summary"].lower() for t in tickets)

    def test_mock_grafana_metrics_structure(self) -> None:
        data = get_mock_grafana_metrics(query="node_cpu_seconds_total")
        assert data["status"] == "success"
        assert "data" in data
        results = data["data"]["result"]
        assert len(results) > 0
        assert len(results[0]["values"]) == 10

    def test_mock_grafana_alerts_returns_list(self) -> None:
        alerts = get_mock_grafana_alerts()
        assert isinstance(alerts, list)
        assert len(alerts) >= 2

    def test_mock_grafana_alerts_state_filter(self) -> None:
        firing = get_mock_grafana_alerts(state="firing")
        assert all(a["state"] == "firing" for a in firing)

    def test_mock_grafana_alerts_state_filter_resolved(self) -> None:
        resolved = get_mock_grafana_alerts(state="resolved")
        assert all(a["state"] == "resolved" for a in resolved)

    def test_mock_grafana_dashboard_structure(self) -> None:
        dash = get_mock_grafana_dashboard(uid="abc123")
        assert dash["dashboard"]["uid"] == "abc123"
        assert len(dash["dashboard"]["panels"]) >= 3

    def test_mock_pd_incidents_returns_list(self) -> None:
        incidents = get_mock_pd_incidents()
        assert isinstance(incidents, list)
        assert len(incidents) >= 1

    def test_mock_pd_incidents_status_filter(self) -> None:
        triggered = get_mock_pd_incidents(status="triggered")
        assert all(i["status"] == "triggered" for i in triggered)

    def test_mock_pd_incidents_multi_status_filter(self) -> None:
        multi = get_mock_pd_incidents(status="triggered,acknowledged")
        assert all(i["status"] in ("triggered", "acknowledged") for i in multi)


# ---------------------------------------------------------------------------
# Jira Tool Tests
# ---------------------------------------------------------------------------


class TestJiraCreateTicket:
    """Tests for incident_jira_create_ticket tool."""

    @pytest.mark.asyncio
    async def test_create_ticket_mock_mode(self, mock_httpx_client) -> None:
        """Should create a ticket in mock mode and return valid JSON."""
        params = JiraCreateTicketInput(
            project_key="OPS",
            summary="Test incident: API latency spike",
            description="Investigating high p99 latency",
            issue_type="Incident",
            priority="High",
            labels=["production", "api"],
        )
        result = await incident_jira_create_ticket(params)
        data = json.loads(result)

        assert "key" in data
        assert data["key"].startswith("OPS-")
        assert data["fields"]["summary"] == "Test incident: API latency spike"
        assert data["fields"]["priority"]["name"] == "High"
        assert data["fields"]["status"]["name"] == "Open"
        assert "production" in data["fields"]["labels"]

    def test_create_ticket_input_validation(self) -> None:
        """Should validate required fields."""
        with pytest.raises(ValidationError):
            JiraCreateTicketInput(project_key="", summary="")

    def test_create_ticket_defaults(self) -> None:
        """Should apply default values correctly."""
        params = JiraCreateTicketInput(project_key="INFRA", summary="Test")
        assert params.issue_type == "Bug"
        assert params.priority == "High"
        assert params.labels == []


class TestJiraSearch:
    """Tests for incident_jira_search tool."""

    @pytest.mark.asyncio
    async def test_search_mock_mode(self, mock_httpx_client) -> None:
        """Should return search results in mock mode."""
        params = JiraSearchInput(jql="project=INFRA", max_results=10)
        result = await incident_jira_search(params)
        data = json.loads(result)

        assert "issues" in data
        assert "total" in data
        assert isinstance(data["issues"], list)
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, mock_httpx_client) -> None:
        """Should limit results to max_results."""
        params = JiraSearchInput(jql="project=INFRA", max_results=2)
        result = await incident_jira_search(params)
        data = json.loads(result)
        assert len(data["issues"]) <= 2

    def test_search_input_validation(self) -> None:
        """Should reject empty JQL."""
        with pytest.raises(ValidationError):
            JiraSearchInput(jql="")


class TestJiraUpdateTicket:
    """Tests for incident_jira_update_ticket tool."""

    @pytest.mark.asyncio
    async def test_update_ticket_status_mock(self, mock_httpx_client) -> None:
        """Should update status in mock mode."""
        params = JiraUpdateTicketInput(issue_key="INFRA-101", status="Resolved")
        result = await incident_jira_update_ticket(params)
        data = json.loads(result)

        assert data["success"] is True
        assert data["issue_key"] == "INFRA-101"
        assert any("status" in u for u in data["updates_applied"])

    @pytest.mark.asyncio
    async def test_update_ticket_comment_mock(self, mock_httpx_client) -> None:
        """Should add comment in mock mode."""
        params = JiraUpdateTicketInput(
            issue_key="INFRA-102",
            comment="Incident resolved by scaling up.",
        )
        result = await incident_jira_update_ticket(params)
        data = json.loads(result)

        assert data["success"] is True
        assert any("comment" in u for u in data["updates_applied"])

    @pytest.mark.asyncio
    async def test_update_ticket_multiple_fields(self, mock_httpx_client) -> None:
        """Should handle multiple simultaneous updates."""
        params = JiraUpdateTicketInput(
            issue_key="INFRA-103",
            status="In Progress",
            assignee="alice@example.com",
            comment="Taking ownership.",
        )
        result = await incident_jira_update_ticket(params)
        data = json.loads(result)

        assert data["success"] is True
        assert len(data["updates_applied"]) == 3

    def test_update_ticket_input_validation(self) -> None:
        """Should reject empty issue key."""
        with pytest.raises(ValidationError):
            JiraUpdateTicketInput(issue_key="")


# ---------------------------------------------------------------------------
# Grafana Tool Tests
# ---------------------------------------------------------------------------


class TestGrafanaQuery:
    """Tests for incident_grafana_query tool."""

    @pytest.mark.asyncio
    async def test_query_metrics(self, mock_httpx_client) -> None:
        """Should execute a PromQL query and return time-series data."""
        params = GrafanaQueryInput(query="rate(http_requests_total[5m])")
        result = await incident_grafana_query(params)
        data = json.loads(result)

        assert data["status"] == "success"
        assert "data" in data
        assert len(data["data"]["result"]) > 0
        assert len(data["data"]["result"][0]["values"]) > 0

    @pytest.mark.asyncio
    async def test_query_with_time_range(self, mock_httpx_client) -> None:
        """Should accept optional time range parameters."""
        params = GrafanaQueryInput(
            query="node_cpu_seconds_total",
            start="2024-01-01T00:00:00Z",
            end="2024-01-01T01:00:00Z",
            step="30s",
        )
        result = await incident_grafana_query(params)
        data = json.loads(result)
        assert data["status"] == "success"

    def test_query_input_validation(self) -> None:
        """Should reject empty query."""
        with pytest.raises(ValidationError):
            GrafanaQueryInput(query="")


class TestGrafanaGetAlerts:
    """Tests for incident_grafana_get_alerts tool."""

    @pytest.mark.asyncio
    async def test_get_all_alerts(self, mock_httpx_client) -> None:
        """Should return all alerts without filter."""
        params = GrafanaGetAlertsInput()
        result = await incident_grafana_get_alerts(params)
        data = json.loads(result)

        assert "alerts" in data
        assert "total" in data
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_get_firing_alerts(self, mock_httpx_client) -> None:
        """Should filter to only firing alerts."""
        params = GrafanaGetAlertsInput(state="firing")
        result = await incident_grafana_get_alerts(params)
        data = json.loads(result)

        assert data["total"] >= 1
        for alert in data["alerts"]:
            assert alert["state"] == "firing"


class TestGrafanaGetDashboard:
    """Tests for incident_grafana_get_dashboard tool."""

    @pytest.mark.asyncio
    async def test_get_dashboard(self, mock_httpx_client) -> None:
        """Should return dashboard structure with panels."""
        params = GrafanaGetDashboardInput(dashboard_uid="infra-overview")
        result = await incident_grafana_get_dashboard(params)
        data = json.loads(result)

        assert "dashboard" in data
        assert data["dashboard"]["uid"] == "infra-overview"
        assert len(data["dashboard"]["panels"]) >= 3

    def test_dashboard_input_validation(self) -> None:
        """Should reject empty UID."""
        with pytest.raises(ValidationError):
            GrafanaGetDashboardInput(dashboard_uid="")


# ---------------------------------------------------------------------------
# PagerDuty Tool Tests
# ---------------------------------------------------------------------------


class TestPagerDutyListIncidents:
    """Tests for incident_pagerduty_list_incidents tool."""

    @pytest.mark.asyncio
    async def test_list_incidents_default(self, mock_httpx_client) -> None:
        """Should list incidents with default filters."""
        params = PagerDutyListIncidentsInput()
        result = await incident_pagerduty_list_incidents(params)
        data = json.loads(result)

        assert "incidents" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_triggered_incidents(self, mock_httpx_client) -> None:
        """Should filter to only triggered incidents."""
        params = PagerDutyListIncidentsInput(status="triggered")
        result = await incident_pagerduty_list_incidents(params)
        data = json.loads(result)

        for inc in data["incidents"]:
            assert inc["status"] == "triggered"

    @pytest.mark.asyncio
    async def test_list_incidents_respects_limit(self, mock_httpx_client) -> None:
        """Should respect the limit parameter."""
        params = PagerDutyListIncidentsInput(status="triggered,acknowledged", limit=1)
        result = await incident_pagerduty_list_incidents(params)
        data = json.loads(result)
        assert len(data["incidents"]) <= 1


class TestPagerDutyAcknowledge:
    """Tests for incident_pagerduty_acknowledge tool."""

    @pytest.mark.asyncio
    async def test_acknowledge_incident(self, mock_httpx_client) -> None:
        """Should acknowledge an incident in mock mode."""
        params = PagerDutyAcknowledgeInput(incident_id="P1ABC23")
        result = await incident_pagerduty_acknowledge(params)
        data = json.loads(result)

        assert data["incident"]["id"] == "P1ABC23"
        assert data["incident"]["status"] == "acknowledged"

    def test_acknowledge_input_validation(self) -> None:
        """Should reject empty incident ID."""
        with pytest.raises(ValidationError):
            PagerDutyAcknowledgeInput(incident_id="")


class TestPagerDutyResolve:
    """Tests for incident_pagerduty_resolve tool."""

    @pytest.mark.asyncio
    async def test_resolve_incident(self, mock_httpx_client) -> None:
        """Should resolve an incident in mock mode."""
        params = PagerDutyResolveInput(incident_id="P2DEF45")
        result = await incident_pagerduty_resolve(params)
        data = json.loads(result)

        assert data["incident"]["id"] == "P2DEF45"
        assert data["incident"]["status"] == "resolved"

    def test_resolve_input_validation(self) -> None:
        """Should reject empty incident ID."""
        with pytest.raises(ValidationError):
            PagerDutyResolveInput(incident_id="")


# ---------------------------------------------------------------------------
# RCA Tool Tests
# ---------------------------------------------------------------------------


class TestGenerateRCA:
    """Tests for incident_generate_rca tool."""

    @pytest.mark.asyncio
    async def test_generate_basic_rca(self, mock_httpx_client) -> None:
        """Should generate an RCA report with summary only."""
        params = GenerateRCAInput(
            incident_summary=("API latency spike caused by CPU exhaustion on api-server-01"),
        )
        result = await incident_generate_rca(params)

        assert "# Root Cause Analysis Report" in result
        assert "API latency spike" in result
        assert "## Summary" in result
        assert "## Root Cause" in result
        assert "## Impact Assessment" in result
        assert "## Remediation Steps" in result
        assert "## Prevention" in result

    @pytest.mark.asyncio
    async def test_generate_rca_with_metrics(self, mock_httpx_client) -> None:
        """Should include metrics data in the report."""
        metrics = json.dumps({"cpu_usage": 94.2, "memory_usage": 78.5})
        params = GenerateRCAInput(
            incident_summary="High CPU on production",
            metrics_data=metrics,
        )
        result = await incident_generate_rca(params)

        assert "Key Metrics" in result
        assert "cpu_usage" in result

    @pytest.mark.asyncio
    async def test_generate_rca_with_tickets(self, mock_httpx_client) -> None:
        """Should include related tickets in the report."""
        tickets = json.dumps(
            [
                {
                    "key": "INFRA-101",
                    "fields": {
                        "summary": "CPU spike",
                        "status": {"name": "Open"},
                    },
                }
            ]
        )
        params = GenerateRCAInput(
            incident_summary="CPU incident",
            related_tickets=tickets,
        )
        result = await incident_generate_rca(params)

        assert "Related Tickets" in result
        assert "INFRA-101" in result

    @pytest.mark.asyncio
    async def test_generate_rca_with_timeline(self, mock_httpx_client) -> None:
        """Should include timeline in the report."""
        timeline = json.dumps(
            [
                {"timestamp": "2024-01-01T10:00:00Z", "event": "Alert fired"},
                {
                    "timestamp": "2024-01-01T10:15:00Z",
                    "event": "On-call paged",
                },
            ]
        )
        params = GenerateRCAInput(
            incident_summary="Service outage",
            timeline=timeline,
        )
        result = await incident_generate_rca(params)

        assert "Timeline" in result
        assert "Alert fired" in result
        assert "On-call paged" in result

    @pytest.mark.asyncio
    async def test_generate_rca_full(self, mock_httpx_client) -> None:
        """Should generate a full RCA with all fields populated."""
        params = GenerateRCAInput(
            incident_summary="Redis cluster failover in us-east-1",
            metrics_data=json.dumps({"latency_p99": 5200, "error_rate": 12.5}),
            related_tickets=json.dumps(
                [
                    {
                        "key": "INFRA-102",
                        "fields": {
                            "summary": "Redis cluster failover",
                            "status": {"name": "In Progress"},
                        },
                    }
                ]
            ),
            timeline=json.dumps(
                [
                    {
                        "timestamp": "2024-01-01T09:45:00Z",
                        "event": "Redis primary unresponsive",
                    },
                    {
                        "timestamp": "2024-01-01T09:46:00Z",
                        "event": "Automatic failover triggered",
                    },
                    {
                        "timestamp": "2024-01-01T09:48:00Z",
                        "event": "PagerDuty alert fired",
                    },
                ]
            ),
        )
        result = await incident_generate_rca(params)

        assert "# Root Cause Analysis Report" in result
        assert "Redis cluster failover" in result
        assert "latency_p99" in result
        assert "INFRA-102" in result
        assert "Automatic failover triggered" in result

    def test_rca_input_validation(self) -> None:
        """Should reject empty incident summary."""
        with pytest.raises(ValidationError):
            GenerateRCAInput(incident_summary="")
