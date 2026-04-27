from __future__ import annotations

import json
import os
import re
from typing import Optional, Any

from .data_questions import answer_data_question
from .llm import ollama_generate
from .python_tools import run_python_tool
from .router_types import RouteDecision, RouteName, RouterContext, RouterResult
from .schema_aliases import ground_user_query
from .sql_flow import run_sql_query

DEFAULT_ROUTER_MODEL = os.getenv("DIAD_ROUTER_MODEL", "llama3.2")
SUPPORTED_PYTHON_TOOLS = {
    "bar_chart",
    "histogram",
    "line_chart",
    "scatter_plot",
    "summary_stats",
    "correlation_check",
    "normalize_emails",
    "fuzzy_match",
    "deduplicate_rows",
    # Backward-compatible name used by older router prompts/rules.
    "create_graph",
}

DATA_QUESTION_PATTERNS = [
    r"\bschema\b",
    r"\bshow\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?tables?(?:\s+(?:i|we)\s+(?:uploaded|loaded))?\b",
    r"\bshow\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?(?:uploaded|loaded)\s+tables?\b",
    r"\blist\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?tables?(?:\s+(?:i|we)\s+(?:uploaded|loaded))?\b",
    r"\blist\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?(?:uploaded|loaded)\s+tables?\b",
    r"\bwhat\s+(?:are\s+)?(?:all\s+)?(?:the\s+)?tables?(?:\s+(?:i|we)\s+(?:uploaded|loaded))?\b",
    r"\bwhich\s+(?:tables?|files?)\s+(?:are\s+)?(?:uploaded|loaded)\b",
    r"\bwhich\s+tables?\b",
    r"\btable\s+names?\b",
    r"\bwhat\s+(?:data|files?)\s+(?:is|are)\s+(?:loaded|uploaded)\b",
    r"\bwhat is loaded\b",
    r"\bloaded data\b",
    r"\bloaded files?\b",
    r"\buploaded files?\b",
    r"\bshow\s+(?:me\s+)?(?:the\s+)?schema\b",
    r"\bshow\s+(?:me\s+)?(?:the\s+)?columns?\b",
    r"\blist\s+(?:the\s+)?columns?\b",
    r"\bwhat\s+(?:are\s+)?(?:the\s+)?columns?\b",
    r"\bwhich\s+columns?\b",
    r"\bheaders?\b",
    r"\bfields?\b",
    r"\bpossible values?\b",
    r"\bdistinct values?\b",
    r"\bwhat values?\b",
    r"\bwhich table\b",
    r"\bwhat table\b",
    r"\bwhat does .* column mean\b",
]

PYTHON_TOOL_RULES = {
    "normalize_emails": [
        "normalize email",
        "normalize emails",
        "canonicalize email",
        "canonicalize emails",
        "standardize email",
        "clean email",
        "clean emails",
    ],
    "fuzzy_match": [
        "fuzzy match",
        "approximate match",
        "similarity",
        "similar names",
        "similar emails",
        "match similar",
    ],
    "deduplicate_rows": [
        "deduplicate",
        "dedupe",
        "duplicate rows",
        "find duplicates",
        "duplicate emails",
        "duplicate employees",
    ],
    "summary_stats": [
        "summary stats",
        "summary statistics",
        "descriptive stats",
        "descriptive statistics",
        "statistics for",
        "stats for",
    ],
    "correlation_check": [
        "correlation",
        "correlate",
        "relationship between",
    ],
    "histogram": [
        "histogram",
        "distribution",
    ],
    "scatter_plot": [
        "scatter",
        "scatter plot",
    ],
    "line_chart": [
        "line chart",
        "line graph",
    ],
    "bar_chart": [
        "graph",
        "plot",
        "chart",
        "visualize",
        "visualise",
        "bar chart",
        "bar graph",
    ],
}

DATA_ACTION_WORDS = {
    "show",
    "list",
    "find",
    "count",
    "sum",
    "avg",
    "average",
    "group",
    "filter",
    "sort",
    "top",
    "bottom",
    "distinct",
    "rows",
    "records",
    "join",
    "compare",
    "where",
    "total",
    "highest",
    "lowest",
    "employees",
    "employee",
    "people",
}

