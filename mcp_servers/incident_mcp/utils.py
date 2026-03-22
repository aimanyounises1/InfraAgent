"""API client helpers and mock data generators for Jira, Grafana, and PagerDuty.

Each client checks for valid credentials and falls back to mock mode
if the corresponding INFRA_AGENT_MOCK_* env var is true.
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta

import httpx

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP Client Factories
# ---------------------------------------------------------------------------


def get_jira_client() -> httpx.AsyncClient:
    """Create an authenticated httpx client for the Jira REST API."""
    if settings.mock_jira or not settings.jira_url:
        raise RuntimeError("Jira mock mode — use mock data instead of real API calls")
    return httpx.AsyncClient(
        base_url=settings.jira_url,
        headers={
            "Authorization": f"Basic {settings.jira_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def get_grafana_client() -> httpx.AsyncClient:
    """Create an authenticated httpx client for the Grafana API."""
    if settings.mock_grafana or not settings.grafana_url:
        raise RuntimeError("Grafana mock mode — use mock data instead of real API calls")
    return httpx.AsyncClient(
        base_url=settings.grafana_url,
        headers={
            "Authorization": f"Bearer {settings.grafana_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def get_pagerduty_client() -> httpx.AsyncClient:
    """Create an authenticated httpx client for the PagerDuty API."""
    if settings.mock_pagerduty or not settings.pagerduty_token:
        raise RuntimeError("PagerDuty mock mode — use mock data instead of real API calls")
    return httpx.AsyncClient(
        base_url="https://api.pagerduty.com",
        headers={
            "Authorization": f"Token token={settings.pagerduty_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


# ---------------------------------------------------------------------------
# Mock Data Generators
# ---------------------------------------------------------------------------


def get_mock_jira_tickets(jql: str = "") -> list[dict]:
    """Return 3-4 realistic incident tickets for mock/demo mode.

    Args:
        jql: Optional JQL string used to coarsely filter results.

    Returns:
        List of dicts representing Jira issue payloads.
    """
    now = datetime.now(tz=UTC)
    tickets: list[dict] = [
        {
            "key": "INFRA-101",
            "fields": {
                "summary": "High CPU usage on production API servers",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "issuetype": {"name": "Incident"},
                "assignee": {
                    "displayName": "Alice Chen",
                    "emailAddress": "alice@example.com",
                },
                "created": (now - timedelta(hours=6)).isoformat(),
                "updated": (now - timedelta(hours=1)).isoformat(),
                "labels": ["production", "cpu", "p1"],
                "description": ("API response times spiked to 5s+ due to CPU saturation."),
            },
        },
        {
            "key": "INFRA-102",
            "fields": {
                "summary": "Redis cluster failover in us-east-1",
                "status": {"name": "Open"},
                "priority": {"name": "Highest"},
                "issuetype": {"name": "Incident"},
                "assignee": {
                    "displayName": "Bob Martinez",
                    "emailAddress": "bob@example.com",
                },
                "created": (now - timedelta(hours=2)).isoformat(),
                "updated": (now - timedelta(minutes=30)).isoformat(),
                "labels": ["production", "redis", "p0"],
                "description": ("Primary Redis node went down triggering automatic failover."),
            },
        },
        {
            "key": "INFRA-103",
            "fields": {
                "summary": "Disk space warning on logging nodes",
                "status": {"name": "Resolved"},
                "priority": {"name": "Medium"},
                "issuetype": {"name": "Bug"},
                "assignee": {
                    "displayName": "Carol Wang",
                    "emailAddress": "carol@example.com",
                },
                "created": (now - timedelta(days=1)).isoformat(),
                "updated": (now - timedelta(hours=4)).isoformat(),
                "labels": ["staging", "disk", "monitoring"],
                "description": ("Elasticsearch data nodes exceeded 85% disk threshold."),
            },
        },
        {
            "key": "INFRA-104",
            "fields": {
                "summary": "SSL certificate expiry for api.example.com",
                "status": {"name": "Open"},
                "priority": {"name": "High"},
                "issuetype": {"name": "Task"},
                "assignee": None,
                "created": (now - timedelta(hours=12)).isoformat(),
                "updated": (now - timedelta(hours=12)).isoformat(),
                "labels": ["security", "certificates"],
                "description": ("TLS cert expires in 7 days — needs rotation."),
            },
        },
    ]

    # Naive JQL keyword filtering for mock mode
    if jql:
        jql_lower = jql.lower()
        filtered: list[dict] = []
        for t in tickets:
            fields = t["fields"]
            searchable = " ".join(
                [
                    t["key"].lower(),
                    fields["summary"].lower(),
                    fields["status"]["name"].lower(),
                    fields["priority"]["name"].lower(),
                    " ".join(fields.get("labels", [])),
                ]
            )
            if any(tok in searchable for tok in jql_lower.split()):
                filtered.append(t)
        return filtered if filtered else tickets

    return tickets


def get_mock_grafana_metrics(query: str) -> dict:
    """Return fake time-series data for a PromQL query.

    Args:
        query: PromQL expression (used only for labeling).

    Returns:
        Dict mimicking a Grafana datasource query response.
    """
    now = datetime.now(tz=UTC)
    # Generate 10 data points at 60-second intervals
    values: list[list[float | str]] = []
    base_value = random.uniform(20.0, 80.0)
    for i in range(10):
        ts = (now - timedelta(minutes=10 - i)).timestamp()
        val = round(base_value + random.uniform(-10.0, 10.0), 2)
        values.append([ts, str(val)])

    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {
                        "__name__": query.split("(")[0] if "(" in query else query,
                    },
                    "values": values,
                }
            ],
        },
    }


def get_mock_grafana_alerts(state: str = "") -> list[dict]:
    """Return 2-3 mock Grafana alerts with varying states.

    Args:
        state: Optional state filter (firing, pending, resolved/inactive).

    Returns:
        List of dicts representing Grafana alert payloads.
    """
    now = datetime.now(tz=UTC)
    alerts: list[dict] = [
        {
            "labels": {
                "alertname": "HighCPUUsage",
                "severity": "critical",
                "instance": "api-server-01:9090",
            },
            "annotations": {
                "summary": "CPU usage above 90% for 5 minutes",
                "description": "api-server-01 CPU at 94%",
            },
            "state": "firing",
            "activeAt": (now - timedelta(minutes=15)).isoformat(),
            "value": "94.2",
        },
        {
            "labels": {
                "alertname": "MemoryPressure",
                "severity": "warning",
                "instance": "worker-node-03:9090",
            },
            "annotations": {
                "summary": "Memory usage above 80%",
                "description": "worker-node-03 memory at 83%",
            },
            "state": "pending",
            "activeAt": (now - timedelta(minutes=5)).isoformat(),
            "value": "83.1",
        },
        {
            "labels": {
                "alertname": "DiskSpaceLow",
                "severity": "info",
                "instance": "logging-node-01:9090",
            },
            "annotations": {
                "summary": "Disk usage dropped below threshold",
                "description": "logging-node-01 disk usage back to 72%",
            },
            "state": "resolved",
            "activeAt": (now - timedelta(hours=1)).isoformat(),
            "value": "72.0",
        },
    ]

    if state:
        state_lower = state.lower()
        # Map common alternate names
        state_map: dict[str, list[str]] = {
            "firing": ["firing", "alerting"],
            "pending": ["pending"],
            "resolved": ["resolved", "inactive", "ok"],
        }
        accepted_states: list[str] = []
        for canonical, aliases in state_map.items():
            if state_lower in aliases:
                accepted_states.append(canonical)
        if accepted_states:
            alerts = [a for a in alerts if a["state"] in accepted_states]

    return alerts


def get_mock_grafana_dashboard(uid: str) -> dict:
    """Return a fake dashboard structure with panels.

    Args:
        uid: Dashboard UID (used in the response payload).

    Returns:
        Dict mimicking a Grafana dashboard API response.
    """
    return {
        "meta": {
            "slug": f"dashboard-{uid}",
            "url": f"/d/{uid}/dashboard-{uid}",
        },
        "dashboard": {
            "uid": uid,
            "title": f"Infrastructure Overview ({uid})",
            "tags": ["infrastructure", "monitoring"],
            "panels": [
                {
                    "id": 1,
                    "title": "CPU Usage",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": ('avg(rate(node_cpu_seconds_total{mode!="idle"}[5m]))'),
                        }
                    ],
                },
                {
                    "id": 2,
                    "title": "Memory Usage",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": ("node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes"),
                        }
                    ],
                },
                {
                    "id": 3,
                    "title": "Network I/O",
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "rate(node_network_receive_bytes_total[5m])",
                        }
                    ],
                },
                {
                    "id": 4,
                    "title": "Disk IOPS",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": "rate(node_disk_io_time_seconds_total[5m])",
                        }
                    ],
                },
            ],
        },
    }


def get_mock_pd_incidents(status: str = "triggered") -> list[dict]:
    """Return 2-3 mock PagerDuty incidents.

    Args:
        status: Comma-separated status filter
                (triggered, acknowledged, resolved).

    Returns:
        List of dicts representing PagerDuty incident payloads.
    """
    now = datetime.now(tz=UTC)
    incidents: list[dict] = [
        {
            "id": "P1ABC23",
            "incident_number": 42,
            "title": "CRITICAL: API latency exceeds 5s threshold",
            "status": "triggered",
            "urgency": "high",
            "created_at": (now - timedelta(minutes=20)).isoformat(),
            "updated_at": (now - timedelta(minutes=5)).isoformat(),
            "service": {
                "id": "PSVC001",
                "summary": "Production API",
            },
            "assignments": [{"assignee": {"id": "PUSER01", "summary": "Alice Chen"}}],
            "html_url": ("https://example.pagerduty.com/incidents/P1ABC23"),
        },
        {
            "id": "P2DEF45",
            "incident_number": 43,
            "title": "WARNING: Redis replication lag > 10s",
            "status": "acknowledged",
            "urgency": "high",
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "updated_at": (now - timedelta(minutes=15)).isoformat(),
            "service": {
                "id": "PSVC002",
                "summary": "Redis Cluster",
            },
            "assignments": [{"assignee": {"id": "PUSER02", "summary": "Bob Martinez"}}],
            "html_url": ("https://example.pagerduty.com/incidents/P2DEF45"),
        },
        {
            "id": "P3GHI67",
            "incident_number": 41,
            "title": "INFO: Disk cleanup completed on logging nodes",
            "status": "resolved",
            "urgency": "low",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "updated_at": (now - timedelta(hours=2)).isoformat(),
            "service": {
                "id": "PSVC003",
                "summary": "Logging Infrastructure",
            },
            "assignments": [{"assignee": {"id": "PUSER03", "summary": "Carol Wang"}}],
            "html_url": ("https://example.pagerduty.com/incidents/P3GHI67"),
        },
    ]

    if status:
        allowed = {s.strip().lower() for s in status.split(",")}
        incidents = [i for i in incidents if i["status"] in allowed]

    return incidents
