# InfraAgent Architecture

## System Overview

InfraAgent is a multi-agent AI platform purpose-built for NVIDIA HPC infrastructure. It combines three MCP (Model Context Protocol) servers with LangGraph orchestration and a React dashboard to provide unified management of DGX GPU clusters, Kubernetes workloads, and incident response — all through natural language.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     React Dashboard (:3000)                       │
│  DGX Fleet │ GPU Heatmap │ NVLink Topology │ Incidents │ NL Chat │
└────────────────────────┬─────────────────────────────────────────┘
                         │ REST + WebSocket
┌────────────────────────┴─────────────────────────────────────────┐
│                    FastAPI Backend (:8000)                         │
│  /api/chat │ /api/gpu │ /api/k8s │ /api/incidents │ /ws          │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────────────┐
│               LangGraph Orchestrator                              │
│                                                                   │
│  ┌───────────┐    ┌──────────────────────────────────┐           │
│  │ Classifier │───▶│  Conditional Router               │           │
│  └───────────┘    └──┬──────────┬──────────┬─────────┘           │
│                      │          │          │                      │
│              ┌───────┴──┐ ┌────┴─────┐ ┌──┴──────────┐          │
│              │ K8s/Slurm │ │ HPC GPU  │ │  Incident   │          │
│              │ Agent     │ │ Agent    │ │  Agent      │          │
│              └───────┬──┘ └────┬─────┘ └──┬──────────┘          │
│                      │         │          │                      │
│                 ┌────┴─────────┴──────────┴────┐                │
│                 │         Synthesizer            │                │
│                 └───────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────┘
         │                    │                    │
┌────────┴───────┐ ┌─────────┴──────────┐ ┌──────┴───────────┐
│   k8s_mcp      │ │     gpu_mcp        │ │  incident_mcp    │
│                │ │                    │ │                   │
│ K8s Pods/Deploy│ │ NVML Telemetry     │ │ Jira Tickets     │
│ K8s Services   │ │ DCGM Deep Diags    │ │ Grafana Queries  │
│ K8s Events     │ │  - XID Errors      │ │ PagerDuty Alerts │
│ Slurm Queue    │ │  - ECC/Ret. Pages  │ │ RCA Generator    │
│ Slurm Nodes    │ │  - SM Occupancy    │ │                   │
│                │ │ NVLink Topology    │ │                   │
│                │ │  - NVSwitch Health  │ │                   │
│                │ │  - Link Bandwidth   │ │                   │
│                │ │ NCCL Profiling     │ │                   │
│                │ │  - AllReduce BW    │ │                   │
│                │ │  - Bottleneck Det. │ │                   │
└────────┬───────┘ └─────────┬──────────┘ └──────┬───────────┘
         │                   │                    │
    K8s API /          DCGM / NVML /         Jira / Grafana /
    Slurm REST         pynvml                PagerDuty APIs
```

## NVIDIA HPC Stack Integration

### GPU Monitoring Layers

```
Layer 4: InfraAgent Agents (natural language → action)
    │
Layer 3: MCP Tools (structured tool interface for LLMs)
    │
Layer 2: DCGM (Data Center GPU Manager)
    │   ├── Field Groups: health, performance, power, memory
    │   ├── XID Error History (31, 48, 63, 79, 94)
    │   ├── ECC Error Tracking (SBE/DBE, volatile/aggregate)
    │   ├── Retired Pages Monitoring
    │   ├── SM Occupancy & Tensor Core Utilization
    │   └── PCIe/NVLink Throughput Metrics
    │
Layer 1: NVML (NVIDIA Management Library)
    │   ├── Basic Utilization (GPU%, Memory%)
    │   ├── Temperature & Power
    │   ├── Process Listing
    │   └── Device Enumeration
    │
Layer 0: NVIDIA Driver / Hardware
        ├── DGX H100/B200 Systems
        ├── NVLink 4.0 (900 GB/s per GPU)
        ├── NVSwitch (full-mesh GPU interconnect)
        └── InfiniBand NDR 400Gb/s (multi-node)
```

### NVLink & Multi-GPU Communication

```
DGX H100 Node (8x H100 SXM5)
┌─────────────────────────────────────────┐
│     NVSwitch 0    NVSwitch 1            │
│     NVSwitch 2    NVSwitch 3            │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐      │
│  │GPU 0│ │GPU 1│ │GPU 2│ │GPU 3│      │
│  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘      │
│     │18 NVLinks per GPU (via NVSwitch)  │
│  ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐      │
│  │GPU 4│ │GPU 5│ │GPU 6│ │GPU 7│      │
│  └─────┘ └─────┘ └─────┘ └─────┘      │
│                                         │
│  InfiniBand NDR 400Gb/s ──► Other Nodes │
└─────────────────────────────────────────┘

Bandwidth:
  GPU-to-GPU (NVLink): 900 GB/s bidirectional
  Node-to-Node (IB NDR): 400 Gb/s (50 GB/s)
  NCCL AllReduce (8 GPU): ~450 GB/s bus bandwidth
  NCCL AllReduce (32 GPU): ~45 GB/s cross-node
```

## Data Flow

1. User enters natural language query in the dashboard
2. Frontend POSTs to `/api/chat`
3. FastAPI routes to the LangGraph orchestrator
4. Classifier node determines intent (kubernetes/slurm | gpu/hpc | incident)
5. Conditional router sends to the appropriate agent
6. Agent calls MCP server tools to gather data / execute actions
7. Synthesizer combines results into a human-readable response
8. Response returned via REST; real-time updates pushed via WebSocket

## Key Design Decisions

- **MCP over direct API calls**: Standardized tool interface enables any LLM to operate the infrastructure
- **DCGM over nvidia-smi**: Programmatic access to deep GPU diagnostics (XID, ECC, NVLink) vs. parsing CLI output
- **Slurm REST API**: Modern slurmrestd integration instead of SSH + CLI parsing
- **LangGraph over simple chains**: Stateful, checkpointable graph supports complex multi-step HPC workflows
- **Mock modes everywhere**: Every external dependency has a mock toggle — simulates a 4-node DGX H100 cluster for demos
- **Pydantic everywhere**: Type-safe inputs, validated at the MCP tool boundary
- **Multi-LLM support**: NVIDIA NIM for on-prem HPC, Ollama for air-gapped clusters, cloud LLMs as fallback
