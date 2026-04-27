from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype

from .llm import ollama_generate
from .router_types import RouteName, RouterContext, RouterResult


SUPPORTED_TOOLS = {
    "bar_chart",
    "histogram",
    "line_chart",
    "scatter_plot",
    "summary_stats",
    "correlation_check",
    "normalize_emails",
    "fuzzy_match",
    "deduplicate_rows",
}

TOOL_ALIASES = {
    "create_graph": "bar_chart",
    "graph": "bar_chart",
    "chart": "bar_chart",
    "plot": "bar_chart",
    "bar": "bar_chart",
    "bar_chart": "bar_chart",
    "hist": "histogram",
    "histogram": "histogram",
    "distribution": "histogram",
    "line": "line_chart",
    "line_chart": "line_chart",
    "scatter": "scatter_plot",
    "scatter_plot": "scatter_plot",
    "summary": "summary_stats",
    "summary_stats": "summary_stats",
    "stats": "summary_stats",
    "statistics": "summary_stats",
    "correlation": "correlation_check",
    "correlation_check": "correlation_check",
    "normalize_email": "normalize_emails",
    "normalize_emails": "normalize_emails",
    "canonicalize_email": "normalize_emails",
    "fuzzy": "fuzzy_match",
    "fuzzy_match": "fuzzy_match",
    "dedupe": "deduplicate_rows",
    "deduplicate": "deduplicate_rows",
    "deduplicate_rows": "deduplicate_rows",
}

AGGREGATIONS = {"count", "avg", "sum", "min", "max"}
PREFERRED_JOIN_KEYS = [
    "employee_id",
    "user_id",
    "id",
    "email",
    "user_email",
    "full_name",
    "name",
]
IDENTITY_HINTS = {"employee", "employees", "people", "person", "worker", "workers", "user", "users"}


@dataclass
class ColumnRef:
    table: str
    column: str

    @property
    def alias(self) -> str:
        return f"{self.table}__{self.column}"

    @property
    def label(self) -> str:
        return self.column


@dataclass
class FilterSpec:
    table: str
    column: str
    value: str


@dataclass
class PythonToolPlan:
    tool_name: str
    tables: list[str] = field(default_factory=list)
    columns: list[ColumnRef] = field(default_factory=list)
    filters: list[FilterSpec] = field(default_factory=list)
    x: ColumnRef | None = None
    y: ColumnRef | None = None
    aggregation: str = "count"
    threshold: float = 0.85
    left: ColumnRef | None = None
    right: ColumnRef | None = None
    dedupe_keys: list[ColumnRef] = field(default_factory=list)
    reason: str = ""
    raw_plan: dict[str, Any] = field(default_factory=dict)


def _normalize(text: Any) -> str:
    text = str(text or "").strip().lower()
    text = text.replace("__", " ").replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9@. /]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _contains_exact_term(text: str, term: str) -> bool:
    text_n = _normalize(text)
    term_n = _normalize(term)
    if not text_n or not term_n:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(term_n)}(?![a-z0-9])", text_n) is not None


def _readable_tool_name(tool_name: str) -> str:
    return tool_name.replace("_", " ")


def _coerce_tool_name(value: Any, user_request: str = "") -> str | None:
    raw = _normalize(value).replace(" ", "_")
    if raw in TOOL_ALIASES:
        return TOOL_ALIASES[raw]
    if raw in SUPPORTED_TOOLS:
        return raw

    q = _normalize(user_request)
    if ("normalize" in q or "canonicalize" in q or "standardize" in q or "clean" in q) and "email" in q:
        return "normalize_emails"
    if any(term in q for term in ["fuzzy match", "approximate match", "similarity", "similar names", "similar emails"]):
        return "fuzzy_match"
    if any(term in q for term in ["dedupe", "deduplicate", "duplicate rows", "duplicate emails", "find duplicates"]):
        return "deduplicate_rows"
    if any(term in q for term in ["correlation", "correlate", "relationship between"]):
        return "correlation_check"
    if any(term in q for term in ["summary stats", "summary statistics", "descriptive stats", "statistics for"]):
        return "summary_stats"
    if any(term in q for term in ["histogram", "distribution"]):
        return "histogram"
    if "scatter" in q:
        return "scatter_plot"
    if "line" in q and any(term in q for term in ["chart", "graph", "plot"]):
        return "line_chart"
    if any(term in q for term in ["chart", "graph", "plot", "visualize", "visualise"]):
        return "bar_chart"
    return None


def _schema_entries(ctx: RouterContext) -> list[ColumnRef]:
    return [ColumnRef(table, column) for table, cols in ctx.schema_map.items() for column in cols.keys()]


def _column_matches_name(col: str, text: str) -> bool:
    col_n = _normalize(col)
    text_n = _normalize(text)
    if not col_n or not text_n:
        return False
    if col_n == text_n:
        return True
    if _contains_exact_term(text_n, col_n):
        return True

    compact_col = col_n.replace(" ", "")
    compact_text = text_n.replace(" ", "")
    if compact_col == compact_text or compact_col in compact_text:
        return True

    # Fuzzy fallback for simple typos in column names from user text, e.g.
    # "deparment" -> department or "salry" -> salary_usd. Keep this conservative
    # so short generic words do not accidentally match unrelated columns.
    if len(compact_text) >= 4:
        candidates = {compact_col}
        candidates.update(tok for tok in col_n.split() if len(tok) >= 4)
        for candidate in candidates:
            if not candidate:
                continue
            score = SequenceMatcher(None, compact_text, candidate.replace(" ", "")).ratio()
            if score >= 0.84:
                return True

    return False


def _table_matches_name(table: str, text: str) -> bool:
    table_n = _normalize(table)
    text_n = _normalize(text)
    if table_n == text_n:
        return True
    if _contains_exact_term(text_n, table_n):
        return True
    tokens = [tok for tok in table_n.split() if tok not in {"test", "export", "sheet", "sheet1", "data"}]
    return any(_contains_exact_term(text_n, tok) for tok in tokens)


def _resolve_table(raw: Any, ctx: RouterContext) -> str | None:
    raw_s = str(raw or "").strip()
    if not raw_s:
        return None
    for table in ctx.schema_map.keys():
        if table.lower() == raw_s.lower() or _table_matches_name(table, raw_s):
            return table
    return None


