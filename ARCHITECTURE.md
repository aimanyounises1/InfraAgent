# InfraAgent Architecture

## System Overview

InfraAgent is a multi-agent AI platform that combines three MCP (Model Context Protocol) servers with LangGraph orchestration and a React dashboard to provide unified infrastructure management.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     React Dashboard (:3000)                   │
│  ClusterStatus │ GPUHeatmap │ IncidentTimeline │ NL Input     │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST + WebSocket
┌────────────────────────┴─────────────────────────────────────┐
│                    FastAPI Backend (:8000)                     │
│  /api/chat │ /api/k8s │ /api/gpu │ /api/incidents │ /ws       │
└────────────────────────┬─────────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────────┐
│               LangGraph Orchestrator                          │
│                                                               │
│  ┌───────────┐    ┌──────────────────────────────────┐       │
│  │ Classifier │───▶│  Conditional Router               │       │
│  └───────────┘    └──┬──────────┬──────────┬─────────┘       │
│                      │          │          │                  │
│              ┌───────┴──┐ ┌────┴─────┐ ┌──┴──────────┐      │
│              │ K8s Agent │ │GPU Agent │ │Incident Agent│      │
│              └───────┬──┘ └────┬─────┘ └──┬──────────┘      │
│                      │          │          │                  │
│                 ┌────┴──────────┴──────────┴────┐            │
│                 │         Synthesizer            │            │
│                 └───────────────────────────────┘            │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
┌────────┴───────┐ ┌─────────┴────────┐ ┌────────┴─────────┐
│   k8s_mcp      │ │    gpu_mcp       │ │  incident_mcp    │
│                │ │                  │ │                   │
│ - list_pods    │ │ - list_devices   │ │ - jira_create     │
│ - describe_pod │ │ - get_util       │ │ - jira_search     │
│ - get_logs     │ │ - get_memory     │ │ - grafana_query   │
│ - list_deploy  │ │ - get_temp       │ │ - grafana_alerts  │
│ - scale_deploy │ │ - list_procs     │ │ - pd_list         │
│ - restart      │ │ - health_check   │ │ - pd_acknowledge  │
│ - list_svc     │ │ - cluster_sum    │ │ - pd_resolve      │
│ - list_nodes   │ │                  │ │ - generate_rca    │
│ - list_events  │ │                  │ │                   │
│ - exec_cmd     │ │                  │ │                   │
└────────┬───────┘ └─────────┬────────┘ └────────┬─────────┘
         │                   │                    │
    K8s API           NVML / Mock          Jira/Grafana/PD
```

## Data Flow

1. User enters natural language query in the dashboard
2. Frontend POSTs to `/api/chat`
3. FastAPI routes to the LangGraph orchestrator
4. Classifier node determines intent (kubernetes | gpu | incident)
5. Conditional router sends to the appropriate agent
6. Agent calls MCP server tools to gather data / execute actions
7. Synthesizer combines results into a human-readable response
8. Response returned via REST; real-time updates pushed via WebSocket

## Directory Structure

See `README.md` for the full file tree.

## Key Design Decisions

- **MCP over direct API calls**: Standardized tool interface enables any LLM to operate the infrastructure
- **LangGraph over simple chains**: Stateful, checkpointable graph supports complex multi-step workflows
- **Mock modes everywhere**: Every external dependency has a mock toggle for demo/development
- **Pydantic everywhere**: Type-safe inputs, validated at the MCP tool boundary
- **Monorepo**: Single repo simplifies development, testing, and Docker deployment
