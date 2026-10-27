"""Mutation policy regressions across direct, registered, and agent call paths."""

from __future__ import annotations

import importlib
import json
from contextlib import ExitStack
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from config import Settings, settings
from mcp_servers.policy import MUTATION_OPT_IN_ENV, blocked_mutation

MUTATORS = [
    ("k8s", "deployments", "k8s_scale_deployment", {"deployment_name": "web", "replicas": 2}),
    ("k8s", "deployments", "k8s_restart_deployment", {"deployment_name": "web"}),
    ("k8s", "pods", "k8s_exec_command", {"pod_name": "web", "command": ["sh"]}),
    ("k8s", "resources", "k8s_cordon_node", {"node_name": "worker"}),
    ("k8s", "resources", "k8s_uncordon_node", {"node_name": "worker"}),
    ("k8s", "resources", "k8s_drain_node", {"node_name": "worker"}),
    ("k8s", "resources", "k8s_rollback_deployment", {"deployment_name": "web"}),
    ("k8s", "slurm", "k8s_slurm_submit_job", {"job_name": "test", "command": "true"}),
    ("k8s", "slurm", "k8s_slurm_cancel_job", {"job_id": "123"}),
    (
        "incident",
        "jira_tools",
        "incident_jira_create_ticket",
        {"project_key": "OPS", "summary": "Test"},
    ),
    ("incident", "jira_tools", "incident_jira_update_ticket", {"issue_key": "OPS-1"}),
    ("incident", "pagerduty_tools", "incident_pagerduty_acknowledge", {"incident_id": "P123"}),
    ("incident", "pagerduty_tools", "incident_pagerduty_resolve", {"incident_id": "P123"}),
]


@pytest.fixture(autouse=True)
def deny_mutations():
    """Make policy tests deterministic regardless of the caller's environment."""
    with patch.object(settings, "allow_mutations", False):
        yield


def test_settings_default_and_explicit_opt_in(monkeypatch):
    """The old approval setting cannot silently enable external writes."""
    monkeypatch.delenv(MUTATION_OPT_IN_ENV, raising=False)
    assert Settings(_env_file=None).allow_mutations is False
    monkeypatch.setenv(MUTATION_OPT_IN_ENV, "true")
    assert Settings(_env_file=None).allow_mutations is True
    with patch.object(settings, "approval_required_for_destructive", False):
        assert json.loads(blocked_mutation("test_tool"))["status"] == "blocked"


def test_policy_rejects_missing_tool_name():
    """Invalid internal usage fails explicitly instead of emitting ambiguous logs."""
    with pytest.raises(ValueError, match="nonempty"):
        blocked_mutation("")


@pytest.mark.parametrize("domain,module_name,tool_name,arguments", MUTATORS)
@pytest.mark.asyncio
async def test_registered_and_direct_tools_block_before_backend(
    domain,
    module_name,
    tool_name,
    arguments,
):
    """Every registered mutator blocks before discovering a client or running CLI."""
    module = importlib.import_module(f"mcp_servers.{domain}_mcp.tools.{module_name}")
    with ExitStack() as stack:
        backends = []
        for client_name in ("get_clients", "get_jira_client", "get_pagerduty_client"):
            if hasattr(module, client_name):
                backends.append(stack.enter_context(patch.object(module, client_name)))
        subprocess_run = stack.enter_context(patch("subprocess.run"))
        # Registration serializes input into each existing Pydantic parameter model.
        content, structured = await module.mcp.call_tool(tool_name, {"params": arguments})
        registered = json.loads(structured["result"])
        assert registered["status"] == "blocked"
        assert registered["tool"] == tool_name
        assert registered["code"] == "mutation_disabled"
        assert content

        # The SDK decorator preserves the Python callable, so bypassing the MCP
        # transport must still enforce policy with a validated input model.
        tool_fn = getattr(module, tool_name)
        input_model = get_type_hints(tool_fn)["params"]
        direct = json.loads(await tool_fn(input_model(**arguments)))
        assert direct == registered
        for backend in backends:
            backend.assert_not_called()
        subprocess_run.assert_not_called()


@pytest.mark.asyncio
async def test_opt_in_reaches_backend_and_read_tools_remain_available():
    """Policy only gates mutators; a trusted opt-in preserves existing execution."""
    from mcp_servers.k8s_mcp.models import K8sListDeploymentsInput, K8sScaleDeploymentInput
    from mcp_servers.k8s_mcp.tools import deployments

    apps = MagicMock()
    apps.list_namespaced_deployment.return_value.items = []
    apps.read_namespaced_deployment.return_value.spec.replicas = 1
    with patch.object(deployments, "get_clients", return_value=(MagicMock(), apps)):
        read = json.loads(await deployments.k8s_list_deployments(K8sListDeploymentsInput()))
        assert read["deployment_count"] == 0
        with patch.object(settings, "allow_mutations", True):
            result = json.loads(
                await deployments.k8s_scale_deployment(
                    K8sScaleDeploymentInput(deployment_name="web", replicas=2),
                )
            )
        assert result["status"] == "scaled"
        apps.patch_namespaced_deployment_scale.assert_called_once()


@pytest.mark.parametrize(
    "query,key",
    [
        ("scale web to 2 replicas", "scale_deployment"),
        ("restart web", "restart_deployment"),
    ],
)
@pytest.mark.asyncio
async def test_keyword_fallback_cannot_bypass_policy(query, key):
    """Fallback returns blocked data and does not claim that it executed a write."""
    from agents.cluster_health import _run_keyword_dispatch

    with patch("mcp_servers.k8s_mcp.tools.deployments.get_clients") as backend:
        result = await _run_keyword_dispatch(query)
    backend.assert_not_called()
    assert json.loads(result["k8s_data"]["raw"][key])["status"] == "blocked"
    assert "requested" in result["actions_taken"][0]


@pytest.mark.asyncio
async def test_llm_selected_tool_receives_blocked_observation():
    """A real graph step and LangChain wrapper cannot bypass the shared guard."""
    from agents.agent_factory import build_tool_agent
    from agents.tools import scale_deployment

    model = MagicMock()
    model.bind_tools.return_value.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "scale_deployment",
                        "args": {"deployment_name": "web", "replicas": 2},
                        "id": "mutation-call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The tool returned a blocked result."),
        ]
    )
    with (
        patch("agents.llm_provider.get_llm", return_value=model),
        patch(
            "mcp_servers.k8s_mcp.tools.deployments.get_clients",
        ) as backend,
    ):
        graph = build_tool_agent([scale_deployment], "Test execution policy")
        result = await graph.ainvoke({"messages": [HumanMessage(content="scale web")]})
    backend.assert_not_called()
    observations = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
    assert len(observations) == 1
    assert json.loads(observations[0].content)["code"] == "mutation_disabled"