_TABLE_STOPWORDS = {"test", "export", "sheet", "sheet1", "sheet2", "sheet3", "table", "data"}
_STOPWORDS = {
    "the", "a", "an", "for", "of", "to", "in", "on", "with", "from", "by", "and", "or",
    "is", "are", "was", "were", "be", "been", "being", "as", "at", "into", "all", "me",
    "find", "show", "list", "give", "who", "that", "employees", "employee", "people", "users", "user",
}

_COLUMN_HINTS = {
    "role": {"role"},
    "team": {"team", "department", "dept", "group"},
    "department": {"department", "dept", "team"},
    "status": {"status", "state"},
    "email": {"email", "mail"},
    "work_mode": {"work mode", "remote", "office", "in office", "hybrid"},
}


def _normalize(text: str) -> str:
    text = str(text or "").strip().lower()
    text = text.replace("__", " ").replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9@. /]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_exact_term(text: str, term: str) -> bool:
    text_n = _normalize(text)
    term_n = _normalize(term)
    if not text_n or not term_n:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(term_n)}(?![a-z0-9])", text_n) is not None


def _table_keywords(table_name: str) -> list[str]:
    tokens = re.split(r"[^a-zA-Z0-9]+", table_name.lower())
    out: list[str] = []
    for token in tokens:
        if token and token not in _TABLE_STOPWORDS and token not in out:
            out.append(token)
    return out


def _infer_mentioned_tables(query: str, ctx: RouterContext) -> list[str]:
    normalized_query = _normalize(query)
    matches: list[tuple[str, int]] = []
    for table_name in ctx.schema_map.keys():
        score = 0
        if _contains_exact_term(normalized_query, table_name.lower()):
            score += 10
        for part in _table_keywords(table_name):
            if _contains_exact_term(normalized_query, part):
                if part in {"notion", "okta", "hr"}:
                    score += 4
                else:
                    score += 2
        if score > 0:
            matches.append((table_name, score))
    matches.sort(key=lambda x: (-x[1], x[0]))
    return [table_name for table_name, _ in matches]


def _schema_terms(ctx: RouterContext) -> set[str]:
    terms: set[str] = set()
    for table_name, cols in ctx.schema_map.items():
        terms.add(table_name.lower())
        for col_name in cols.keys():
            terms.add(col_name.lower())
            terms.add(col_name.lower().replace("_", " "))
    return {term for term in terms if len(term) > 1}


def _contains_schema_reference(query: str, ctx: RouterContext) -> bool:
    normalized_query = _normalize(query)
    for term in _schema_terms(ctx):
        if _contains_exact_term(normalized_query, term):
            return True
    return False


def _is_table_list_request(normalized_query: str) -> bool:
    patterns = [
        r"\bshow\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?tables?(?:\s+(?:i|we)\s+(?:uploaded|loaded))?\b",
        r"\bshow\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?(?:uploaded|loaded)\s+tables?\b",
        r"\blist\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?tables?(?:\s+(?:i|we)\s+(?:uploaded|loaded))?\b",
        r"\blist\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?(?:uploaded|loaded)\s+tables?\b",
        r"\bwhat\s+(?:are\s+)?(?:all\s+)?(?:the\s+)?tables?(?:\s+(?:i|we)\s+(?:uploaded|loaded))?\b",
        r"\bwhat\s+(?:tables?|files?)\s+(?:are\s+)?(?:loaded|uploaded)\b",
        r"\bwhich\s+(?:tables?|files?)\s+(?:are\s+)?(?:loaded|uploaded)\b",
        r"\btable\s+names?\b",
        r"\bloaded\s+(?:tables?|files?|data)\b",
        r"\buploaded\s+(?:tables?|files?|data)\b",
    ]
    return any(re.search(pattern, normalized_query) for pattern in patterns)


def _detect_data_question(query: str, ctx: RouterContext) -> Optional[str]:
    normalized_query = _normalize(query)

    if _is_table_list_request(normalized_query):
        return "Matched loaded-table metadata request."

    for pattern in DATA_QUESTION_PATTERNS:
        if re.search(pattern, normalized_query):
            return "Matched metadata-focused question pattern."

    if _contains_schema_reference(query, ctx) and any(
        phrase in normalized_query
        for phrase in [
            "what values",
            "possible values",
            "distinct values",
            "which table",
            "what table",
            "what columns",
            "which columns",
        ]
    ):
        return "Matched schema terms plus metadata wording."

    return None


