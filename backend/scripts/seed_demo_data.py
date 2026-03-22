#!/usr/bin/env python3
"""Seed realistic demo data into RayOlly for demonstration and development."""

import random
from datetime import UTC, datetime, timedelta

import clickhouse_connect

# Connect to ClickHouse
client = clickhouse_connect.get_client(
    host="localhost", port=8123, username="rayolly", password="rayolly_dev"
)

TENANT = "demo"
NOW = datetime.now(UTC)

# ─── Services ────────────────────────────────────────────────
SERVICES = [
    "payment-api", "user-service", "gateway", "order-service",
    "notification-service", "inventory-service", "search-service", "auth-service",
]

HOSTS = [
    "web-1.prod.us-east-1", "web-2.prod.us-east-1", "web-3.prod.us-east-1",
    "web-4.prod.us-west-2", "api-1.prod.us-east-1", "api-2.prod.us-east-1",
    "worker-1.prod.us-east-1", "worker-2.prod.us-east-1",
]

# ─── Log Messages ────────────────────────────────────────────
LOG_TEMPLATES = {
    "INFO": [
        "Request processed successfully in {latency}ms",
        "User {user_id} authenticated via {method}",
        "Cache hit for key {cache_key}, ttl={ttl}s",
        "Health check passed, uptime={uptime}h",
        "Order {order_id} created, amount=${amount}",
        "Payment {payment_id} processed successfully",
        "Email notification sent to {email}",
        "Inventory updated for product {product_id}",
        "Search query completed in {latency}ms, {results} results",
        "Session {session_id} started from {ip}",
        "API rate limit check passed for tenant {tenant}",
        "Database connection pool: {active}/{max} active connections",
        "Deployment v{version} health check passed",
        "WebSocket connection established for user {user_id}",
        "Background job {job_id} completed in {latency}ms",
    ],
    "WARN": [
        "Slow query detected: {query_time}ms on {table}",
        "Memory usage at {memory_pct}%, threshold 85%",
        "API rate limit approaching: {current}/{limit} requests",
        "Retry attempt {retry}/{max_retry} for {operation}",
        "Certificate expiring in {days} days for {domain}",
        "Connection pool near capacity: {active}/{max}",
        "Disk usage at {disk_pct}% on {mount}",
        "Response time degraded: p99={latency}ms (SLO: 500ms)",
        "Stale cache entry detected for key {cache_key}",
        "Kafka consumer lag: {lag} messages on {topic}",
    ],
    "ERROR": [
        "Connection timeout to {service} after {timeout}ms",
        "Database query failed: {error_msg}",
        "Payment processing failed for order {order_id}: {error_msg}",
        "Authentication failed for user {user_id}: invalid credentials",
        "HTTP 503 from upstream {service}: service unavailable",
        "Out of memory: container {container} killed (OOMKilled)",
        "SSL handshake failed with {host}: certificate expired",
        "Unhandled exception in {handler}: {error_msg}",
        "Circuit breaker OPEN for {service} after {failures} failures",
        "Data validation failed: {field} is required",
    ],
}

ERROR_MSGS = [
    "Connection refused", "Timeout exceeded", "Resource not found",
    "Permission denied", "Constraint violation", "Deadlock detected",
]


