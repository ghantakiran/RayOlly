"""Log pattern mining using the Drain algorithm for automatic log clustering."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# Common variable patterns to replace with <*>
VARIABLE_PATTERNS = [
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b"), "<IP>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<UUID>"),
    (re.compile(r"\b[0-9a-f]{24,64}\b"), "<HEX>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?\b"), "<TIMESTAMP>"),
    (re.compile(r"\b\d+\.\d+\b"), "<FLOAT>"),
    (re.compile(r"\b\d{4,}\b"), "<NUM>"),
]


@dataclass
class LogPattern:
    pattern_id: str
    template: str
    tokens: list[str]
    count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sample_logs: list[str] = field(default_factory=list)

    @property
    def pattern_hash(self) -> str:
        return hashlib.md5(self.template.encode()).hexdigest()[:16]


@dataclass
class DrainNode:
    children: dict[str, DrainNode] = field(default_factory=dict)
    patterns: list[LogPattern] = field(default_factory=list)


class DrainParser:
    """Drain algorithm for online log parsing and pattern extraction.

    Reference: "Drain: An Online Log Parsing Approach with Fixed Depth Tree"
    (He et al., 2017)
    """

    def __init__(
        self,
        depth: int = 4,
        similarity_threshold: float = 0.5,
        max_children: int = 100,
        max_patterns: int = 10000,
    ) -> None:
        self.depth = depth
        self.similarity_threshold = similarity_threshold
        self.max_children = max_children
        self.max_patterns = max_patterns
        self._root = DrainNode()
        self._patterns: dict[str, LogPattern] = {}

    def parse(self, log_message: str, timestamp: str = "") -> LogPattern:
        """Parse a log message and return its pattern (creating one if new)."""
        # Preprocess: replace known variable patterns
        preprocessed = self._preprocess(log_message)
        tokens = preprocessed.split()

        if not tokens:
            return LogPattern(
                pattern_id="empty",
                template="<EMPTY>",
                tokens=[],
                count=1,
            )

        # Step 1: Navigate tree by log length
        length_key = str(len(tokens))
        if length_key not in self._root.children:
            if len(self._root.children) >= self.max_children:
                length_key = "*"
            self._root.children[length_key] = DrainNode()
        length_node = self._root.children[length_key]

        # Step 2: Navigate by first token (depth-limited)
        current_node = length_node
        for d in range(min(self.depth - 1, len(tokens))):
            token = tokens[d]
            if self._is_variable(token):
                token = "<*>"
            if token not in current_node.children:
                if len(current_node.children) >= self.max_children:
                    token = "<*>"
                if token not in current_node.children:
                    current_node.children[token] = DrainNode()
            current_node = current_node.children[token]

        # Step 3: Find matching pattern in leaf node
        matched = self._find_matching_pattern(current_node, tokens)

        if matched:
            matched.count += 1
            matched.last_seen = timestamp
            if len(matched.sample_logs) < 3:
                matched.sample_logs.append(log_message[:500])
            return matched

        # Step 4: Create new pattern
        template_tokens = self._create_template(tokens)
        template = " ".join(template_tokens)
        pattern = LogPattern(
            pattern_id=f"pat_{hashlib.md5(template.encode()).hexdigest()[:12]}",
            template=template,
            tokens=template_tokens,
            count=1,
            first_seen=timestamp,
            last_seen=timestamp,
            sample_logs=[log_message[:500]],
        )

        if len(self._patterns) < self.max_patterns:
            current_node.patterns.append(pattern)
            self._patterns[pattern.pattern_id] = pattern

        return pattern

    def get_patterns(self) -> list[LogPattern]:
        """Return all discovered patterns sorted by count."""
        return sorted(self._patterns.values(), key=lambda p: p.count, reverse=True)

    def get_new_patterns(self, since_count: int = 1) -> list[LogPattern]:
        """Return patterns seen only a few times (potentially new issues)."""
        return [p for p in self._patterns.values() if p.count <= since_count]

    def _preprocess(self, message: str) -> str:
        """Replace known variable patterns with placeholders."""
        result = message
        for pattern, replacement in VARIABLE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def _is_variable(self, token: str) -> bool:
        """Check if a token looks like a variable value."""
        if token.startswith("<") and token.endswith(">"):
            return True
        if token.isdigit():
            return True
        if re.match(r"^0x[0-9a-f]+$", token, re.I):
            return True
        return False

    def _find_matching_pattern(
        self, node: DrainNode, tokens: list[str]
    ) -> LogPattern | None:
        """Find the most similar existing pattern."""
        best_match = None
        best_sim = 0.0

        for pattern in node.patterns:
            sim = self._compute_similarity(tokens, pattern.tokens)
            if sim >= self.similarity_threshold and sim > best_sim:
                best_match = pattern
                best_sim = sim

        if best_match:
            # Update template with wildcards where tokens differ
            self._update_template(best_match, tokens)

        return best_match

    def _compute_similarity(
        self, tokens: list[str], pattern_tokens: list[str]
    ) -> float:
        """Compute similarity between token sequence and pattern."""
        if len(tokens) != len(pattern_tokens):
            return 0.0

        match_count = sum(
            1 for t, p in zip(tokens, pattern_tokens)
            if t == p or p == "<*>"
        )
        return match_count / len(tokens)

    def _create_template(self, tokens: list[str]) -> list[str]:
        """Create initial template from tokens."""
        return [
            "<*>" if self._is_variable(t) else t
            for t in tokens
        ]

    def _update_template(self, pattern: LogPattern, tokens: list[str]) -> None:
        """Update template: where tokens differ, replace with <*>."""
        for i in range(min(len(pattern.tokens), len(tokens))):
            if pattern.tokens[i] != tokens[i] and pattern.tokens[i] != "<*>":
                pattern.tokens[i] = "<*>"
        pattern.template = " ".join(pattern.tokens)
