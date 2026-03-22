"""Multi-LLM provider -- supports Ollama, NVIDIA NIM, Claude, OpenAI, Gemini.

Configure via INFRA_AGENT_LLM_PROVIDER env var:
  - "ollama"  -> local Ollama (default, no API key needed)
  - "nvidia"  -> NVIDIA NIM API
  - "claude"  -> Anthropic Claude
  - "openai"  -> OpenAI GPT
  - "gemini"  -> Google Gemini

Usage:
    from agents.llm_provider import get_llm
    llm = get_llm()                       # uses configured default
    llm = get_llm("claude")               # explicit provider
    llm = get_llm("openai", "gpt-4o")    # explicit provider + model
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from config import settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported providers
# ---------------------------------------------------------------------------

SUPPORTED_PROVIDERS: list[str] = ["ollama", "nvidia", "claude", "openai", "gemini"]


# ---------------------------------------------------------------------------
# Per-provider factory helpers
# ---------------------------------------------------------------------------


def _create_ollama(model: str | None) -> BaseChatModel:
    """Create a ChatOllama instance for local Ollama inference.

    Args:
        model: Model name override, or None to use settings.ollama_model.

    Returns:
        A ChatOllama instance.

    Raises:
        ImportError: If langchain-ollama is not installed.
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "Ollama provider requires 'langchain-ollama'. "
            "Install it with: pip install 'langchain-ollama>=0.3'"
        ) from exc

    resolved_model: str = model or settings.ollama_model
    logger.info(
        "Creating Ollama LLM with model=%s, base_url=%s",
        resolved_model,
        settings.ollama_base_url,
    )
    return ChatOllama(
        model=resolved_model,
        base_url=settings.ollama_base_url,
    )


def _create_nvidia(model: str | None) -> BaseChatModel:
    """Create a ChatNVIDIA instance for NVIDIA NIM inference.

    Args:
        model: Model name override, or None to use settings.nvidia_model.

    Returns:
        A ChatNVIDIA instance.

    Raises:
        ImportError: If langchain-nvidia-ai-endpoints is not installed.
        ValueError: If no NVIDIA API key is configured.
    """
    try:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
    except ImportError as exc:
        raise ImportError(
            "NVIDIA provider requires 'langchain-nvidia-ai-endpoints'. "
            "Install it with: pip install 'langchain-nvidia-ai-endpoints>=0.3'"
        ) from exc

    if not settings.nvidia_api_key:
        raise ValueError(
            "NVIDIA provider requires an API key. "
            "Set INFRA_AGENT_NVIDIA_API_KEY environment variable."
        )

    resolved_model: str = model or settings.nvidia_model
    logger.info("Creating NVIDIA NIM LLM with model=%s", resolved_model)
    return ChatNVIDIA(
        model=resolved_model,
        api_key=settings.nvidia_api_key,
    )


def _create_claude(model: str | None) -> BaseChatModel:
    """Create a ChatAnthropic instance for Anthropic Claude inference.

    Args:
        model: Model name override, or None to use settings.claude_model.

    Returns:
        A ChatAnthropic instance.

    Raises:
        ImportError: If langchain-anthropic is not installed.
        ValueError: If no Anthropic API key is configured.
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        raise ImportError(
            "Claude provider requires 'langchain-anthropic'. "
            "Install it with: pip install 'langchain-anthropic>=0.4'"
        ) from exc

    if not settings.anthropic_api_key:
        raise ValueError(
            "Claude provider requires an API key. "
            "Set INFRA_AGENT_ANTHROPIC_API_KEY environment variable."
        )

    resolved_model: str = model or settings.claude_model
    logger.info("Creating Claude LLM with model=%s", resolved_model)
    return ChatAnthropic(
        model=resolved_model,
        api_key=settings.anthropic_api_key,
    )


def _create_openai(model: str | None) -> BaseChatModel:
    """Create a ChatOpenAI instance for OpenAI GPT inference.

    Args:
        model: Model name override, or None to use settings.openai_model.

    Returns:
        A ChatOpenAI instance.

    Raises:
        ImportError: If langchain-openai is not installed.
        ValueError: If no OpenAI API key is configured.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError(
            "OpenAI provider requires 'langchain-openai'. "
            "Install it with: pip install 'langchain-openai>=0.3'"
        ) from exc

    if not settings.openai_api_key:
        raise ValueError(
            "OpenAI provider requires an API key. "
            "Set INFRA_AGENT_OPENAI_API_KEY environment variable."
        )

    resolved_model: str = model or settings.openai_model
    logger.info("Creating OpenAI LLM with model=%s", resolved_model)
    return ChatOpenAI(
        model=resolved_model,
        api_key=settings.openai_api_key,
    )


