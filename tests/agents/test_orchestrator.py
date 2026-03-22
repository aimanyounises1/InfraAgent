"""Tests for the LangGraph orchestrator.

TODO (Phase 4): Expand tests as agent logic is implemented.
"""

import pytest

from agents.orchestrator import InfraState, classify_intent


class TestIntentClassification:
    """Tests for the intent classifier node."""

    @pytest.mark.asyncio
    async def test_routes_k8s_query(self):
        state = InfraState(query="list all failing pods in production")
        result = await classify_intent(state)
        assert result["intent"] == "kubernetes"

    @pytest.mark.asyncio
    async def test_routes_gpu_query(self):
        state = InfraState(query="which GPUs are running above 90% utilization")
        result = await classify_intent(state)
        assert result["intent"] == "gpu"

    @pytest.mark.asyncio
    async def test_routes_incident_query(self):
        state = InfraState(query="create a jira ticket for the outage")
        result = await classify_intent(state)
        assert result["intent"] == "incident"

    @pytest.mark.asyncio
    async def test_defaults_to_kubernetes(self):
        state = InfraState(query="what is happening")
        result = await classify_intent(state)
        assert result["intent"] == "kubernetes"
