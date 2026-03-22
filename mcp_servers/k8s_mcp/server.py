"""Kubernetes MCP Server — FastMCP entry point.

Run standalone:
    python -m mcp_servers.k8s_mcp.server
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("k8s_mcp")

# --- Tool imports (registers tools on the mcp instance) ---
from mcp_servers.k8s_mcp.tools import deployments as deployments  # noqa: E402, F401
from mcp_servers.k8s_mcp.tools import logs as logs  # noqa: E402, F401
from mcp_servers.k8s_mcp.tools import pods as pods  # noqa: E402, F401
from mcp_servers.k8s_mcp.tools import services as services  # noqa: E402, F401

if __name__ == "__main__":
    mcp.run()
