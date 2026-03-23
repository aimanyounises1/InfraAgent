"""Centralized configuration using Pydantic Settings.

All values are driven by environment variables with INFRA_AGENT_ prefix.
The system auto-detects available hardware and services at startup.
Set explicit overrides via environment variables when needed.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """InfraAgent configuration -- all values driven by environment variables.

    Prefix: INFRA_AGENT_
    Example: INFRA_AGENT_LLM_PROVIDER=claude  ->  settings.llm_provider == "claude"

    The system auto-detects available infrastructure. Use environment
    variables to override auto-detection when needed.
    """

    # --- LLM Provider ---
    llm_provider: str = "ollama"  # ollama, nvidia, claude, openai, gemini

    # --- Ollama (local / air-gapped HPC) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "nemotron-3-nano"

    # --- NVIDIA NIM (on-prem HPC preferred) ---
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
    # K8s availability is detected at the tool layer (k8s_mcp).
    # No mock flag needed -- tools return errors when K8s is unavailable.
    k8s_context: str = ""
    k8s_namespace_default: str = "default"

    # --- GPU Monitoring ---
    # GPU backend is auto-detected by gpu_mcp/utils.py (pynvml -> Apple -> none)
    # No mock_gpu flag needed -- the system adapts to available hardware.

    # --- DCGM (optional, for NVIDIA datacenter GPUs) ---
    dcgm_host: str = "localhost"
    dcgm_port: int = 5555

    # --- Slurm HPC Scheduler ---
    # Slurm availability is detected at the tool layer.
    # No mock flag needed -- tools return errors when Slurm is unavailable.
    slurm_rest_url: str = "http://localhost:6820"
    slurm_jwt_token: str = ""
    slurm_cluster_name: str = ""

    # --- Jira ---
    # Auto-detected: tools check jira_url + jira_token at call time
    jira_url: str = ""
    jira_token: str = ""
    jira_user: str = ""

    # --- Grafana ---
    # Auto-detected: tools check grafana_url + grafana_token at call time
    grafana_url: str = ""
    grafana_token: str = ""

    # --- PagerDuty ---
    # Auto-detected: tools check pagerduty_token at call time
    pagerduty_token: str = ""

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- LLM Analysis ---
    llm_analysis_timeout: int = 120  # seconds
    llm_analysis_max_data_chars: int = 4000

    # --- ReAct Engine ---
    react_max_iterations: int = 15
    react_step_timeout: int = 30  # seconds per tool step
    react_planning_enabled: bool = True  # False = legacy keyword routing

    # --- Approval Workflow ---
    approval_timeout: int = 300  # seconds to wait for human approval
    approval_required_for_destructive: bool = True

    # --- Conversation Memory ---
    memory_max_turns: int = 10

    # --- API Security ---
    auth_enabled: bool = False
    api_keys: str = ""  # comma-separated API keys
    rate_limit_rpm: int = 60

    # --- Runbooks ---
    runbook_dir: str = "runbooks"

    # --- Audit ---
    audit_log_file: str = "audit.log"
    audit_enabled: bool = True

    # --- Classification ---
    classification_confidence_threshold: float = 0.3
    classification_use_llm: bool = True

    model_config = {
        "env_prefix": "INFRA_AGENT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
