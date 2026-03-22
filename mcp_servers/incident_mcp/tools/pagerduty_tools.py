"""PagerDuty alert tools for incident_mcp."""

import json
import logging

import httpx

from config import settings
from mcp_servers.incident_mcp.models import (
    PagerDutyAcknowledgeInput,
    PagerDutyListIncidentsInput,
    PagerDutyResolveInput,
)
from mcp_servers.incident_mcp.server import mcp
from mcp_servers.incident_mcp.utils import (
    get_mock_pd_incidents,
    get_pagerduty_client,
)

logger = logging.getLogger(__name__)


@mcp.tool(
    name="incident_pagerduty_list_incidents",
    annotations={
        "title": "List PagerDuty Incidents",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def incident_pagerduty_list_incidents(
    params: PagerDutyListIncidentsInput,
) -> str:
    """List active PagerDuty incidents with status filter."""
    logger.info(
        "incident_pagerduty_list_incidents called",
        extra={"status": params.status, "limit": params.limit},
    )

    if settings.mock_pagerduty:
        logger.debug("Using mock mode for PagerDuty list incidents")
        incidents = get_mock_pd_incidents(status=params.status or "")
        limited = incidents[: params.limit]
        result = {
            "incidents": limited,
            "total": len(limited),
            "more": len(incidents) > params.limit,
        }
        return json.dumps(result, indent=2, default=str)

    # Real PagerDuty API call
    try:
        async with get_pagerduty_client() as client:
            query_params: dict[str, str | int] = {"limit": params.limit}
            if params.status:
                # PagerDuty API accepts statuses[] as repeated params
                query_params["statuses[]"] = params.status.split(",")

            resp = await client.get("/incidents", params=query_params)
            resp.raise_for_status()
            data = resp.json()
            incidents = data.get("incidents", [])
            result = {
                "incidents": incidents,
                "total": len(incidents),
                "more": data.get("more", False),
            }
            logger.info(
                "PagerDuty incidents retrieved",
                extra={"count": len(incidents)},
            )
            return json.dumps(result, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "PagerDuty API HTTP error",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "PagerDuty API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("PagerDuty connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to PagerDuty", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error listing PagerDuty incidents",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )


@mcp.tool(
    name="incident_pagerduty_acknowledge",
    annotations={
        "title": "Acknowledge PD Incident",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
async def incident_pagerduty_acknowledge(
    params: PagerDutyAcknowledgeInput,
) -> str:
    """Acknowledge a PagerDuty incident."""
    logger.info(
        "incident_pagerduty_acknowledge called",
        extra={"incident_id": params.incident_id},
    )

    if settings.mock_pagerduty:
        logger.debug("Using mock mode for PagerDuty acknowledge")
        result = {
            "incident": {
                "id": params.incident_id,
                "status": "acknowledged",
                "message": (f"Incident {params.incident_id} acknowledged successfully (mock mode)"),
            },
        }
        return json.dumps(result, indent=2, default=str)

    # Real PagerDuty API call
    try:
        async with get_pagerduty_client() as client:
            payload = {
                "incident": {
                    "id": params.incident_id,
                    "type": "incident_reference",
                    "status": "acknowledged",
                }
            }
            resp = await client.put(
                f"/incidents/{params.incident_id}",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "PagerDuty incident acknowledged",
                extra={"incident_id": params.incident_id},
            )
            return json.dumps(data, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "PagerDuty API HTTP error during acknowledge",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "PagerDuty API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("PagerDuty connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to PagerDuty", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error acknowledging PagerDuty incident",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )


@mcp.tool(
    name="incident_pagerduty_resolve",
    annotations={
        "title": "Resolve PD Incident",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
async def incident_pagerduty_resolve(params: PagerDutyResolveInput) -> str:
    """Resolve a PagerDuty incident."""
    logger.info(
        "incident_pagerduty_resolve called",
        extra={"incident_id": params.incident_id},
    )

    if settings.mock_pagerduty:
        logger.debug("Using mock mode for PagerDuty resolve")
        result = {
            "incident": {
                "id": params.incident_id,
                "status": "resolved",
                "message": (f"Incident {params.incident_id} resolved successfully (mock mode)"),
            },
        }
        return json.dumps(result, indent=2, default=str)

    # Real PagerDuty API call
    try:
        async with get_pagerduty_client() as client:
            payload = {
                "incident": {
                    "id": params.incident_id,
                    "type": "incident_reference",
                    "status": "resolved",
                }
            }
            resp = await client.put(
                f"/incidents/{params.incident_id}",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "PagerDuty incident resolved",
                extra={"incident_id": params.incident_id},
            )
            return json.dumps(data, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "PagerDuty API HTTP error during resolve",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "PagerDuty API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("PagerDuty connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to PagerDuty", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error resolving PagerDuty incident",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )
