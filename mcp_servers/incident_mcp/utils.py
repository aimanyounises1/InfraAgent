"""API client factories for Jira, Grafana, and PagerDuty.

Each factory auto-detects whether the service is configured by checking
for URL + token environment variables.  When a service is not configured
the factory raises a typed *Unavailable* error so the calling tool can
return a structured JSON error to the user.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unavailable Error Types
# ---------------------------------------------------------------------------


class JiraUnavailableError(Exception):
    """Raised when Jira URL or token is not configured."""


class GrafanaUnavailableError(Exception):
    """Raised when Grafana URL or token is not configured."""


class PagerDutyUnavailableError(Exception):
    """Raised when PagerDuty token is not configured."""


# ---------------------------------------------------------------------------
# HTTP Client Factories
# ---------------------------------------------------------------------------


def get_jira_client() -> httpx.AsyncClient:
    """Get an authenticated httpx client for the Jira REST API.

    Raises:
        JiraUnavailableError: If ``INFRA_AGENT_JIRA_URL`` or
            ``INFRA_AGENT_JIRA_TOKEN`` are not set.

    Returns:
        Configured ``httpx.AsyncClient`` targeting the Jira instance.
    """
    from config import settings

    if not settings.jira_url or not settings.jira_token:
        raise JiraUnavailableError(
            "Jira not configured. Set INFRA_AGENT_JIRA_URL and INFRA_AGENT_JIRA_TOKEN. "
            "See .env.example for configuration."
        )
    logger.debug("Creating Jira client for %s", settings.jira_url)
    return httpx.AsyncClient(
        base_url=settings.jira_url,
        headers={
            "Authorization": f"Basic {settings.jira_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def get_grafana_client() -> httpx.AsyncClient:
    """Get an authenticated httpx client for the Grafana API.

    Raises:
        GrafanaUnavailableError: If ``INFRA_AGENT_GRAFANA_URL`` or
            ``INFRA_AGENT_GRAFANA_TOKEN`` are not set.

    Returns:
        Configured ``httpx.AsyncClient`` targeting the Grafana instance.
    """
    from config import settings

    if not settings.grafana_url or not settings.grafana_token:
        raise GrafanaUnavailableError(
            "Grafana not configured. Set INFRA_AGENT_GRAFANA_URL and "
            "INFRA_AGENT_GRAFANA_TOKEN. See .env.example for configuration."
        )
    logger.debug("Creating Grafana client for %s", settings.grafana_url)
    return httpx.AsyncClient(
        base_url=settings.grafana_url,
        headers={
            "Authorization": f"Bearer {settings.grafana_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def get_pagerduty_client() -> httpx.AsyncClient:
    """Get an authenticated httpx client for the PagerDuty API.

    Raises:
        PagerDutyUnavailableError: If ``INFRA_AGENT_PAGERDUTY_TOKEN``
            is not set.

    Returns:
        Configured ``httpx.AsyncClient`` targeting ``api.pagerduty.com``.
    """
    from config import settings

    if not settings.pagerduty_token:
        raise PagerDutyUnavailableError(
            "PagerDuty not configured. Set INFRA_AGENT_PAGERDUTY_TOKEN. "
            "See .env.example for configuration."
        )
    logger.debug("Creating PagerDuty client")
    return httpx.AsyncClient(
        base_url="https://api.pagerduty.com",
        headers={
            "Authorization": f"Token token={settings.pagerduty_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
