"""Tests for FastAPI routes.

TODO (Phase 5): Expand as routes are wired to MCP tools.
"""


class TestHealthCheck:
    def test_healthz(self, api_client):
        response = api_client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestChatEndpoint:
    def test_chat_placeholder(self, api_client):
        response = api_client.post("/api/chat", json={"query": "list pods"})
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "intent" in data


class TestK8sRoutes:
    def test_list_pods_placeholder(self, api_client):
        response = api_client.get("/api/k8s/pods")
        assert response.status_code == 200

    def test_list_deployments_placeholder(self, api_client):
        response = api_client.get("/api/k8s/deployments")
        assert response.status_code == 200