def _resolve_column_ref(
    raw: Any,
    ctx: RouterContext,
    *,
    preferred_table: str | None = None,
    allowed_tables: list[str] | None = None,
) -> ColumnRef | None:
    raw_s = str(raw or "").strip()
    if not raw_s:
        return None

    if "." in raw_s:
        left, right = raw_s.split(".", 1)
        table = _resolve_table(left, ctx)
        if table:
            for col in ctx.schema_map.get(table, {}).keys():
                if _column_matches_name(col, right):
                    return ColumnRef(table, col)

    candidate_tables = allowed_tables or list(ctx.schema_map.keys())
    if preferred_table:
        candidate_tables = [preferred_table] + [t for t in candidate_tables if t != preferred_table]

    matches: list[ColumnRef] = []
    for table in candidate_tables:
        for col in ctx.schema_map.get(table, {}).keys():
            if _column_matches_name(col, raw_s):
                matches.append(ColumnRef(table, col))

    if not matches:
        return None

    if preferred_table:
        for ref in matches:
            if ref.table == preferred_table:
                return ref

    # Unique column name across schema is safe. If ambiguous, prefer common HR identity table names.
    names = {(m.table, m.column) for m in matches}
    if len(names) == 1:
        return matches[0]

    for preferred in ["hr_data", "employees", "users"]:
        for ref in matches:
            if ref.table == preferred:
                return ref

    return matches[0]


def _find_columns_in_query(query: str, ctx: RouterContext) -> list[ColumnRef]:
    found: list[ColumnRef] = []
    seen: set[tuple[str, str]] = set()
    q = _normalize(query)

    for ref in _schema_entries(ctx):
        col_n = _normalize(ref.column)
        if col_n and _contains_exact_term(q, col_n):
            key = (ref.table, ref.column)
            if key not in seen:
                seen.add(key)
                found.append(ref)

    # Friendly aliases for the sample HR data and common datasets.
    alias_map = {
        "salary": ["salary_usd", "salary"],
        "salaries": ["salary_usd", "salary"],
        "salry": ["salary_usd", "salary"],
        "sallery": ["salary_usd", "salary"],
        "pay": ["salary_usd", "salary"],
        "compensation": ["salary_usd", "salary"],
        "bonus": ["bonus_pct", "bonus"],
        "rating": ["rating"],
        "review rating": ["rating"],
        "department": ["department", "team"],
        "departments": ["department", "team"],
        "deparment": ["department", "team"],
        "deparments": ["department", "team"],
        "team": ["department", "team"],
        "work mode": ["work_mode"],
        "remote": ["work_mode"],
        "office": ["work_mode"],
        "role": ["role"],
        "level": ["level"],
        "goal": ["goal_attainment"],
        "goals": ["goal_attainment"],
        "promotion": ["promotion_eligible"],
        "email": ["email", "user_email"],
        "name": ["full_name", "name"],
        "full name": ["full_name", "name"],
        "employee id": ["employee_id", "user_id", "id"],
        "years": ["years_at_company", "tenure"],
        "tenure": ["years_at_company", "tenure"],
    }

    for phrase, targets in alias_map.items():
        if _contains_exact_term(q, phrase):
            for target in targets:
                ref = _resolve_column_ref(target, ctx)
                if ref and (ref.table, ref.column) not in seen:
                    seen.add((ref.table, ref.column))
                    found.append(ref)
                    break

    return found


def _infer_aggregation(query: str, tool_name: str) -> str:
    q = _normalize(query)
    if tool_name == "histogram":
        return "count"
    if any(term in q for term in ["average", "avg", "mean"]):
        return "avg"
    if any(term in q for term in ["sum", "total"]):
        return "sum"
    if any(term in q for term in ["minimum", "lowest", "min"]):
        return "min"
    if any(term in q for term in ["maximum", "highest", "max"]):
        return "max"
    return "count"


def _is_numeric_ref(ref: ColumnRef, ctx: RouterContext) -> bool:
    dtype = str(ctx.schema_map.get(ref.table, {}).get(ref.column, "")).lower()
    return any(term in dtype for term in ["int", "double", "float", "decimal", "numeric", "real", "bigint", "utinyint", "usmallint"])


def _choose_chart_axes(query: str, ctx: RouterContext, tool_name: str) -> tuple[ColumnRef | None, ColumnRef | None, str]:
    refs = _find_columns_in_query(query, ctx)
    aggregation = _infer_aggregation(query, tool_name)

    x: ColumnRef | None = None
    y: ColumnRef | None = None

    q = _normalize(query)
    by_match = re.search(r"\bby\s+([a-zA-Z0-9_ ]+?)(?:\s+(?:for|where|with|who|that|and)\b|$)", q)
    if by_match:
        by_text = by_match.group(1).strip()
        x = _resolve_column_ref(by_text, ctx)

    if tool_name == "histogram":
        numeric_refs = [ref for ref in refs if _is_numeric_ref(ref, ctx)]
        y = numeric_refs[0] if numeric_refs else None
        if y is None:
            for hint in ["salary_usd", "salary", "rating", "bonus_pct", "years_at_company"]:
                y = _resolve_column_ref(hint, ctx)
                if y:
                    break
        return None, y, "count"

    if x is None:
        non_numeric_refs = [ref for ref in refs if not _is_numeric_ref(ref, ctx)]
        if non_numeric_refs:
            x = non_numeric_refs[0]

    numeric_refs = [ref for ref in refs if _is_numeric_ref(ref, ctx)]
    if aggregation != "count" and numeric_refs:
        y = numeric_refs[0]
    elif aggregation != "count" and y is None:
        # If the user asked for an aggregation like average/sum but misspelled the
        # measure, try common numeric measures before falling back to a count chart.
        # Example: "average salry by deparment" should still mean salary_usd by department.
        measure_hints = [
            ("salary", ["salary_usd", "salary"]),
            ("salry", ["salary_usd", "salary"]),
            ("salar", ["salary_usd", "salary"]),
            ("pay", ["salary_usd", "salary"]),
            ("rating", ["rating"]),
            ("bonus", ["bonus_pct", "bonus"]),
            ("years", ["years_at_company", "tenure"]),
            ("tenure", ["years_at_company", "tenure"]),
        ]
        for phrase, targets in measure_hints:
            if _contains_exact_term(q, phrase):
                for target in targets:
                    candidate = _resolve_column_ref(target, ctx)
                    if candidate and _is_numeric_ref(candidate, ctx):
                        y = candidate
                        break
            if y is not None:
                break
    elif tool_name in {"line_chart", "scatter_plot"}:
        if len(numeric_refs) >= 2:
            x = numeric_refs[0]
            y = numeric_refs[1]
        elif numeric_refs:
            y = numeric_refs[0]

    if x is None:
        # Common default for "employees by ..." style requests.
        for hint in ["department", "work_mode", "level", "goal_attainment", "promotion_eligible", "role"]:
            ref = _resolve_column_ref(hint, ctx)
            if ref:
                x = ref
                break

    return x, y, aggregation