def random_log_body(severity: str) -> tuple[str, dict]:
    template = random.choice(LOG_TEMPLATES[severity])
    attrs = {}
    body = template
    replacements = {
        "{latency}": str(random.randint(1, 2000)),
        "{user_id}": f"usr_{random.randint(1000, 9999)}",
        "{method}": random.choice(["password", "oauth2", "saml", "api_key"]),
        "{cache_key}": f"session:{random.randint(100, 999)}",
        "{ttl}": str(random.randint(60, 3600)),
        "{uptime}": str(random.randint(1, 720)),
        "{order_id}": f"ord_{random.randint(10000, 99999)}",
        "{amount}": f"{random.uniform(9.99, 999.99):.2f}",
        "{payment_id}": f"pay_{random.randint(10000, 99999)}",
        "{email}": f"user{random.randint(1, 500)}@example.com",
        "{product_id}": f"prod_{random.randint(100, 999)}",
        "{results}": str(random.randint(0, 500)),
        "{session_id}": f"sess_{random.randint(10000, 99999)}",
        "{ip}": f"{random.randint(10, 200)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}",
        "{tenant}": random.choice(["acme", "globex", "initech"]),
        "{active}": str(random.randint(5, 18)),
        "{max}": "20",
        "{version}": f"{random.randint(1, 5)}.{random.randint(0, 12)}.{random.randint(0, 30)}",
        "{job_id}": f"job_{random.randint(1000, 9999)}",
        "{query_time}": str(random.randint(500, 10000)),
        "{table}": random.choice(["users", "orders", "payments", "sessions"]),
        "{memory_pct}": str(random.randint(75, 95)),
        "{current}": str(random.randint(80, 100)),
        "{limit}": "100",
        "{retry}": str(random.randint(1, 3)),
        "{max_retry}": "3",
        "{operation}": random.choice(["db_query", "http_request", "queue_publish"]),
        "{days}": str(random.randint(1, 30)),
        "{domain}": random.choice(["api.example.com", "auth.example.com"]),
        "{disk_pct}": str(random.randint(80, 95)),
        "{mount}": random.choice(["/data", "/var/log", "/"]),
        "{lag}": str(random.randint(100, 50000)),
        "{topic}": random.choice(["orders", "events", "notifications"]),
        "{service}": random.choice(SERVICES),
        "{timeout}": str(random.randint(5000, 30000)),
        "{error_msg}": random.choice(ERROR_MSGS),
        "{container}": f"payment-api-{random.randint(1, 5)}",
        "{host}": random.choice(HOSTS),
        "{handler}": random.choice(["PaymentHandler", "OrderController", "AuthMiddleware"]),
        "{failures}": str(random.randint(3, 10)),
        "{field}": random.choice(["email", "amount", "user_id"]),
    }
    for key, val in replacements.items():
        if key in body:
            attr_name = key.strip("{}")
            attrs[attr_name] = val
            body = body.replace(key, val)
    return body, attrs


def seed_logs(count: int = 500):
    """Seed log entries across multiple services and time ranges."""
    print(f"Seeding {count} logs...")
    rows = []
    severity_weights = {"INFO": 70, "WARN": 20, "ERROR": 10}
    severity_nums = {"INFO": 9, "WARN": 13, "ERROR": 17}

    for i in range(count):
        ts = NOW - timedelta(minutes=random.randint(0, 1440))  # Last 24h
        severity = random.choices(
            list(severity_weights.keys()),
            weights=list(severity_weights.values()),
        )[0]
        service = random.choice(SERVICES)
        host = random.choice(HOSTS)
        body, attrs = random_log_body(severity)
        attrs["request_id"] = f"req_{random.randint(100000, 999999)}"

        rows.append([
            TENANT, ts, severity, severity_nums[severity],
            service, host, body, attrs, {},
            "", "", service.replace("-", "_"),
        ])

    client.insert(
        "logs.log_entries", rows,
        column_names=[
            "tenant_id", "timestamp", "severity", "severity_number",
            "service", "host", "body", "attributes", "resource_attrs",
            "trace_id", "span_id", "stream",
        ],
    )
    print(f"  ✓ {count} logs inserted")


def seed_metrics(points_per_metric: int = 60):
    """Seed metric time series for the last hour at 1-minute intervals."""
    print(f"Seeding metrics ({points_per_metric} points each)...")
    rows = []

    metric_defs = [
        ("http_requests_total", "counter", {"service": "payment-api", "status": "200"}, lambda: random.randint(50, 300)),
        ("http_requests_total", "counter", {"service": "payment-api", "status": "500"}, lambda: random.randint(0, 5)),
        ("http_requests_total", "counter", {"service": "user-service", "status": "200"}, lambda: random.randint(100, 500)),
        ("http_requests_total", "counter", {"service": "gateway", "status": "200"}, lambda: random.randint(200, 800)),
        ("http_request_duration_ms", "gauge", {"service": "payment-api", "quantile": "p50"}, lambda: random.uniform(10, 50)),
        ("http_request_duration_ms", "gauge", {"service": "payment-api", "quantile": "p99"}, lambda: random.uniform(100, 500)),
        ("http_request_duration_ms", "gauge", {"service": "user-service", "quantile": "p99"}, lambda: random.uniform(20, 200)),
        ("cpu_utilization", "gauge", {"host": "web-1.prod.us-east-1"}, lambda: random.uniform(30, 85)),
        ("cpu_utilization", "gauge", {"host": "web-2.prod.us-east-1"}, lambda: random.uniform(25, 70)),
        ("cpu_utilization", "gauge", {"host": "api-1.prod.us-east-1"}, lambda: random.uniform(40, 90)),
        ("memory_used_pct", "gauge", {"host": "web-1.prod.us-east-1"}, lambda: random.uniform(50, 80)),
        ("memory_used_pct", "gauge", {"host": "api-1.prod.us-east-1"}, lambda: random.uniform(60, 85)),
        ("error_rate", "gauge", {"service": "payment-api"}, lambda: random.uniform(0.1, 5.0)),
        ("error_rate", "gauge", {"service": "user-service"}, lambda: random.uniform(0.01, 2.0)),
        ("disk_usage_pct", "gauge", {"host": "web-1.prod.us-east-1", "mount": "/data"}, lambda: random.uniform(40, 75)),
        ("active_connections", "gauge", {"service": "payment-api"}, lambda: random.randint(10, 100)),
        ("queue_depth", "gauge", {"queue": "orders"}, lambda: random.randint(0, 500)),
        ("queue_depth", "gauge", {"queue": "notifications"}, lambda: random.randint(0, 200)),
    ]

    for metric_name, metric_type, labels, value_fn in metric_defs:
        for i in range(points_per_metric):
            ts = NOW - timedelta(minutes=points_per_metric - i)
            value = value_fn()
            rows.append([
                TENANT, metric_name, metric_type, ts, float(value),
                labels, labels.get("service", ""), labels.get("host", ""),
            ])

    client.insert(
        "metrics.samples", rows,
        column_names=[
            "tenant_id", "metric_name", "metric_type", "timestamp",
            "value", "labels", "label_service", "label_host",
        ],
    )
    print(f"  ✓ {len(rows)} metric data points inserted")


