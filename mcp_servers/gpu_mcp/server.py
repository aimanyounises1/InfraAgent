"""GPU Monitoring MCP Server — FastMCP entry point.

Provides comprehensive GPU fleet monitoring for DGX clusters:
- Basic telemetry via NVML (utilization, memory, temp, power)
- Deep diagnostics via DCGM (XID errors, ECC, PCIe, SM occupancy)
- NVLink topology and interconnect health
- NCCL collective operation profiling
- Cluster-wide health scoring

Run standalone:
    python -m mcp_servers.gpu_mcp.server
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gpu_mcp")

# --- Tool imports (must come after mcp is defined to avoid circular imports) ---
from mcp_servers.gpu_mcp.tools import (  # noqa: F401, E402
    dcgm,
    health,
    monitor,
    nccl,
    nvlink,
    processes,
)

if __name__ == "__main__":
    mcp.run()
