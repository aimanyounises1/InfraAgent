"""Jira ticket operations for incident_mcp.

All tools auto-detect Jira availability by attempting to create an
authenticated client.  When Jira is not configured the tool returns a
structured JSON error instead of raising.
"""

import json
import logging

import httpx

from mcp_servers.incident_mcp.models import (
    JiraCreateTicketInput,
    JiraSearchInput,
    JiraUpdateTicketInput,
)
from mcp_servers.incident_mcp.server import mcp
from mcp_servers.incident_mcp.utils import JiraUnavailableError, get_jira_client

logger = logging.getLogger(__name__)


def _jira_unavailable_response(exc: JiraUnavailableError) -> str:
    """Return a standardised JSON error when Jira is not configured."""
    return json.dumps(
        {
            "error": "Jira not configured",
            "detail": str(exc),
            "hint": "Set INFRA_AGENT_JIRA_URL and INFRA_AGENT_JIRA_TOKEN in .env",
        },
        indent=2,
    )


@mcp.tool(
    name="incident_jira_create_ticket",
    annotations={
        "title": "Create Jira Ticket",
        "readOnlyHint": False,
        "destructiveHint": False,
    },
)
async def incident_jira_create_ticket(params: JiraCreateTicketInput) -> str:
    """Create a Jira incident ticket with summary, description, and priority."""
    logger.info(
        "incident_jira_create_ticket called",
        extra={"project_key": params.project_key, "summary": params.summary},
    )

    try:
        client = get_jira_client()
    except JiraUnavailableError as exc:
        logger.warning("Jira unavailable: %s", exc)
        return _jira_unavailable_response(exc)

    try:
        async with client:
            payload = {
                "fields": {
                    "project": {"key": params.project_key},
                    "summary": params.summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": params.description}],
                            }
                        ],
                    },
                    "issuetype": {"name": params.issue_type},
                    "priority": {"name": params.priority},
                    "labels": params.labels,
                }
            }
            resp = await client.post("/rest/api/3/issue", json=payload)
            resp.raise_for_status()
            data: dict = resp.json()
            logger.info("Jira ticket created", extra={"key": data.get("key")})
            return json.dumps(data, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Jira API HTTP error",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "Jira API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("Jira connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to Jira", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error creating Jira ticket",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )


@mcp.tool(
    name="incident_jira_search",
    annotations={
        "title": "Search Jira",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def incident_jira_search(params: JiraSearchInput) -> str:
    """Search Jira for related incidents using JQL."""
    logger.info("incident_jira_search called", extra={"jql": params.jql})

    try:
        client = get_jira_client()
    except JiraUnavailableError as exc:
        logger.warning("Jira unavailable: %s", exc)
        return _jira_unavailable_response(exc)

    try:
        async with client:
            resp = await client.get(
                "/rest/api/3/search",
                params={"jql": params.jql, "maxResults": params.max_results},
            )
            resp.raise_for_status()
            data: dict = resp.json()
            logger.info(
                "Jira search completed",
                extra={"total": data.get("total", 0)},
            )
            return json.dumps(data, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Jira API HTTP error",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "Jira API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("Jira connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to Jira", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error searching Jira",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )


@mcp.tool(
    name="incident_jira_update_ticket",
    annotations={
        "title": "Update Jira Ticket",
        "readOnlyHint": False,
        "destructiveHint": True,
    },
)
async def incident_jira_update_ticket(params: JiraUpdateTicketInput) -> str:
    """Update a Jira ticket's status, assignee, or add a comment."""
    logger.info(
        "incident_jira_update_ticket called",
        extra={"issue_key": params.issue_key},
    )

    try:
        client = get_jira_client()
    except JiraUnavailableError as exc:
        logger.warning("Jira unavailable: %s", exc)
        return _jira_unavailable_response(exc)

    try:
        async with client:
            updates_applied: list[str] = []

            # Update fields (assignee)
            if params.assignee:
                field_payload = {"fields": {"assignee": {"emailAddress": params.assignee}}}
                resp = await client.put(
                    f"/rest/api/3/issue/{params.issue_key}",
                    json=field_payload,
                )
                resp.raise_for_status()
                updates_applied.append(f"assignee -> {params.assignee}")

            # Add comment
            if params.comment:
                comment_payload = {
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": params.comment}],
                            }
                        ],
                    }
                }
                resp = await client.post(
                    f"/rest/api/3/issue/{params.issue_key}/comment",
                    json=comment_payload,
                )
                resp.raise_for_status()
                updates_applied.append(f"comment added ({len(params.comment)} chars)")

            # Transition status
            if params.status:
                resp = await client.get(f"/rest/api/3/issue/{params.issue_key}/transitions")
                resp.raise_for_status()
                transitions: list[dict] = resp.json().get("transitions", [])
                target = next(
                    (t for t in transitions if t["name"].lower() == params.status.lower()),
                    None,
                )
                if target:
                    resp = await client.post(
                        f"/rest/api/3/issue/{params.issue_key}/transitions",
                        json={"transition": {"id": target["id"]}},
                    )
                    resp.raise_for_status()
                    updates_applied.append(f"status -> {params.status}")
                else:
                    available = [t["name"] for t in transitions]
                    updates_applied.append(
                        f"status transition '{params.status}' not found; available: {available}"
                    )

            result: dict = {
                "issue_key": params.issue_key,
                "success": True,
                "updates_applied": updates_applied,
                "message": f"Ticket {params.issue_key} updated successfully",
            }
            logger.info(
                "Jira ticket updated",
                extra={
                    "issue_key": params.issue_key,
                    "updates": updates_applied,
                },
            )
            return json.dumps(result, indent=2, default=str)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Jira API HTTP error during update",
            extra={
                "status": exc.response.status_code,
                "body": exc.response.text,
            },
        )
        return json.dumps(
            {
                "error": "Jira API error",
                "status_code": exc.response.status_code,
                "detail": exc.response.text,
            },
            indent=2,
            default=str,
        )
    except httpx.ConnectError as exc:
        logger.error("Jira connection failed", extra={"error": str(exc)})
        return json.dumps(
            {"error": "Failed to connect to Jira", "detail": str(exc)},
            indent=2,
            default=str,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error updating Jira ticket",
            extra={"error": str(exc)},
        )
        return json.dumps(
            {"error": "Unexpected error", "detail": str(exc)},
            indent=2,
            default=str,
        )
