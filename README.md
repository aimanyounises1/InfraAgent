# InfraAgent

**Agentic AI Platform for Infrastructure Operations**

> Unified Kubernetes management, GPU workload monitoring, and automated incident response — all through natural language.

---

## Features

- **Natural Language Infrastructure Control** — "Scale nginx to 5 replicas", "Which GPUs are thermal throttling?"
- **3 MCP Servers** — Kubernetes, GPU Monitoring, Incident Response (Jira + Grafana + PagerDuty)
- **Multi-Agent Orchestration** — LangGraph-powered intent classification and routing
- **Real-Time Dashboard** — React + Tailwind dark-themed mission control UI
- **Mock Mode** — Demo everything without real infrastructure
- **One-Click Deploy** — `docker-compose up` and you're running

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed diagrams and design decisions.

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/InfraAgent.git
cd InfraAgent

# Configure
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Run (mock mode — no real infra needed)
docker-compose up
```

Dashboard: http://localhost:3000
API: http://localhost:8000
API Docs: http://localhost:8000/docs

## Development

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint & format
ruff check . && ruff format .

# Type check
mypy mcp_servers/ agents/ api/

# Run API locally
uvicorn api.main:app --reload

# Run dashboard locally
cd dashboard && npm install && npm run dev
```

## Tech Stack

**Backend**: Python 3.11+ · FastMCP 3.x · LangGraph 1.0 · LangChain 1.0 · FastAPI · Pydantic v2

**Frontend**: React 18 · Vite · Tailwind CSS · Recharts · shadcn/ui

**Infrastructure**: Docker Compose · Prometheus · Kubernetes Python Client · pynvml

## Project Structure

```
InfraAgent/
├── mcp_servers/           # Three FastMCP servers
│   ├── k8s_mcp/           # Kubernetes management
│   ├── gpu_mcp/           # GPU monitoring
│   └── incident_mcp/      # Incident response
├── agents/                # LangGraph multi-agent orchestration
├── api/                   # FastAPI REST + WebSocket backend
├── dashboard/             # React frontend
├── tests/                 # Comprehensive test suite
├── config.py              # Centralized Pydantic Settings
├── docker-compose.yml     # One-click deployment
└── pyproject.toml         # Python project config
```

## Build Phases

| Phase | Component | Status |
|-------|-----------|--------|
| 1 | k8s_mcp server | Scaffolded |
| 2 | gpu_mcp server | Scaffolded |
| 3 | incident_mcp server | Scaffolded |
| 4 | LangGraph agents | Scaffolded |
| 5 | FastAPI backend | Scaffolded |
| 6 | React dashboard | Scaffolded |
| 7 | Docker + README | Scaffolded |

## Contributing

Contributions welcome! Please read the architecture docs first, then:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Commit with conventional commits (`feat:`, `fix:`, `test:`)
4. Open a pull request

## License

MIT
