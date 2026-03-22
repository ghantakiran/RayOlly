"""Integration tests requiring running ClickHouse.

Run: pytest tests/integration/ -m integration (requires `make dev` running)
"""
import clickhouse_connect
import pytest


@pytest.fixture
def ch():
    try:
        client = clickhouse_connect.get_client(host="localhost", port=8123, username="rayolly", password="rayolly_dev")
        client.ping()
        return client
    except Exception:
        pytest.skip("ClickHouse not available")

@pytest.mark.integration
class TestClickHouseSchema:
    def test_logs_table_exists(self, ch):
        result = ch.query("SELECT count() FROM system.tables WHERE database='logs' AND name='log_entries'")
        assert result.result_rows[0][0] == 1

    def test_metrics_table_exists(self, ch):
        result = ch.query("SELECT count() FROM system.tables WHERE database='metrics' AND name='samples'")
        assert result.result_rows[0][0] == 1

    def test_traces_table_exists(self, ch):
        result = ch.query("SELECT count() FROM system.tables WHERE database='traces' AND name='spans'")
        assert result.result_rows[0][0] == 1

    def test_insert_and_query_log(self, ch):
        ch.insert("logs.log_entries",
            [["integration-test", "2026-03-20 10:00:00.000000000", "INFO", 9, "test-svc", "test-host", "Integration test log", {}, {}, "", "", "test"]],
            column_names=["tenant_id", "timestamp", "severity", "severity_number", "service", "host", "body", "attributes", "resource_attrs", "trace_id", "span_id", "stream"])
        result = ch.query("SELECT body FROM logs.log_entries WHERE tenant_id='integration-test' AND body='Integration test log'")
        assert len(result.result_rows) >= 1
        # Cleanup
        ch.command("ALTER TABLE logs.log_entries DELETE WHERE tenant_id='integration-test'")

    def test_insert_and_query_metric(self, ch):
        ch.insert("metrics.samples",
            [["integration-test", "test_metric", "gauge", "2026-03-20 10:00:00.000", 99.9, {}, "", ""]],
            column_names=["tenant_id", "metric_name", "metric_type", "timestamp", "value", "labels", "label_service", "label_host"])
        result = ch.query("SELECT value FROM metrics.samples WHERE tenant_id='integration-test' AND metric_name='test_metric'")
        assert len(result.result_rows) >= 1
        assert result.result_rows[0][0] == 99.9
        ch.command("ALTER TABLE metrics.samples DELETE WHERE tenant_id='integration-test'")
