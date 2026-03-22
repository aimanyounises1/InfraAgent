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

### Data Flow

User query → `POST /api/chat` → LangGraph orchestrator → classifier (keyword-based intent detection) → conditional router → domain agent (k8s/gpu/incident) → MCP server tools → synthesizer → response. Real-time updates via WebSocket.

### LangGraph Orchestrator (`agents/orchestrator.py`)

StateGraph with `InfraState` (Pydantic model): `START → classifier → router → {k8s_agent, gpu_agent, incident_agent} → synthesizer → END`. The classifier uses keyword matching to set `state.intent`, which the conditional router reads to dispatch. Each agent populates its own data field (`k8s_data`, `gpu_data`, `incident_data`). The synthesizer combines results into `state.response`. Compiled with `MemorySaver()` for checkpoint support. `ChatRequest` includes `thread_id` for future conversation threading.

### MCP Server Pattern (all three servers follow this)

Each server in `mcp_servers/{k8s,gpu,incident}_mcp/`:
- `server.py` — FastMCP instance, imports and registers tools
- `models.py` — Pydantic BaseModel inputs with field validators and constraints
- `utils.py` — Client helpers with mock mode support (lazy-init)
- `tools/*.py` — Domain tools decorated with `@mcp.tool(name="...", annotations={...})`

Every tool has MCP annotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.

### FastAPI Backend (`api/`)

- `main.py` — App init with CORS middleware, includes routers from `routes/`
- `routes/{chat,k8s,gpu,incidents}.py` — Domain routers
- `websocket.py` — `ConnectionManager` for WebSocket broadcast

### Configuration (`config.py`)

All env vars prefixed with `INFRA_AGENT_` via Pydantic Settings. Example: `INFRA_AGENT_MOCK_GPU=true`. Mock mode flags exist for every external dependency (GPU, Jira, Grafana, PagerDuty) — all default to `True`. See `.env.example` for the full list.

### Dashboard (`dashboard/`)

React 18 + Vite + Tailwind dark theme. Vite proxies `/api/*` and `/ws/*` to `localhost:8000`. Custom color tokens in `tailwind.config.js`: `bg-primary` (#0A0E17), `accent-green` (#00FF88), etc. Fonts: JetBrains Mono / Space Grotesk.

### Docker Compose

5 services: `api` (port 8000), `dashboard` (Nginx on port 3000), `k8s-mcp`, `gpu-mcp`, `incident-mcp`. Dashboard depends on API; API depends on all three MCP servers. K8s services mount `~/.kube` read-only.

## Implementation Status

The project is scaffolded — structure and contracts are in place but most tool/route implementations raise `NotImplementedError` or return placeholders. Phase comments in source indicate what needs implementation (Phase 1-3: MCP tools, Phase 4: agent logic, Phase 5: API routes, Phase 6: dashboard wiring, Phase 7: integration tests).

## Testing Patterns

- `pytest-asyncio` with `asyncio_mode = "auto"` — async tests work without `@pytest.mark.asyncio`
- `tests/conftest.py` provides shared fixtures: `mock_k8s_core_v1`, `mock_k8s_apps_v1`, `mock_nvml`, `mock_httpx_client`, `api_client` (FastAPI TestClient)
- Tests mirror source layout: `tests/mcp_servers/`, `tests/agents/`, `tests/api/`, `tests/integration/`
- Use `respx` for HTTP mocking (httpx-compatible)

## Coding Rules

- ALWAYS use type hints on every function
- ALWAYS use Pydantic BaseModel for MCP tool inputs
- ALWAYS use async/await for I/O operations
- NEVER use deprecated LangChain APIs (initialize_agent, AgentExecutor, LLMChain)
- NEVER use langgraph.prebuilt — use langchain.agents instead
- Use Pydantic v2 patterns (model_config, field_validator, model_dump)
- Error handling on EVERY external API call
- Mock mode for every external dependency (env var toggle)
- MCP tools return Markdown/JSON strings, not Python objects
- ruff line-length: 100, target: py311
- mypy strict mode enabled

## Git

- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`
- One logical change per commit
- Always run tests before committing
