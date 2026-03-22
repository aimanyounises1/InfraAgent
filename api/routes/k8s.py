"""Kubernetes API routes -- wired to k8s_mcp tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter

from mcp_servers.k8s_mcp.models import (
    K8sListDeploymentsInput,
    K8sListPodsInput,
    K8sListServicesInput,
)
from mcp_servers.k8s_mcp.tools.deployments import k8s_list_deployments
from mcp_servers.k8s_mcp.tools.pods import k8s_list_pods
from mcp_servers.k8s_mcp.tools.services import k8s_list_services

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/pods")
async def list_pods(namespace: str = "default") -> dict[str, Any]:
    """List pods in a namespace by calling the k8s_mcp list pods tool.

    Args:
        namespace: Kubernetes namespace to query. Defaults to "default".

    Returns:
        Dictionary with status and pod data, or an error message.
    """
    logger.info("list_pods route called", extra={"namespace": namespace})

    try:
        raw_result: str = await k8s_list_pods(
            K8sListPodsInput(namespace=namespace),
        )
        parsed: dict[str, Any] = json.loads(raw_result)

        if "error" in parsed:
            logger.warning(
                "list_pods returned error from tool",
                extra={"error": parsed["error"]},
            )
            return {
                "status": "error",
                "message": parsed.get("error", "Unknown error"),
                "data": parsed,
            }

        return {"status": "ok", "data": parsed}

    except json.JSONDecodeError as e:
        logger.error("list_pods JSON parse failed", extra={"error": str(e)})
        return {"status": "error", "message": f"Failed to parse tool response: {e}"}
    except Exception as e:
        logger.error(
            "list_pods failed",
            extra={"error": str(e), "namespace": namespace},
        )
        return {"status": "error", "message": str(e)}


@router.get("/deployments")
async def list_deployments(namespace: str = "default") -> dict[str, Any]:
    """List deployments in a namespace by calling the k8s_mcp tool.

    Args:
        namespace: Kubernetes namespace to query. Defaults to "default".

    Returns:
        Dictionary with status and deployment data, or an error message.
    """
    logger.info(
        "list_deployments route called",
        extra={"namespace": namespace},
    )

    try:
        raw_result: str = await k8s_list_deployments(
            K8sListDeploymentsInput(namespace=namespace),
        )
        parsed: dict[str, Any] = json.loads(raw_result)

        if "error" in parsed:
            logger.warning(
                "list_deployments returned error from tool",
                extra={"error": parsed["error"]},
            )
            return {
                "status": "error",
                "message": parsed.get("error", "Unknown error"),
                "data": parsed,
            }

        return {"status": "ok", "data": parsed}

    except json.JSONDecodeError as e:
        logger.error(
            "list_deployments JSON parse failed",
            extra={"error": str(e)},
        )
        return {"status": "error", "message": f"Failed to parse tool response: {e}"}
    except Exception as e:
        logger.error(
            "list_deployments failed",
            extra={"error": str(e), "namespace": namespace},
        )
        return {"status": "error", "message": str(e)}


@router.get("/services")
async def list_services(namespace: str = "default") -> dict[str, Any]:
    """List services in a namespace by calling the k8s_mcp tool.

    Args:
        namespace: Kubernetes namespace to query. Defaults to "default".

    Returns:
        Dictionary with status and service data, or an error message.
    """
    logger.info(
        "list_services route called",
        extra={"namespace": namespace},
    )

    try:
        raw_result: str = await k8s_list_services(
            K8sListServicesInput(namespace=namespace),
        )
        parsed: dict[str, Any] = json.loads(raw_result)

        if "error" in parsed:
            logger.warning(
                "list_services returned error from tool",
                extra={"error": parsed["error"]},
            )
            return {
                "status": "error",
                "message": parsed.get("error", "Unknown error"),
                "data": parsed,
            }

        return {"status": "ok", "data": parsed}

    except json.JSONDecodeError as e:
        logger.error(
            "list_services JSON parse failed",
            extra={"error": str(e)},
        )
        return {"status": "error", "message": f"Failed to parse tool response: {e}"}
    except Exception as e:
        logger.error(
            "list_services failed",
            extra={"error": str(e), "namespace": namespace},
        )
        return {"status": "error", "message": str(e)}
