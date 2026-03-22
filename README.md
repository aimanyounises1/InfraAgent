# InfraAgent

**Agentic AI Platform for HPC & GPU Infrastructure Operations**

> Natural-language management for DGX clusters, GPU fleet monitoring via DCGM, NVLink topology inspection, NCCL profiling, Slurm job orchestration, and automated incident response — built for teams running large-scale NVIDIA HPC infrastructure.

---

## Why InfraAgent?

Managing HPC clusters at scale means juggling nvidia-smi, DCGM, Slurm, Grafana, PagerDuty, and Kubernetes simultaneously. InfraAgent unifies all of that behind natural language:

```
> "Which DGX nodes have NVLink errors in the last hour?"
> "Show me GPU utilization heatmap across the training cluster"
> "Scale the inference pool to 8 replicas and check NCCL allreduce bandwidth"
> "Create an incident ticket — node dgx-07 has ECC uncorrectable errors"
```

Three MCP servers expose NVIDIA's HPC stack as AI-callable tools. A LangGraph multi-agent orchestrator routes queries to the right specialist. A React dashboard gives you mission-control visibility.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    React Dashboard (:3000)                       │
│  DGX Fleet Status │ GPU Heatmap │ NVLink Topology │ NL Input    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────┴──────────────────────────────────────┐
│                    FastAPI Backend (:8000)                       │
│  /api/chat │ /api/gpu │ /api/k8s │ /api/incidents │ /ws         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                  LangGraph Orchestrator                          │
│  Intent Classifier → Conditional Router → Domain Agents         │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐      │
│  │  HPC/GPU      │ │  K8s Cluster │ │ Incident Response  │      │
│  │  Agent        │ │  Agent       │ │ Agent              │      │
│  └──────┬───────┘ └──────┬───────┘ └────────┬───────────┘      │
└─────────┼────────────────┼──────────────────┼───────────────────┘
          │                │                  │
┌─────────┴──────┐ ┌──────┴───────┐ ┌────────┴─────────┐
│   gpu_mcp      │ │   k8s_mcp    │ │  incident_mcp    │
│                │ │              │ │                   │
│ DCGM Telemetry │ │ Pod/Deploy   │ │ Jira + Grafana   │
│ NVLink Topology│ │ Nodes/Events │ │ PagerDuty        │
│ NCCL Profiling │ │ Slurm Jobs   │ │ RCA Generator    │
│ GPU Health/ECC │ │ HPC Sched    │ │                   │
│ Power/Thermal  │ │              │ │                   │
└─────────┬──────┘ └──────┬───────┘ └────────┬─────────┘
          │                │                  │
   DCGM / NVML /     K8s API /          Jira / Grafana /
   pynvml             Slurm REST         PagerDuty APIs
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed design decisions.

---

## Features

**GPU Fleet Management (DCGM + NVML)**
- Real-time GPU utilization, memory, temperature, and power across all DGX nodes
- DCGM field group queries for deep telemetry (XID errors, PCIe throughput, NVLink bandwidth)
- ECC error monitoring with correctable/uncorrectable breakdown
- Thermal throttle detection and power cap awareness
- Cluster-wide GPU heatmap and health scoring

**NVLink & Interconnect Topology**
- NVLink status per GPU pair (active links, bandwidth, error counters)
- NVSwitch health monitoring
- GPU topology discovery (NVLink, PCIe, SMP interconnect hierarchy)
- InfiniBand fabric awareness for multi-node communication

**NCCL Communication Profiling**
- AllReduce, AllGather, ReduceScatter bandwidth monitoring
- Per-ring/tree algorithm performance tracking
- Multi-node NCCL collective latency analysis
- Bottleneck detection across GPU-to-GPU communication paths

**Kubernetes + Slurm HPC Scheduling**
- K8s pod/deployment management with GPU resource awareness
- Slurm job submission, queue status, and node allocation
- GPU-aware scheduling metrics (requested vs. allocated GPUs)
- Training job lifecycle tracking (queued → running → completed)

**Automated Incident Response**
- Grafana alert correlation with GPU telemetry
- Jira ticket creation with auto-populated DCGM diagnostics
- PagerDuty integration for on-call escalation
- Auto-generated Root Cause Analysis reports

**Multi-LLM Support**
- NVIDIA NIM (Nemotron) — optimized for on-prem HPC environments
- Ollama (local) — air-gapped cluster support
- Claude, OpenAI, Gemini — cloud fallback options

