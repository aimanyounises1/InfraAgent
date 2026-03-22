"""Tests for incident_mcp server tools.

Tests cover three categories for each tool:
1. **Unavailable path** -- service not configured, tool returns structured error JSON.
2. **Real API path** -- ``respx`` mocks HTTP responses, tool processes them correctly.
3. **Input validation** -- Pydantic rejects invalid inputs.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import respx
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
    GrafanaUnavailableError,
    JiraUnavailableError,
    PagerDutyUnavailableError,
    get_grafana_client,
    get_jira_client,
    get_pagerduty_client,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JIRA_BASE = "https://jira.test.local"
GRAFANA_BASE = "https://grafana.test.local"
PD_BASE = "https://api.pagerduty.com"


# ---------------------------------------------------------------------------
# Client Factory Tests
# ---------------------------------------------------------------------------


class TestClientFactories:
    """Verify that client factories raise when services are not configured."""

    def test_jira_client_raises_when_unconfigured(self) -> None:
        with patch(
            "config.settings.jira_url", "", create=False
        ), patch(
            "config.settings.jira_token", "", create=False
        ), pytest.raises(JiraUnavailableError):
            get_jira_client()

    def test_jira_client_raises_when_token_missing(self) -> None:
        with patch(
            "config.settings.jira_url", JIRA_BASE, create=False
        ), patch(
            "config.settings.jira_token", "", create=False
        ), pytest.raises(JiraUnavailableError):
            get_jira_client()

    def test_jira_client_returns_client_when_configured(self) -> None:
        with patch(
            "config.settings.jira_url", JIRA_BASE, create=False
        ), patch("config.settings.jira_token", "test-token", create=False):
            client = get_jira_client()
            assert isinstance(client, httpx.AsyncClient)

    def test_grafana_client_raises_when_unconfigured(self) -> None:
        with patch(
            "config.settings.grafana_url", "", create=False
        ), patch(
            "config.settings.grafana_token", "", create=False
        ), pytest.raises(GrafanaUnavailableError):
            get_grafana_client()

    def test_grafana_client_returns_client_when_configured(self) -> None:
        with patch(
            "config.settings.grafana_url", GRAFANA_BASE, create=False
        ), patch(
            "config.settings.grafana_token", "test-token", create=False
        ):
            client = get_grafana_client()
            assert isinstance(client, httpx.AsyncClient)

    def test_pagerduty_client_raises_when_unconfigured(self) -> None:
        with patch(
            "config.settings.pagerduty_token", "", create=False
        ), pytest.raises(PagerDutyUnavailableError):
            get_pagerduty_client()

    def test_pagerduty_client_returns_client_when_configured(self) -> None:
        with patch(
            "config.settings.pagerduty_token", "test-token", create=False
        ):
            client = get_pagerduty_client()
            assert isinstance(client, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# Jira Tool Tests
# ---------------------------------------------------------------------------


class TestJiraCreateTicket:
    """Tests for incident_jira_create_ticket tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_jira_unavailable(self) -> None:
        """Tool should return structured error JSON when Jira is not configured."""
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            side_effect=JiraUnavailableError("not configured"),
        ):
            params = JiraCreateTicketInput(
                project_key="OPS",
                summary="Test ticket",
            )
            result = await incident_jira_create_ticket(params)
            data = json.loads(result)

            assert data["error"] == "Jira not configured"
            assert "hint" in data
            assert "INFRA_AGENT_JIRA_URL" in data["hint"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_ticket_via_api(self) -> None:
        """Tool should POST to Jira and return created ticket data."""
        api_response = {"key": "OPS-42", "id": "12345", "self": "..."}
        respx.post(f"{JIRA_BASE}/rest/api/3/issue").mock(
            return_value=httpx.Response(201, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            return_value=httpx.AsyncClient(base_url=JIRA_BASE),
        ):
            params = JiraCreateTicketInput(
                project_key="OPS",
                summary="API latency spike",
                description="Investigating high p99 latency",
                priority="High",
                labels=["production"],
            )
            result = await incident_jira_create_ticket(params)
            data = json.loads(result)

            assert data["key"] == "OPS-42"

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_api_error(self) -> None:
        """Tool should return error JSON on HTTP 400."""
        respx.post(f"{JIRA_BASE}/rest/api/3/issue").mock(
            return_value=httpx.Response(400, json={"errorMessages": ["bad"]})
        )
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            return_value=httpx.AsyncClient(base_url=JIRA_BASE),
        ):
            params = JiraCreateTicketInput(
                project_key="OPS", summary="Bad ticket"
            )
            result = await incident_jira_create_ticket(params)
            data = json.loads(result)

            assert "error" in data
            assert data["status_code"] == 400

    def test_input_validation_rejects_empty_fields(self) -> None:
        with pytest.raises(ValidationError):
            JiraCreateTicketInput(project_key="", summary="")

    def test_defaults_applied(self) -> None:
        params = JiraCreateTicketInput(project_key="INFRA", summary="Test")
        assert params.issue_type == "Bug"
        assert params.priority == "High"
        assert params.labels == []


class TestJiraSearch:
    """Tests for incident_jira_search tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_jira_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            side_effect=JiraUnavailableError("not configured"),
        ):
            params = JiraSearchInput(jql="project=OPS")
            result = await incident_jira_search(params)
            data = json.loads(result)
            assert data["error"] == "Jira not configured"

    @respx.mock
    @pytest.mark.asyncio
    async def test_searches_via_api(self) -> None:
        api_response = {
            "total": 1,
            "issues": [{"key": "OPS-1", "fields": {"summary": "test"}}],
        }
        respx.get(f"{JIRA_BASE}/rest/api/3/search").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            return_value=httpx.AsyncClient(base_url=JIRA_BASE),
        ):
            params = JiraSearchInput(jql="project=OPS", max_results=10)
            result = await incident_jira_search(params)
            data = json.loads(result)

            assert data["total"] == 1
            assert data["issues"][0]["key"] == "OPS-1"

    def test_input_validation_rejects_empty_jql(self) -> None:
        with pytest.raises(ValidationError):
            JiraSearchInput(jql="")


class TestJiraUpdateTicket:
    """Tests for incident_jira_update_ticket tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_jira_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            side_effect=JiraUnavailableError("not configured"),
        ):
            params = JiraUpdateTicketInput(
                issue_key="OPS-1", status="Resolved"
            )
            result = await incident_jira_update_ticket(params)
            data = json.loads(result)
            assert data["error"] == "Jira not configured"

    @respx.mock
    @pytest.mark.asyncio
    async def test_updates_assignee_via_api(self) -> None:
        respx.put(f"{JIRA_BASE}/rest/api/3/issue/OPS-1").mock(
            return_value=httpx.Response(204)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            return_value=httpx.AsyncClient(base_url=JIRA_BASE),
        ):
            params = JiraUpdateTicketInput(
                issue_key="OPS-1", assignee="alice@example.com"
            )
            result = await incident_jira_update_ticket(params)
            data = json.loads(result)

            assert data["success"] is True
            assert any("assignee" in u for u in data["updates_applied"])

    @respx.mock
    @pytest.mark.asyncio
    async def test_adds_comment_via_api(self) -> None:
        respx.post(f"{JIRA_BASE}/rest/api/3/issue/OPS-1/comment").mock(
            return_value=httpx.Response(201, json={"id": "100"})
        )
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            return_value=httpx.AsyncClient(base_url=JIRA_BASE),
        ):
            params = JiraUpdateTicketInput(
                issue_key="OPS-1", comment="Scaling up."
            )
            result = await incident_jira_update_ticket(params)
            data = json.loads(result)

            assert data["success"] is True
            assert any("comment" in u for u in data["updates_applied"])

    @respx.mock
    @pytest.mark.asyncio
    async def test_transitions_status_via_api(self) -> None:
        respx.get(f"{JIRA_BASE}/rest/api/3/issue/OPS-1/transitions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "transitions": [
                        {"id": "31", "name": "Resolved"},
                        {"id": "21", "name": "In Progress"},
                    ]
                },
            ),
        )
        respx.post(f"{JIRA_BASE}/rest/api/3/issue/OPS-1/transitions").mock(
            return_value=httpx.Response(204)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.jira_tools.get_jira_client",
            return_value=httpx.AsyncClient(base_url=JIRA_BASE),
        ):
            params = JiraUpdateTicketInput(
                issue_key="OPS-1", status="Resolved"
            )
            result = await incident_jira_update_ticket(params)
            data = json.loads(result)

            assert data["success"] is True
            assert any("status" in u for u in data["updates_applied"])

    def test_input_validation_rejects_empty_key(self) -> None:
        with pytest.raises(ValidationError):
            JiraUpdateTicketInput(issue_key="")


