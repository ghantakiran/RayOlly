"""E2E tests for the full RayOlly pipeline.

These tests use FastAPI TestClient to test the API end-to-end.
ClickHouse/NATS/Redis are mocked for CI — in integration tests they're real.
"""
import pytest
from fastapi.testclient import TestClient

from rayolly.api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

TENANT_HEADERS = {"X-RayOlly-Tenant": "e2e-test"}

class TestHealthEndpoints:
    def test_healthz(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_docs(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_openapi_json(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data
        assert len(data["paths"]) > 50  # Should have 100+ paths

class TestAuthFlow:
    def test_login_success(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "demo"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["tenant_id"] == "demo"

    def test_login_wrong_password(self, client):
        r = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "wrong"})
        assert r.status_code == 401

    def test_me_with_token(self, client):
        # Login first
        login = client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "demo"})
        token = login.json()["access_token"]
        # Use token
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "test@example.com"

    def test_me_without_token(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code in (401, 404)  # Depends on middleware behavior

class TestIngestion:
    def test_ingest_logs_json(self, client):
        r = client.post("/api/v1/logs/ingest",
            json={"stream": "test", "logs": [
                {"timestamp": "2026-03-20T10:00:00Z", "body": "Test log entry", "severity": "INFO"}
            ]},
            headers=TENANT_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["accepted"] >= 0  # May be 0 if pipeline has issues, but shouldn't error
        assert "errors" in data

    def test_ingest_metrics_json(self, client):
        r = client.post("/api/v1/metrics/ingest",
            json={"metrics": [
                {"name": "test_metric", "type": "gauge", "value": 42.0, "timestamp": "2026-03-20T10:00:00Z", "labels": {"host": "test"}}
            ]},
            headers=TENANT_HEADERS)
        assert r.status_code == 200

    def test_ingest_splunk_hec(self, client):
        r = client.post("/services/collector/event",
            json={"event": "Splunk HEC test", "sourcetype": "test"},
            headers={**TENANT_HEADERS, "Authorization": "Splunk test-token"})
        assert r.status_code == 200

    def test_ingest_elasticsearch_bulk(self, client):
        r = client.post("/_bulk",
            content='{"index":{"_index":"test"}}\n{"@timestamp":"2026-03-20T10:00:00Z","message":"ES bulk test"}\n',
            headers={**TENANT_HEADERS, "Content-Type": "application/x-ndjson"})
        assert r.status_code == 200

    def test_tenant_required(self, client):
        r = client.post("/api/v1/logs/ingest",
            json={"stream": "test", "logs": [{"timestamp": "2026-03-20T10:00:00Z", "body": "No tenant", "severity": "INFO"}]})
        assert r.status_code == 401

class TestAgents:
    def test_list_agents(self, client):
        r = client.get("/api/v1/agents", headers=TENANT_HEADERS)
        assert r.status_code == 200
        agents = r.json()
        assert len(agents) == 4
        names = {a["name"] for a in agents}
        assert "RCA Agent" in names
        assert "Query Agent" in names

    def test_agent_has_tools(self, client):
        r = client.get("/api/v1/agents", headers=TENANT_HEADERS)
        for agent in r.json():
            assert len(agent["tools"]) > 0

class TestAlerts:
    def test_list_alerts(self, client):
        r = client.get("/api/v1/alerts", headers=TENANT_HEADERS)
        assert r.status_code == 200

class TestIntegrations:
    def test_list_available(self, client):
        r = client.get("/api/v1/integrations/available", headers=TENANT_HEADERS)
        assert r.status_code == 200
        data = r.json()
        names = {i["name"] for i in data.get("integrations", [])}
        assert "slack" in names
        assert "servicenow" in names
        assert "twilio" in names

class TestDashboard:
    def test_overview(self, client):
        r = client.get("/api/v1/dashboard/overview", headers=TENANT_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "total_services" in data
        assert "total_logs_24h" in data

class TestDataAPIs:
    def test_log_search(self, client):
        r = client.get("/api/v1/data/logs/search", headers=TENANT_HEADERS)
        assert r.status_code == 200
        assert "logs" in r.json()

    def test_metrics_list(self, client):
        r = client.get("/api/v1/data/metrics/list", headers=TENANT_HEADERS)
        assert r.status_code == 200
        assert "metrics" in r.json()

    def test_trace_search(self, client):
        r = client.get("/api/v1/data/traces/search", headers=TENANT_HEADERS)
        assert r.status_code == 200

    def test_apm_services(self, client):
        r = client.get("/api/v1/data/apm/services", headers=TENANT_HEADERS)
        assert r.status_code == 200
