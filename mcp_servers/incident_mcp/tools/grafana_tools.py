"""Grafana query tools for incident_mcp."""

import json
import logging

import httpx

from config import settings
from mcp_servers.incident_mcp.models import (
    GrafanaGetAlertsInput,
    GrafanaGetDashboardInput,
    GrafanaQueryInput,
)
from mcp_servers.incident_mcp.server import mcp
from mcp_servers.incident_mcp.utils import (
    get_grafana_client,
    get_mock_grafana_alerts,
    get_mock_grafana_dashboard,
    get_mock_grafana_metrics,
)

logger = logging.getLogger(__name__)


@mcp.tool(
    name="incident_grafana_query",
    annotations={
        "title": "Query Grafana Metrics",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def incident_grafana_query(params: GrafanaQueryInput) -> str:
    """Query Grafana for metrics using PromQL."""
    logger.info("incident_grafana_query called", extra={"query": params.query})

    if settings.mock_grafana:
        logger.debug("Using mock mode for Grafana query")
        data = get_mock_grafana_metrics(query=params.query)
        return json.dumps(data, indent=2, default=str)

    # Real Grafana API call
    try:
        async with get_grafana_client() as client:
            payload: dict = {
                "queries": [
                    {
                        "refId": "A",
                        "expr": params.query,
                        "intervalMs": 60000,
                        "maxDataPoints": 500,
                    }
                ],
            }
            if params.start:
                payload["from"] = params.start
            if params.end:
                payload["to"] = params.end

            resp = await client.post("/api/ds/query", json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Grafana query completed")
            return json.dumps(data, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Grafana API HTTP error",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "Grafana API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("Grafana connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to Grafana", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error("Unexpected error querying Grafana", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )


@mcp.tool(
    name="incident_grafana_get_alerts",
    annotations={
        "title": "Get Grafana Alerts",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def incident_grafana_get_alerts(params: GrafanaGetAlertsInput) -> str:
    """Get active Grafana alerts with optional state filter."""
    logger.info("incident_grafana_get_alerts called", extra={"state": params.state})

    if settings.mock_grafana:
        logger.debug("Using mock mode for Grafana alerts")
        alerts = get_mock_grafana_alerts(state=params.state or "")
        result = {"alerts": alerts, "total": len(alerts)}
        return json.dumps(result, indent=2, default=str)

    # Real Grafana API call
    try:
        async with get_grafana_client() as client:
            query_params: dict[str, str] = {}
            if params.state:
                query_params["filter"] = f"state={params.state}"

            resp = await client.get(
                "/api/alertmanager/grafana/api/v2/alerts",
                params=query_params,
            )
            resp.raise_for_status()
            alerts = resp.json()
            result = {"alerts": alerts, "total": len(alerts)}
            logger.info(
                "Grafana alerts retrieved",
                extra={"count": len(alerts)},
            )
            return json.dumps(result, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Grafana API HTTP error",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "Grafana API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("Grafana connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to Grafana", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error getting Grafana alerts",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )


@mcp.tool(
    name="incident_grafana_get_dashboard",
    annotations={
        "title": "Get Grafana Dashboard",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def incident_grafana_get_dashboard(
    params: GrafanaGetDashboardInput,
) -> str:
    """Get dashboard panel data by UID."""
    logger.info(
        "incident_grafana_get_dashboard called",
        extra={"uid": params.dashboard_uid},
    )

    if settings.mock_grafana:
        logger.debug("Using mock mode for Grafana dashboard")
        data = get_mock_grafana_dashboard(uid=params.dashboard_uid)
        return json.dumps(data, indent=2, default=str)

    # Real Grafana API call
    try:
        async with get_grafana_client() as client:
            resp = await client.get(f"/api/dashboards/uid/{params.dashboard_uid}")
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Grafana dashboard retrieved",
                extra={"uid": params.dashboard_uid},
            )
            return json.dumps(data, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Grafana API HTTP error",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "Grafana API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("Grafana connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to Grafana", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error getting Grafana dashboard",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )
