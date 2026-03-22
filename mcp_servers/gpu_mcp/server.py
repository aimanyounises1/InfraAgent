"""GPU Monitoring MCP Server — FastMCP entry point.

Run standalone:
    python -m mcp_servers.gpu_mcp.server
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gpu_mcp")

# --- Tool imports (must come after mcp is defined to avoid circular imports) ---
from mcp_servers.gpu_mcp.tools import (  # noqa: F401, E402
    health,
    monitor,
    processes,
)

if __name__ == "__main__":
    mcp.run()
