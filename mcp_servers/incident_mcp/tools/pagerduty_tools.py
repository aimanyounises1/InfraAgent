"""PagerDuty alert tools for incident_mcp.

All tools auto-detect PagerDuty availability by attempting to create an
authenticated client.  When PagerDuty is not configured the tool returns
a structured JSON error instead of raising.
"""

import json
import logging

import httpx

from mcp_servers.incident_mcp.models import (
    PagerDutyAcknowledgeInput,
    PagerDutyListIncidentsInput,
    PagerDutyResolveInput,
)
from mcp_servers.incident_mcp.server import mcp
from mcp_servers.incident_mcp.utils import (
    PagerDutyUnavailableError,
    get_pagerduty_client,
)

logger = logging.getLogger(__name__)


def _pd_unavailable_response(exc: PagerDutyUnavailableError) -> str:
    """Return a standardised JSON error when PagerDuty is not configured."""
    return json.dumps(
        {
            "error": "PagerDuty not configured",
            "detail": str(exc),
            "hint": "Set INFRA_AGENT_PAGERDUTY_TOKEN in .env",
        },
        indent=2,
    )


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

    try:
        client = get_pagerduty_client()
    except PagerDutyUnavailableError as exc:
        logger.warning("PagerDuty unavailable: %s", exc)
        return _pd_unavailable_response(exc)

    try:
        async with client:
            query_params: dict[str, str | int] = {"limit": params.limit}
            if params.status:
                # PagerDuty API accepts statuses[] as repeated params
                query_params["statuses[]"] = params.status.split(",")

            resp = await client.get("/incidents", params=query_params)
            resp.raise_for_status()
            data: dict = resp.json()
            incidents: list = data.get("incidents", [])
            result: dict = {
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

    try:
        client = get_pagerduty_client()
    except PagerDutyUnavailableError as exc:
        logger.warning("PagerDuty unavailable: %s", exc)
        return _pd_unavailable_response(exc)

    try:
        async with client:
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
            data: dict = resp.json()
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

    try:
        client = get_pagerduty_client()
    except PagerDutyUnavailableError as exc:
        logger.warning("PagerDuty unavailable: %s", exc)
        return _pd_unavailable_response(exc)

    try:
        async with client:
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
            data: dict = resp.json()
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
