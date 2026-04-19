from __future__ import annotations

import re
from typing import Optional

from .data_questions import answer_data_question
from .python_tools import run_python_tool
from .router_types import RouteDecision, RouteName, RouterContext, RouterResult
from .schema_aliases import ground_user_query
from .sql_flow import run_sql_query


DATA_QUESTION_PATTERNS = [
    r"\bschema\b",
    r"\bwhat tables?\b",
    r"\bwhich tables?\b",
    r"\blist tables?\b",
    r"\bshow tables?\b",
    r"\bwhat data is loaded\b",
    r"\bwhat is loaded\b",
    r"\bloaded data\b",
    r"\bloaded files?\b",
    r"\bcolumns?\b",
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
    ],
    "fuzzy_match": [
        "fuzzy match",
        "approximate match",
        "similarity",
        "dedupe similar",
        "deduplicate similar",
    ],
    "create_graph": [
        "graph",
        "plot",
        "chart",
        "visualize",
        "visualise",
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
}

_TABLE_STOPWORDS = {
    "test",
    "export",
    "sheet",
    "sheet1",
    "sheet2",
    "sheet3",
    "table",
    "data",
}

_COLUMN_HINTS = {
    "role": {"role"},
    "team": {"team", "department", "dept", "group"},
    "status": {"status", "state"},
    "email": {"email", "mail"},
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _table_keywords(table_name: str) -> list[str]:
    tokens = re.split(r"[^a-zA-Z0-9]+", table_name.lower())
    out: list[str] = []
    for token in tokens:
        if token and token not in _TABLE_STOPWORDS and token not in out:
            out.append(token)
    return out


def _contains_exact_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", text.lower()) is not None


def _infer_mentioned_tables(query: str, ctx: RouterContext) -> list[str]:
    normalized_query = _normalize(query)
    matches: list[tuple[str, int]] = []

    for table_name in ctx.schema_map.keys():
        score = 0

        if re.search(rf"\b{re.escape(table_name.lower())}\b", normalized_query):
            score += 10

        for part in _table_keywords(table_name):
            if re.search(rf"\b{re.escape(part)}\b", normalized_query):
                if part in {"notion", "okta"}:
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
    return {term for term in terms if len(term) > 1}


def _contains_schema_reference(query: str, ctx: RouterContext) -> bool:
    normalized_query = _normalize(query)
    for term in _schema_terms(ctx):
        if re.search(rf"\b{re.escape(term)}\b", normalized_query):
            return True
    return False


def _detect_data_question(query: str, ctx: RouterContext) -> Optional[str]:
    normalized_query = _normalize(query)

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


def _make_route_decision(user_request: str, ctx: RouterContext) -> RouteDecision:
    data_reason = _detect_data_question(user_request, ctx)
    if data_reason:
        return RouteDecision(route=RouteName.DATA_QUESTION, reason=data_reason)

    tool_name, tool_reason = _detect_python_tool(user_request)
    if tool_name:
        return RouteDecision(
            route=RouteName.PYTHON_TOOL,
            reason=tool_reason or "Matched supported Python tool route.",
            tool_name=tool_name,
        )

    out_of_scope_reason = _detect_out_of_scope(user_request, ctx)
    if out_of_scope_reason:
        return RouteDecision(route=RouteName.OUT_OF_SCOPE, reason=out_of_scope_reason)

    return RouteDecision(
        route=RouteName.SQL_QUERY,
        reason="Defaulted to SQL because the request was not metadata-only, not a Python tool request, and not clearly out of scope.",
    )


def _out_of_scope_result(user_request: str, decision: RouteDecision) -> RouterResult:
    return RouterResult(
        route=RouteName.OUT_OF_SCOPE,
        ok=False,
        message=(
            "This assistant is focused on the loaded DuckDB data. "
            "It can answer schema questions, run SQL-style retrieval, "
            "normalize emails, fuzzy match data, and create simple graphs."
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

            if re.search(
                rf"\b(users|people|rows|records|members)\s+in\s+{re.escape(token)}\b",
                normalized_query,
            ):
                scores[table_name] += 8

            if re.search(
                rf"\bin\s+{re.escape(token)}\b\s+who\b",
                normalized_query,
            ):
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
    normalized_column = column_name.lower()
    normalized_query = query.lower()
    score = 0

    for canonical, hints in _COLUMN_HINTS.items():
        if canonical in normalized_column and any(_contains_exact_term(normalized_query, hint) for hint in hints):
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

        pattern_role = rf"(?<!\w){re.escape(value.lower())}(?!\w)\s+role\b|\brole\s+{re.escape(value.lower())}(?!\w)"
        pattern_team = rf"(?<!\w){re.escape(value.lower())}(?!\w)\s+(team|department|dept|group)\b|\b(team|department|dept|group)\s+{re.escape(value.lower())}(?!\w)"
        pattern_status = rf"(?<!\w){re.escape(value.lower())}(?!\w)\s+status\b|\bstatus\s+{re.escape(value.lower())}(?!\w)"

        if re.search(pattern_role, query.lower()) and "role" in column_name.lower():
            score += 5
        if re.search(pattern_team, query.lower()) and any(tok in column_name.lower() for tok in ["team", "department", "dept", "group"]):
            score += 5
        if re.search(pattern_status, query.lower()) and "status" in column_name.lower():
            score += 5

        scored.append((score, (table_name, column_name, canonical_value)))

    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        return None
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return None


def _collect_bound_constraints(
    user_request: str,
    ctx: RouterContext,
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
            value_owners.setdefault(canonical_value.lower(), []).append((table_name, column_name, canonical_value))

    bindings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for value_lower, owners in value_owners.items():
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
        key = (table_name, column_name, canonical_value)
        if key in seen:
            continue
        seen.add(key)
        bindings.append(
            {
                "table": table_name,
                "column": column_name,
                "value": canonical_value,
                "source": "categorical_exact_match",
            }
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
            value = item["value"].replace('"', '\\"')
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
        bound_constraints, preferred_table = _collect_bound_constraints(grounded_user_request, ctx)

        phrase_preferred = _infer_preferred_table(grounded_user_request, ctx)
        if phrase_preferred and phrase_preferred in mentioned_tables:
            preferred_table = phrase_preferred
        elif len(mentioned_tables) >= 2 and preferred_table and preferred_table not in mentioned_tables:
            preferred_table = None

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

    return result