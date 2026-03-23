"""Alert correlation, change detection, and postmortem tools for incident_mcp.

Provides cross-system correlation of PagerDuty incidents and Grafana alerts,
detection of recent changes in Kubernetes, and comprehensive postmortem
report generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from mcp_servers.incident_mcp.models import (  # noqa: TCH001
    CorrelateAlertsInput,
    DetectChangesInput,
    GeneratePostmortemInput,
)
from mcp_servers.incident_mcp.server import mcp
from mcp_servers.incident_mcp.utils import (
    GrafanaUnavailableError,
    PagerDutyUnavailableError,
    get_grafana_client,
    get_pagerduty_client,
)

logger = logging.getLogger(__name__)


def _json(data: Any) -> str:
    """Serialize data to a JSON string with indentation."""
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_pagerduty_incidents(
    since: str,
    until: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch PagerDuty incidents within a time range.

    Args:
        since: ISO 8601 start time.
        until: ISO 8601 end time.

    Returns:
        Tuple of (list of incident dicts, error string or None).
    """
    try:
        client = get_pagerduty_client()
    except PagerDutyUnavailableError as exc:
        return [], f"PagerDuty not configured: {exc}"

    try:
        async with client:
            resp = await client.get(
                "/incidents",
                params={
                    "since": since,
                    "until": until,
                    "limit": 100,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("incidents", []), None
    except httpx.HTTPStatusError as exc:
        return [], f"PagerDuty API error: {exc.response.status_code}"
    except httpx.ConnectError as exc:
        return [], f"PagerDuty connection failed: {exc}"
    except Exception as exc:
        return [], f"PagerDuty error: {exc}"


async def _fetch_grafana_alerts() -> tuple[list[dict[str, Any]], str | None]:
    """Fetch active Grafana alerts.

    Returns:
        Tuple of (list of alert dicts, error string or None).
    """
    try:
        client = get_grafana_client()
    except GrafanaUnavailableError as exc:
        return [], f"Grafana not configured: {exc}"

    try:
        async with client:
            resp = await client.get(
                "/api/alertmanager/grafana/api/v2/alerts",
            )
            resp.raise_for_status()
            alerts = resp.json()
            return alerts if isinstance(alerts, list) else [], None
    except httpx.HTTPStatusError as exc:
        return [], f"Grafana API error: {exc.response.status_code}"
    except httpx.ConnectError as exc:
        return [], f"Grafana connection failed: {exc}"
    except Exception as exc:
        return [], f"Grafana error: {exc}"


async def _fetch_k8s_events(
    namespace: str,
    since_time: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch recent K8s events for change detection.

    Args:
        namespace: Kubernetes namespace to query.
        since_time: Only return events after this time.

    Returns:
        Tuple of (list of event dicts, error string or None).
    """
    try:
        from mcp_servers.k8s_mcp.utils import get_clients

        v1, _ = get_clients()
    except Exception as exc:
        return [], f"Kubernetes not available: {exc}"

    try:
        event_list = await asyncio.to_thread(
            v1.list_namespaced_event,
            namespace=namespace,
        )

        events: list[dict[str, Any]] = []
        for ev in event_list.items:
            ev_time = ev.last_timestamp or ev.first_timestamp
            if ev_time and ev_time.replace(tzinfo=UTC) >= since_time:
                events.append(
                    {
                        "type": ev.type,
                        "reason": ev.reason,
                        "message": ev.message,
                        "involved_object": (
                            f"{ev.involved_object.kind}/{ev.involved_object.name}"
                            if ev.involved_object
                            else None
                        ),
                        "count": ev.count,
                        "first_timestamp": str(ev.first_timestamp),
                        "last_timestamp": str(ev.last_timestamp),
                        "source": ev.source.component if ev.source else None,
                    }
                )
        return events, None
    except Exception as exc:
        return [], f"K8s events error: {exc}"


async def _fetch_k8s_recent_deployments(
    namespace: str,
    since_time: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch K8s deployments that have been modified recently.

    Args:
        namespace: Kubernetes namespace to query.
        since_time: Only return deployments changed after this time.

    Returns:
        Tuple of (list of deployment change dicts, error string or None).
    """
    try:
        from mcp_servers.k8s_mcp.utils import get_clients

        _, apps_v1 = get_clients()
    except Exception as exc:
        return [], f"Kubernetes not available: {exc}"

    try:
        deploy_list = await asyncio.to_thread(
            apps_v1.list_namespaced_deployment,
            namespace=namespace,
        )

        changes: list[dict[str, Any]] = []
        for deploy in deploy_list.items:
            # Check conditions for recent updates
            if deploy.status and deploy.status.conditions:
                for cond in deploy.status.conditions:
                    if cond.last_update_time:
                        cond_time = cond.last_update_time
                        if hasattr(cond_time, "replace"):
                            cond_time = cond_time.replace(tzinfo=UTC)
                        if cond_time >= since_time:
                            changes.append(
                                {
                                    "deployment": deploy.metadata.name,
                                    "namespace": deploy.metadata.namespace,
                                    "condition_type": cond.type,
                                    "status": cond.status,
                                    "reason": cond.reason or "",
                                    "message": cond.message or "",
                                    "last_update": str(cond.last_update_time),
                                    "replicas": deploy.spec.replicas if deploy.spec else 0,
                                    "ready_replicas": (
                                        deploy.status.ready_replicas
                                        if deploy.status.ready_replicas
                                        else 0
                                    ),
                                }
                            )
                            break  # One entry per deployment
        return changes, None
    except Exception as exc:
        return [], f"K8s deployments error: {exc}"


# ---------------------------------------------------------------------------
# Tool 1: incident_correlate_alerts
# ---------------------------------------------------------------------------


@mcp.tool(
    name="incident_correlate_alerts",
    annotations={
        "title": "Correlate Alerts Across Systems",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def incident_correlate_alerts(params: CorrelateAlertsInput) -> str:
    """Correlate PagerDuty incidents and Grafana alerts by overlapping time window.

    Fetches incidents and alerts from both systems, groups them into
    clusters based on temporal proximity within the specified time window,
    and identifies potential correlations.
    """
    logger.info(
        "incident_correlate_alerts called",
        extra={
            "time_window_minutes": params.time_window_minutes,
            "min_alerts": params.min_alerts,
        },
    )

    now = datetime.now(tz=UTC)
    lookback = timedelta(minutes=params.time_window_minutes)
    since_time = now - lookback

    since_iso = since_time.isoformat()
    until_iso = now.isoformat()

    # Fetch from both sources in parallel
    pd_task = _fetch_pagerduty_incidents(since_iso, until_iso)
    grafana_task = _fetch_grafana_alerts()
    (pd_incidents, pd_error), (grafana_alerts, grafana_error) = await asyncio.gather(
        pd_task, grafana_task
    )

    source_errors: list[str] = []
    if pd_error:
        source_errors.append(pd_error)
    if grafana_error:
        source_errors.append(grafana_error)

    # Normalize alerts into a common format
    all_alerts: list[dict[str, Any]] = []

    for inc in pd_incidents:
        all_alerts.append(
            {
                "source": "pagerduty",
                "id": inc.get("id", ""),
                "title": inc.get("title", inc.get("summary", "")),
                "status": inc.get("status", ""),
                "created_at": inc.get("created_at", ""),
                "service": (
                    inc.get("service", {}).get("summary", "")
                    if isinstance(inc.get("service"), dict)
                    else ""
                ),
                "urgency": inc.get("urgency", ""),
            }
        )

    for alert in grafana_alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        all_alerts.append(
            {
                "source": "grafana",
                "id": labels.get("alertname", ""),
                "title": annotations.get("summary", labels.get("alertname", "")),
                "status": alert.get("status", {}).get("state", "")
                if isinstance(alert.get("status"), dict)
                else str(alert.get("status", "")),
                "created_at": alert.get("startsAt", ""),
                "service": labels.get("job", labels.get("service", "")),
                "severity": labels.get("severity", ""),
            }
        )

    # Group alerts by service/component for correlation
    service_groups: dict[str, list[dict[str, Any]]] = {}
    for alert in all_alerts:
        service_key = alert.get("service", "") or "unknown"
        if service_key not in service_groups:
            service_groups[service_key] = []
        service_groups[service_key].append(alert)

    # Build correlation clusters (services with >= min_alerts)
    correlated: list[dict[str, Any]] = []
    uncorrelated: list[dict[str, Any]] = []

    for service, alerts_list in service_groups.items():
        if len(alerts_list) >= params.min_alerts:
            sources = list({a["source"] for a in alerts_list})
            correlated.append(
                {
                    "service": service,
                    "alert_count": len(alerts_list),
                    "sources": sources,
                    "cross_system": len(sources) > 1,
                    "alerts": alerts_list,
                }
            )
        else:
            uncorrelated.extend(alerts_list)

    result = {
        "time_window_minutes": params.time_window_minutes,
        "since": since_iso,
        "until": until_iso,
        "total_alerts": len(all_alerts),
        "pagerduty_count": len(pd_incidents),
        "grafana_count": len(grafana_alerts),
        "correlated_groups": len(correlated),
        "correlated": correlated,
        "uncorrelated_count": len(uncorrelated),
        "uncorrelated": uncorrelated,
        "source_errors": source_errors,
    }

    logger.info(
        "incident_correlate_alerts completed",
        extra={
            "total_alerts": len(all_alerts),
            "correlated_groups": len(correlated),
        },
    )
    return _json(result)


# ---------------------------------------------------------------------------
# Tool 2: incident_detect_changes
# ---------------------------------------------------------------------------


@mcp.tool(
    name="incident_detect_changes",
    annotations={
        "title": "Detect Recent Infrastructure Changes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def incident_detect_changes(params: DetectChangesInput) -> str:
    """Detect recent changes in Kubernetes that could cause incidents.

    Examines K8s events and deployment updates within the lookback window
    to identify configuration changes, scaling events, container restarts,
    image updates, and other changes that may correlate with incidents.
    """
    logger.info(
        "incident_detect_changes called",
        extra={
            "namespace": params.namespace,
            "lookback_minutes": params.lookback_minutes,
        },
    )

    now = datetime.now(tz=UTC)
    since_time = now - timedelta(minutes=params.lookback_minutes)

    # Fetch events and deployments in parallel
    events_task = _fetch_k8s_events(params.namespace, since_time)
    deploys_task = _fetch_k8s_recent_deployments(params.namespace, since_time)
    (events, events_error), (deploy_changes, deploys_error) = await asyncio.gather(
        events_task, deploys_task
    )

    errors: list[str] = []
    if events_error:
        errors.append(events_error)
    if deploys_error:
        errors.append(deploys_error)

    # Categorize events by type
    warning_events = [e for e in events if e.get("type") == "Warning"]
    normal_events = [e for e in events if e.get("type") == "Normal"]

    # Identify high-signal changes
    significant_changes: list[dict[str, Any]] = []

    # Look for image pull issues, OOMKilled, CrashLoopBackOff, etc.
    significant_reasons = {
        "BackOff",
        "CrashLoopBackOff",
        "Failed",
        "FailedScheduling",
        "OOMKilling",
        "Unhealthy",
        "FailedMount",
        "FailedAttachVolume",
        "Evicted",
        "Killing",
        "Preempting",
    }
    for ev in events:
        reason = ev.get("reason", "")
        if reason in significant_reasons:
            significant_changes.append(
                {
                    "category": "warning_event",
                    "reason": reason,
                    "message": ev.get("message", ""),
                    "object": ev.get("involved_object", ""),
                    "count": ev.get("count", 1),
                    "last_seen": ev.get("last_timestamp", ""),
                }
            )

    # Flag deployment changes as significant
    for change in deploy_changes:
        significant_changes.append(
            {
                "category": "deployment_change",
                "deployment": change.get("deployment", ""),
                "condition": change.get("condition_type", ""),
                "reason": change.get("reason", ""),
                "message": change.get("message", ""),
                "replicas": change.get("replicas", 0),
                "ready_replicas": change.get("ready_replicas", 0),
                "last_update": change.get("last_update", ""),
            }
        )

    result = {
        "namespace": params.namespace,
        "lookback_minutes": params.lookback_minutes,
        "since": str(since_time),
        "total_events": len(events),
        "warning_events": len(warning_events),
        "normal_events": len(normal_events),
        "deployment_changes": len(deploy_changes),
        "significant_changes_count": len(significant_changes),
        "significant_changes": significant_changes,
        "all_warning_events": warning_events,
        "recent_deployment_changes": deploy_changes,
        "errors": errors,
    }

    logger.info(
        "incident_detect_changes completed",
        extra={
            "total_events": len(events),
            "significant": len(significant_changes),
        },
    )
    return _json(result)


# ---------------------------------------------------------------------------
# Tool 3: incident_generate_postmortem
# ---------------------------------------------------------------------------


@mcp.tool(
    name="incident_generate_postmortem",
    annotations={
        "title": "Generate Incident Postmortem",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def incident_generate_postmortem(params: GeneratePostmortemInput) -> str:
    """Generate a comprehensive postmortem report for a PagerDuty incident.

    Fetches the incident details from PagerDuty, optionally gathers
    Grafana metrics and K8s events, and assembles a structured Markdown
    postmortem document.
    """
    logger.info(
        "incident_generate_postmortem called",
        extra={"incident_id": params.incident_id},
    )

    now = datetime.now(tz=UTC)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")

    # ---------- Fetch PagerDuty incident details ----------
    incident_data: dict[str, Any] = {}
    pd_error: str | None = None

    try:
        client = get_pagerduty_client()
        async with client:
            resp = await client.get(f"/incidents/{params.incident_id}")
            resp.raise_for_status()
            data = resp.json()
            incident_data = data.get("incident", data)
    except PagerDutyUnavailableError as exc:
        pd_error = f"PagerDuty not configured: {exc}"
    except httpx.HTTPStatusError as exc:
        pd_error = f"PagerDuty API error: {exc.response.status_code}"
    except httpx.ConnectError as exc:
        pd_error = f"PagerDuty connection failed: {exc}"
    except Exception as exc:
        pd_error = f"PagerDuty error: {exc}"

    # Extract incident info
    title = incident_data.get("title", incident_data.get("summary", params.incident_id))
    status = incident_data.get("status", "unknown")
    urgency = incident_data.get("urgency", "unknown")
    created_at = incident_data.get("created_at", "unknown")
    resolved_at = incident_data.get("resolved_at", "")
    service_name = ""
    if isinstance(incident_data.get("service"), dict):
        service_name = incident_data["service"].get("summary", "")

    # ---------- Fetch Grafana metrics (optional) ----------
    metrics_section = ""
    if params.include_metrics:
        grafana_alerts, grafana_error = await _fetch_grafana_alerts()
        if grafana_error:
            metrics_section = (
                f"### Metrics Data\n*Could not fetch Grafana metrics: {grafana_error}*\n\n"
            )
        elif grafana_alerts:
            metrics_section = "### Active Alerts at Time of Incident\n\n"
            for i, alert in enumerate(grafana_alerts[:10], 1):
                labels = alert.get("labels", {})
                annotations = alert.get("annotations", {})
                alert_name = labels.get("alertname", f"Alert {i}")
                severity = labels.get("severity", "unknown")
                summary = annotations.get("summary", "")
                metrics_section += f"**{i}. {alert_name}** (severity: {severity})\n"
                if summary:
                    metrics_section += f"   {summary}\n"
                metrics_section += "\n"
        else:
            metrics_section = "### Metrics Data\n*No active Grafana alerts found.*\n\n"

    # ---------- Fetch K8s timeline (optional) ----------
    timeline_section = ""
    if params.include_timeline:
        lookback = timedelta(hours=2)
        since_time = now - lookback
        events, events_error = await _fetch_k8s_events("default", since_time)
        if events_error:
            timeline_section = (
                f"### Infrastructure Timeline\n*Could not fetch K8s events: {events_error}*\n\n"
            )
        elif events:
            timeline_section = "### Infrastructure Timeline (last 2 hours)\n\n"
            timeline_section += "| Time | Type | Object | Reason | Message |\n"
            timeline_section += "|------|------|--------|--------|---------|\n"
            # Sort by timestamp, show last 20
            sorted_events = sorted(
                events,
                key=lambda e: e.get("last_timestamp", ""),
                reverse=True,
            )
            for ev in sorted_events[:20]:
                ev_time = ev.get("last_timestamp", "")
                ev_type = ev.get("type", "")
                ev_obj = ev.get("involved_object", "")
                ev_reason = ev.get("reason", "")
                ev_msg = (ev.get("message", "") or "")[:80]
                timeline_section += (
                    f"| {ev_time} | {ev_type} | {ev_obj} | {ev_reason} | {ev_msg} |\n"
                )
            timeline_section += "\n"
        else:
            timeline_section = "### Infrastructure Timeline\n*No recent K8s events found.*\n\n"

    # ---------- Assemble postmortem report ----------
    errors_note = ""
    if pd_error:
        errors_note = f"\n> **Note:** {pd_error}. Some incident details may be incomplete.\n\n"

    duration = ""
    if created_at and resolved_at and created_at != "unknown":
        duration = f"**Duration:** {created_at} -- {resolved_at}"
    elif created_at and created_at != "unknown":
        duration = f"**Started:** {created_at} (ongoing or resolved time unknown)"

    report = f"""# Postmortem Report

**Generated:** {now_str}
**Incident ID:** {params.incident_id}
**Title:** {title}

---
{errors_note}
## Incident Summary

| Field | Value |
|-------|-------|
| **Status** | {status} |
| **Urgency** | {urgency} |
| **Service** | {service_name or "N/A"} |
| **Created** | {created_at} |
| **Resolved** | {resolved_at or "N/A"} |

{duration}

---

## Impact

- **Affected Service:** {service_name or title}
- **Severity:** {urgency}
- **User Impact:** To be assessed by the on-call team

---

## Investigation

{metrics_section}{timeline_section}

---

## Root Cause

*To be completed during postmortem review.*

Based on available data, initial investigation points:
1. Review the timeline events above for configuration changes or failures
2. Check metrics for resource exhaustion patterns
3. Correlate with recent deployments or infrastructure changes

---

## Resolution

*Document the steps taken to resolve the incident.*

---

## Action Items

| Priority | Action | Owner | Due Date |
|----------|--------|-------|----------|
| P0 | Investigate root cause | TBD | This week |
| P1 | Update monitoring/alerting | TBD | Next sprint |
| P2 | Add runbook for this failure mode | TBD | Next sprint |
| P2 | Review and improve incident response | TBD | Next quarter |

---

## Lessons Learned

*To be completed during postmortem review.*

1. What went well?
2. What could be improved?
3. Where did we get lucky?

---

*This report was auto-generated by InfraAgent Postmortem tool.
Review and update with specific findings from the investigation.*
"""

    logger.info(
        "incident_generate_postmortem completed",
        extra={"incident_id": params.incident_id},
    )
    return report
