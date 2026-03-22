"""SQL safety utilities for preventing injection."""
import re


def validate_identifier(value: str, name: str = "identifier") -> str:
    """Validate that a string is safe to use as a SQL identifier."""
    if not re.match(r'^[a-zA-Z0-9_.-]+$', value):
        raise ValueError(f"Invalid {name}: {value!r}")
    return value


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format."""
    return validate_identifier(tenant_id, "tenant_id")


def sanitize_search_term(term: str) -> str:
    """Remove non-alphanumeric chars from search term."""
    return re.sub(r'[^a-zA-Z0-9_.-]', '', term)


def escape_clickhouse_string(value: str) -> str:
    """Escape a string for safe use in ClickHouse SQL."""
    return value.replace("\\", "\\\\").replace("'", "\\'")
