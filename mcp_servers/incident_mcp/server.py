"""Incident Response MCP Server — FastMCP entry point.

Run standalone:
    python -m mcp_servers.incident_mcp.server
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("incident_mcp")

# --- Tool imports (must come after mcp is created) ---
from mcp_servers.incident_mcp.tools import (  # noqa: E402, F401
    grafana_tools,
    jira_tools,
    pagerduty_tools,
    rca,
)

if __name__ == "__main__":
    mcp.run()
