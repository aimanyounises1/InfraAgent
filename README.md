# InfraAgent

A local infrastructure assistant for inspecting Kubernetes workloads, GPU telemetry, and incident data through a React dashboard and a natural-language interface.

InfraAgent explores a practical question: how can an operator bring data from several systems into one investigation while keeping the model away from unrestricted execution? The repository contains a FastAPI application, LangGraph domain agents, and callable adapters for Kubernetes, Slurm, NVML, Jira, Grafana, and PagerDuty.

**Status:** working development prototype for trusted local use. Hardware and service integrations depend on your environment. There is no deployed public service or simulated GPU cluster. Missing services return structured unavailable/error responses. Authentication, rate limiting, durable audit storage, and a per-action human approval workflow are not implemented.

## Start here

- [Architecture and design decisions](ARCHITECTURE.md): execution boundary, model/fallback behavior, and deployment tradeoffs.
- [Execution policy](mcp_servers/policy.py): the shared default-deny mutation guard.
- [Policy regression tests](tests/test_mutation_policy.py): registered MCP calls, direct calls, the real tool graph, and keyword fallback.
- [Agent factory](agents/agent_factory.py): model/tool loop with validated state and bounded execution.

## Implemented behavior

| Area | Implementation | Prerequisites / limits |
|---|---|---|
| Kubernetes | Pods, deployments, services, logs, events, nodes, rollout inspection; mutation adapters for scaling, restart, node management, rollback, and pod exec | A reachable cluster and configured Kubernetes client credentials |
| GPU | Local device/utilization/memory/temperature and health tools; additional DCGM, NVLink, NCCL adapter modules | NVIDIA access depends on NVML and installed hardware; Apple telemetry is platform-specific; no claim of remote fleet verification |
| Slurm | Queue/node/job inspection and submit/cancel adapters | Local Slurm CLI commands; the implementation does not use the configured REST URL |
| Incidents | Jira search/create/update; Grafana queries/alerts/dashboard; PagerDuty list/acknowledge/resolve; report helpers | Explicit service credentials; report generation is not a guarantee of correct root cause |
| Agents | Intent routing, domain tool agents, optional model analysis, deterministic keyword fallback | A configured model provider for model-driven behavior; keyword fallback is narrower than natural-language understanding |
| Interface | Dashboard, REST routes, SSE chat, and WebSocket support | Local backend; no multi-user isolation |

Read adapters do not need mutation permission. All 13 tools that can change external state, including pod exec and Slurm submission/cancellation, return a structured `status: blocked` result by default, before client discovery or network/CLI execution.

## Run locally

Use Python 3.11+ and Node.js 20+. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. The committed `uv.lock` and `dashboard/package-lock.json` define reproducible dependency versions.

```sh
git clone https://github.com/aimanyounises1/InfraAgent.git
cd InfraAgent
cp .env.example .env
uv sync --frozen --extra dev --extra ollama
uv run --no-sync uvicorn api.main:app --host 127.0.0.1
```

In a second terminal:

```sh
cd InfraAgent/dashboard
npm ci
npm run dev
```

