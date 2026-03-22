# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

- Install: `pip install -e ".[dev]"`
- Test all: `pytest tests/ -v --tb=short`
- Test single file: `pytest tests/mcp_servers/test_k8s_mcp.py -v`
- Test single test: `pytest tests/mcp_servers/test_k8s_mcp.py::test_name -v`
- Lint: `ruff check .`
- Format: `ruff format .`
- Type check: `mypy mcp_servers/ agents/ api/`
- Run API: `uvicorn api.main:app --reload`
- Run MCP server: `python -m mcp_servers.k8s_mcp.server`
- Run dashboard: `cd dashboard && npm install && npm run dev`
- Full stack: `docker-compose up`

## Architecture

Monorepo: Python backend (FastAPI + FastMCP + LangGraph) + React frontend.
Production-ready infrastructure monitoring: auto-detects NVIDIA GPUs (pynvml/DCGM), Apple Silicon (psutil), Kubernetes, Slurm, and incident tools at startup.

### Design Philosophy: Auto-Detection, Not Mocking

The system auto-detects available infrastructure at import time and adapts:
- **GPU**: Tries pynvml (NVIDIA) → psutil (Apple Silicon) → reports "no GPU"
- **Kubernetes**: Checks kubeconfig / in-cluster token → real API or error
- **Slurm**: Checks for squeue/sinfo in PATH → real CLI or error
- **DCGM/NVLink/NCCL**: Checks for binaries/libraries → real queries or clear error
- **Incidents (Jira/Grafana/PagerDuty)**: Checks URL reachability and tokens

No mock data. Every tool queries real hardware or returns a clear "subsystem not available" error with installation hints. The `platform_detect.py` module runs a full probe at startup and caches results.

### Data Flow

User query → `POST /api/chat` → LangGraph orchestrator → classifier (keyword-based intent detection) → conditional router → domain agent (k8s+slurm/gpu+dcgm+nvlink+nccl/incident) → MCP server tools → synthesizer → response. Real-time updates via WebSocket.

### LangGraph Orchestrator (`agents/orchestrator.py`)

StateGraph with `InfraState` (Pydantic model): `START → classifier → router → {k8s_agent, gpu_agent, incident_agent} → synthesizer → END`. The classifier uses keyword matching to set `state.intent`, which the conditional router reads to dispatch. Each agent populates its own data field (`k8s_data`, `gpu_data`, `incident_data`). The synthesizer combines results into `state.response`. Compiled with `MemorySaver()` for checkpoint support.

### Agent Pattern (`agents/agent_factory.py`)

All three domain agents follow the same dual-path pattern:

1. **LLM path**: `build_tool_agent()` creates a LangGraph StateGraph with `model.bind_tools()` → `llm_call` / `tool_node` / `should_continue` loop. This is the modern LangGraph 1.0 pattern.
2. **Keyword fallback**: If the LLM is unavailable, each agent has its own keyword-based dispatch that calls MCP tools directly.

The LLM path uses `agents/tools.py` which provides `@tool`-decorated wrappers around MCP functions. Tool groups: `K8S_TOOLS`, `GPU_TOOLS`, `INCIDENT_TOOLS`.

### MCP Server Pattern (all three servers follow this)

Each server in `mcp_servers/{k8s,gpu,incident}_mcp/`:
- `server.py` — FastMCP instance, imports and registers tools
- `models.py` — Pydantic BaseModel inputs with field validators and constraints
- `utils.py` — Client helpers with auto-detection (lazy-init)
- `tools/*.py` — Domain tools decorated with `@mcp.tool(name="...", annotations={...})`

gpu_mcp has 6 tool modules: `monitor.py` (NVML basics), `dcgm.py` (DCGM field groups, XID errors, cluster health), `nvlink.py` (NVLink status, NVSwitch topology), `nccl.py` (collective profiling), `health.py` (ECC/thermal scoring), `processes.py`.

k8s_mcp includes `slurm.py` for HPC job scheduling (via squeue/sinfo CLI).

Every tool has MCP annotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.

### Configuration (`config.py`)

All env vars prefixed with `INFRA_AGENT_` via Pydantic Settings. K8s and Slurm availability are auto-detected at startup. Override with explicit env vars when needed. See `.env.example` for the full list.

### Dashboard (`dashboard/`)

React 18 + Vite + Tailwind dark theme. Vite proxies `/api/*` and `/ws/*` to `localhost:8000`. Custom color tokens in `tailwind.config.js`: `bg-primary` (#0A0E17), `accent-green` (#00FF88), etc. Fonts: JetBrains Mono / Space Grotesk.

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"` — async tests work without `@pytest.mark.asyncio`
- `tests/conftest.py` provides shared fixtures: `mock_k8s_core_v1`, `mock_k8s_apps_v1`, `mock_nvml`, `mock_httpx_client`, `api_client` (FastAPI TestClient)
- Tests mirror source layout: `tests/mcp_servers/`, `tests/agents/`, `tests/api/`, `tests/integration/`
- Use `respx` for HTTP mocking (httpx-compatible)

## Coding Rules

- ALWAYS use type hints on every function
- ALWAYS use Pydantic BaseModel for MCP tool inputs
- ALWAYS use async/await for I/O operations
- NEVER use deprecated LangChain APIs (initialize_agent, AgentExecutor, LLMChain, create_agent)
- NEVER use langgraph.prebuilt — build StateGraph manually with model.bind_tools()
- Use LangGraph 1.0 patterns: StateGraph + bind_tools + llm_call/tool_node loop
- Use Pydantic v2 patterns (model_config, field_validator, model_dump)
- Error handling on EVERY external API call
- No mock data — auto-detect hardware and return clear errors when unavailable
- MCP tools return Markdown/JSON strings, not Python objects
- ruff line-length: 100, target: py311
- mypy strict mode enabled

## Git

- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`
- One logical change per commit
- Always run tests before committing