# ---------------------------------------------------------------------------
# Grafana Tool Tests
# ---------------------------------------------------------------------------


class TestGrafanaQuery:
    """Tests for incident_grafana_query tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_grafana_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.grafana_tools.get_grafana_client",
            side_effect=GrafanaUnavailableError("not configured"),
        ):
            params = GrafanaQueryInput(query="rate(http_requests_total[5m])")
            result = await incident_grafana_query(params)
            data = json.loads(result)
            assert data["error"] == "Grafana not configured"
            assert "INFRA_AGENT_GRAFANA_URL" in data["hint"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_queries_metrics_via_api(self) -> None:
        api_response = {
            "results": {"A": {"frames": [{"data": {"values": [[1, 2]]}}]}}
        }
        respx.post(f"{GRAFANA_BASE}/api/ds/query").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.grafana_tools.get_grafana_client",
            return_value=httpx.AsyncClient(base_url=GRAFANA_BASE),
        ):
            params = GrafanaQueryInput(query="rate(http_requests_total[5m])")
            result = await incident_grafana_query(params)
            data = json.loads(result)

            assert "results" in data

    def test_input_validation_rejects_empty_query(self) -> None:
        with pytest.raises(ValidationError):
            GrafanaQueryInput(query="")


class TestGrafanaGetAlerts:
    """Tests for incident_grafana_get_alerts tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_grafana_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.grafana_tools.get_grafana_client",
            side_effect=GrafanaUnavailableError("not configured"),
        ):
            params = GrafanaGetAlertsInput()
            result = await incident_grafana_get_alerts(params)
            data = json.loads(result)
            assert data["error"] == "Grafana not configured"

    @respx.mock
    @pytest.mark.asyncio
    async def test_retrieves_alerts_via_api(self) -> None:
        api_alerts = [
            {
                "labels": {"alertname": "HighCPU", "severity": "critical"},
                "state": "firing",
            },
        ]
        respx.get(
            f"{GRAFANA_BASE}/api/alertmanager/grafana/api/v2/alerts"
        ).mock(return_value=httpx.Response(200, json=api_alerts))
        with patch(
            "mcp_servers.incident_mcp.tools.grafana_tools.get_grafana_client",
            return_value=httpx.AsyncClient(base_url=GRAFANA_BASE),
        ):
            params = GrafanaGetAlertsInput(state="firing")
            result = await incident_grafana_get_alerts(params)
            data = json.loads(result)

            assert data["total"] == 1
            assert data["alerts"][0]["labels"]["alertname"] == "HighCPU"


