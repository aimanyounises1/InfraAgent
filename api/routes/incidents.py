"""Incident management API routes -- wired to incident_mcp tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter

from mcp_servers.incident_mcp.models import (
    GrafanaGetAlertsInput,
    PagerDutyListIncidentsInput,
)
from mcp_servers.incident_mcp.tools.grafana_tools import incident_grafana_get_alerts
from mcp_servers.incident_mcp.tools.pagerduty_tools import incident_pagerduty_list_incidents

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/active")
async def active_incidents() -> dict[str, Any]:
    """Get active incidents from PagerDuty and Grafana alerts.

    Calls both the PagerDuty incident listing tool and the Grafana alerts
    tool, combining the results into a single response payload.

    Returns:
        Dictionary with status, PagerDuty incidents, and Grafana alerts.
    """
    logger.info("active_incidents route called")

    pagerduty_data: Any = None
    grafana_data: Any = None
    errors: list[str] = []

    # Fetch PagerDuty incidents
    try:
        pd_raw: str = await incident_pagerduty_list_incidents(PagerDutyListIncidentsInput())
        pagerduty_data = json.loads(pd_raw)

        if isinstance(pagerduty_data, dict) and "error" in pagerduty_data:
            logger.warning(
                "active_incidents PagerDuty returned error",
                extra={"error": pagerduty_data["error"]},
            )
            errors.append(f"PagerDuty: {pagerduty_data['error']}")
    except json.JSONDecodeError as e:
        logger.error("active_incidents PagerDuty JSON parse failed", extra={"error": str(e)})
        errors.append(f"PagerDuty: Failed to parse response: {e}")
    except Exception as e:
        logger.error("active_incidents PagerDuty call failed", extra={"error": str(e)})
        errors.append(f"PagerDuty: {e}")

    # Fetch Grafana alerts
    try:
        grafana_raw: str = await incident_grafana_get_alerts(GrafanaGetAlertsInput())
        grafana_data = json.loads(grafana_raw)

        if isinstance(grafana_data, dict) and "error" in grafana_data:
            logger.warning(
                "active_incidents Grafana returned error",
                extra={"error": grafana_data["error"]},
            )
            errors.append(f"Grafana: {grafana_data['error']}")
    except json.JSONDecodeError as e:
        logger.error("active_incidents Grafana JSON parse failed", extra={"error": str(e)})
        errors.append(f"Grafana: Failed to parse response: {e}")
    except Exception as e:
        logger.error("active_incidents Grafana call failed", extra={"error": str(e)})
        errors.append(f"Grafana: {e}")

    # If both sources failed, return error status
    if pagerduty_data is None and grafana_data is None:
        return {
            "status": "error",
            "message": "Failed to fetch from all incident sources",
            "errors": errors,
        }

    result: dict[str, Any] = {
        "status": "ok" if not errors else "partial",
        "pagerduty": pagerduty_data,
        "grafana_alerts": grafana_data,
    }

    if errors:
        result["errors"] = errors

    logger.info(
        "active_incidents completed",
        extra={
            "has_pagerduty": pagerduty_data is not None,
            "has_grafana": grafana_data is not None,
            "error_count": len(errors),
        },
    )

    return result