def _create_gemini(model: str | None) -> BaseChatModel:
    """Create a ChatGoogleGenerativeAI instance for Google Gemini inference.

    Args:
        model: Model name override, or None to use settings.gemini_model.

    Returns:
        A ChatGoogleGenerativeAI instance.

    Raises:
        ImportError: If langchain-google-genai is not installed.
        ValueError: If no Gemini API key is configured.
    """
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise ImportError(
            "Gemini provider requires 'langchain-google-genai'. "
            "Install it with: pip install 'langchain-google-genai>=2.0'"
        ) from exc

    if not settings.gemini_api_key:
        raise ValueError(
            "Gemini provider requires an API key. "
            "Set INFRA_AGENT_GEMINI_API_KEY environment variable."
        )

    resolved_model: str = model or settings.gemini_model
    logger.info("Creating Gemini LLM with model=%s", resolved_model)
    return ChatGoogleGenerativeAI(
        model=resolved_model,
        google_api_key=settings.gemini_api_key,
    )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDER_FACTORIES: dict[str, Any] = {
    "ollama": _create_ollama,
    "nvidia": _create_nvidia,
    "claude": _create_claude,
    "openai": _create_openai,
    "gemini": _create_gemini,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_llm(provider: str | None = None, model: str | None = None) -> BaseChatModel:
    """Create and return a LangChain BaseChatModel for the specified provider.

    If no provider is given, falls back to the INFRA_AGENT_LLM_PROVIDER
    environment variable (via settings), which defaults to "ollama".

    Args:
        provider: One of "ollama", "nvidia", "claude", "openai", "gemini".
                  Defaults to settings.llm_provider if not specified.
        model: Model name override. If None, each provider uses its
               configured default from settings.

    Returns:
        A LangChain BaseChatModel instance for the selected provider.

    Raises:
        ValueError: If the provider name is not recognized.
        ImportError: If the provider's LangChain integration is not installed.
        ValueError: If required API keys are missing.
    """
    resolved_provider: str = (provider or settings.llm_provider).lower().strip()

    if resolved_provider not in _PROVIDER_FACTORIES:
        raise ValueError(
            f"Unknown LLM provider: '{resolved_provider}'. "
            f"Supported providers: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    logger.debug(
        "get_llm called with provider=%s, model=%s", resolved_provider, model
    )
    factory = _PROVIDER_FACTORIES[resolved_provider]
    return factory(model)


def list_providers() -> list[dict[str, Any]]:
    """List all supported LLM providers with their configuration status.

    Checks each provider for:
    - Whether its LangChain dependency is importable
    - Whether required API keys are configured
    - The default model from settings

    Returns:
        A list of dicts, each containing provider name, installed status,
        configured status, and default model name.
    """
    providers: list[dict[str, Any]] = []

    provider_info: list[dict[str, Any]] = [
        {
            "name": "ollama",
            "display_name": "Ollama (Local)",
            "package": "langchain_ollama",
            "requires_api_key": False,
            "api_key_set": True,
            "default_model": settings.ollama_model,
        },
        {
            "name": "nvidia",
            "display_name": "NVIDIA NIM",
            "package": "langchain_nvidia_ai_endpoints",
            "requires_api_key": True,
            "api_key_set": bool(settings.nvidia_api_key),
            "default_model": settings.nvidia_model,
        },
        {
            "name": "claude",
            "display_name": "Anthropic Claude",
            "package": "langchain_anthropic",
            "requires_api_key": True,
            "api_key_set": bool(settings.anthropic_api_key),
            "default_model": settings.claude_model,
        },
        {
            "name": "openai",
            "display_name": "OpenAI GPT",
            "package": "langchain_openai",
            "requires_api_key": True,
            "api_key_set": bool(settings.openai_api_key),
            "default_model": settings.openai_model,
        },
        {
            "name": "gemini",
            "display_name": "Google Gemini",
            "package": "langchain_google_genai",
            "requires_api_key": True,
            "api_key_set": bool(settings.gemini_api_key),
            "default_model": settings.gemini_model,
        },
    ]

    for info in provider_info:
        # Check if the package is importable
        installed: bool = False
        try:
            __import__(info["package"])
            installed = True
        except ImportError:
            pass

        # A provider is "ready" if installed and (no key needed OR key is set)
        configured: bool = installed and (
            not info["requires_api_key"] or info["api_key_set"]
        )

        providers.append(
            {
                "name": info["name"],
                "display_name": info["display_name"],
                "installed": installed,
                "requires_api_key": info["requires_api_key"],
                "api_key_set": info["api_key_set"],
                "configured": configured,
                "default_model": info["default_model"],
                "is_active": info["name"] == settings.llm_provider,
            }
        )

    return providers
