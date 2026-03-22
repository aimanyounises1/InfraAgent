"""Tests for the multi-LLM provider module.

Covers:
- get_llm() factory with each provider
- list_providers() introspection
- Error handling for missing packages and invalid providers
- Default provider behaviour
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_provider_module() -> Any:
    """Re-import agents.llm_provider to pick up patched settings."""
    import agents.llm_provider as mod

    importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# get_llm() tests
# ---------------------------------------------------------------------------


class TestGetLlm:
    """Tests for the get_llm factory function."""

    def test_default_provider_is_ollama(self) -> None:
        """Default provider should be 'ollama' when no override is given."""
        from config import settings

        assert settings.llm_provider == "ollama"

    def test_get_llm_ollama_returns_correct_type(self) -> None:
        """get_llm('ollama') should return a ChatOllama instance."""
        mock_chat_ollama = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama

        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            mod = _reload_provider_module()
            result = mod.get_llm("ollama")
            mock_chat_ollama.assert_called_once()
            assert result == mock_chat_ollama.return_value

    def test_get_llm_ollama_uses_settings_defaults(self) -> None:
        """get_llm('ollama') should pass settings.ollama_model and base_url."""
        mock_chat_ollama = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama

        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            mod = _reload_provider_module()
            mod.get_llm("ollama")
            call_kwargs = mock_chat_ollama.call_args
            assert call_kwargs.kwargs["model"] == "nemotron-3-nano"
            assert "localhost:11434" in call_kwargs.kwargs["base_url"]

    def test_get_llm_ollama_custom_model(self) -> None:
        """get_llm('ollama', model='mistral') should use the custom model."""
        mock_chat_ollama = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama

        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            mod = _reload_provider_module()
            mod.get_llm("ollama", model="mistral")
            call_kwargs = mock_chat_ollama.call_args
            assert call_kwargs.kwargs["model"] == "mistral"

    def test_get_llm_claude_returns_chat_anthropic(self) -> None:
        """get_llm('claude') should return a ChatAnthropic instance."""
        mock_chat_anthropic = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatAnthropic = mock_chat_anthropic

        with (
            patch.dict("sys.modules", {"langchain_anthropic": mock_module}),
            patch("agents.llm_provider.settings") as mock_settings,
        ):
            mock_settings.llm_provider = "ollama"
            mock_settings.anthropic_api_key = "test-key-123"
            mock_settings.claude_model = "claude-sonnet-4-20250514"

            mod = _reload_provider_module()
            # Re-patch after reload since reload re-imports settings
            with patch.object(mod, "settings") as inner_settings:
                inner_settings.anthropic_api_key = "test-key-123"
                inner_settings.claude_model = "claude-sonnet-4-20250514"
                inner_settings.llm_provider = "ollama"
                result = mod.get_llm("claude")
                mock_chat_anthropic.assert_called_once()
                assert result == mock_chat_anthropic.return_value

    def test_get_llm_openai_missing_package_raises_import_error(self) -> None:
        """get_llm('openai') raises ImportError when package is missing."""
        import sys

        # Ensure langchain_openai is not importable
        saved = sys.modules.get("langchain_openai")
        sys.modules["langchain_openai"] = None  # type: ignore[assignment]

        try:
            mod = _reload_provider_module()
            with (
                patch.object(mod, "settings") as mock_settings,
                pytest.raises(ImportError, match="langchain-openai"),
            ):
                mock_settings.llm_provider = "ollama"
                mock_settings.openai_api_key = "test-key"
                mock_settings.openai_model = "gpt-4o"
                mod.get_llm("openai")
        finally:
            if saved is not None:
                sys.modules["langchain_openai"] = saved
            else:
                sys.modules.pop("langchain_openai", None)

    def test_get_llm_nvidia_missing_api_key_raises_value_error(self) -> None:
        """get_llm('nvidia') with empty API key should raise ValueError."""
        mock_nvidia = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatNVIDIA = mock_nvidia

        with patch.dict(
            "sys.modules", {"langchain_nvidia_ai_endpoints": mock_module}
        ):
            mod = _reload_provider_module()
            with (
                patch.object(mod, "settings") as mock_settings,
                pytest.raises(ValueError, match="API key"),
            ):
                mock_settings.llm_provider = "ollama"
                mock_settings.nvidia_api_key = ""
                mock_settings.nvidia_model = (
                    "nvidia/llama-3.1-nemotron-70b-instruct"
                )
                mod.get_llm("nvidia")

    def test_get_llm_invalid_provider_raises_value_error(self) -> None:
        """get_llm('nonexistent') should raise ValueError."""
        from agents.llm_provider import get_llm

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm("nonexistent")

    def test_get_llm_gemini_returns_correct_type(self) -> None:
        """get_llm('gemini') should return a ChatGoogleGenerativeAI."""
        mock_chat_gemini = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatGoogleGenerativeAI = mock_chat_gemini

        with patch.dict(
            "sys.modules", {"langchain_google_genai": mock_module}
        ):
            mod = _reload_provider_module()
            with patch.object(mod, "settings") as mock_settings:
                mock_settings.llm_provider = "ollama"
                mock_settings.gemini_api_key = "test-gemini-key"
                mock_settings.gemini_model = "gemini-2.0-flash"
                result = mod.get_llm("gemini")
                mock_chat_gemini.assert_called_once()
                assert result == mock_chat_gemini.return_value

    def test_get_llm_uses_settings_provider_when_none(self) -> None:
        """get_llm(None) should fall back to settings.llm_provider."""
        mock_chat_ollama = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama

        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            mod = _reload_provider_module()
            with patch.object(mod, "settings") as mock_settings:
                mock_settings.llm_provider = "ollama"
                mock_settings.ollama_model = "llama3.2"
                mock_settings.ollama_base_url = "http://localhost:11434"
                mod.get_llm()  # no provider argument
                mock_chat_ollama.assert_called_once()

    def test_get_llm_provider_case_insensitive(self) -> None:
        """get_llm('OLLAMA') should work case-insensitively."""
        mock_chat_ollama = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama

        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            mod = _reload_provider_module()
            mod.get_llm("OLLAMA")
            mock_chat_ollama.assert_called_once()

    def test_get_llm_openai_with_package_and_key(self) -> None:
        """get_llm('openai') with package and key should succeed."""
        mock_chat_openai = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOpenAI = mock_chat_openai

        with patch.dict("sys.modules", {"langchain_openai": mock_module}):
            mod = _reload_provider_module()
            with patch.object(mod, "settings") as mock_settings:
                mock_settings.llm_provider = "ollama"
                mock_settings.openai_api_key = "sk-test-key"
                mock_settings.openai_model = "gpt-4o"
                result = mod.get_llm("openai")
                mock_chat_openai.assert_called_once()
                assert result == mock_chat_openai.return_value


# ---------------------------------------------------------------------------
# list_providers() tests
# ---------------------------------------------------------------------------


class TestListProviders:
    """Tests for the list_providers introspection function."""

    def test_list_providers_returns_all_five(self) -> None:
        """list_providers() should return exactly 5 providers."""
        from agents.llm_provider import list_providers

        providers = list_providers()
        assert len(providers) == 5

    def test_list_providers_contains_expected_names(self) -> None:
        """list_providers() should include all supported provider names."""
        from agents.llm_provider import list_providers

        providers = list_providers()
        names = {p["name"] for p in providers}
        assert names == {"ollama", "nvidia", "claude", "openai", "gemini"}

    def test_list_providers_has_required_keys(self) -> None:
        """Each provider dict should contain all expected keys."""
        from agents.llm_provider import list_providers

        required_keys = {
            "name",
            "display_name",
            "installed",
            "requires_api_key",
            "api_key_set",
            "configured",
            "default_model",
            "is_active",
        }
        providers = list_providers()
        for provider in providers:
            assert required_keys.issubset(provider.keys()), (
                f"Provider {provider.get('name')} missing keys: "
                f"{required_keys - provider.keys()}"
            )

    def test_list_providers_ollama_does_not_require_api_key(self) -> None:
        """Ollama should be marked as not requiring an API key."""
        from agents.llm_provider import list_providers

        providers = list_providers()
        ollama = next(p for p in providers if p["name"] == "ollama")
        assert ollama["requires_api_key"] is False

    def test_list_providers_active_provider_flag(self) -> None:
        """Only the active provider should have is_active=True."""
        from agents.llm_provider import list_providers

        providers = list_providers()
        active = [p for p in providers if p["is_active"]]
        assert len(active) == 1
        assert active[0]["name"] == "ollama"  # default

    def test_list_providers_claude_is_installed(self) -> None:
        """Claude (langchain-anthropic) is installed as a main dependency."""
        from agents.llm_provider import list_providers

        providers = list_providers()
        claude = next(p for p in providers if p["name"] == "claude")
        assert claude["installed"] is True


# ---------------------------------------------------------------------------
# SUPPORTED_PROVIDERS constant
# ---------------------------------------------------------------------------


class TestSupportedProviders:
    """Tests for the SUPPORTED_PROVIDERS constant."""

    def test_supported_providers_has_five_entries(self) -> None:
        """SUPPORTED_PROVIDERS should have exactly 5 entries."""
        from agents.llm_provider import SUPPORTED_PROVIDERS

        assert len(SUPPORTED_PROVIDERS) == 5

    def test_supported_providers_matches_factory_registry(self) -> None:
        """SUPPORTED_PROVIDERS should match the factory registry keys."""
        from agents.llm_provider import (
            _PROVIDER_FACTORIES,
            SUPPORTED_PROVIDERS,
        )

        assert set(SUPPORTED_PROVIDERS) == set(_PROVIDER_FACTORIES.keys())
