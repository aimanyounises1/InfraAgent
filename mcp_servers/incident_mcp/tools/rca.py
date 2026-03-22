"""Root Cause Analysis generator for incident_mcp."""

import json
import logging
from datetime import UTC, datetime

from mcp_servers.incident_mcp.models import GenerateRCAInput
from mcp_servers.incident_mcp.server import mcp

logger = logging.getLogger(__name__)


def _build_rca_report(
    incident_summary: str,
    metrics_data: str | None,
    related_tickets: str | None,
    timeline: str | None,
) -> str:
    """Build a structured Root Cause Analysis Markdown report.

    Args:
        incident_summary: Brief description of the incident.
        metrics_data: Optional JSON string of Grafana metrics.
        related_tickets: Optional JSON string of related Jira tickets.
        timeline: Optional JSON string of event timeline.

    Returns:
        Formatted Markdown string containing the full RCA report.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Parse optional JSON fields safely
    metrics_section = ""
    if metrics_data:
        try:
            parsed_metrics = json.loads(metrics_data)
            metrics_section = (
                "### Key Metrics\n"
                "```json\n"
                f"{json.dumps(parsed_metrics, indent=2, default=str)}"
                "\n```\n\n"
            )
        except (json.JSONDecodeError, TypeError):
            metrics_section = f"### Key Metrics\n```\n{metrics_data}\n```\n\n"

    tickets_section = ""
    if related_tickets:
        try:
            parsed_tickets = json.loads(related_tickets)
            if isinstance(parsed_tickets, list):
                ticket_lines = []
                for t in parsed_tickets:
                    key = t.get("key", "N/A")
                    summary = t.get("fields", {}).get("summary", t.get("summary", "N/A"))
                    status = t.get("fields", {}).get("status", {}).get("name", "Unknown")
                    ticket_lines.append(f"- **{key}**: {summary} (Status: {status})")
                tickets_section = "### Related Tickets\n" + "\n".join(ticket_lines) + "\n\n"
            else:
                tickets_section = (
                    "### Related Tickets\n"
                    "```json\n"
                    f"{json.dumps(parsed_tickets, indent=2, default=str)}"
                    "\n```\n\n"
                )
        except (json.JSONDecodeError, TypeError):
            tickets_section = f"### Related Tickets\n```\n{related_tickets}\n```\n\n"

    timeline_section = ""
    if timeline:
        try:
            parsed_timeline = json.loads(timeline)
            if isinstance(parsed_timeline, list):
                tl_lines = []
                for entry in parsed_timeline:
                    ts = entry.get("timestamp", entry.get("time", ""))
                    event = entry.get("event", entry.get("description", str(entry)))
                    tl_lines.append(f"| {ts} | {event} |")
                timeline_section = (
                    "### Timeline of Events\n"
                    "| Time | Event |\n"
                    "|------|-------|\n" + "\n".join(tl_lines) + "\n\n"
                )
            else:
                timeline_section = (
                    "### Timeline of Events\n"
                    "```json\n"
                    f"{json.dumps(parsed_timeline, indent=2, default=str)}"
                    "\n```\n\n"
                )
        except (json.JSONDecodeError, TypeError):
            timeline_section = f"### Timeline of Events\n```\n{timeline}\n```\n\n"

    report = f"""# Root Cause Analysis Report

**Generated:** {now}
**Incident:** {incident_summary}

---

## Summary

An incident was detected requiring root cause analysis. The following report
documents the findings, impact assessment, and recommended remediation steps.

**Incident Description:** {incident_summary}

---

## Investigation

{metrics_section}{tickets_section}{timeline_section}

---

## Root Cause

Based on the available data, the root cause analysis indicates:

1. **Primary Cause:** The incident appears to be related to resource exhaustion
   or misconfiguration based on the observed symptoms described in:
   "{incident_summary}"

2. **Contributing Factors:**
   - Increased load or traffic patterns exceeding provisioned capacity
   - Potential gap in monitoring/alerting thresholds
   - Configuration drift from baseline

---

## Impact Assessment

| Dimension | Assessment |
|-----------|-----------|
| **Severity** | High - Service degradation detected |
| **Duration** | To be determined from timeline data |
| **Affected Services** | Services related to: {incident_summary} |
| **User Impact** | Potential latency increase or partial outage |

---

## Remediation Steps

1. **Immediate (0-1 hour):**
   - Verify current system health and confirm incident resolution
   - Roll back any recent changes if they are identified as the trigger
   - Scale resources if capacity-related

2. **Short-term (1-24 hours):**
   - Review and tighten monitoring alert thresholds
   - Perform full health check on affected services
   - Document all actions taken during the incident

3. **Long-term (1-2 weeks):**
   - Implement automated scaling policies if not already in place
   - Add canary deployments for early detection
   - Schedule post-incident review meeting

---

## Prevention

- **Monitoring:** Add/refine alerts for early detection of similar issues
- **Testing:** Include load/chaos testing scenarios that cover this failure mode
- **Runbooks:** Update or create runbooks for this incident class
- **Architecture:** Evaluate whether redundancy or failover improvements are needed

---

*This report was auto-generated by InfraAgent RCA tool. Review and update with
specific findings from the investigation.*
"""
    return report


@mcp.tool(
    name="incident_generate_rca",
    annotations={
        "title": "Generate Root Cause Analysis",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def incident_generate_rca(params: GenerateRCAInput) -> str:
    """Generate a Root Cause Analysis report from collected incident data."""
    logger.info(
        "incident_generate_rca called",
        extra={"incident_summary": params.incident_summary},
    )

    try:
        report = _build_rca_report(
            incident_summary=params.incident_summary,
            metrics_data=params.metrics_data,
            related_tickets=params.related_tickets,
            timeline=params.timeline,
        )
        logger.info("RCA report generated successfully")
        return report
    except Exception as exc:
        logger.error("Failed to generate RCA report", extra={"error": str(exc)})
        return json.dumps(
            {
                "error": "Failed to generate RCA report",
                "detail": str(exc),
            },
            indent=2,
            default=str,
        )
