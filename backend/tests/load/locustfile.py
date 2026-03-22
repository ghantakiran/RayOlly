"""Load test for RayOlly API.

Run: locust -f tests/load/locustfile.py --host=http://localhost:8080

Targets:
- Ingestion: 1000 logs/sec sustained
- Query: p99 < 2s for log search
- Dashboard: p99 < 500ms
"""
import random

from locust import HttpUser, between, tag, task


class RayOllyUser(HttpUser):
    wait_time = between(0.1, 1.0)
    headers = {"X-RayOlly-Tenant": "loadtest", "Content-Type": "application/json"}

    @tag("ingest")
    @task(5)  # 50% of traffic
    def ingest_logs(self):
        sevs = ["INFO", "INFO", "INFO", "WARN", "ERROR"]
        self.client.post("/api/v1/logs/ingest",
            json={"stream": "loadtest", "logs": [
                {"timestamp": f"2026-03-20T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00Z",
                 "body": f"Load test log entry {random.randint(1,10000)}",
                 "severity": random.choice(sevs),
                 "attributes": {"request_id": f"req_{random.randint(100000,999999)}"}}
            ]},
            headers=self.headers, name="/api/v1/logs/ingest")

    @tag("ingest")
    @task(2)  # 20%
    def ingest_metrics(self):
        self.client.post("/api/v1/metrics/ingest",
            json={"metrics": [
                {"name": "http_requests_total", "type": "counter",
                 "value": random.randint(1, 1000),
                 "timestamp": f"2026-03-20T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00Z",
                 "labels": {"service": random.choice(["api", "web", "worker"]), "status": random.choice(["200", "500"])}}
            ]},
            headers=self.headers, name="/api/v1/metrics/ingest")

    @tag("query")
    @task(2)  # 20%
    def query_logs(self):
        self.client.get("/api/v1/data/logs/search?limit=50",
            headers=self.headers, name="/api/v1/data/logs/search")

    @tag("query")
    @task(1)  # 10%
    def dashboard_overview(self):
        self.client.get("/api/v1/dashboard/overview",
            headers=self.headers, name="/api/v1/dashboard/overview")

class RayOllyHeavyUser(HttpUser):
    """Simulates heavy dashboard users."""
    wait_time = between(2, 5)
    headers = {"X-RayOlly-Tenant": "loadtest"}

    @task
    def full_dashboard_load(self):
        self.client.get("/api/v1/dashboard/overview", headers=self.headers)
        self.client.get("/api/v1/dashboard/top-services", headers=self.headers)
        self.client.get("/api/v1/dashboard/ingestion-chart", headers=self.headers)
        self.client.get("/api/v1/data/logs/search?severity=ERROR&limit=20", headers=self.headers)
