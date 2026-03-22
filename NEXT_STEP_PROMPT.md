# Claude Code Prompt — InfraAgent Phase 2: Complete Auto-Detection Refactor

> Paste this entire prompt into Claude Code when opening the InfraAgent project.

---

## Context

You are continuing work on **InfraAgent**, an Agentic AI Platform for Infrastructure Operations. The project is a monorepo: Python backend (FastAPI + FastMCP + LangGraph) + React frontend.

**Read `CLAUDE.md` first** — it has build/test commands, architecture, and coding rules.

### What Was Already Completed (Phase 1)

The following files have **already been refactored** to remove all mock/simulation data and use real auto-detection. **DO NOT modify these files** unless fixing bugs found during testing:

1. **`platform_detect.py`** (NEW) — Full platform auto-detection module. Probes GPU, K8s, Slurm, incident tools at startup. Uses `@lru_cache(maxsize=1)`.

2. **`mcp_servers/gpu_mcp/utils.py`** — Completely rewritten. Auto-detects GPU backend at import time: pynvml (NVIDIA) → psutil (Apple Silicon) → "none". Backend-agnostic public API: `get_gpu_count()`, `get_gpu_info()`, `get_processes()`, `get_health()`, `get_backend()`. No mock data.

3. **`mcp_servers/gpu_mcp/tools/monitor.py`** — Rewritten. Uses backend-agnostic utils. Synchronous helpers wrapped in `asyncio.to_thread()`.

4. **`mcp_servers/gpu_mcp/tools/health.py`** — Rewritten. Uses `get_health()` from utils.

5. **`mcp_servers/gpu_mcp/tools/processes.py`** — Rewritten. Uses `get_processes()` from utils.

6. **`mcp_servers/gpu_mcp/tools/dcgm.py`** — Rewritten. Detects DCGM via `pydcgm` import or `shutil.which("dcgmi")`. Returns clear error with install hints when DCGM not found.

7. **`mcp_servers/gpu_mcp/tools/nvlink.py`** — Rewritten. Real queries via pynvml NVLink APIs and `nvidia-smi topo -m`. Returns clear error on non-NVLink hardware.

8. **`mcp_servers/gpu_mcp/tools/nccl.py`** — Rewritten. Detects nccl-tests binaries via `shutil.which()`. Returns clear error with install instructions when not found.

9. **`mcp_servers/k8s_mcp/tools/slurm.py`** — Rewritten. Detects Slurm via `shutil.which("squeue")` and `shutil.which("sinfo")`. Real queries with proper parsing.

10. **`agents/agent_factory.py`** (NEW) — Shared agent factory. `build_tool_agent()` creates a LangGraph StateGraph with `model.bind_tools()` → `llm_call` / `tool_node` / `should_continue` loop. `run_tool_agent()` runs and extracts results.

11. **`agents/cluster_health.py`**, **`agents/gpu_workload.py`**, **`agents/incident_response.py`** — `_run_llm_agent()` in each now uses `build_tool_agent()` + `run_tool_agent()` from agent_factory.

12. **`agents/tools.py`** — Docstring updated.

13. **`config.py`** — Added `_auto_detect_k8s()` and `_auto_detect_slurm()`. Removed `mock_gpu`, `dgx_node_count`, `gpus_per_node`.

14. **`.env.example`** and **`CLAUDE.md`** — Updated.

---

## Your Task: Phase 2

Complete the auto-detection refactor for the remaining subsystems that **still use mock data**. The philosophy: **auto-detect real infrastructure → use it if available → return a clear "subsystem not available" error with installation hints if not**. Never return fake data.

### Task 1: Refactor `mcp_servers/k8s_mcp/utils.py`

This file currently contains ~695 lines of hardcoded mock data: `MOCK_PODS`, `MOCK_DEPLOYMENTS`, `MOCK_SERVICES`, `MOCK_NODES`, `MOCK_EVENTS`, `_MOCK_LOG_LINES`, and mock helper functions.

**What to do:**
- Remove ALL mock data constants and mock helper functions.
- Keep (or rewrite) only the real Kubernetes client helpers: `get_core_v1_client()`, `get_apps_v1_client()`, etc.
- These should use lazy initialization: try to create the K8s client, cache it, and raise a clear error if kubeconfig is not found.
- The auto-detection logic in `config.py` (`_auto_detect_k8s()`) already handles detecting K8s availability. The utils should just provide the client — if K8s isn't available, the tools should return a clear error.

### Task 2: Refactor `mcp_servers/k8s_mcp/tools/pods.py`

Currently checks `if settings.mock_k8s:` and calls mock functions.