def _parse_threshold(query: str, default: float = 0.85) -> float:
    pct_match = re.search(r"(\d{1,3})\s*%", query)
    if pct_match:
        pct = max(0, min(100, int(pct_match.group(1))))
        return pct / 100.0
    dec_match = re.search(r"threshold\s*(?:=|of|to)?\s*(0(?:\.\d+)?|1(?:\.0+)?)", query.lower())
    if dec_match:
        return max(0.0, min(1.0, float(dec_match.group(1))))
    return default


def _extract_explicit_refs(query: str, ctx: RouterContext) -> list[ColumnRef]:
    refs: list[ColumnRef] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", query):
        ref = _resolve_column_ref(f"{match.group(1)}.{match.group(2)}", ctx)
        if ref and (ref.table, ref.column) not in seen:
            seen.add((ref.table, ref.column))
            refs.append(ref)
    return refs


def _infer_filters(query: str, ctx: RouterContext) -> list[FilterSpec]:
    q = _normalize(query)
    filters: list[FilterSpec] = []
    seen: set[tuple[str, str, str]] = set()

    column_hints = _find_columns_in_query(query, ctx)

    for (table, column), values in ctx.categorical_index.items():
        for raw_value in values:
            value = str(raw_value).strip()
            if not value:
                continue
            value_n = _normalize(value)
            if len(value_n) < 2 or value_n in {"in", "on", "at", "to", "of", "the"}:
                continue
            if not _contains_exact_term(q, value_n):
                continue

            # If the value appears in multiple places, prefer the column also mentioned in the query.
            score = 0
            for hint in column_hints:
                if hint.table == table and hint.column == column:
                    score += 3
                elif hint.column == column:
                    score += 1
            if score == 0:
                # Still allow unique-looking business values like Engineering, Senior, Exceeds.
                pass

            key = (table, column, value)
            if key not in seen:
                seen.add(key)
                filters.append(FilterSpec(table, column, value))

    return filters


def _query_supports_filter(user_request: str, filter_spec: FilterSpec) -> bool:
    """Return True only when a planned filter is clearly supported by the user's words.

    The Python-tool planner is allowed to use an LLM, but the LLM should not be able
    to silently add a filter such as department = Engineering when the user only asked
    for "average salary by department". This guard keeps chart/data-prep filters tied
    to text that actually appears, or to a small set of safe business-word aliases.
    """
    q = _normalize(user_request)
    column_n = _normalize(filter_spec.column)
    value_n = _normalize(filter_spec.value)

    if not q or not value_n:
        return False

    # Exact categorical value in the user's request is always safe.
    if _contains_exact_term(q, value_n):
        return True

    # A few safe natural-language aliases for the HR test data.
    if column_n in {"goal attainment", "goal"} or filter_spec.column.lower() == "goal_attainment":
        if value_n == "exceeds" and any(term in q for term in ["exceed", "exceeds", "exceeded", "above goals", "did well"]):
            return True
        if value_n == "meets" and any(term in q for term in ["meet goals", "meets goals", "met goals"]):
            return True
        if value_n == "below" and any(term in q for term in ["below goals", "under goals", "missed goals"]):
            return True

    if column_n in {"promotion eligible", "promotion"} or filter_spec.column.lower() == "promotion_eligible":
        if value_n in {"yes", "true", "eligible"} and any(term in q for term in ["promotion eligible", "eligible for promotion"]):
            return True
        if value_n in {"no", "false", "not eligible"} and any(term in q for term in ["not promotion eligible", "not eligible for promotion"]):
            return True

    # Do not trust unsupported LLM filters. This is what prevents charts from
    # randomly becoming "Engineering only" when no Engineering filter was requested.
    return False


def _merge_supported_filters(
    user_request: str,
    ctx: RouterContext,
    raw_filters: list[FilterSpec],
) -> list[FilterSpec]:
    """Merge LLM and deterministic filters, keeping only filters grounded in the query."""
    merged: list[FilterSpec] = []
    seen: set[tuple[str, str, str]] = set()

    for f in raw_filters:
        if not _query_supports_filter(user_request, f):
            continue
        key = (f.table, f.column, f.value)
        if key not in seen:
            seen.add(key)
            merged.append(f)

    # Deterministic filters are still useful because they come from exact categorical
    # matches in the query, but run them through the same merge path for dedupe.
    for f in _infer_filters(user_request, ctx):
        key = (f.table, f.column, f.value)
        if key not in seen:
            seen.add(key)
            merged.append(f)

    return merged


def _build_schema_summary(ctx: RouterContext) -> str:
    lines: list[str] = []
    for table, cols in sorted(ctx.schema_map.items()):
        col_bits = [f"{col} ({dtype})" for col, dtype in cols.items()]
        lines.append(f"- {table}: {', '.join(col_bits)}")
    return "\n".join(lines) if lines else "(no schema loaded)"


def _build_categorical_summary(ctx: RouterContext, limit: int = 60) -> str:
    lines: list[str] = []
    for idx, ((table, column), values) in enumerate(sorted(ctx.categorical_index.items())):
        if idx >= limit:
            lines.append("- ...")
            break
        shown = ", ".join(str(v) for v in values[:20])
        lines.append(f"- {table}.{column}: {shown}")
    return "\n".join(lines) if lines else "(none detected)"


