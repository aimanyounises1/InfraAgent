"""Shared execution policy for tools that can change external state.

The guard runs inside each registered tool, before backend discovery. It applies
equally to direct Python calls, MCP calls, and both agent dispatch paths.
"""

from __future__ import annotations

import json
import logging

from config import settings

logger = logging.getLogger(__name__)
MUTATION_OPT_IN_ENV = "INFRA_AGENT_ALLOW_MUTATIONS"


def blocked_mutation(tool_name: str) -> str | None:
    """Return an explicit blocked result unless local mutations are enabled.

    This is a deployment-wide opt-in, not a human approval workflow. Input models
    validate tool parameters separately; this function only controls execution.
    """
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("tool_name must be a nonempty string")
    if settings.allow_mutations:
        logger.info("Mutation policy allows tool %s", tool_name)
        return None

    logger.warning("Mutation policy blocked tool %s", tool_name)
    return json.dumps(
        {
            "status": "blocked",
            "error": "Mutating tools are disabled",
            "code": "mutation_disabled",
            "tool": tool_name,
            "hint": (
                f"An operator can set {MUTATION_OPT_IN_ENV}=true and restart "
                "the process for a trusted local environment. This enables all "
                "mutating tools; it does not approve one action."
            ),
        }
    )
