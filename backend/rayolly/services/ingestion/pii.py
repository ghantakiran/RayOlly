from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from rayolly.services.ingestion.models import PIIMatch

logger = structlog.get_logger(__name__)

DEFAULT_PATTERNS: dict[str, re.Pattern[str]] = {
    "credit_card": re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|"
        r"3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b"
    ),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "ip_address": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
}

REDACTION_LABELS: dict[str, str] = {
    "credit_card": "[CREDIT_CARD]",
    "ssn": "[SSN]",
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "ip_address": "[IP_ADDRESS]",
}


@dataclass
class TenantPIIConfig:
    enabled_patterns: set[str] = field(default_factory=lambda: {"credit_card", "ssn", "email", "phone"})
    redact_ip: bool = False


class PIIDetector:
    def __init__(
        self,
        patterns: dict[str, re.Pattern[str]] | None = None,
        tenant_configs: dict[str, TenantPIIConfig] | None = None,
    ) -> None:
        self._patterns = patterns or DEFAULT_PATTERNS
        self._tenant_configs = tenant_configs or {}
        self._default_config = TenantPIIConfig()

    def get_config(self, tenant_id: str) -> TenantPIIConfig:
        return self._tenant_configs.get(tenant_id, self._default_config)

    def detect_pii(self, text: str, tenant_id: str | None = None) -> list[PIIMatch]:
        config = self.get_config(tenant_id) if tenant_id else self._default_config
        matches: list[PIIMatch] = []

        active_patterns = set(config.enabled_patterns)
        if config.redact_ip:
            active_patterns.add("ip_address")

        for pattern_name in active_patterns:
            pattern = self._patterns.get(pattern_name)
            if pattern is None:
                continue

            replacement = REDACTION_LABELS.get(pattern_name, f"[{pattern_name.upper()}]")
            for match in pattern.finditer(text):
                matches.append(
                    PIIMatch(
                        type=pattern_name,
                        start=match.start(),
                        end=match.end(),
                        replacement=replacement,
                    )
                )

        matches.sort(key=lambda m: m.start)
        return matches

    def redact(self, text: str, matches: list[PIIMatch]) -> str:
        if not matches:
            return text

        parts: list[str] = []
        last_end = 0
        for m in sorted(matches, key=lambda m: m.start):
            if m.start < last_end:
                continue
            parts.append(text[last_end : m.start])
            parts.append(m.replacement)
            last_end = m.end
        parts.append(text[last_end:])
        return "".join(parts)

    def detect_and_redact(self, text: str, tenant_id: str | None = None) -> str:
        matches = self.detect_pii(text, tenant_id)
        return self.redact(text, matches)