def _build_planner_prompt(user_request: str, ctx: RouterContext) -> str:
    return f"""You are planning a safe Python data tool call for DIAD.

The Python tool path is multi-step:
1. choose one approved tool
2. choose the needed tables/columns/filters
3. DIAD validates the plan
4. DIAD prepares data using safe SQL
5. DIAD runs the approved Python function

Approved tools:
- bar_chart: grouped counts or grouped numeric aggregation
- histogram: distribution of one numeric column
- line_chart: x/y line chart
- scatter_plot: x/y scatter chart
- summary_stats: descriptive stats for numeric columns
- correlation_check: correlation between two numeric columns
- normalize_emails: add a normalized email column
- fuzzy_match: fuzzy match two explicit text columns
- deduplicate_rows: return duplicate rows using selected keys

Return JSON only, no markdown, in this shape:
{{
  "tool_name": "bar_chart | histogram | line_chart | scatter_plot | summary_stats | correlation_check | normalize_emails | fuzzy_match | deduplicate_rows",
  "tables": ["table_name"],
  "columns": ["column_name_or_table.column"],
  "x": "column_name_or_table.column or null",
  "y": "column_name_or_table.column or null",
  "aggregation": "count | avg | sum | min | max",
  "filters": [{{"table": "table_name", "column": "column_name", "value": "exact categorical value"}}],
  "left": "table.column for fuzzy_match or null",
  "right": "table.column for fuzzy_match or null",
  "dedupe_keys": ["column_name_or_table.column"],
  "threshold": 0.85,
  "reason": "brief reason"
}}

Rules:
- Do not invent tables, columns, or values.
- For categorical filters, use the exact values shown in the categorical values section.
- For charts like "employees by department", use bar_chart with x=department and aggregation=count.
- For charts like "average salary by department", use bar_chart with x=department, y=salary_usd, aggregation=avg.
- Use null for fields that do not apply.

Schema:
{_build_schema_summary(ctx)}

Categorical values:
{_build_categorical_summary(ctx)}

User request:
{user_request}

JSON:"""


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_plan(user_request: str, ctx: RouterContext) -> dict[str, Any] | None:
    model = os.getenv("DIAD_PYTHON_PLANNER_MODEL", os.getenv("DIAD_ROUTER_MODEL", "llama3.2"))
    prompt = _build_planner_prompt(user_request, ctx)
    try:
        raw = ollama_generate(model, prompt)
    except Exception:
        return None
    data = _extract_json_object(raw)
    if not data:
        return None
    data["_raw_llm_output"] = raw
    data["_planner_model"] = model
    return data


def _deterministic_plan(user_request: str, ctx: RouterContext) -> dict[str, Any]:
    tool_name = _coerce_tool_name(None, user_request) or "bar_chart"
    columns = _find_columns_in_query(user_request, ctx)
    filters = _infer_filters(user_request, ctx)
    x, y, aggregation = _choose_chart_axes(user_request, ctx, tool_name)
    explicit_refs = _extract_explicit_refs(user_request, ctx)

    plan: dict[str, Any] = {
        "tool_name": tool_name,
        "tables": [],
        "columns": [f"{ref.table}.{ref.column}" for ref in columns],
        "x": f"{x.table}.{x.column}" if x else None,
        "y": f"{y.table}.{y.column}" if y else None,
        "aggregation": aggregation,
        "filters": [filter_spec.__dict__ for filter_spec in filters],
        "left": None,
        "right": None,
        "dedupe_keys": [],
        "threshold": _parse_threshold(user_request),
        "reason": "Planned with deterministic Python tool heuristics.",
    }

    if tool_name == "normalize_emails":
        email_cols = [ref for ref in columns if "email" in ref.column.lower()]
        if not email_cols:
            for ref in _schema_entries(ctx):
                if "email" in ref.column.lower():
                    email_cols.append(ref)
        if email_cols:
            plan["columns"] = [f"{email_cols[0].table}.{email_cols[0].column}"]

    if tool_name == "fuzzy_match":
        refs = explicit_refs or columns
        if len(refs) >= 2:
            plan["left"] = f"{refs[0].table}.{refs[0].column}"
            plan["right"] = f"{refs[1].table}.{refs[1].column}"

    if tool_name == "deduplicate_rows":
        refs = explicit_refs or columns
        if refs:
            plan["dedupe_keys"] = [f"{ref.table}.{ref.column}" for ref in refs[:3]]
        else:
            for hint in ["employee_id", "email", "full_name"]:
                ref = _resolve_column_ref(hint, ctx)
                if ref:
                    plan["dedupe_keys"] = [f"{ref.table}.{ref.column}"]
                    break

    return plan


def _tables_from_refs(refs: list[ColumnRef]) -> list[str]:
    tables: list[str] = []
    for ref in refs:
        if ref.table not in tables:
            tables.append(ref.table)
    return tables


