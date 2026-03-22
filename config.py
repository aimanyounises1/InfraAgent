"""Centralized configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """InfraAgent configuration -- all values driven by environment variables.

    Prefix: INFRA_AGENT_
    Example: INFRA_AGENT_MOCK_GPU=true  ->  settings.mock_gpu == True
    """

    # --- LLM Provider ---
    llm_provider: str = "ollama"  # ollama, nvidia, claude, openai, gemini

    # --- Ollama (local) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:14b"

    # --- NVIDIA NIM ---
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"

    # --- Claude (Anthropic) ---
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # --- Google Gemini ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- Kubernetes ---
    k8s_context: str = ""
    k8s_namespace_default: str = "default"
    mock_k8s: bool = True

    # --- GPU Monitoring ---
    mock_gpu: bool = True

    # --- Jira ---
    mock_jira: bool = True
    jira_url: str = ""
    jira_token: str = ""
    jira_user: str = ""

    # --- Grafana ---
    mock_grafana: bool = True
    grafana_url: str = ""
    grafana_token: str = ""

    # --- PagerDuty ---
    mock_pagerduty: bool = True
    pagerduty_token: str = ""

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- LLM Analysis ---
    llm_analysis_timeout: int = 30  # seconds for LLM analysis calls
    llm_analysis_max_data_chars: int = 4000  # max chars of data sent to LLM

    model_config = {
        "env_prefix": "INFRA_AGENT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