def _detect_python_tool(query: str) -> tuple[Optional[str], Optional[str]]:
    normalized_query = _normalize(query)
    for tool_name, phrases in PYTHON_TOOL_RULES.items():
        if any(phrase in normalized_query for phrase in phrases):
            return tool_name, f"Matched supported Python tool phrase for {tool_name}."
    if ("normalize" in normalized_query or "canonicalize" in normalized_query) and "email" in normalized_query:
        return "normalize_emails", "Matched email normalization wording."
    return None, None


def _detect_out_of_scope(query: str, ctx: RouterContext) -> Optional[str]:
    normalized_query = _normalize(query)
    if _contains_schema_reference(query, ctx):
        return None
    tool_name, _ = _detect_python_tool(query)
    if tool_name is not None:
        return None
    if any(word in normalized_query.split() for word in DATA_ACTION_WORDS):
        return None
    if any(
        keyword in normalized_query
        for keyword in [
            "table",
            "column",
            "field",
            "row",
            "record",
            "dataset",
            "data",
            "file",
            "loaded",
            "value",
            "values",
        ]
    ):
        return None
    return "The request does not appear related to the loaded dataset or supported Python tools."


def _router_schema_summary(ctx: RouterContext) -> str:
    if not ctx.schema_map:
        return "(no schema loaded)"

    lines: list[str] = []
    for table_name, columns in sorted(ctx.schema_map.items()):
        column_bits = [f"{col_name} ({dtype})" for col_name, dtype in columns.items()]
        lines.append(f"- {table_name}: {', '.join(column_bits) if column_bits else '(no columns)'}")
    return "\n".join(lines)


def _router_source_files(ctx: RouterContext) -> str:
    files = [str(path) for path in getattr(ctx, "source_files", []) or []]
    return "\n".join(f"- {path}" for path in files) if files else "(none listed)"


