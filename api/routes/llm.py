"""LLM provider management endpoints -- list and switch LLM providers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from agents.llm_provider import SUPPORTED_PROVIDERS, get_llm, list_providers
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SetProviderRequest(BaseModel):
    """Request body for switching the active LLM provider."""

    provider: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="LLM provider name (ollama, nvidia, claude, openai, gemini)",
    )
    model: str | None = Field(
        default=None,
        max_length=200,
        description="Optional model override for the provider",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Ensure the provider name is one of the supported options."""
        normalized: str = v.lower().strip()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unknown provider '{v}'. "
                f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
            )
        return normalized


class SetProviderResponse(BaseModel):
    """Response body confirming the provider switch."""

    provider: str
    model: str
    status: str


class ListProvidersResponse(BaseModel):
    """Response body listing all available LLM providers."""

    active_provider: str
    providers: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=ListProvidersResponse)
async def list_llm_providers() -> ListProvidersResponse:
    """List available LLM providers and their configuration status.

    Returns each provider's installation status, API key configuration,
    default model, and whether it is the currently active provider.

    Returns:
        ListProvidersResponse with the active provider and a list of
        all provider details.
    """
    logger.debug("Listing LLM providers")
    try:
        providers: list[dict[str, Any]] = list_providers()
        return ListProvidersResponse(
            active_provider=settings.llm_provider,
            providers=providers,
        )
    except Exception as exc:
        logger.error("Failed to list LLM providers: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list providers: {exc}",
        ) from exc


@router.post("/provider", response_model=SetProviderResponse)
async def set_provider(request: SetProviderRequest) -> SetProviderResponse:
    """Switch the active LLM provider at runtime.

    Validates that the requested provider is installed and configured,
    then updates the runtime settings. Note: this changes the in-process
    setting only -- it does not persist across restarts. Set the
    INFRA_AGENT_LLM_PROVIDER environment variable for persistence.

    Args:
        request: The provider switch request with provider name and
                 optional model override.

    Returns:
        SetProviderResponse confirming the new active provider and model.

    Raises:
        HTTPException 400: If the provider dependency is not installed
                           or required API keys are missing.
    """
    logger.info(
        "Switching LLM provider",
        extra={"provider": request.provider, "model": request.model},
    )

    # Validate that the provider can actually be instantiated
    try:
        llm = get_llm(provider=request.provider, model=request.model)
    except ImportError as exc:
        logger.warning("Provider not installed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        logger.warning("Provider configuration error: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error creating LLM: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize provider: {exc}",
        ) from exc

    # Update the runtime setting
    settings.llm_provider = request.provider

    # Determine the resolved model name from the LLM instance
    resolved_model: str = getattr(llm, "model_name", "") or getattr(llm, "model", "unknown")

    logger.info(
        "LLM provider switched successfully",
        extra={"provider": request.provider, "model": resolved_model},
    )

    return SetProviderResponse(
        provider=request.provider,
        model=str(resolved_model),
        status="active",
    )