---

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/InfraAgent.git
cd InfraAgent

# Configure
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY or INFRA_AGENT_LLM_PROVIDER=ollama

# Run in mock mode (no real GPUs or cluster needed)
docker-compose up

# Or run locally
pip install -e ".[dev,nvidia]"
uvicorn api.main:app --reload
```

- Dashboard: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

Mock mode simulates a **4-node DGX H100 cluster** (32 GPUs total) with realistic utilization patterns, NVLink topology, and NCCL metrics — great for demos and development.

---

## Development

```bash
pip install -e ".[dev,all-llm]"

# Tests
pytest tests/ -v

# Lint & format
ruff check . && ruff format .

# Type check
mypy mcp_servers/ agents/ api/

# Run individual MCP server
python -m mcp_servers.gpu_mcp.server
python -m mcp_servers.k8s_mcp.server

# Frontend
cd dashboard && npm install && npm run dev
```

---

## Tech Stack

**Backend:** Python 3.11+ · FastMCP 3.x · LangGraph 1.0 · LangChain 1.0 · FastAPI · Pydantic v2

**NVIDIA HPC:** DCGM (Data Center GPU Manager) · pynvml (NVML bindings) · NCCL profiling · NVLink/NVSwitch telemetry

**Frontend:** React 18 · Vite · Tailwind CSS · Recharts · shadcn/ui

**Infrastructure:** Docker Compose · Prometheus · Kubernetes · Slurm REST API

---

## Project Structure

```
InfraAgent/
├── mcp_servers/
│   ├── gpu_mcp/               # GPU fleet monitoring (DCGM + NVML)
│   │   └── tools/
│   │       ├── monitor.py     # Utilization, memory, temp, power
│   │       ├── dcgm.py        # DCGM field groups, XID errors, PCIe stats
│   │       ├── nvlink.py      # NVLink topology, bandwidth, error counters
│   │       ├── nccl.py        # NCCL collective profiling
│   │       ├── health.py      # Cluster-wide health scoring + ECC
│   │       └── processes.py   # GPU process management
│   ├── k8s_mcp/               # Kubernetes + Slurm HPC scheduling
│   │   └── tools/
│   │       ├── pods.py        # Pod management
│   │       ├── deployments.py # Deployment scaling
│   │       ├── services.py    # Service discovery
│   │       ├── logs.py        # Log retrieval
│   │       └── slurm.py       # Slurm job submission & queue status
│   └── incident_mcp/          # Incident response (Jira/Grafana/PagerDuty)
├── agents/                    # LangGraph multi-agent orchestration
│   ├── orchestrator.py        # StateGraph with intent classification
│   ├── gpu_workload.py        # HPC GPU workload specialist
│   ├── cluster_health.py      # K8s + Slurm cluster health
│   └── incident_response.py   # Automated incident management
├── api/                       # FastAPI REST + WebSocket backend
├── dashboard/                 # React mission-control UI
├── tests/                     # Comprehensive pytest suite
├── config.py                  # Pydantic Settings (DCGM, Slurm, NIM config)
├── docker-compose.yml         # One-click deployment
└── pyproject.toml             # Dependencies
```

---

## Mock Mode — DGX H100 Cluster Simulation

When `INFRA_AGENT_MOCK_GPU=true` (default), InfraAgent simulates a realistic DGX cluster:

| Node | GPUs | Model | NVLink | Interconnect |
|------|------|-------|--------|--------------|
| dgx-h100-01 | 8x H100 SXM | 80GB HBM3 | NVLink 4.0 (900 GB/s) | InfiniBand NDR |
| dgx-h100-02 | 8x H100 SXM | 80GB HBM3 | NVLink 4.0 (900 GB/s) | InfiniBand NDR |
| dgx-h100-03 | 8x H100 SXM | 80GB HBM3 | NVLink 4.0 (900 GB/s) | InfiniBand NDR |
| dgx-h100-04 | 8x H100 SXM | 80GB HBM3 | NVLink 4.0 (900 GB/s) | InfiniBand NDR |

Mock data includes realistic training workload patterns, NVLink error injection, ECC fault simulation, and NCCL bandwidth profiles.

---

## Contributing

Contributions welcome! Please read [ARCHITECTURE.md](./ARCHITECTURE.md) first, then:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Commit with conventional commits (`feat:`, `fix:`, `test:`)
4. Open a pull request

## License

MIT
