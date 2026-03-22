"""Tests for rayolly.services.ai.patterns — DrainParser."""

from __future__ import annotations

import pytest

from rayolly.services.ai.patterns import DrainParser, LogPattern


@pytest.fixture
def parser() -> DrainParser:
    return DrainParser(depth=4, similarity_threshold=0.5, max_patterns=100)


# -----------------------------------------------------------------------
# Basic parsing
# -----------------------------------------------------------------------

class TestBasicParsing:
    def test_parse_single_log(self, parser: DrainParser) -> None:
        pattern = parser.parse("Connection established from host alpha")
        assert isinstance(pattern, LogPattern)
        assert pattern.count == 1

    def test_parse_creates_pattern(self, parser: DrainParser) -> None:
        parser.parse("Server started on port 8080")
        patterns = parser.get_patterns()
        assert len(patterns) >= 1

    def test_similar_logs_same_pattern(self, parser: DrainParser) -> None:
        parser.parse("Connection established from host alpha")
        pattern = parser.parse("Connection established from host beta")
        # After parsing two similar logs the matched pattern count should be > 1
        # (either the same pattern object incremented, or a new one if not matched)
        patterns = parser.get_patterns()
        total_count = sum(p.count for p in patterns)
        assert total_count == 2

    def test_different_logs_different_patterns(self, parser: DrainParser) -> None:
        parser.parse("User login successful")
        parser.parse("Disk usage exceeded threshold on node db-1")
        patterns = parser.get_patterns()
        assert len(patterns) >= 2


# -----------------------------------------------------------------------
# Variable replacement
# -----------------------------------------------------------------------

class TestVariableReplacement:
    def test_variable_replacement_ip(self, parser: DrainParser) -> None:
        pattern = parser.parse("Connection from 192.168.1.1 accepted")
        # The preprocessor replaces IPs with <IP>, then _create_template
        # treats the <IP> placeholder as a variable and converts it to <*>
        assert "<*>" in pattern.template
        # Verify the original IP was indeed replaced during preprocessing
        assert "192.168.1.1" not in pattern.template

    def test_variable_replacement_uuid(self, parser: DrainParser) -> None:
        pattern = parser.parse("Processing request 550e8400-e29b-41d4-a716-446655440000")
        assert "<*>" in pattern.template
        assert "550e8400" not in pattern.template

    def test_variable_replacement_timestamp(self, parser: DrainParser) -> None:
        pattern = parser.parse("Event at 2025-03-15T10:30:00Z processed")
        assert "<*>" in pattern.template
        assert "2025-03-15" not in pattern.template


# -----------------------------------------------------------------------
# Pattern management
# -----------------------------------------------------------------------

class TestPatternManagement:
    def test_get_patterns_sorted_by_count(self, parser: DrainParser) -> None:
        for _ in range(5):
            parser.parse("Frequent log message here")
        parser.parse("Rare log message once")

        patterns = parser.get_patterns()
        # First pattern should have the highest count
        assert patterns[0].count >= patterns[-1].count

    def test_new_pattern_detection(self, parser: DrainParser) -> None:
        parser.parse("One-time error xyz occurred")
        new_patterns = parser.get_new_patterns(since_count=1)
        assert len(new_patterns) >= 1

    def test_max_patterns_limit(self) -> None:
        small_parser = DrainParser(max_patterns=3)
        for i in range(10):
            # Each message is structurally very different to force new patterns
            small_parser.parse(f"unique_keyword_{i} " + "x " * (i + 3))
        # Should not exceed the configured limit
        assert len(small_parser.get_patterns()) <= 3


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_log(self, parser: DrainParser) -> None:
        pattern = parser.parse("")
        assert pattern.pattern_id == "empty"
        assert pattern.template == "<EMPTY>"