Open [the dashboard](http://localhost:3000). The API is at [the local backend](http://127.0.0.1:8000), with OpenAPI documentation at `/docs` and liveness at `/healthz`. `/healthz` only confirms that the API process responds; it does not verify cluster, model, or GPU connectivity.

The dashboard development proxy expects the backend's default port. `INFRA_AGENT_API_HOST` and `INFRA_AGENT_API_PORT` are configuration fields, but uvicorn's host/port arguments control this launch command. Keep the application bound to your local machine.

### Try it without infrastructure

The dashboard and API can start without Kubernetes, NVIDIA hardware, or incident credentials. Try `list pods` or a GPU inspection request: unavailable backends should be reported honestly. Try `scale web to 2 replicas`: execution must be blocked while mutations are disabled. These responses are a disconnected demonstration, not simulated infrastructure results.

For model-assisted queries, run Ollama separately, install a model supporting tool calling, and set `INFRA_AGENT_OLLAMA_MODEL` to its installed name. Provider/model IDs in `config.py` are defaults, not evidence that those models have been installed or benchmarked. The unit tests use scripted model responses and do not download a model.

## Configuration

Settings are loaded from environment variables and `.env` with the `INFRA_AGENT_` prefix. See [.env.example](.env.example) and [config.py](config.py) for the complete fields.

| Variable | Purpose |
|---|---|
| `INFRA_AGENT_LLM_PROVIDER` | `ollama`, `nvidia`, `claude`, `openai`, or `gemini` |
| `INFRA_AGENT_OLLAMA_BASE_URL`, `INFRA_AGENT_OLLAMA_MODEL` | Local Ollama endpoint and installed tool-calling model |
| `INFRA_AGENT_ALLOW_MUTATIONS` | Defaults to `false`; deployment-wide local opt-in for all mutation tools |
| `INFRA_AGENT_JIRA_URL`, `INFRA_AGENT_JIRA_TOKEN`, `INFRA_AGENT_JIRA_USER` | Jira connection, when needed |
| `INFRA_AGENT_GRAFANA_URL`, `INFRA_AGENT_GRAFANA_TOKEN` | Grafana connection, when needed |
| `INFRA_AGENT_PAGERDUTY_TOKEN` | PagerDuty connection, when needed |
| `INFRA_AGENT_CORS_ORIGINS` | JSON array of allowed browser origins |

Kubernetes uses the normal Kubernetes client configuration (`KUBECONFIG` or in-cluster configuration). Start with read-only credentials. Optional model providers require their matching package extra, for example `uv sync --frozen --extra dev --extra openai`, plus the corresponding key/model settings in `config.py`. Do not commit `.env` or credentials.

### Enabling writes in an isolated environment

Only an operator controlling the process can opt in:

```dotenv
INFRA_AGENT_ALLOW_MUTATIONS=true
```

Restart the process after changing settings. This enables **all** mutation tools for that process; it is not approval of one proposed action. Use an isolated test cluster/account and credentials limited to the work you intend to permit. The existing `approval_required_for_destructive`, `approval_timeout`, `auth_enabled`, `rate_limit_rpm`, and audit-file settings are legacy placeholders and must not be treated as security controls.

## Verification

After installing both locked dependency sets:

```sh
sh .claude/docs-first/verify.sh
```

The gate runs the complete backend test suite, lint for the policy implementation and its new regression tests, and the dashboard production build. CI runs the same gate, then builds and installs a wheel in a clean environment and verifies imports outside the checkout.

The mutation tests cover all 13 registered/direct mutators without contacting any external backend, a model-selected mutation through the compiled graph, keyword fallback, opt-in behavior, and read availability. Existing backend tests exercise adapter contracts with mocked clients. This does not establish live integration readiness, model answer quality, hardware throughput, or operating cost.

The portfolio pass was verified with **252 passing backend tests** and a successful dashboard build on macOS with Python 3.14.0. GPU adapter tests use controlled NVIDIA and Apple readings at the hardware boundary, so they run without GPU hardware or skipped cases. Explicit no-hardware tests cover disconnected responses; a zero-device process listing is labeled empty, while out-of-range indices are errors when a device count exists. Two dependency warnings remain: Pydantic V1 compatibility under Python 3.14 and the deprecated `pynvml` package. `npm ci` reports existing dashboard dependency advisories; dependency updates need their own compatibility review. The older dashboard lint script lacks an ESLint configuration; repository-wide lint and strict typing are not passing acceptance gates in this change.

## Project structure

```text
api/                  FastAPI routes, streaming, logging, correlation middleware
agents/               Intent routing, model/tool loop, domain agents, keyword fallback
mcp_servers/          MCP registration and backend adapter implementations
mcp_servers/policy.py  Guard enforced inside every external mutation tool
dashboard/            React/Vite interface
runbooks/             Incident investigation references
tests/                Mocked adapter tests and execution-policy regressions
```

Agents call adapter functions in the same process. Each adapter server can also run independently with `python -m mcp_servers.k8s_mcp.server` (or `mcp_servers.gpu_mcp.server`, `mcp_servers.incident_mcp.server`) through the MCP SDK's default stdio transport. The web application does not require those servers to be started separately.

## Scope and contribution

This repository is a portfolio prototype, not a claim of operation at a particular company or cluster scale. Review the source history for attribution. The execution-policy pass adds a shared mutation boundary, regression coverage across dispatch paths, a fix for Pydantic state access in the model/tool graph, distributable module packaging, and reproducible verification. No measured latency, retrieval accuracy, or production reliability claim is made.

High-value next steps are authenticated access, per-action approval bound to exact arguments, live read-only integration tests, and dependency maintenance before any hosted deployment.