def seed_traces(count: int = 50):
    """Seed trace data with realistic service-to-service calls."""
    print(f"Seeding {count} traces...")
    rows = []

    for i in range(count):
        trace_id = f"{random.randint(10**31, 10**32-1):032x}"
        ts = NOW - timedelta(minutes=random.randint(0, 60))
        duration_base = random.randint(10_000_000, 500_000_000)  # 10ms - 500ms in ns

        # Root span (gateway)
        root_span = f"{random.randint(10**15, 10**16-1):016x}"
        rows.append([
            TENANT, trace_id, root_span, "", "HTTP GET /api/checkout",
            "gateway", "SERVER", ts, ts + timedelta(microseconds=duration_base // 1000),
            duration_base, "OK", {"http.method": "GET", "http.url": "/api/checkout", "http.status_code": "200"}, {},
        ])

        # Child span (payment-api)
        child1 = f"{random.randint(10**15, 10**16-1):016x}"
        child_dur = int(duration_base * 0.6)
        rows.append([
            TENANT, trace_id, child1, root_span, "POST /process-payment",
            "payment-api", "SERVER", ts + timedelta(microseconds=5000),
            ts + timedelta(microseconds=5000 + child_dur // 1000),
            child_dur, "OK", {"http.method": "POST", "payment.amount": f"{random.uniform(10, 200):.2f}"}, {},
        ])

        # Child span (database)
        child2 = f"{random.randint(10**15, 10**16-1):016x}"
        db_dur = int(duration_base * 0.3)
        status = random.choice(["OK", "OK", "OK", "ERROR"])
        rows.append([
            TENANT, trace_id, child2, child1, "SELECT orders WHERE user_id = ?",
            "postgres", "CLIENT", ts + timedelta(microseconds=10000),
            ts + timedelta(microseconds=10000 + db_dur // 1000),
            db_dur, status, {"db.system": "postgresql", "db.statement": "SELECT * FROM orders"}, {},
        ])

    client.insert(
        "traces.spans", rows,
        column_names=[
            "tenant_id", "trace_id", "span_id", "parent_span_id",
            "operation_name", "service", "span_kind",
            "start_time", "end_time", "duration_ns",
            "status_code", "attributes", "resource_attrs",
        ],
    )
    print(f"  ✓ {len(rows)} spans inserted ({count} traces)")


def main():
    print("╔═══════════════════════════════════════════╗")
    print("║   RayOlly Demo Data Seeder                ║")
    print("╚═══════════════════════════════════════════╝")
    print()

    seed_logs(500)
    seed_metrics(60)
    seed_traces(50)

    print()
    print("=== Verification ===")
    for table in ["logs.log_entries", "metrics.samples", "traces.spans"]:
        result = client.query(f"SELECT count() FROM {table} WHERE tenant_id='{TENANT}'")
        print(f"  {table}: {result.result_rows[0][0]} rows")

    print()
    print("✓ Demo data seeded successfully!")
    print("  Browse: http://localhost:3001")
    print("  API:    http://localhost:8080/docs")


if __name__ == "__main__":
    main()