**What to do:**
- Remove all `if settings.mock_k8s:` branches and mock function calls.
- Keep only the real Kubernetes API calls.
- If the K8s client is not available (no kubeconfig), catch the exception and return a clear JSON error: `{"error": "Kubernetes not available", "detail": "No kubeconfig found. Set KUBECONFIG or run inside a cluster.", "hint": "Install kubectl and configure cluster access."}`.

### Task 3: Refactor `mcp_servers/k8s_mcp/tools/deployments.py`

Same pattern as pods.py — remove mock branches, keep real API calls, return clear errors when K8s unavailable.

### Task 4: Refactor `mcp_servers/k8s_mcp/tools/services.py`

Same pattern.

### Task 5: Refactor `mcp_servers/k8s_mcp/tools/logs.py`

Same pattern.

### Task 6: Refactor `mcp_servers/incident_mcp/` tools

The incident tools (Jira, Grafana, PagerDuty) currently default to `mock_jira=True`, `mock_grafana=True`, `mock_pagerduty=True` and return fake incident data.

**What to do for each tool file (`jira_tools.py`, `grafana_tools.py`, `pagerduty_tools.py`):**
- Remove all mock data generators and `if settings.mock_*:` branches.
- Keep only the real API call paths.
- Add auto-detection: check if the URL/token is configured. If not, return a clear error:
  ```json
  {"error": "Jira not configured", "detail": "Set INFRA_AGENT_JIRA_URL and INFRA_AGENT_JIRA_TOKEN to enable.", "hint": "See .env.example for configuration."}
  ```
- Same pattern for Grafana and PagerDuty.

**Update `mcp_servers/incident_mcp/utils.py`:**
- Remove mock flag checks from client factory functions.
- Auto-detect: if URL + token are set, create real client. If not, functions should raise a clear error.

**Update `config.py`:**
- Remove `mock_jira`, `mock_grafana`, `mock_pagerduty` fields entirely.
- Add auto-detection helpers: `_auto_detect_jira()` (checks if URL + token are set), `_auto_detect_grafana()`, `_auto_detect_pagerduty()`.
- Add computed properties: `jira_available`, `grafana_available`, `pagerduty_available`.

**Update `.env.example`:**
- Remove `INFRA_AGENT_MOCK_JIRA=true`, `INFRA_AGENT_MOCK_GRAFANA=true`, `INFRA_AGENT_MOCK_PAGERDUTY=true`.
- Update comments to say "Set URL and token to enable" instead of "set to false to disable mock".

### Task 7: Clean up stale comments

In `agents/gpu_workload.py`, `agents/cluster_health.py`, and `agents/incident_response.py`:
- The section comment `# LLM-powered agent path (create_agent)` should be updated to `# LLM-powered agent path (LangGraph StateGraph)`.

### Task 8: Remove `mock_k8s` and `mock_slurm` from config.py

Now that K8s tools handle their own error cases:
- Remove `mock_k8s` and `mock_slurm` fields from `config.py`.
- Remove `_auto_detect_k8s()` and `_auto_detect_slurm()` helper functions (detection is now inline in the tools themselves).
- Remove `INFRA_AGENT_MOCK_SLURM` from `.env.example`.

### Task 9: Verify and test

```bash
pip install -e ".[dev]" --break-system-packages
ruff check . --fix
ruff format .
pytest tests/ -v --tb=short
```

Fix any import errors, missing references to removed mock functions, or test failures. Tests that relied on mock data will need to be updated to either:
- Test the real code path with proper mocking via `unittest.mock.patch` (mock the external API, not our internal mock data)
- Test the error path (what happens when K8s/Jira/etc. is not available)

### Task 10: Update `CLAUDE.md`

Ensure the architecture section accurately reflects that NO subsystem uses mock flags anymore. Every tool auto-detects or checks configuration and returns clear errors.

---

## Coding Rules (from CLAUDE.md)

- ALWAYS use type hints on every function
- ALWAYS use Pydantic BaseModel for MCP tool inputs
- ALWAYS use async/await for I/O operations
- NEVER use deprecated LangChain APIs (initialize_agent, AgentExecutor, LLMChain, create_agent)
- NEVER use langgraph.prebuilt — build StateGraph manually with model.bind_tools()
- Use Pydantic v2 patterns (model_config, field_validator, model_dump)
- Error handling on EVERY external API call
- No mock data — auto-detect hardware and return clear errors when unavailable
- MCP tools return Markdown/JSON strings, not Python objects
- ruff line-length: 100, target: py311
- mypy strict mode enabled
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`

## Important

- Do NOT touch any of the Phase 1 files listed above unless you find actual bugs.
- Every tool should work in two modes: (a) real infrastructure available → query it, (b) not available → return clear JSON error with what to install/configure.
- The `platform_detect.py` module can be imported anywhere for a quick summary of what's available: `from platform_detect import detect_platform`.