def _validate_plan_dict(plan_dict: dict[str, Any], user_request: str, ctx: RouterContext) -> PythonToolPlan:
    tool_name = _coerce_tool_name(plan_dict.get("tool_name"), user_request)
    if tool_name not in SUPPORTED_TOOLS:
        raise ValueError(
            "I could not map that request to a supported Python tool. Try asking for a chart, histogram, summary stats, correlation, fuzzy match, email normalization, or duplicate check."
        )

    raw_tables = plan_dict.get("tables") or []
    if isinstance(raw_tables, str):
        raw_tables = [raw_tables]
    tables: list[str] = []
    for raw_table in raw_tables:
        table = _resolve_table(raw_table, ctx)
        if table and table not in tables:
            tables.append(table)

    def resolve_with_tables(raw: Any) -> ColumnRef | None:
        return _resolve_column_ref(raw, ctx, allowed_tables=tables or None)

    columns: list[ColumnRef] = []
    raw_columns = plan_dict.get("columns") or []
    if isinstance(raw_columns, str):
        raw_columns = [raw_columns]
    for raw_col in raw_columns:
        ref = resolve_with_tables(raw_col)
        if ref and ref not in columns:
            columns.append(ref)

    x = resolve_with_tables(plan_dict.get("x"))
    y = resolve_with_tables(plan_dict.get("y"))

    aggregation = str(plan_dict.get("aggregation") or "count").strip().lower()
    aggregation = {"average": "avg", "mean": "avg", "total": "sum"}.get(aggregation, aggregation)
    if aggregation not in AGGREGATIONS:
        aggregation = "count"

    raw_filter_specs: list[FilterSpec] = []
    raw_filters = plan_dict.get("filters") or []
    if not isinstance(raw_filters, list):
        raw_filters = []
    for item in raw_filters:
        if not isinstance(item, dict):
            continue
        table = _resolve_table(item.get("table"), ctx)
        column_ref = _resolve_column_ref(item.get("column"), ctx, preferred_table=table)
        value = str(item.get("value") or "").strip()
        if column_ref and value:
            raw_filter_specs.append(FilterSpec(column_ref.table, column_ref.column, value))

    # LLM filters are never trusted blindly. Only keep filters that are clearly
    # grounded in the user request, then add exact deterministic filters.
    filters = _merge_supported_filters(user_request, ctx, raw_filter_specs)

    left = resolve_with_tables(plan_dict.get("left"))
    right = resolve_with_tables(plan_dict.get("right"))

    dedupe_keys: list[ColumnRef] = []
    raw_keys = plan_dict.get("dedupe_keys") or []
    if isinstance(raw_keys, str):
        raw_keys = [raw_keys]
    for raw_key in raw_keys:
        ref = resolve_with_tables(raw_key)
        if ref and ref not in dedupe_keys:
            dedupe_keys.append(ref)

    refs_for_tables = columns + [r for r in [x, y, left, right] if r is not None] + dedupe_keys
    refs_for_tables.extend(ColumnRef(f.table, f.column) for f in filters)
    for table in _tables_from_refs(refs_for_tables):
        if table not in tables:
            tables.append(table)

    # Tool-specific defaults and validation.
    if tool_name in {"bar_chart", "line_chart", "scatter_plot", "histogram"}:
        # Prefer deterministic axis/aggregation choices for charts. The LLM can still
        # help with tool selection, but chart axes and filters should be driven by the
        # user's actual words so a generic chart does not silently become filtered.
        det_x, det_y, det_agg = _choose_chart_axes(user_request, ctx, tool_name)
        if det_x is not None:
            x = det_x
        if det_y is not None:
            y = det_y
        if det_agg:
            aggregation = det_agg

        # Important repair: recompute chart tables AFTER choosing deterministic axes.
        # The LLM may plan tables=["compensation"] for "average salary by department"
        # because salary lives there, while the x-axis department lives in hr_data.
        # If we keep the stale table list, the prepared dataframe lacks the x-axis and
        # chart creation fails with "Chart needs a valid x-axis column." For charts,
        # the required tables are exactly the tables used by x/y plus any real filters.
        chart_refs = [ref for ref in [x, y] if ref is not None]
        chart_refs.extend(ColumnRef(f.table, f.column) for f in filters)
        chart_tables = _tables_from_refs(chart_refs)
        if chart_tables:
            tables = chart_tables

        if tool_name == "histogram" and y is None:
            raise ValueError("A histogram needs one numeric column. Try something like 'create a histogram of salary_usd'.")
        if tool_name in {"bar_chart", "line_chart", "scatter_plot"} and x is None:
            raise ValueError("That chart needs a clear x-axis column. Try something like 'bar chart of employees by department'.")
        if tool_name in {"line_chart", "scatter_plot"} and y is None:
            raise ValueError("That chart needs a clear y-axis column.")

    if tool_name == "summary_stats":
        if not columns:
            numeric_refs = [ref for ref in _schema_entries(ctx) if _is_numeric_ref(ref, ctx)]
            columns = numeric_refs[:8]
        if not columns:
            raise ValueError("I could not find numeric columns to summarize.")

    if tool_name == "correlation_check":
        if len(columns) < 2:
            numeric_refs = [ref for ref in _find_columns_in_query(user_request, ctx) if _is_numeric_ref(ref, ctx)]
            columns = numeric_refs
        if len(columns) < 2:
            raise ValueError("Correlation needs two numeric columns. Try 'find correlation between salary_usd and rating'.")
        x = x or columns[0]
        y = y or columns[1]

    if tool_name == "normalize_emails":
        email_refs = [ref for ref in columns if "email" in ref.column.lower()]
        if not email_refs:
            email_refs = [ref for ref in _schema_entries(ctx) if "email" in ref.column.lower()]
        if len(email_refs) != 1:
            raise ValueError("Please specify one email column to normalize, like hr_data.email.")
        columns = [email_refs[0]]
        tables = [email_refs[0].table]

    if tool_name == "fuzzy_match":
        if left is None or right is None:
            refs = _extract_explicit_refs(user_request, ctx)
            if len(refs) >= 2:
                left, right = refs[0], refs[1]
        if left is None or right is None:
            raise ValueError("For fuzzy matching, specify two columns like 'fuzzy match hr_data.full_name with performance_reviews.full_name'.")
        tables = _tables_from_refs([left, right])

    if tool_name == "deduplicate_rows":
        if not dedupe_keys:
            for hint in ["employee_id", "email", "full_name", "id"]:
                ref = _resolve_column_ref(hint, ctx, allowed_tables=tables or None)
                if ref:
                    dedupe_keys = [ref]
                    break
        if not dedupe_keys:
            raise ValueError("Please specify which column or columns to use for duplicate detection.")
        tables = _tables_from_refs(dedupe_keys)

    # Final safety sync: if tool-specific validation changed important refs,
    # make sure the prepared-data SQL includes the tables needed for those refs.
    final_refs = columns + [r for r in [x, y, left, right] if r is not None] + dedupe_keys
    final_refs.extend(ColumnRef(f.table, f.column) for f in filters)
    final_tables = _tables_from_refs(final_refs)
    if tool_name in {"bar_chart", "histogram", "line_chart", "scatter_plot", "summary_stats", "correlation_check"} and final_tables:
        tables = final_tables
    elif not tables and final_tables:
        tables = final_tables

    return PythonToolPlan(
        tool_name=tool_name,
        tables=tables,
        columns=columns,
        filters=filters,
        x=x,
        y=y,
        aggregation=aggregation,
        threshold=_parse_threshold(user_request, float(plan_dict.get("threshold") or 0.85)),
        left=left,
        right=right,
        dedupe_keys=dedupe_keys,
        reason=str(plan_dict.get("reason") or "Planned Python tool call.").strip(),
        raw_plan=plan_dict,
    )


def plan_python_tool(user_request: str, ctx: RouterContext) -> PythonToolPlan:
    # Use deterministic planning first so the common path remains fast and reliable.
    deterministic = _deterministic_plan(user_request, ctx)

    # Let the LLM improve the plan if available. If it fails or returns junk, the deterministic
    # plan is still used.
    llm = _llm_plan(user_request, ctx)
    plan_dict = llm or deterministic

    try:
        return _validate_plan_dict(plan_dict, user_request, ctx)
    except Exception:
        # One retry with deterministic fallback is useful if the LLM picked a bad field.
        return _validate_plan_dict(deterministic, user_request, ctx)