def _build_llm_router_prompt(user_request: str, ctx: RouterContext) -> str:
    return f"""You are routing a user request for DIAD, a local data assistant.

Choose exactly one route:

DATA_QUESTION:
- The user asks about metadata, not actual data rows.
- Examples: tables loaded, files uploaded, schemas, columns, headers, table names, available fields, possible values, distinct categorical values, which table contains a column.

SQL_QUERY:
- The user wants to read, filter, join, count, group, sort, compare, or aggregate actual rows in the loaded data.
- Examples: find employees in Engineering, count employees by department, show salaries over 100000, list rows where status is inactive.

PYTHON_TOOL:
- The user asks for a supported non-SQL operation.
- Supported tools only: bar_chart, histogram, line_chart, scatter_plot, summary_stats, correlation_check, normalize_emails, fuzzy_match, deduplicate_rows.

OUT_OF_SCOPE:
- The request is not about the loaded data, its schema, or a supported Python tool.

Important rules:
- "show all tables", "show all the tables I uploaded", "what files did I add", and similar requests are DATA_QUESTION.
- "show all employees", "find users", "count rows", and similar requests are SQL_QUERY.
- If the user asks for a chart/graph/plot, choose PYTHON_TOOL with the best tool_name: bar_chart, histogram, line_chart, or scatter_plot. If the user asks for stats, correlation, duplicate checks, fuzzy matching, or email normalization, choose PYTHON_TOOL with that specific tool_name.
- Return JSON only. Do not include markdown.

Return exactly this shape:
{{
  "route": "DATA_QUESTION | SQL_QUERY | PYTHON_TOOL | OUT_OF_SCOPE",
  "reason": "short reason",
  "tool_name": null
}}

Loaded schema:
{_router_schema_summary(ctx)}

Loaded source files:
{_router_source_files(ctx)}

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


def _coerce_route_name(value: Any) -> RouteName | None:
    route_text = str(value or "").strip().upper()
    for route in RouteName:
        if route.value == route_text:
            return route
    return None


def _coerce_tool_name(value: Any, user_request: str) -> str | None:
    tool_text = str(value or "").strip().lower()
    alias_map = {
        "create_graph": "bar_chart",
        "graph": "bar_chart",
        "chart": "bar_chart",
        "plot": "bar_chart",
        "bar": "bar_chart",
        "bar_graph": "bar_chart",
        "hist": "histogram",
        "distribution": "histogram",
        "scatter": "scatter_plot",
        "line": "line_chart",
        "stats": "summary_stats",
        "statistics": "summary_stats",
        "summary": "summary_stats",
        "correlation": "correlation_check",
        "dedupe": "deduplicate_rows",
        "deduplicate": "deduplicate_rows",
    }
    tool_text = alias_map.get(tool_text, tool_text)
    if tool_text in SUPPORTED_PYTHON_TOOLS:
        return tool_text

    detected_tool, _reason = _detect_python_tool(user_request)
    return detected_tool


def _llm_route_decision(user_request: str, ctx: RouterContext) -> RouteDecision | None:
    model = os.getenv("DIAD_ROUTER_MODEL", DEFAULT_ROUTER_MODEL)
    prompt = _build_llm_router_prompt(user_request, ctx)

    try:
        raw = ollama_generate(model, prompt)
        data = _extract_json_object(raw)
    except Exception as exc:
        return RouteDecision(
            route=RouteName.SQL_QUERY,
            reason="LLM router failed; fell back to normal SQL/default routing.",
            metadata={
                "llm_router_used": False,
                "llm_router_model": model,
                "llm_router_error": str(exc),
            },
        )

    if not data:
        return RouteDecision(
            route=RouteName.SQL_QUERY,
            reason="LLM router returned invalid JSON; fell back to normal SQL/default routing.",
            metadata={
                "llm_router_used": False,
                "llm_router_model": model,
                "llm_router_raw_output": str(raw),
            },
        )

    route = _coerce_route_name(data.get("route"))
    if route is None:
        return RouteDecision(
            route=RouteName.SQL_QUERY,
            reason="LLM router returned an unknown route; fell back to normal SQL/default routing.",
            metadata={
                "llm_router_used": False,
                "llm_router_model": model,
                "llm_router_raw_output": str(raw),
            },
        )

    tool_name = None
    if route == RouteName.PYTHON_TOOL:
        tool_name = _coerce_tool_name(data.get("tool_name"), user_request)
        if tool_name is None:
            # Unsupported Python tool request should not silently run arbitrary code.
            route = RouteName.OUT_OF_SCOPE

    reason = str(data.get("reason") or "LLM router selected this route.").strip()
    return RouteDecision(
        route=route,
        reason=f"LLM router: {reason}",
        tool_name=tool_name,
        metadata={
            "llm_router_used": True,
            "llm_router_model": model,
            "llm_router_raw_output": str(raw),
        },
    )


def _looks_like_row_or_aggregate_request(query: str) -> bool:
    normalized_query = _normalize(query)
    if _is_table_list_request(normalized_query):
        return False

    words = set(normalized_query.split())
    row_nouns = {
        "employee", "employees", "user", "users", "person", "people", "row", "rows",
        "record", "records", "salary", "salaries", "compensation", "review", "reviews",
        "name", "names", "email", "emails",
    }
    sql_verbs = {
        "find", "show", "list", "give", "get", "count", "sum", "average", "avg",
        "group", "sort", "filter", "compare", "join", "top", "bottom", "highest", "lowest",
    }

    if words & row_nouns and words & sql_verbs:
        return True

    if any(phrase in normalized_query for phrase in ["how many", "group by", "order by", "greater than", "less than"]):
        return True

    return False


def _apply_route_safety_overrides(user_request: str, ctx: RouterContext, decision: RouteDecision) -> RouteDecision:
    # Hard metadata requests should never fall into SQL just because they contain "show" or "list".
    data_reason = _detect_data_question(user_request, ctx)
    if data_reason:
        return RouteDecision(
            route=RouteName.DATA_QUESTION,
            reason=f"Safety override: {data_reason}",
            metadata=decision.metadata,
        )

    # Hard Python tool requests should not be overwritten by the LLM router.
    tool_name, tool_reason = _detect_python_tool(user_request)
    if tool_name:
        return RouteDecision(
            route=RouteName.PYTHON_TOOL,
            reason=f"Safety override: {tool_reason or 'Matched supported Python tool.'}",
            tool_name=tool_name,
            metadata=decision.metadata,
        )

    # If the LLM calls an actual row/filter/aggregate request metadata, put it back on SQL.
    if decision.route == RouteName.DATA_QUESTION and _looks_like_row_or_aggregate_request(user_request):
        return RouteDecision(
            route=RouteName.SQL_QUERY,
            reason="Safety override: request asks for actual rows or aggregation, not metadata.",
            metadata=decision.metadata,
        )

    # If the LLM says out-of-scope but the user clearly references the loaded schema, try SQL.
    if decision.route == RouteName.OUT_OF_SCOPE and _contains_schema_reference(user_request, ctx):
        return RouteDecision(
            route=RouteName.SQL_QUERY,
            reason="Safety override: request references the loaded schema, so route to SQL.",
            metadata=decision.metadata,
        )

    return decision


def _make_fallback_route_decision(user_request: str, ctx: RouterContext, llm_decision: RouteDecision | None = None) -> RouteDecision:
    out_of_scope_reason = _detect_out_of_scope(user_request, ctx)
    metadata = dict(llm_decision.metadata) if llm_decision else {}

    if out_of_scope_reason:
        return RouteDecision(route=RouteName.OUT_OF_SCOPE, reason=out_of_scope_reason, metadata=metadata)

    return RouteDecision(
        route=RouteName.SQL_QUERY,
        reason="Defaulted to SQL because the request was not metadata-only, not a Python tool request, and not clearly out of scope.",
        metadata=metadata,
    )


def _make_route_decision(user_request: str, ctx: RouterContext) -> RouteDecision:
    # 1) Fast deterministic routes for things we know with high confidence.
    data_reason = _detect_data_question(user_request, ctx)
    if data_reason:
        return RouteDecision(route=RouteName.DATA_QUESTION, reason=data_reason, metadata={"llm_router_used": False})

    tool_name, tool_reason = _detect_python_tool(user_request)
    if tool_name:
        return RouteDecision(
            route=RouteName.PYTHON_TOOL,
            reason=tool_reason or "Matched supported Python tool route.",
            tool_name=tool_name,
            metadata={"llm_router_used": False},
        )

    # 2) LLM fallback handles natural wording that regex/patterns missed.
    llm_decision = _llm_route_decision(user_request, ctx)
    if llm_decision and llm_decision.metadata.get("llm_router_used"):
        return _apply_route_safety_overrides(user_request, ctx, llm_decision)

    # 3) If the LLM router is unavailable/invalid, keep the old safe fallback behavior.
    return _make_fallback_route_decision(user_request, ctx, llm_decision)

def _out_of_scope_result(user_request: str, decision: RouteDecision) -> RouterResult:
    return RouterResult(
        route=RouteName.OUT_OF_SCOPE,
        ok=False,
        message=(
            "This assistant is focused on the loaded DuckDB data. "
            "It can answer schema questions, run SQL-style retrieval, "
            "normalize emails, fuzzy match data, check duplicates, calculate summary stats/correlation, and create charts."
        ),
        reason=decision.reason,
        original_query=user_request,
    )


def _infer_preferred_table(query: str, ctx: RouterContext) -> str | None:
    normalized_query = _normalize(query)
    scores: dict[str, int] = {table_name: 0 for table_name in ctx.schema_map.keys()}

    for table_name in ctx.schema_map.keys():
        if _contains_exact_term(normalized_query, table_name.lower()):
            scores[table_name] += 10
        for token in _table_keywords(table_name):
            if not token:
                continue
            if _contains_exact_term(normalized_query, token):
                scores[table_name] += 4
            if re.search(rf"\b(users|people|rows|records|members|employees)\s+in\s+{re.escape(token)}\b", normalized_query):
                scores[table_name] += 8
            if re.search(rf"\bin\s+{re.escape(token)}\b\s+who\b", normalized_query):
                scores[table_name] += 8
            if re.search(rf"\bfrom\s+{re.escape(token)}\b", normalized_query):
                scores[table_name] += 6

    best_table = None
    best_score = 0
    tied = False
    for table_name, score in scores.items():
        if score > best_score:
            best_table = table_name
            best_score = score
            tied = False
        elif score == best_score and score > 0:
            tied = True

    if best_score > 0 and not tied:
        return best_table
    return None


def _column_hint_score(column_name: str, query: str) -> int:
    normalized_column = _normalize(column_name)
    normalized_query = _normalize(query)
    score = 0
    for canonical, hints in _COLUMN_HINTS.items():
        if canonical.replace("_", " ") in normalized_column and any(
            _contains_exact_term(normalized_query, hint) for hint in hints
        ):
            score += 3
    return score


def _choose_constraint_owner(
    *,
    query: str,
    value: str,
    owners: list[tuple[str, str, str]],
    preferred_table: str | None,
) -> tuple[str, str, str] | None:
    if not owners:
        return None
    if len(owners) == 1:
        return owners[0]

    scored: list[tuple[int, tuple[str, str, str]]] = []
    for owner in owners:
        table_name, column_name, canonical_value = owner
        score = 0
        if preferred_table and table_name == preferred_table:
            score += 4
        score += _column_hint_score(column_name, query)
        if _contains_exact_term(query, table_name.lower()):
            score += 2
        for token in _table_keywords(table_name):
            if _contains_exact_term(query, token):
                score += 1
        column_n = _normalize(column_name)
        value_n = _normalize(value)
        if re.search(rf"\b{re.escape(column_n)}\s+(?:is|=|equals|of)?\s*{re.escape(value_n)}\b", _normalize(query)):
            score += 5
        if re.search(rf"\b{re.escape(value_n)}\s+{re.escape(column_n)}\b", _normalize(query)):
            score += 4
        scored.append((score, owner))

    scored.sort(key=lambda x: (-x[0], x[1][0].lower(), x[1][1].lower()))
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        return None
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return None


def _clean_bound_value(table_name: str, column_name: str, value: Any) -> str:
    value_s = str(value or "").strip()
    prefix = f"{table_name}.{column_name}."
    if value_s.startswith(prefix):
        return value_s[len(prefix) :]
    return value_s


def _add_binding(
    bindings: list[dict[str, str]],
    seen: set[tuple[str, str, str]],
    *,
    table: str,
    column: str,
    value: str,
    source: str,
) -> None:
    clean_value = _clean_bound_value(table, column, value)
    if not table or not column or not clean_value:
        return
    key = (table, column, clean_value)
    if key in seen:
        return
    seen.add(key)
    bindings.append(
        {
            "table": table,
            "column": column,
            "value": clean_value,
            "source": source,
        }
    )


def _is_safe_alias_value_hit(hit: Any, original_query: str) -> bool:
    alias = _normalize(getattr(hit, "alias", ""))
    if not alias or alias in _STOPWORDS or len(alias) < 3:
        return False
    # For value hits, do not let a single filler word from the query bind a categorical value.
    # The alias must appear as an exact phrase, or be a strong fuzzy match handled by schema_aliases.
    if len(alias.split()) == 1 and alias in _normalize(original_query).split() and alias not in _STOPWORDS:
        return True
    if _contains_exact_term(original_query, alias):
        return True
    return float(getattr(hit, "score", 0.0)) >= 0.985


def _collect_bound_constraints(
    user_request: str,
    ctx: RouterContext,
    grounded_query: Any | None = None,
) -> tuple[list[dict[str, str]], str | None]:
    normalized_query = _normalize(user_request)
    preferred_table = _infer_preferred_table(normalized_query, ctx)
    mentioned_tables = _infer_mentioned_tables(normalized_query, ctx)

    value_owners: dict[str, list[tuple[str, str, str]]] = {}
    for (table_name, column_name), values in ctx.categorical_index.items():
        for raw_value in values:
            canonical_value = str(raw_value).strip()
            if not canonical_value:
                continue
            value_owners.setdefault(_normalize(canonical_value), []).append((table_name, column_name, canonical_value))

    bindings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    # 1) Exact categorical values from the user's original request.
    for value_lower, owners in value_owners.items():
        if not value_lower or value_lower in _STOPWORDS or len(value_lower) < 3:
            continue
        if not _contains_exact_term(normalized_query, value_lower):
            continue
        chosen = _choose_constraint_owner(
            query=normalized_query,
            value=value_lower,
            owners=owners,
            preferred_table=preferred_table,
        )
        if chosen is None:
            continue
        table_name, column_name, canonical_value = chosen
        _add_binding(
            bindings,
            seen,
            table=table_name,
            column=column_name,
            value=canonical_value,
            source="categorical_exact_match",
        )

    # 2) Alias-grounded categorical values. This is the important fix: use hit.metadata["value"],
    # not hit.key. hit.key is the full internal key like hr_data.department.Engineering.
    if grounded_query is not None:
        for hit in getattr(grounded_query, "value_hits", []) or []:
            if not _is_safe_alias_value_hit(hit, user_request):
                continue
            metadata = dict(getattr(hit, "metadata", {}) or {})
            table_name = str(metadata.get("table", "")).strip()
            column_name = str(metadata.get("column", "")).strip()
            canonical_value = str(metadata.get("value", "")).strip()
            if not table_name or not column_name or not canonical_value:
                continue
            if preferred_table and table_name != preferred_table:
                # Keep cross-table cases possible only if the table is actually mentioned.
                if table_name not in mentioned_tables:
                    continue
            _add_binding(
                bindings,
                seen,
                table=table_name,
                column=column_name,
                value=canonical_value,
                source="alias_grounding",
            )

    if preferred_table is None and bindings and len(mentioned_tables) <= 1:
        tables = {binding["table"] for binding in bindings}
        if len(tables) == 1:
            preferred_table = next(iter(tables))

    return bindings, preferred_table


def _augment_request_with_constraints(
    user_request: str,
    preferred_table: str | None,
    bound_constraints: list[dict[str, str]],
) -> str:
    if not bound_constraints and not preferred_table:
        return user_request

    lines = [user_request.strip(), "", "SQL BINDING HINTS:"]
    if preferred_table:
        lines.append(f'- prefer table "{preferred_table}" unless the request clearly requires another table')
    if bound_constraints:
        lines.append("- apply these categorical constraints exactly:")
        for item in bound_constraints:
            table_name = item["table"]
            column_name = item["column"]
            value = _clean_bound_value(table_name, column_name, item["value"]).replace('"', '\\"')
            lines.append(f'  - "{table_name}"."{column_name}" = "{value}"')
        lines.append("- combine these constraints with AND unless the user explicitly says OR")
        lines.append("- do not move a categorical value to a different column")
    return "\n".join(lines).strip()


def route_request(user_request: str, ctx: RouterContext) -> RouterResult:
    decision = _make_route_decision(user_request, ctx)

    if decision.route == RouteName.DATA_QUESTION:
        result = answer_data_question(user_request, ctx)
    elif decision.route == RouteName.PYTHON_TOOL:
        result = run_python_tool(user_request, ctx)
    elif decision.route == RouteName.OUT_OF_SCOPE:
        result = _out_of_scope_result(user_request, decision)
    else:
        grounded_query = ground_user_query(user_request, ctx.alias_index) if ctx.alias_index else None
        grounded_user_request = (
            grounded_query.rewritten_query.strip()
            if grounded_query and grounded_query.rewritten_query.strip()
            else user_request
        )

        mentioned_tables = _infer_mentioned_tables(grounded_user_request, ctx)
        bound_constraints, preferred_table = _collect_bound_constraints(
            user_request,
            ctx,
            grounded_query=grounded_query,
        )

        phrase_preferred = _infer_preferred_table(grounded_user_request, ctx)
        if phrase_preferred and phrase_preferred in mentioned_tables:
            preferred_table = phrase_preferred
        elif len(mentioned_tables) >= 2 and preferred_table and preferred_table not in mentioned_tables:
            preferred_table = None

        for item in bound_constraints:
            if item["table"] not in mentioned_tables:
                mentioned_tables.append(item["table"])

        bound_user_request = _augment_request_with_constraints(
            grounded_user_request,
            preferred_table,
            bound_constraints,
        )

        result = run_sql_query(
            con=ctx.con,
            model=ctx.model,
            schema_text=ctx.schema_text,
            schema_map=ctx.schema_map,
            categorical_index=ctx.categorical_index,
            categorical_text=ctx.categorical_text,
            user_request_original=user_request,
            user_request_grounded=bound_user_request,
            grounded_query=grounded_query,
            bound_constraints=bound_constraints,
            preferred_table=preferred_table,
            mentioned_tables=mentioned_tables,
        )

    if not result.reason:
        result.reason = decision.reason
    if not result.original_query:
        result.original_query = user_request
    if decision.tool_name and not result.tool_name:
        result.tool_name = decision.tool_name

    result.metadata = dict(result.metadata)
    result.metadata.setdefault("router_decision", decision.route.value)
    result.metadata.setdefault("router_reason", decision.reason)
    if decision.tool_name:
        result.metadata.setdefault("router_tool_name", decision.tool_name)
    for key, value in (decision.metadata or {}).items():
        result.metadata.setdefault(f"router_{key}", value)

    return result