class TestGrafanaGetDashboard:
    """Tests for incident_grafana_get_dashboard tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_grafana_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.grafana_tools.get_grafana_client",
            side_effect=GrafanaUnavailableError("not configured"),
        ):
            params = GrafanaGetDashboardInput(dashboard_uid="abc123")
            result = await incident_grafana_get_dashboard(params)
            data = json.loads(result)
            assert data["error"] == "Grafana not configured"

    @respx.mock
    @pytest.mark.asyncio
    async def test_retrieves_dashboard_via_api(self) -> None:
        api_response = {
            "dashboard": {
                "uid": "abc123",
                "title": "Infra Overview",
                "panels": [{"id": 1, "title": "CPU"}],
            }
        }
        respx.get(f"{GRAFANA_BASE}/api/dashboards/uid/abc123").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.grafana_tools.get_grafana_client",
            return_value=httpx.AsyncClient(base_url=GRAFANA_BASE),
        ):
            params = GrafanaGetDashboardInput(dashboard_uid="abc123")
            result = await incident_grafana_get_dashboard(params)
            data = json.loads(result)

            assert data["dashboard"]["uid"] == "abc123"

    def test_input_validation_rejects_empty_uid(self) -> None:
        with pytest.raises(ValidationError):
            GrafanaGetDashboardInput(dashboard_uid="")


# ---------------------------------------------------------------------------
# PagerDuty Tool Tests
# ---------------------------------------------------------------------------


class TestPagerDutyListIncidents:
    """Tests for incident_pagerduty_list_incidents tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_pd_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.pagerduty_tools.get_pagerduty_client",
            side_effect=PagerDutyUnavailableError("not configured"),
        ):
            params = PagerDutyListIncidentsInput()
            result = await incident_pagerduty_list_incidents(params)
            data = json.loads(result)
            assert data["error"] == "PagerDuty not configured"
            assert "INFRA_AGENT_PAGERDUTY_TOKEN" in data["hint"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_lists_incidents_via_api(self) -> None:
        api_response = {
            "incidents": [
                {
                    "id": "P1ABC",
                    "title": "API latency",
                    "status": "triggered",
                }
            ],
            "more": False,
        }
        respx.get(f"{PD_BASE}/incidents").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.pagerduty_tools.get_pagerduty_client",
            return_value=httpx.AsyncClient(base_url=PD_BASE),
        ):
            params = PagerDutyListIncidentsInput(
                status="triggered", limit=10
            )
            result = await incident_pagerduty_list_incidents(params)
            data = json.loads(result)

            assert data["total"] == 1
            assert data["incidents"][0]["id"] == "P1ABC"