def canonicalize_email(value: Any) -> str:
    email = _normalize(value)
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if domain == "googlemail.com":
        domain = "gmail.com"
    if domain == "gmail.com":
        local = local.split("+", 1)[0]
        local = local.replace(".", "")
    return f"{local}@{domain}"


def normalize_emails_in_dataframe(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        raise KeyError(f"Column '{column}' was not found in the dataframe.")
    result = df.copy()
    result[f"{column}__normalized"] = result[column].map(canonicalize_email)
    return result


def fuzzy_match_dataframes(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    left_on: str,
    right_on: str,
    threshold: float = 0.85,
) -> pd.DataFrame:
    if left_on not in left_df.columns:
        raise KeyError(f"Left column '{left_on}' was not found.")
    if right_on not in right_df.columns:
        raise KeyError(f"Right column '{right_on}' was not found.")

    threshold = threshold / 100.0 if threshold > 1 else threshold
    threshold = max(0.0, min(1.0, threshold))

    right_candidates: list[tuple[int, str, Any]] = []
    for idx, value in right_df[right_on].items():
        norm = _normalize(value)
        if norm:
            right_candidates.append((int(idx), norm, value))

    rows: list[dict[str, Any]] = []
    for left_idx, left_row in left_df.iterrows():
        left_value = left_row[left_on]
        left_norm = _normalize(left_value)
        best_score = 0.0
        best_right_idx: int | None = None
        best_right_value: Any = None

        if left_norm:
            for candidate_idx, right_norm, raw_right in right_candidates:
                score = SequenceMatcher(None, left_norm, right_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_right_idx = candidate_idx
                    best_right_value = raw_right

        matched = best_right_idx is not None and best_score >= threshold
        record: dict[str, Any] = {
            "left_index": left_idx,
            "left_value": left_value,
            "matched": matched,
            "match_score": round(best_score, 4),
            "right_index": best_right_idx if matched else None,
            "right_value": best_right_value if matched else None,
        }
        for col_name in left_df.columns:
            record[f"left_{col_name}"] = left_row[col_name]
        if matched and best_right_idx is not None:
            right_row = right_df.loc[best_right_idx]
            for col_name in right_df.columns:
                record[f"right_{col_name}"] = right_row[col_name]
        rows.append(record)

    return pd.DataFrame(rows)


def _fetch_table_df(con, table_name: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {_quote_ident(table_name)}").df()


def _find_join_key(ctx: RouterContext, left_table: str, right_table: str) -> tuple[str, str] | None:
    left_cols = ctx.schema_map.get(left_table, {})
    right_cols = ctx.schema_map.get(right_table, {})
    left_lower = {col.lower(): col for col in left_cols.keys()}
    right_lower = {col.lower(): col for col in right_cols.keys()}

    for key in PREFERRED_JOIN_KEYS:
        if key in left_lower and key in right_lower:
            return left_lower[key], right_lower[key]

    for left_col in left_cols.keys():
        for right_col in right_cols.keys():
            if left_col.lower() == right_col.lower():
                return left_col, right_col

    return None


def _refs_for_plan(plan: PythonToolPlan) -> list[ColumnRef]:
    refs: list[ColumnRef] = []
    for ref in plan.columns:
        refs.append(ref)
    for ref in [plan.x, plan.y, plan.left, plan.right]:
        if ref:
            refs.append(ref)
    refs.extend(plan.dedupe_keys)
    refs.extend(ColumnRef(f.table, f.column) for f in plan.filters)

    out: list[ColumnRef] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref.table, ref.column)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def _build_prepared_dataframe(ctx: RouterContext, plan: PythonToolPlan) -> tuple[pd.DataFrame, str, dict[tuple[str, str], str]]:
    refs = _refs_for_plan(plan)
    tables = plan.tables or _tables_from_refs(refs)
    if not tables:
        if len(ctx.schema_map) == 1:
            tables = [next(iter(ctx.schema_map.keys()))]
        else:
            raise ValueError("I need a clear table to prepare data for this tool.")

    # For single table tools with no specific refs, include the full table.
    if not refs and len(tables) == 1:
        refs = [ColumnRef(tables[0], col) for col in ctx.schema_map.get(tables[0], {}).keys()]

    aliases = {table: f"t{idx}" for idx, table in enumerate(tables)}

    select_parts: list[str] = []
    alias_map: dict[tuple[str, str], str] = {}
    for ref in refs:
        if ref.table not in aliases:
            continue
        out_alias = ref.alias
        alias_map[(ref.table, ref.column)] = out_alias
        select_parts.append(f'{aliases[ref.table]}.{_quote_ident(ref.column)} AS {_quote_ident(out_alias)}')

    if not select_parts:
        select_parts.append(f"{aliases[tables[0]]}.*")

    sql_parts = [f"SELECT DISTINCT {', '.join(select_parts)}", f"FROM {_quote_ident(tables[0])} {aliases[tables[0]]}"]

    for table in tables[1:]:
        join_key = _find_join_key(ctx, tables[0], table)
        if join_key is None:
            raise ValueError(f'I could not find a safe join key between "{tables[0]}" and "{table}".')
        left_col, right_col = join_key
        sql_parts.append(
            f"JOIN {_quote_ident(table)} {aliases[table]} ON "
            f"lower(trim(cast({aliases[tables[0]]}.{_quote_ident(left_col)} AS varchar))) = "
            f"lower(trim(cast({aliases[table]}.{_quote_ident(right_col)} AS varchar)))"
        )

    params: list[Any] = []
    where_parts: list[str] = []
    for f in plan.filters:
        if f.table not in aliases:
            continue
        where_parts.append(f"lower(trim(cast({aliases[f.table]}.{_quote_ident(f.column)} AS varchar))) = lower(trim(cast(? AS varchar)))")
        params.append(f.value)

    if where_parts:
        sql_parts.append("WHERE " + " AND ".join(where_parts))

    sql = "\n".join(sql_parts)
    df = ctx.con.execute(sql, params).df()
    return df, sql, alias_map


def _alias_for(ref: ColumnRef | None, alias_map: dict[tuple[str, str], str]) -> str | None:
    if ref is None:
        return None
    return alias_map.get((ref.table, ref.column), ref.alias)


def _make_chart(plan: PythonToolPlan, df: pd.DataFrame, alias_map: dict[tuple[str, str], str], output_dir: str) -> tuple[str, pd.DataFrame]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for chart creation.") from exc

    if df.empty:
        raise ValueError("Cannot create a chart because the prepared data has no rows.")

    os.makedirs(output_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(output_dir, f"{plan.tool_name}_{stamp}_{uuid.uuid4().hex[:8]}.png")

    if plan.tool_name == "histogram":
        y_col = _alias_for(plan.y, alias_map)
        if not y_col or y_col not in df.columns:
            raise ValueError("Histogram needs a valid numeric column.")
        series = pd.to_numeric(df[y_col], errors="coerce").dropna()
        if series.empty:
            raise ValueError("The selected histogram column does not contain numeric values.")
        chart_df = pd.DataFrame({plan.y.column: series})
        plt.figure(figsize=(10, 6))
        plt.hist(series, bins=20)
        plt.xlabel(plan.y.column)
        plt.ylabel("Count")
        plt.title(f"Histogram of {plan.y.column}")
        plt.tight_layout()
        plt.savefig(file_path, dpi=150)
        plt.close()
        return file_path, chart_df

    x_col = _alias_for(plan.x, alias_map)
    y_col = _alias_for(plan.y, alias_map)
    if not x_col or x_col not in df.columns:
        raise ValueError("Chart needs a valid x-axis column.")

    if plan.aggregation == "count":
        grouped = df.groupby(x_col, dropna=False).size().reset_index(name="count")
        grouped = grouped.sort_values("count", ascending=False).head(30)
        display_x = plan.x.column if plan.x else x_col
        chart_df = grouped.rename(columns={x_col: display_x})
        plt.figure(figsize=(10, 6))
        plt.bar(chart_df[display_x].astype(str).tolist(), chart_df["count"].tolist())
        plt.xlabel(display_x)
        plt.ylabel("Count")
        plt.title(f"Count by {display_x}")
        plt.xticks(rotation=45, ha="right")
    else:
        if y_col is None:
            raise ValueError(
                f"This chart asked for {plan.aggregation}, but I could not find the numeric column to aggregate. "
                "Try naming the numeric field directly, like salary_usd or rating."
            )
        if y_col not in df.columns:
            raise ValueError("Chart needs a valid y-axis column.")
        work = df[[x_col, y_col]].copy()
        work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
        work = work.dropna(subset=[y_col])
        if work.empty:
            raise ValueError("The selected y-axis column does not contain numeric values.")

        if plan.aggregation == "avg":
            grouped = work.groupby(x_col, dropna=False)[y_col].mean().reset_index(name=f"avg_{plan.y.column}")
            y_display = f"Average {plan.y.column}"
            y_out = f"avg_{plan.y.column}"
        elif plan.aggregation == "sum":
            grouped = work.groupby(x_col, dropna=False)[y_col].sum().reset_index(name=f"sum_{plan.y.column}")
            y_display = f"Sum of {plan.y.column}"
            y_out = f"sum_{plan.y.column}"
        elif plan.aggregation == "min":
            grouped = work.groupby(x_col, dropna=False)[y_col].min().reset_index(name=f"min_{plan.y.column}")
            y_display = f"Minimum {plan.y.column}"
            y_out = f"min_{plan.y.column}"
        else:
            grouped = work.groupby(x_col, dropna=False)[y_col].max().reset_index(name=f"max_{plan.y.column}")
            y_display = f"Maximum {plan.y.column}"
            y_out = f"max_{plan.y.column}"

        grouped = grouped.sort_values(y_out, ascending=False).head(30)
        display_x = plan.x.column if plan.x else x_col
        chart_df = grouped.rename(columns={x_col: display_x})
        plt.figure(figsize=(10, 6))
        if plan.tool_name == "line_chart":
            plt.plot(chart_df[display_x].astype(str).tolist(), chart_df[y_out].tolist())
        elif plan.tool_name == "scatter_plot":
            plt.scatter(chart_df[display_x].astype(str).tolist(), chart_df[y_out].tolist())
        else:
            plt.bar(chart_df[display_x].astype(str).tolist(), chart_df[y_out].tolist())
        plt.xlabel(display_x)
        plt.ylabel(y_display)
        plt.title(f"{y_display} by {display_x}")
        plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(file_path, dpi=150)
    plt.close()
    return file_path, chart_df


def _summary_stats(plan: PythonToolPlan, df: pd.DataFrame, alias_map: dict[tuple[str, str], str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    refs = plan.columns or [ColumnRef(table, col) for table, cols in [] for col in cols]
    target_cols = [_alias_for(ref, alias_map) for ref in refs]
    if not target_cols:
        target_cols = list(df.columns)

    for col in target_cols:
        if not col or col not in df.columns:
            continue
        series = df[col]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() == 0:
            continue
        rows.append(
            {
                "column": col.split("__", 1)[-1],
                "count": int(numeric.notna().sum()),
                "missing": int(series.isna().sum()),
                "mean": round(float(numeric.mean()), 4),
                "median": round(float(numeric.median()), 4),
                "min": round(float(numeric.min()), 4),
                "max": round(float(numeric.max()), 4),
                "std": round(float(numeric.std()), 4) if numeric.notna().sum() > 1 else None,
            }
        )
    return pd.DataFrame(rows)


def _correlation_check(plan: PythonToolPlan, df: pd.DataFrame, alias_map: dict[tuple[str, str], str]) -> pd.DataFrame:
    x_col = _alias_for(plan.x, alias_map)
    y_col = _alias_for(plan.y, alias_map)
    if not x_col or not y_col or x_col not in df.columns or y_col not in df.columns:
        raise ValueError("Correlation needs two valid numeric columns.")
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    work = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(work) < 2:
        raise ValueError("Not enough numeric rows to calculate correlation.")
    corr = float(work["x"].corr(work["y"]))
    return pd.DataFrame(
        [
            {
                "x_column": plan.x.column if plan.x else x_col,
                "y_column": plan.y.column if plan.y else y_col,
                "rows_used": len(work),
                "correlation": round(corr, 4),
            }
        ]
    )


def _deduplicate_rows(plan: PythonToolPlan, ctx: RouterContext) -> tuple[pd.DataFrame, str]:
    table = plan.dedupe_keys[0].table
    df = _fetch_table_df(ctx.con, table)
    keys = [ref.column for ref in plan.dedupe_keys if ref.table == table]
    if not keys:
        raise ValueError("Duplicate detection keys must come from one table for now.")
    duplicate_mask = df.duplicated(subset=keys, keep=False)
    out = df.loc[duplicate_mask].sort_values(keys).reset_index(drop=True)
    return out, f"Checked duplicates in {table} using: {', '.join(keys)}"


def _plan_metadata(plan: PythonToolPlan, prep_sql: str | None = None) -> dict[str, Any]:
    return {
        "tool_plan": {
            "tool_name": plan.tool_name,
            "tables": plan.tables,
            "columns": [f"{ref.table}.{ref.column}" for ref in plan.columns],
            "filters": [filter_spec.__dict__ for filter_spec in plan.filters],
            "x": f"{plan.x.table}.{plan.x.column}" if plan.x else None,
            "y": f"{plan.y.table}.{plan.y.column}" if plan.y else None,
            "aggregation": plan.aggregation,
            "left": f"{plan.left.table}.{plan.left.column}" if plan.left else None,
            "right": f"{plan.right.table}.{plan.right.column}" if plan.right else None,
            "dedupe_keys": [f"{ref.table}.{ref.column}" for ref in plan.dedupe_keys],
            "threshold": plan.threshold,
            "reason": plan.reason,
        },
        "prepared_sql": prep_sql,
        "python_tool_multistep": True,
    }


def run_python_tool(user_request: str, ctx: RouterContext) -> RouterResult:
    try:
        plan = plan_python_tool(user_request, ctx)
    except Exception as exc:
        return RouterResult(
            route=RouteName.PYTHON_TOOL,
            ok=False,
            message=str(exc),
            reason="Python tool planning failed.",
            error=str(exc),
            tool_name=None,
            metadata={"python_tool_multistep": True, "planning_error": str(exc)},
        ).with_query(user_request)

    try:
        if plan.tool_name == "normalize_emails":
            ref = plan.columns[0]
            df = _fetch_table_df(ctx.con, ref.table)
            result_df = normalize_emails_in_dataframe(df, ref.column)
            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f'I normalized the email values in "{ref.table}"."{ref.column}" and added "{ref.column}__normalized".',
                reason=plan.reason,
                dataframe=result_df,
                metadata={**_plan_metadata(plan), "row_count": len(result_df)},
                tool_name=plan.tool_name,
            ).with_query(user_request)

        if plan.tool_name == "fuzzy_match":
            assert plan.left is not None and plan.right is not None
            left_df = _fetch_table_df(ctx.con, plan.left.table)
            right_df = _fetch_table_df(ctx.con, plan.right.table)
            match_df = fuzzy_match_dataframes(left_df, right_df, plan.left.column, plan.right.column, plan.threshold)
            matched_count = int(match_df["matched"].sum()) if "matched" in match_df.columns else 0
            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=(
                    f'I fuzzy matched "{plan.left.table}"."{plan.left.column}" against '
                    f'"{plan.right.table}"."{plan.right.column}" at threshold {plan.threshold:.2f}. '
                    f"{matched_count} row(s) matched."
                ),
                reason=plan.reason,
                dataframe=match_df,
                metadata={**_plan_metadata(plan), "row_count": len(match_df), "matched_count": matched_count},
                tool_name=plan.tool_name,
            ).with_query(user_request)

        if plan.tool_name == "deduplicate_rows":
            result_df, detail = _deduplicate_rows(plan, ctx)
            duplicate_count = len(result_df)
            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f"{detail}. I found {duplicate_count} duplicate row(s)." if duplicate_count else f"{detail}. I did not find duplicate rows.",
                reason=plan.reason,
                dataframe=result_df,
                metadata={**_plan_metadata(plan), "row_count": duplicate_count},
                tool_name=plan.tool_name,
            ).with_query(user_request)

        df, prep_sql, alias_map = _build_prepared_dataframe(ctx, plan)

        if plan.tool_name in {"bar_chart", "histogram", "line_chart", "scatter_plot"}:
            output_path, chart_df = _make_chart(plan, df, alias_map, ctx.output_dir)
            chart_desc = _readable_tool_name(plan.tool_name)
            if plan.tool_name == "bar_chart" and plan.x:
                if plan.aggregation == "count" or not plan.y:
                    chart_desc = f"bar chart of counts by {plan.x.column}"
                else:
                    chart_desc = f"bar chart of {plan.aggregation} {plan.y.column} by {plan.x.column}"
            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f"I created a {chart_desc}. Chart file: {output_path}",
                reason=plan.reason,
                dataframe=chart_df,
                output_path=output_path,
                metadata={**_plan_metadata(plan, prep_sql), "row_count": len(chart_df), "chart_path": output_path},
                tool_name=plan.tool_name,
            ).with_query(user_request)

        if plan.tool_name == "summary_stats":
            stats_df = _summary_stats(plan, df, alias_map)
            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f"I calculated summary statistics for {len(stats_df)} numeric column(s).",
                reason=plan.reason,
                dataframe=stats_df,
                metadata={**_plan_metadata(plan, prep_sql), "row_count": len(stats_df)},
                tool_name=plan.tool_name,
            ).with_query(user_request)

        if plan.tool_name == "correlation_check":
            corr_df = _correlation_check(plan, df, alias_map)
            corr = corr_df.iloc[0]["correlation"] if not corr_df.empty else None
            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f"I calculated the correlation. Correlation: {corr}",
                reason=plan.reason,
                dataframe=corr_df,
                metadata={**_plan_metadata(plan, prep_sql), "row_count": len(corr_df)},
                tool_name=plan.tool_name,
            ).with_query(user_request)

        raise ValueError(f"Unsupported Python tool: {plan.tool_name}")

    except Exception as exc:
        return RouterResult(
            route=RouteName.PYTHON_TOOL,
            ok=False,
            message=f"Python tool execution failed: {exc}",
            reason="The Python tool was planned, but execution failed.",
            error=str(exc),
            metadata={**_plan_metadata(plan), "execution_error": str(exc)},
            tool_name=plan.tool_name,
        ).with_query(user_request)
