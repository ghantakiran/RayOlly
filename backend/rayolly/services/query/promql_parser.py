"""PromQL parser — converts PromQL expressions to an AST, then to ClickHouse SQL.

Supports: instant vectors, range vectors, rate(), sum(), avg(), min(), max(),
count(), topk(), bottomk(), histogram_quantile(), label_replace(),
binary operations (+, -, *, /), comparison operators (>, <, ==, !=, >=, <=),
aggregation with by/without clauses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class NodeType(Enum):
    VECTOR_SELECTOR = "vector_selector"
    MATRIX_SELECTOR = "matrix_selector"
    FUNCTION_CALL = "function_call"
    AGGREGATION = "aggregation"
    BINARY_EXPR = "binary_expr"
    NUMBER_LITERAL = "number_literal"
    STRING_LITERAL = "string_literal"


@dataclass
class ASTNode:
    type: NodeType
    value: Any = None
    children: list[ASTNode] = field(default_factory=list)
    # For vector selectors
    metric_name: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    label_matchers: list[tuple[str, str, str]] = field(default_factory=list)  # (name, op, value)
    # For range vectors
    range_duration: str = ""  # "5m", "1h", etc.
    # For functions
    func_name: str = ""
    # For aggregations
    agg_op: str = ""
    by_labels: list[str] = field(default_factory=list)
    without_labels: list[str] = field(default_factory=list)
    # For binary expressions
    operator: str = ""


class PromQLParser:
    """Parse PromQL into an AST.

    Grammar (simplified):
        expr           = aggregation | function_call | binary_expr | matrix_sel | vector_sel | number
        aggregation    = AGG_OP (by|without)? '(' labels ')' '(' expr ')'
                       | AGG_OP '(' expr ')' (by|without)? '(' labels ')'
        function_call  = FUNC '(' args ')'
        matrix_sel     = vector_sel '[' duration ']'
        vector_sel     = METRIC_NAME label_matchers?
        label_matchers = '{' matcher (',' matcher)* '}'
        matcher        = LABEL_NAME ('='|'!='|'=~'|'!~') STRING
        binary_expr    = expr OP expr
        number         = FLOAT
    """

    FUNCTIONS = frozenset({
        "rate", "irate", "increase", "delta", "deriv", "predict_linear",
        "histogram_quantile", "label_replace", "label_join",
        "abs", "ceil", "floor", "round", "sqrt", "ln", "log2", "log10", "exp",
        "time", "timestamp", "vector", "scalar", "sgn",
        "clamp", "clamp_min", "clamp_max",
        "changes", "resets", "absent", "absent_over_time", "present_over_time",
        "avg_over_time", "min_over_time", "max_over_time", "sum_over_time",
        "count_over_time", "quantile_over_time", "stddev_over_time", "stdvar_over_time",
        "last_over_time", "sort", "sort_desc",
    })

    AGGREGATIONS = frozenset({
        "sum", "avg", "min", "max", "count", "group",
        "stddev", "stdvar", "topk", "bottomk",
        "count_values", "quantile",
    })

    # Binary operators ordered by *increasing* precedence so that when we split
    # on the lowest-precedence operator first, the tree respects evaluation order.
    _BINARY_OPS = [
        " or ", " unless ",
        " and ",
        " == ", " != ", " >= ", " <= ", " > ", " < ",
        " + ", " - ",
        " * ", " / ", " % ",
        " ^ ",
    ]

    def parse(self, expr: str) -> ASTNode:
        """Parse a PromQL expression string into an AST."""
        expr = expr.strip()
        if not expr:
            raise ValueError("Empty PromQL expression")

        # Strip outermost redundant parentheses: "(expr)"
        if expr.startswith("(") and self._matching_paren(expr, 0) == len(expr) - 1:
            return self.parse(expr[1:-1])

        # --- Try aggregation ---
        node = self._try_aggregation(expr)
        if node is not None:
            return node

        # --- Try function call ---
        node = self._try_function_call(expr)
        if node is not None:
            return node

        # --- Try binary expression (lowest precedence first) ---
        node = self._try_binary(expr)
        if node is not None:
            return node

        # --- Try matrix selector: <vector>[duration] ---
        matrix_match = re.match(r'^(.+)\[(\d+[smhdwy])\]\s*$', expr)
        if matrix_match:
            inner = self.parse(matrix_match.group(1).strip())
            inner.type = NodeType.MATRIX_SELECTOR
            inner.range_duration = matrix_match.group(2)
            return inner

        # --- Try vector selector: metric_name{...} ---
        vec_match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(\{[^}]*\})?\s*$', expr)
        if vec_match:
            metric = vec_match.group(1)
            labels_str = vec_match.group(2) or ""
            matchers = self._parse_label_matchers(labels_str)
            return ASTNode(
                type=NodeType.VECTOR_SELECTOR,
                metric_name=metric,
                label_matchers=matchers,
            )

        # --- Try number literal ---
        try:
            val = float(expr)
            return ASTNode(type=NodeType.NUMBER_LITERAL, value=val)
        except ValueError:
            pass

        # --- Try string literal ---
        if (expr.startswith('"') and expr.endswith('"')) or (
            expr.startswith("'") and expr.endswith("'")
        ):
            return ASTNode(type=NodeType.STRING_LITERAL, value=expr[1:-1])

        # Fallback: treat as a bare metric name
        return ASTNode(type=NodeType.VECTOR_SELECTOR, metric_name=expr.strip())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_aggregation(self, expr: str) -> ASTNode | None:
        """Try to parse ``expr`` as an aggregation expression.

        Handles both forms:
            sum by (label) (inner_expr)
            sum (inner_expr) by (label)
        """
        # Form 1: op (by|without) (labels) (inner)
        m = re.match(
            r'^(\w+)\s+(by|without)\s*\(([^)]*)\)\s*\((.+)\)\s*$',
            expr,
            re.DOTALL,
        )
        if m and m.group(1) in self.AGGREGATIONS:
            return self._build_aggregation(
                op=m.group(1),
                clause=m.group(2),
                labels_str=m.group(3),
                inner_expr=m.group(4),
            )

        # Form 2: op (inner) by|without (labels)
        m2 = re.match(
            r'^(\w+)\s*\((.+)\)\s+(by|without)\s*\(([^)]*)\)\s*$',
            expr,
            re.DOTALL,
        )
        if m2 and m2.group(1) in self.AGGREGATIONS:
            return self._build_aggregation(
                op=m2.group(1),
                clause=m2.group(3),
                labels_str=m2.group(4),
                inner_expr=m2.group(2),
            )

        # Form 3: op (inner) — no by/without
        m3 = re.match(r'^(\w+)\s*\((.+)\)\s*$', expr, re.DOTALL)
        if m3 and m3.group(1) in self.AGGREGATIONS:
            return self._build_aggregation(
                op=m3.group(1),
                clause="",
                labels_str="",
                inner_expr=m3.group(2),
            )

        return None

    def _build_aggregation(
        self, op: str, clause: str, labels_str: str, inner_expr: str
    ) -> ASTNode:
        labels = [l.strip() for l in labels_str.split(",") if l.strip()] if labels_str else []
        node = ASTNode(type=NodeType.AGGREGATION, agg_op=op)
        if clause == "by":
            node.by_labels = labels
        elif clause == "without":
            node.without_labels = labels
        # For topk/bottomk the first arg is the k-value
        args = self._split_args(inner_expr)
        if op in ("topk", "bottomk", "quantile", "count_values") and len(args) >= 2:
            node.value = args[0].strip()
            node.children = [self.parse(args[1].strip())]
        else:
            node.children = [self.parse(a.strip()) for a in args]
        return node

    def _try_function_call(self, expr: str) -> ASTNode | None:
        m = re.match(r'^(\w+)\s*\((.+)\)\s*$', expr, re.DOTALL)
        if not m or m.group(1) not in self.FUNCTIONS:
            return None
        fname = m.group(1)
        args = self._split_args(m.group(2))
        node = ASTNode(type=NodeType.FUNCTION_CALL, func_name=fname)
        node.children = [self.parse(a.strip()) for a in args]
        return node

    def _try_binary(self, expr: str) -> ASTNode | None:
        """Split on the lowest-precedence binary operator outside parentheses."""
        for op in self._BINARY_OPS:
            idx = self._find_op_outside_parens(expr, op)
            if idx >= 0:
                left = expr[:idx].strip()
                right = expr[idx + len(op):].strip()
                if left and right:
                    node = ASTNode(type=NodeType.BINARY_EXPR, operator=op.strip())
                    node.children = [self.parse(left), self.parse(right)]
                    return node
        return None

    def _find_op_outside_parens(self, expr: str, op: str) -> int:
        """Return the *rightmost* position of ``op`` at parenthesis depth 0, or -1."""
        depth = 0
        best = -1
        i = 0
        lower = expr.lower()
        while i < len(expr):
            ch = expr[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif depth == 0 and lower[i:i + len(op)] == op:
                best = i
            i += 1
        return best

    @staticmethod
    def _matching_paren(expr: str, start: int) -> int:
        """Return the index of the closing paren matching the one at ``start``."""
        depth = 0
        for i in range(start, len(expr)):
            if expr[i] == '(':
                depth += 1
            elif expr[i] == ')':
                depth -= 1
                if depth == 0:
                    return i
        return -1

    @staticmethod
    def _parse_label_matchers(labels_str: str) -> list[tuple[str, str, str]]:
        labels_str = labels_str.strip("{}")
        if not labels_str:
            return []
        matchers: list[tuple[str, str, str]] = []
        for pair in labels_str.split(","):
            pair = pair.strip()
            if not pair:
                continue
            # Try operators in order of longest first to avoid partial matches
            for op in ("=~", "!~", "!=", "="):
                if op in pair:
                    parts = pair.split(op, 1)
                    matchers.append((
                        parts[0].strip(),
                        op,
                        parts[1].strip().strip('"').strip("'"),
                    ))
                    break
        return matchers

    @staticmethod
    def _split_args(args_str: str) -> list[str]:
        """Split function/aggregation arguments respecting parentheses and brackets."""
        depth = 0
        current: list[str] = []
        args: list[str] = []
        for ch in args_str:
            if ch in ('(', '[', '{'):
                depth += 1
            elif ch in (')', ']', '}'):
                depth -= 1
            elif ch == ',' and depth == 0:
                args.append("".join(current))
                current = []
                continue
            current.append(ch)
        remainder = "".join(current).strip()
        if remainder:
            args.append(remainder)
        return args


# ---------------------------------------------------------------------------
# AST -> ClickHouse SQL translator
# ---------------------------------------------------------------------------


class PromQLToSQL:
    """Convert a PromQL AST to ClickHouse SQL.

    The generated SQL targets the ``metrics.samples`` table layout used by RayOlly:
        - tenant_id      LowCardinality(String)
        - metric_name    LowCardinality(String)
        - labels         Map(String, String)
        - value          Float64
        - timestamp      DateTime64(3)
    """

    def __init__(self, tenant_id: str) -> None:
        if not re.match(r'^[a-zA-Z0-9_-]+$', tenant_id):
            raise ValueError(f"Invalid tenant_id: {tenant_id}")
        self.tenant_id = tenant_id

    def translate(
        self,
        node: ASTNode,
        time_range: tuple[str, str] | None = None,
    ) -> str:
        """Convert an AST node to a ClickHouse SQL string."""
        match node.type:
            case NodeType.VECTOR_SELECTOR:
                return self._vector_to_sql(node, time_range)
            case NodeType.MATRIX_SELECTOR:
                return self._matrix_to_sql(node, time_range)
            case NodeType.FUNCTION_CALL:
                return self._function_to_sql(node, time_range)
            case NodeType.AGGREGATION:
                return self._aggregation_to_sql(node, time_range)
            case NodeType.BINARY_EXPR:
                return self._binary_to_sql(node, time_range)
            case NodeType.NUMBER_LITERAL:
                return str(node.value)
            case NodeType.STRING_LITERAL:
                return f"'{node.value}'"
            case _:
                return f"/* unsupported node type: {node.type} */"

    # ------------------------------------------------------------------
    # Node translators
    # ------------------------------------------------------------------

    def _base_where(self, node: ASTNode, tr: tuple[str, str] | None) -> str:
        """Build the WHERE clause fragments for a vector/matrix selector."""
        clauses = [
            f"tenant_id = '{self.tenant_id}'",
            f"metric_name = '{node.metric_name}'",
        ]
        for name, op, value in node.label_matchers:
            match op:
                case "=":
                    clauses.append(f"labels['{name}'] = '{value}'")
                case "!=":
                    clauses.append(f"labels['{name}'] != '{value}'")
                case "=~":
                    clauses.append(f"match(labels['{name}'], '{value}')")
                case "!~":
                    clauses.append(f"NOT match(labels['{name}'], '{value}')")
        if tr:
            clauses.append(f"timestamp >= '{tr[0]}'")
            clauses.append(f"timestamp <= '{tr[1]}'")
        return " AND ".join(clauses)

    def _vector_to_sql(self, node: ASTNode, tr: tuple[str, str] | None) -> str:
        where = self._base_where(node, tr)
        return (
            f"SELECT timestamp, value, labels "
            f"FROM metrics.samples "
            f"WHERE {where} "
            f"ORDER BY timestamp"
        )

    def _matrix_to_sql(self, node: ASTNode, tr: tuple[str, str] | None) -> str:
        # Matrix selectors use the same base query; the range duration is
        # handled by wrapping functions like rate().
        return self._vector_to_sql(node, tr)

    def _function_to_sql(self, node: ASTNode, tr: tuple[str, str] | None) -> str:
        fname = node.func_name

        # rate / irate / increase — counter derivative
        if fname in ("rate", "irate", "increase") and node.children:
            return self._rate_to_sql(node.children[0], tr, fname)

        # histogram_quantile(scalar, vector)
        if fname == "histogram_quantile" and len(node.children) >= 2:
            quantile_val = (
                node.children[0].value
                if node.children[0].type == NodeType.NUMBER_LITERAL
                else 0.99
            )
            inner_sql = self.translate(node.children[1], tr)
            return (
                f"SELECT ts, quantile({quantile_val})(value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        # *_over_time functions
        if fname.endswith("_over_time") and node.children:
            agg_map = {
                "avg_over_time": "avg",
                "min_over_time": "min",
                "max_over_time": "max",
                "sum_over_time": "sum",
                "count_over_time": "count",
                "stddev_over_time": "stddevPop",
                "stdvar_over_time": "varPop",
                "last_over_time": "argMax",
                "quantile_over_time": "quantile",
            }
            ch_func = agg_map.get(fname, "avg")
            inner = node.children[0]
            where = self._base_where(inner, tr)
            if fname == "last_over_time":
                return (
                    f"SELECT toStartOfMinute(timestamp) AS ts, "
                    f"argMax(value, timestamp) AS value "
                    f"FROM metrics.samples WHERE {where} "
                    f"GROUP BY ts ORDER BY ts"
                )
            return (
                f"SELECT toStartOfMinute(timestamp) AS ts, "
                f"{ch_func}(value) AS value "
                f"FROM metrics.samples WHERE {where} "
                f"GROUP BY ts ORDER BY ts"
            )

        # abs, ceil, floor, round, sqrt, etc. — scalar math wrappers
        scalar_funcs = {
            "abs", "ceil", "floor", "round", "sqrt",
            "ln", "log2", "log10", "exp", "sgn",
        }
        if fname in scalar_funcs and node.children:
            inner_sql = self.translate(node.children[0], tr)
            ch_func = {"ln": "log", "sgn": "sign"}.get(fname, fname)
            return (
                f"SELECT ts, {ch_func}(value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        # clamp(vector, min, max)
        if fname == "clamp" and len(node.children) >= 3:
            inner_sql = self.translate(node.children[0], tr)
            lo = node.children[1].value if node.children[1].type == NodeType.NUMBER_LITERAL else 0
            hi = node.children[2].value if node.children[2].type == NodeType.NUMBER_LITERAL else 1
            return (
                f"SELECT ts, greatest({lo}, least({hi}, value)) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        if fname == "clamp_min" and len(node.children) >= 2:
            inner_sql = self.translate(node.children[0], tr)
            lo = node.children[1].value if node.children[1].type == NodeType.NUMBER_LITERAL else 0
            return (
                f"SELECT ts, greatest({lo}, value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        if fname == "clamp_max" and len(node.children) >= 2:
            inner_sql = self.translate(node.children[0], tr)
            hi = node.children[1].value if node.children[1].type == NodeType.NUMBER_LITERAL else 1
            return (
                f"SELECT ts, least({hi}, value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        # sort / sort_desc
        if fname in ("sort", "sort_desc") and node.children:
            inner_sql = self.translate(node.children[0], tr)
            direction = "DESC" if fname == "sort_desc" else "ASC"
            return f"SELECT * FROM ({inner_sql}) ORDER BY value {direction}"

        # absent(vector) — returns 1 if vector is empty
        if fname == "absent" and node.children:
            inner_sql = self.translate(node.children[0], tr)
            return (
                f"SELECT if(count() = 0, 1, 0) AS value "
                f"FROM ({inner_sql})"
            )

        # changes / resets
        if fname in ("changes", "resets") and node.children:
            inner = node.children[0]
            where = self._base_where(inner, tr)
            if fname == "changes":
                return (
                    f"SELECT toStartOfMinute(timestamp) AS ts, "
                    f"countIf(value != neighbor(value, -1)) AS value "
                    f"FROM metrics.samples WHERE {where} "
                    f"GROUP BY ts ORDER BY ts"
                )
            else:  # resets
                return (
                    f"SELECT toStartOfMinute(timestamp) AS ts, "
                    f"countIf(value < neighbor(value, -1)) AS value "
                    f"FROM metrics.samples WHERE {where} "
                    f"GROUP BY ts ORDER BY ts"
                )

        # Fallback: translate first child
        if node.children:
            return self.translate(node.children[0], tr)
        return "SELECT 1"

    def _rate_to_sql(
        self, inner: ASTNode, tr: tuple[str, str] | None, fname: str
    ) -> str:
        where = self._base_where(inner, tr)
        # rate = (max - min) / duration_seconds.  For irate, use last two samples.
        if fname == "irate":
            return (
                f"SELECT toStartOfMinute(timestamp) AS ts, "
                f"(argMax(value, timestamp) - argMin(value, timestamp)) "
                f"/ dateDiff('second', min(timestamp), max(timestamp)) AS value "
                f"FROM metrics.samples WHERE {where} "
                f"GROUP BY ts "
                f"HAVING dateDiff('second', min(timestamp), max(timestamp)) > 0 "
                f"ORDER BY ts"
            )
        # rate & increase share the same shape; increase just omits the /seconds
        divisor = " / dateDiff('second', min(timestamp), max(timestamp))" if fname == "rate" else ""
        return (
            f"SELECT toStartOfMinute(timestamp) AS ts, "
            f"(max(value) - min(value)){divisor} AS value "
            f"FROM metrics.samples WHERE {where} "
            f"GROUP BY ts "
            f"HAVING max(value) >= min(value) "
            f"ORDER BY ts"
        )

    def _aggregation_to_sql(self, node: ASTNode, tr: tuple[str, str] | None) -> str:
        inner_sql = self.translate(node.children[0], tr) if node.children else "SELECT 1"

        agg_map = {
            "sum": "sum",
            "avg": "avg",
            "min": "min",
            "max": "max",
            "count": "count",
            "group": "count",
            "stddev": "stddevPop",
            "stdvar": "varPop",
        }

        # topk / bottomk: SELECT ... ORDER BY value DESC/ASC LIMIT k
        if node.agg_op in ("topk", "bottomk"):
            k = node.value or 10
            direction = "DESC" if node.agg_op == "topk" else "ASC"
            if node.by_labels:
                label_cols = ", ".join(f"labels['{l}'] AS {l}" for l in node.by_labels)
                group_labels = ", ".join(node.by_labels)
                return (
                    f"SELECT ts, {label_cols}, value "
                    f"FROM ({inner_sql}) "
                    f"ORDER BY value {direction} "
                    f"LIMIT {k}"
                )
            return (
                f"SELECT * FROM ({inner_sql}) "
                f"ORDER BY value {direction} LIMIT {k}"
            )

        # quantile aggregation
        if node.agg_op == "quantile":
            q = node.value or 0.5
            if node.by_labels:
                label_cols = ", ".join(f"labels['{l}'] AS {l}" for l in node.by_labels)
                group_labels = ", ".join(node.by_labels)
                return (
                    f"SELECT ts, {label_cols}, quantile({q})(value) AS value "
                    f"FROM ({inner_sql}) "
                    f"GROUP BY ts, {group_labels} ORDER BY ts"
                )
            return (
                f"SELECT ts, quantile({q})(value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        ch_func = agg_map.get(node.agg_op, "sum")

        if node.by_labels:
            label_cols = ", ".join(f"labels['{l}'] AS {l}" for l in node.by_labels)
            group_labels = ", ".join(node.by_labels)
            return (
                f"SELECT ts, {label_cols}, {ch_func}(value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts, {group_labels} ORDER BY ts"
            )

        if node.without_labels:
            # ``without`` is the inverse of ``by`` — we include all labels *except* listed ones.
            # At the SQL level we simply don't project those labels.
            return (
                f"SELECT ts, {ch_func}(value) AS value "
                f"FROM ({inner_sql}) "
                f"GROUP BY ts ORDER BY ts"
            )

        return (
            f"SELECT ts, {ch_func}(value) AS value "
            f"FROM ({inner_sql}) "
            f"GROUP BY ts ORDER BY ts"
        )

    def _binary_to_sql(self, node: ASTNode, tr: tuple[str, str] | None) -> str:
        left = self.translate(node.children[0], tr) if node.children else "0"
        right = self.translate(node.children[1], tr) if len(node.children) > 1 else "0"

        # If both sides are sub-queries, join them
        left_is_query = left.strip().upper().startswith("SELECT")
        right_is_query = right.strip().upper().startswith("SELECT")

        if left_is_query and right_is_query:
            return (
                f"SELECT l.ts AS ts, l.value {node.operator} r.value AS value "
                f"FROM ({left}) AS l "
                f"INNER JOIN ({right}) AS r ON l.ts = r.ts "
                f"ORDER BY ts"
            )
        if left_is_query:
            return (
                f"SELECT ts, value {node.operator} {right} AS value "
                f"FROM ({left}) ORDER BY ts"
            )
        if right_is_query:
            return (
                f"SELECT ts, {left} {node.operator} value AS value "
                f"FROM ({right}) ORDER BY ts"
            )
        # Both are scalars
        return f"SELECT {left} {node.operator} {right} AS value"