class TestPagerDutyAcknowledge:
    """Tests for incident_pagerduty_acknowledge tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_pd_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.pagerduty_tools.get_pagerduty_client",
            side_effect=PagerDutyUnavailableError("not configured"),
        ):
            params = PagerDutyAcknowledgeInput(incident_id="P1ABC")
            result = await incident_pagerduty_acknowledge(params)
            data = json.loads(result)
            assert data["error"] == "PagerDuty not configured"

    @respx.mock
    @pytest.mark.asyncio
    async def test_acknowledges_incident_via_api(self) -> None:
        api_response = {
            "incident": {"id": "P1ABC", "status": "acknowledged"}
        }
        respx.put(f"{PD_BASE}/incidents/P1ABC").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.pagerduty_tools.get_pagerduty_client",
            return_value=httpx.AsyncClient(base_url=PD_BASE),
        ):
            params = PagerDutyAcknowledgeInput(incident_id="P1ABC")
            result = await incident_pagerduty_acknowledge(params)
            data = json.loads(result)

            assert data["incident"]["status"] == "acknowledged"

    def test_input_validation_rejects_empty_id(self) -> None:
        with pytest.raises(ValidationError):
            PagerDutyAcknowledgeInput(incident_id="")


class TestPagerDutyResolve:
    """Tests for incident_pagerduty_resolve tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_pd_unavailable(self) -> None:
        with patch(
            "mcp_servers.incident_mcp.tools.pagerduty_tools.get_pagerduty_client",
            side_effect=PagerDutyUnavailableError("not configured"),
        ):
            params = PagerDutyResolveInput(incident_id="P2DEF")
            result = await incident_pagerduty_resolve(params)
            data = json.loads(result)
            assert data["error"] == "PagerDuty not configured"

    @respx.mock
    @pytest.mark.asyncio
    async def test_resolves_incident_via_api(self) -> None:
        api_response = {"incident": {"id": "P2DEF", "status": "resolved"}}
        respx.put(f"{PD_BASE}/incidents/P2DEF").mock(
            return_value=httpx.Response(200, json=api_response)
        )
        with patch(
            "mcp_servers.incident_mcp.tools.pagerduty_tools.get_pagerduty_client",
            return_value=httpx.AsyncClient(base_url=PD_BASE),
        ):
            params = PagerDutyResolveInput(incident_id="P2DEF")
            result = await incident_pagerduty_resolve(params)
            data = json.loads(result)

            assert data["incident"]["status"] == "resolved"

    def test_input_validation_rejects_empty_id(self) -> None:
        with pytest.raises(ValidationError):
            PagerDutyResolveInput(incident_id="")


# ---------------------------------------------------------------------------
# RCA Tool Tests
# ---------------------------------------------------------------------------


class TestGenerateRCA:
    """Tests for incident_generate_rca tool."""

    @pytest.mark.asyncio
    async def test_generate_basic_rca(self) -> None:
        """Should generate an RCA report with summary only."""
        params = GenerateRCAInput(
            incident_summary="API latency spike caused by CPU exhaustion",
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
    async def test_generate_rca_with_metrics(self) -> None:
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
    async def test_generate_rca_with_tickets(self) -> None:
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
    async def test_generate_rca_with_timeline(self) -> None:
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
    async def test_generate_rca_full(self) -> None:
        """Should generate a full RCA with all fields populated."""
        params = GenerateRCAInput(
            incident_summary="Redis cluster failover in us-east-1",
            metrics_data=json.dumps(
                {"latency_p99": 5200, "error_rate": 12.5}
            ),
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
