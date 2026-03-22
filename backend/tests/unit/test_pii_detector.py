"""Tests for rayolly.services.ingestion.pii — PIIDetector."""

from __future__ import annotations

import pytest

from rayolly.services.ingestion.pii import PIIDetector, TenantPIIConfig


@pytest.fixture
def detector() -> PIIDetector:
    return PIIDetector()


# -----------------------------------------------------------------------
# Detection
# -----------------------------------------------------------------------

class TestDetection:
    def test_detect_credit_card(self, detector: PIIDetector) -> None:
        matches = detector.detect_pii("Card number: 4111111111111111")
        types = {m.type for m in matches}
        assert "credit_card" in types

    def test_detect_ssn(self, detector: PIIDetector) -> None:
        matches = detector.detect_pii("SSN: 123-45-6789")
        types = {m.type for m in matches}
        assert "ssn" in types

    def test_detect_email(self, detector: PIIDetector) -> None:
        matches = detector.detect_pii("Contact alice@example.com for details")
        types = {m.type for m in matches}
        assert "email" in types

    def test_detect_phone(self, detector: PIIDetector) -> None:
        matches = detector.detect_pii("Call us at (555) 123-4567")
        types = {m.type for m in matches}
        assert "phone" in types

    def test_detect_ip_address(self) -> None:
        # IP detection requires redact_ip=True in config
        config = TenantPIIConfig(redact_ip=True)
        detector = PIIDetector(tenant_configs={"t1": config})
        matches = detector.detect_pii("Source IP: 10.0.0.1", tenant_id="t1")
        types = {m.type for m in matches}
        assert "ip_address" in types

    def test_no_pii_in_normal_text(self, detector: PIIDetector) -> None:
        matches = detector.detect_pii("The quick brown fox jumps over the lazy dog")
        assert len(matches) == 0


# -----------------------------------------------------------------------
# Redaction
# -----------------------------------------------------------------------

class TestRedaction:
    def test_redact_replaces_matches(self, detector: PIIDetector) -> None:
        text = "Email: alice@example.com"
        result = detector.detect_and_redact(text)
        assert "alice@example.com" not in result
        assert "[EMAIL]" in result

    def test_multiple_pii_in_one_string(self, detector: PIIDetector) -> None:
        text = "User alice@example.com SSN 123-45-6789"
        result = detector.detect_and_redact(text)
        assert "[EMAIL]" in result
        assert "[SSN]" in result
        assert "alice@example.com" not in result
        assert "123-45-6789" not in result


# -----------------------------------------------------------------------
# Tenant config
# -----------------------------------------------------------------------

class TestTenantConfig:
    def test_per_tenant_config_disable_specific_patterns(self) -> None:
        # Tenant only wants email detection
        config = TenantPIIConfig(enabled_patterns={"email"})
        detector = PIIDetector(tenant_configs={"tenant-x": config})

        text = "Email: alice@example.com SSN: 123-45-6789"
        matches = detector.detect_pii(text, tenant_id="tenant-x")
        types = {m.type for m in matches}

        assert "email" in types
        # SSN should NOT be detected because the tenant only enabled email
        assert "ssn" not in types
