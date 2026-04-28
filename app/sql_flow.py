from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from .llm import nl_to_sql, rewrite_failed_sql
from .router_types import RouteName, RouterResult
from .validate import is_select_only, sanitize_sql, strip_ansi_and_control_chars, strip_code_fences

if TYPE_CHECKING:
    from .schema_aliases import GroundedQuery

_TABLE_STOPWORDS = {"test", "export", "sheet", "sheet1", "sheet2", "sheet3", "table", "data"}
_AGGREGATE_WORDS = {
    "count", "sum", "avg", "average", "min", "max", "group", "order", "sort",
    "distinct", "top", "bottom", "highest", "lowest", "chart", "plot", "graph",
}


def format_categorical_text(categorical_index: dict[tuple[str, str], list[str]]) -> str:
    lines: list[str] = []
    for (t, c) in sorted(categorical_index.keys(), key=lambda x: (x[0].lower(), x[1].lower())):
        vals = categorical_index[(t, c)]
        clean: list[str] = []
        seen = set()
        for v in vals:
            s = str(v).strip()
            if not s or s in seen:
                continue
            clean.append(s)
            seen.add(s)
        if not clean:
            continue
        escaped = [v.replace('"', '\\"') for v in clean[:50]]
        quoted = ", ".join(f'"{v}"' for v in escaped)
        suffix = " ..." if len(clean) > 50 else ""
        lines.append(f'- "{t}"."{c}" allowed_values=[{quoted}]{suffix}')
    return "\n".join(lines).strip()


def _normalize_text(text: str) -> str:
    text = str(text or "").strip().lower()
    text = text.replace("__", " ").replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9@. /]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_exact_term(text: str, term: str) -> bool:
    text_n = _normalize_text(text)
    term_n = _normalize_text(term)
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


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def extract_tables(sql: str) -> set[str]:
    from_tables = re.findall(
        r'\bFROM\s+((?:[A-Za-z0-9_]+\.)?"?[A-Za-z0-9_]+"?)',
        sql,
        flags=re.IGNORECASE,
    )
    join_tables = re.findall(
        r'\bJOIN\s+((?:[A-Za-z0-9_]+\.)?"?[A-Za-z0-9_]+"?)',
        sql,
        flags=re.IGNORECASE,
    )

    def normalize(name: str) -> str:
        if "." in name:
            name = name.split(".", 1)[-1]
        return name.strip('"')

    return {normalize(t) for t in (from_tables + join_tables) if t}


def find_missing_columns_tables(
    sql: str,
    schema_map: dict[str, dict[str, str]],
    present_tables: set[str],
) -> list[tuple[str, str]]:
    tokens = set(m.group(1) for m in re.finditer(r'(?<!\.)"([A-Za-z_][A-Za-z0-9_]*)"', sql))
    missing: list[tuple[str, str]] = []
    for token in sorted(tokens):
        if any(token in schema_map.get(table, {}) for table in present_tables):
            continue
        owners = [table for table, cols in schema_map.items() if token in cols]
        for owner in owners:
            if owner not in present_tables:
                missing.append((token, owner))
    return missing


def auto_join_and_qualify(
    con,
    sql: str,
    schema_map: dict[str, dict[str, str]],
    missing: list[tuple[str, str]],
) -> tuple[str, bool]:
    from .db import find_join_candidates

    present = extract_tables(sql)
    if len(present) != 1 or not missing:
        return sql, False

    base_table = list(present)[0]
    by_owner: dict[str, list[str]] = {}
    for col, owner in missing:
        by_owner.setdefault(owner, []).append(col)

    rewritten = sql
    changed = False
    for owner_table, cols in by_owner.items():
        candidates = find_join_candidates(
            con,
            schema_map,
            base_table,
            owner_table,
            sample_limit=200,
            min_overlap=0.05,
        )
        if not candidates:
            continue
        left_col, right_col, _score = candidates[0]
        join_clause = (
            f'FROM {_quote_ident(base_table)} t '
            f'JOIN {_quote_ident(owner_table)} o '
            f'ON lower(trim(t.{_quote_ident(left_col)})) = lower(trim(o.{_quote_ident(right_col)}))'
        )
        rewritten2 = re.sub(
            rf'\bFROM\s+"?{re.escape(base_table)}"?(?:\s+AS\s+\w+)?\b',
            join_clause,
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
        if rewritten2 == rewritten:
            continue
        rewritten = rewritten2
        changed = True
        for col in cols:
            rewritten = re.sub(rf'(?<!\.)"{re.escape(col)}"', f'o.{_quote_ident(col)}', rewritten)

    return rewritten, changed


def repair_categorical_literals(sql: str, categorical_index: dict[tuple[str, str], list[str]]) -> str:
    allowed_by_col: dict[str, set[str]] = {}
    for (_t, c), vals in categorical_index.items():
        allowed_by_col.setdefault(c, set())
        for v in vals:
            s = str(v).strip()
            if s:
                allowed_by_col[c].add(s)

    pattern = re.compile(
        r'(?P<lhs>(?:[A-Za-z_][A-Za-z0-9_]*\.)?"?(?P<col>[A-Za-z_][A-Za-z0-9_]*)"?)(?P<op>\s*=\s*)\'(?P<val>[^\']*)\'',
        flags=re.IGNORECASE,
    )

    def repl(m: re.Match) -> str:
        col = m.group("col")
        lhs = m.group("lhs")
        val = m.group("val").strip()
        if col not in allowed_by_col:
            return m.group(0)
        allowed = allowed_by_col[col]
        if val in allowed:
            return m.group(0)
        parts = [p.strip() for p in val.split(",") if p.strip()]
        if len(parts) >= 2 and all(p in allowed for p in parts):
            in_list = ", ".join(_sql_literal(p) for p in parts)
            return f"{lhs} IN ({in_list})"
        return m.group(0)

    return pattern.sub(repl, sql)


def _has_subquery(sql: str) -> bool:
    return len(re.findall(r"\bselect\b", sql, flags=re.IGNORECASE)) > 1


def _prepare_sql_candidate(sql: str, categorical_index: dict[tuple[str, str], list[str]]) -> str:
    sql = strip_ansi_and_control_chars(sql)
    sql = sanitize_sql(strip_code_fences(sql)).strip()
    sql = repair_categorical_literals(sql, categorical_index)
    return sql


def _try_execute_sql(con, sql: str, schema_map: dict[str, dict[str, str]]) -> tuple[str, bool, list[tuple[str, str]], object]:
    final_sql = sql
    changed = False
    missing: list[tuple[str, str]] = []
    if not _has_subquery(sql):
        present = extract_tables(sql)
        missing = find_missing_columns_tables(sql, schema_map, present)
        final_sql, changed = auto_join_and_qualify(con, sql, schema_map, missing)

    ok_after_join, reason_after_join = is_select_only(final_sql)
    if not ok_after_join:
        raise ValueError(f"Auto-joined SQL failed validation: {reason_after_join}")

    df = con.execute(final_sql).df()
    return final_sql, changed, missing, df


def _serialize_grounding_hits(hits: list[Any], limit: int = 5) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for hit in hits[:limit]:
        serialized.append(
            {
                "kind": hit.kind,
                "key": hit.key,
                "alias": hit.alias,
                "score": round(float(hit.score), 4),
                "metadata": dict(hit.metadata),
            }
        )
    return serialized


def _canonical_value_for_constraint(
    table_name: str,
    column_name: str,
    value: str,
    categorical_index: dict[tuple[str, str], list[str]] | None = None,
) -> str:
    value_s = str(value or "").strip()
    prefix = f"{table_name}.{column_name}."
    if value_s.startswith(prefix):
        value_s = value_s[len(prefix) :]

    if categorical_index:
        allowed = [str(v).strip() for v in categorical_index.get((table_name, column_name), [])]
        for allowed_value in allowed:
            if value_s == allowed_value:
                return allowed_value
        for allowed_value in allowed:
            if _normalize_text(value_s) == _normalize_text(allowed_value):
                return allowed_value

    return value_s


def _normalize_bound_constraints(
    bound_constraints: list[dict[str, str]] | None,
    categorical_index: dict[tuple[str, str], list[str]] | None = None,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for item in bound_constraints or []:
        table_name = str(item.get("table", "")).strip()
        column_name = str(item.get("column", "")).strip()
        value = _canonical_value_for_constraint(
            table_name,
            column_name,
            str(item.get("value", "")).strip(),
            categorical_index,
        )
        source = str(item.get("source", "")).strip() or "router_binding"
        if not table_name or not column_name or not value:
            continue
        key = (table_name, column_name, value)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"table": table_name, "column": column_name, "value": value, "source": source})

    return cleaned



_GOAL_EXCEEDS_PHRASES = {
    "exceeds", "exceed", "exceeded", "exceeded goals", "exceeds goals",
    "exceed goals", "exceeded their goals", "exceeds their goals",
    "above goals", "above goal", "did well", "high performer", "high performers",
}
_GOAL_MEETS_PHRASES = {
    "meets", "meet", "met", "met goals", "meets goals", "meet goals",
    "met their goals", "meets their goals", "on target",
}
_GOAL_BELOW_PHRASES = {
    "below", "below goals", "below goal", "missed goals", "misses goals",
    "under goals", "underperformed", "under performing", "low performer", "low performers",
}
_PROMO_YES_PHRASES = {
    "promotion eligible", "eligible for promotion", "ready for promotion",
}
_PROMO_NO_PHRASES = {
    "not promotion eligible", "not eligible for promotion", "not ready for promotion",
}
_PROMO_REVIEW_PHRASES = {
    "under review", "promotion review", "review for promotion", "being reviewed for promotion",
}


def _contains_any_phrase(query_n: str, phrases: set[str]) -> bool:
    return any(_contains_exact_term(query_n, phrase) for phrase in phrases)


def _find_allowed_value(
    categorical_index: dict[tuple[str, str], list[str]],
    table_name: str,
    column_name: str,
    *candidates: str,
) -> str | None:
    allowed = [str(v).strip() for v in categorical_index.get((table_name, column_name), []) if str(v).strip()]
    for candidate in candidates:
        candidate_n = _normalize_text(candidate)
        for value in allowed:
            if _normalize_text(value) == candidate_n:
                return value
    return None


def _append_bound_constraint(
    constraints: list[dict[str, str]],
    *,
    table_name: str,
    column_name: str,
    value: str | None,
    source: str,
) -> None:
    if not value:
        return
    key = (table_name, column_name, value)
    for item in constraints:
        if (item.get("table"), item.get("column"), item.get("value")) == key:
            return
    constraints.append({"table": table_name, "column": column_name, "value": value, "source": source})


def _augment_bound_constraints_from_query(
    user_request: str,
    schema_map: dict[str, dict[str, str]],
    categorical_index: dict[tuple[str, str], list[str]],
    bound_constraints: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Add safe natural-language constraints that alias matching can miss.

    This is intentionally narrow. It only adds constraints when the table/column/value
    already exist in the loaded schema and the wording is very clear. The main case it
    protects is queries like "employees who exceeded goals", where the data value is
    usually stored as goal_attainment = "Exceeds".
    """
    query_n = _normalize_text(user_request)
    constraints = [dict(item) for item in (bound_constraints or [])]

    for table_name, columns in schema_map.items():
        for column_name in columns.keys():
            col_n = _normalize_text(column_name).replace(" ", "_")

            if col_n == "goal_attainment":
                if _contains_any_phrase(query_n, _GOAL_EXCEEDS_PHRASES):
                    _append_bound_constraint(
                        constraints,
                        table_name=table_name,
                        column_name=column_name,
                        value=_find_allowed_value(categorical_index, table_name, column_name, "Exceeds"),
                        source="natural_language_goal_synonym",
                    )
                elif _contains_any_phrase(query_n, _GOAL_MEETS_PHRASES):
                    _append_bound_constraint(
                        constraints,
                        table_name=table_name,
                        column_name=column_name,
                        value=_find_allowed_value(categorical_index, table_name, column_name, "Meets"),
                        source="natural_language_goal_synonym",
                    )
                elif _contains_any_phrase(query_n, _GOAL_BELOW_PHRASES):
                    _append_bound_constraint(
                        constraints,
                        table_name=table_name,
                        column_name=column_name,
                        value=_find_allowed_value(categorical_index, table_name, column_name, "Below"),
                        source="natural_language_goal_synonym",
                    )

            elif col_n == "promotion_eligible":
                # Check negative/review wording before positive wording.
                if _contains_any_phrase(query_n, _PROMO_NO_PHRASES):
                    _append_bound_constraint(
                        constraints,
                        table_name=table_name,
                        column_name=column_name,
                        value=_find_allowed_value(categorical_index, table_name, column_name, "No"),
                        source="natural_language_promotion_synonym",
                    )
                elif _contains_any_phrase(query_n, _PROMO_REVIEW_PHRASES):
                    _append_bound_constraint(
                        constraints,
                        table_name=table_name,
                        column_name=column_name,
                        value=_find_allowed_value(categorical_index, table_name, column_name, "Under Review"),
                        source="natural_language_promotion_synonym",
                    )
                elif _contains_any_phrase(query_n, _PROMO_YES_PHRASES):
                    _append_bound_constraint(
                        constraints,
                        table_name=table_name,
                        column_name=column_name,
                        value=_find_allowed_value(categorical_index, table_name, column_name, "Yes"),
                        source="natural_language_promotion_synonym",
                    )

    return constraints


def _infer_mentioned_tables(
    query: str,
    schema_map: dict[str, dict[str, str]],
    bound_constraints: list[dict[str, str]] | None = None,
) -> list[str]:
    normalized_query = _normalize_text(query)
    scores: dict[str, int] = {table_name: 0 for table_name in schema_map.keys()}

    for table_name in schema_map.keys():
        if _contains_exact_term(normalized_query, table_name.lower()):
            scores[table_name] += 10
        for token in _table_keywords(table_name):
            if _contains_exact_term(normalized_query, token):
                if token in {"notion", "okta", "hr"}:
                    scores[table_name] += 4
                else:
                    scores[table_name] += 1

    for item in bound_constraints or []:
        table_name = item.get("table", "")
        if table_name in scores:
            scores[table_name] += 2

    ranked = [(table_name, score) for table_name, score in scores.items() if score > 0]
    ranked.sort(key=lambda x: (-x[1], x[0].lower()))
    return [table_name for table_name, _ in ranked]


def _infer_preferred_table(query: str, mentioned_tables: list[str]) -> str | None:
    if not mentioned_tables:
        return None
    if len(mentioned_tables) == 1:
        return mentioned_tables[0]

    normalized_query = _normalize_text(query)
    scored: list[tuple[int, str]] = []
    for table_name in mentioned_tables:
        score = 0
        for token in _table_keywords(table_name):
            if not token:
                continue
            if re.search(rf"\b(users|people|rows|records|members|employees)\s+in\s+{re.escape(token)}\b", normalized_query):
                score += 8
            if re.search(rf"\bin\s+{re.escape(token)}\b\s+who\b", normalized_query):
                score += 8
            if re.search(rf"\bfrom\s+{re.escape(token)}\b", normalized_query):
                score += 6
            if re.search(rf"\bin\s+{re.escape(token)}\b", normalized_query):
                score += 3
        if _contains_exact_term(normalized_query, table_name.lower()):
            score += 2
        scored.append((score, table_name))

    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    if not scored or scored[0][0] <= 0:
        return mentioned_tables[0]
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        return mentioned_tables[0]
    return scored[0][1]


def _is_simple_filter_request(user_request: str) -> bool:
    q = f" {_normalize_text(user_request)} "
    return not any(f" {word} " in q for word in _AGGREGATE_WORDS)


def _infer_boolean_operator(user_request: str) -> str:
    lowered = f" {_normalize_text(user_request)} "
    has_and = " and " in lowered
    has_or = " or " in lowered
    if has_or and not has_and:
        return "OR"
    return "AND"


def _column_aliases(column_name: str) -> set[str]:
    normalized = _normalize_text(column_name)
    normalized_key = normalized.replace(" ", "_")
    aliases = {normalized, column_name.lower(), column_name.lower().replace("_", " ")}

    if normalized_key == "full_name":
        aliases.update({"full name", "fullname", "name", "names", "employee name", "employee names"})
    elif normalized_key in {"employee_id", "user_id"}:
        aliases.update({"employee id", "employee ids", "id", "ids"})
    elif normalized_key in {"email", "user_email", "email_address"}:
        aliases.update({"email", "emails", "mail", "email address", "email addresses"})
    elif normalized_key == "department":
        aliases.update({"department", "departments", "dept", "team", "teams"})
    elif normalized_key == "work_mode":
        aliases.update({"work mode", "work modes", "remote", "hybrid", "in office", "in-office"})
    elif normalized_key == "role":
        aliases.update({"role", "roles", "job role", "job roles", "title", "titles"})
    elif normalized_key == "level":
        aliases.update({"level", "levels", "seniority", "seniority level"})
    elif normalized_key in {"salary", "salary_usd", "base_salary", "annual_salary"}:
        aliases.update({"salary", "salaries", "pay", "compensation", "salary usd", "salary_usd", "annual salary", "base salary"})
    elif normalized_key in {"bonus", "bonus_pct", "bonus_percent", "bonus_percentage"}:
        aliases.update({"bonus", "bonus pct", "bonus percent", "bonus percentage", "bonus_pct"})
    elif normalized_key == "years_at_company":
        aliases.update({"years at company", "tenure", "years", "years employed", "time at company"})
    elif normalized_key == "rating":
        aliases.update({"rating", "ratings", "score", "review score", "performance rating"})
    elif normalized_key == "goal_attainment":
        aliases.update({"goal attainment", "goals", "goal", "goal status", "performance goals"})
    elif normalized_key == "promotion_eligible":
        aliases.update({"promotion eligible", "eligible for promotion", "promotion eligibility", "promotion"})
    elif normalized_key == "manager_id":
        aliases.update({"manager", "manager id", "manager_id"})
    elif normalized_key == "review_cycle":
        aliases.update({"review cycle", "cycle", "review period"})

    return {a for a in aliases if a}



_IDENTITY_COLUMNS = {"employee_id", "full_name", "name", "email", "user_email", "email_address"}
_PEOPLE_WORDS = {
    "employee", "employees", "person", "people", "worker", "workers",
    "staff", "user", "users", "member", "members", "who",
}
_IDENTITY_BLOCK_PHRASES = {
    "count", "how many", "average", "avg", "sum", "total", "group by",
    "distinct", "unique", "breakdown", "distribution",
}


def _is_people_lookup_request(user_request: str) -> bool:
    q = _normalize_text(user_request)
    return any(_contains_exact_term(q, word) for word in _PEOPLE_WORDS)


def _blocks_default_identity_columns(user_request: str) -> bool:
    q = _normalize_text(user_request)
    if _contains_exact_term(q, "only"):
        return True
    return any(phrase in q for phrase in _IDENTITY_BLOCK_PHRASES)


def _selected_has_identity(selected_columns: list[tuple[str, str]]) -> bool:
    for _table_name, column_name in selected_columns:
        if _normalize_text(column_name).replace(" ", "_") in _IDENTITY_COLUMNS:
            return True
    return False


def _should_add_identity_columns(user_request: str, selected_columns: list[tuple[str, str]]) -> bool:
    if _blocks_default_identity_columns(user_request):
        return False
    if not _is_people_lookup_request(user_request):
        return False
    if _selected_has_identity(selected_columns):
        return False
    return True


def _find_identity_table(schema_map: dict[str, dict[str, str]]) -> str | None:
    candidates: list[tuple[int, str]] = []
    for table_name, columns in schema_map.items():
        normalized_cols = {_normalize_text(col).replace(" ", "_") for col in columns.keys()}
        if "employee_id" not in normalized_cols or "full_name" not in normalized_cols:
            continue

        score = 0
        table_n = _normalize_text(table_name)
        if table_n == "hr data" or table_name.lower() == "hr_data":
            score += 10
        if "hr" in table_n:
            score += 5
        if "employee" in table_n or "people" in table_n or "user" in table_n:
            score += 3
        candidates.append((score, table_name))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1].lower()))
    return candidates[0][1]


def _has_column(schema_map: dict[str, dict[str, str]], table_name: str, column_name: str) -> bool:
    return column_name in schema_map.get(table_name, {})


def _can_join_identity_table(schema_map: dict[str, dict[str, str]], base_table: str, identity_table: str | None) -> bool:
    if not identity_table or identity_table == base_table:
        return False
    return _has_column(schema_map, base_table, "employee_id") and _has_column(schema_map, identity_table, "employee_id")


def _identity_join_for_request(
    *,
    user_request: str,
    selected_columns: list[tuple[str, str]],
    schema_map: dict[str, dict[str, str]],
    base_table: str,
) -> str | None:
    if not _should_add_identity_columns(user_request, selected_columns):
        return None
    if _has_column(schema_map, base_table, "full_name"):
        return None
    identity_table = _find_identity_table(schema_map)
    if _can_join_identity_table(schema_map, base_table, identity_table):
        return identity_table
    return None


def _add_default_identity_columns(
    *,
    user_request: str,
    selected_columns: list[tuple[str, str]],
    schema_map: dict[str, dict[str, str]],
    base_table: str,
    identity_table: str | None = None,
) -> list[tuple[str, str]]:
    if not _should_add_identity_columns(user_request, selected_columns):
        return selected_columns

    enriched = list(selected_columns)
    seen = set(enriched)

    def add_front(table_name: str, column_name: str):
        key = (table_name, column_name)
        if key not in seen and _has_column(schema_map, table_name, column_name):
            enriched.insert(0, key)
            seen.add(key)

    # Insert in reverse order because add_front places each item at the beginning.
    if identity_table and identity_table != base_table:
        add_front(identity_table, "full_name")
        add_front(base_table, "employee_id")
    else:
        add_front(base_table, "full_name")
        add_front(base_table, "employee_id")

    return enriched


def _build_select_clause_with_aliases(
    selected_columns: list[tuple[str, str]],
    *,
    base_table: str,
    alias_map: dict[str, str],
    default_alias: str | None = None,
) -> str:
    if not selected_columns:
        return "*" if default_alias is None else f"{default_alias}.*"

    parts: list[str] = []
    seen_sql_parts: set[str] = set()
    for table_name, column_name in selected_columns:
        alias = alias_map.get(table_name)
        if alias is None and table_name == base_table:
            alias = default_alias
        if alias is None:
            continue
        lhs = f'{alias}.{_quote_ident(column_name)}' if alias else _quote_ident(column_name)
        if lhs not in seen_sql_parts:
            parts.append(lhs)
            seen_sql_parts.add(lhs)

    return ", ".join(parts) if parts else ("*" if default_alias is None else f"{default_alias}.*")


def _infer_selected_columns(
    user_request: str,
    schema_map: dict[str, dict[str, str]],
    preferred_table: str | None,
    mentioned_tables: list[str],
    bound_constraints: list[dict[str, str]],
) -> list[tuple[str, str]]:
    # Only infer projection for simple retrieval phrasing. Aggregates/grouping should go to the LLM/Python path.
    if not _is_simple_filter_request(user_request):
        return []

    candidate_tables: list[str] = []
    if preferred_table:
        candidate_tables.append(preferred_table)
    for table_name in mentioned_tables:
        if table_name not in candidate_tables:
            candidate_tables.append(table_name)
    for item in bound_constraints:
        if item["table"] not in candidate_tables:
            candidate_tables.append(item["table"])

    # Projection words such as "salary" can point to a table that is not part of the filters.
    # Search every loaded table after the likely tables so requests like
    # "Engineering employees who exceeded goals with their salary" can include compensation.salary_usd.
    for table_name in schema_map.keys():
        if table_name not in candidate_tables:
            candidate_tables.append(table_name)

    request_n = _normalize_text(user_request)
    selected: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for table_name in candidate_tables:
        for column_name in schema_map.get(table_name, {}).keys():
            for alias in _column_aliases(column_name):
                if _contains_exact_term(request_n, alias):
                    key = (table_name, column_name)
                    if key not in seen:
                        selected.append(key)
                        seen.add(key)
                    break

    # Do not treat filter columns as requested output columns unless the user explicitly named them.
    # Example: "employees in Engineering" should filter by department, not necessarily return department.
    filter_cols = {(item["table"], item["column"]) for item in bound_constraints}
    selected = [item for item in selected if item not in filter_cols or _contains_exact_term(request_n, item[1])]

    return selected


def _make_employee_id_join(left_alias: str, right_alias: str) -> str:
    return (
        f"lower(trim({left_alias}.{_quote_ident('employee_id')})) = "
        f"lower(trim({right_alias}.{_quote_ident('employee_id')}))"
    )


def _can_join_on_employee_id(schema_map: dict[str, dict[str, str]], left_table: str, right_table: str) -> bool:
    return _has_column(schema_map, left_table, "employee_id") and _has_column(schema_map, right_table, "employee_id")


def _external_selected_tables(selected_columns: list[tuple[str, str]], base_table: str) -> list[str]:
    tables: list[str] = []
    for table_name, _column_name in selected_columns:
        if table_name != base_table and table_name not in tables:
            tables.append(table_name)
    return tables


def _add_output_joins(
    *,
    schema_map: dict[str, dict[str, str]],
    base_table: str,
    from_clause: str,
    alias_map: dict[str, str],
    selected_columns: list[tuple[str, str]],
    blocked_tables: set[str] | None = None,
) -> tuple[str, dict[str, str]] | None:
    """Join extra tables that are needed only because the user asked to display columns from them.

    This is intentionally conservative. It only joins extra output tables when both the
    base table and the output table have employee_id. It also refuses blocked tables
    such as the EXISTS/filter table, because selecting columns from a one-to-many
    filter table can reintroduce duplicate people.
    """
    blocked_tables = blocked_tables or set()
    next_idx = 1
    for table_name in _external_selected_tables(selected_columns, base_table):
        if table_name in blocked_tables:
            return None
        if table_name in alias_map:
            continue
        if not _can_join_on_employee_id(schema_map, base_table, table_name):
            return None
        alias = f"j{next_idx}"
        next_idx += 1
        alias_map[table_name] = alias
        from_clause += (
            f"\nJOIN {_quote_ident(table_name)} {alias} "
            f"ON {_make_employee_id_join('t', alias)}"
        )
    return from_clause, alias_map




def _build_employee_lookup_sql(
    *,
    schema_map: dict[str, dict[str, str]],
    user_request: str,
    preferred_table: str | None,
    mentioned_tables: list[str],
    bound_constraints: list[dict[str, str]],
) -> str | None:
    """Build a safer employee/person lookup query.

    Employee-style questions should usually show who the rows refer to. This
    path uses the identity table, normally hr_data, as the base table, adds
    employee_id/full_name by default, uses EXISTS for filter-only tables, and
    joins extra output tables only for requested display columns such as salary
    or role.
    """
    constraints = _normalize_bound_constraints(bound_constraints)
    if not _is_simple_filter_request(user_request):
        return None
    if not _is_people_lookup_request(user_request):
        return None

    identity_table = _find_identity_table(schema_map)
    if identity_table:
        base_table = identity_table
    elif preferred_table:
        base_table = preferred_table
    elif mentioned_tables:
        base_table = mentioned_tables[0]
    elif constraints:
        base_table = constraints[0]["table"]
    else:
        return None

    if base_table not in schema_map:
        return None

    selected_columns = _infer_selected_columns(
        user_request=user_request,
        schema_map=schema_map,
        preferred_table=base_table,
        mentioned_tables=mentioned_tables,
        bound_constraints=constraints,
    )

    # Treat constraint columns as filters, not default output. For example,
    # "promotion eligible employees with salary and role" should show the
    # employee plus salary/role, not just a column full of Yes values.
    filter_cols = {(item["table"], item["column"]) for item in constraints}
    selected_columns = [item for item in selected_columns if item not in filter_cols]

    selected_columns = _add_default_identity_columns(
        user_request=user_request,
        selected_columns=selected_columns,
        schema_map=schema_map,
        base_table=base_table,
        identity_table=None,
    )

    alias_map: dict[str, str] = {base_table: "t"}
    from_clause = f"FROM {_quote_ident(base_table)} t"
    where_parts: list[str] = []
    exists_idx = 1

    for item in constraints:
        table_name = item["table"]
        column_name = item["column"]
        value = item["value"]

        if table_name == base_table:
            where_parts.append(f't.{_quote_ident(column_name)} = {_sql_literal(value)}')
            continue

        if not _can_join_on_employee_id(schema_map, base_table, table_name):
            return None

        exists_alias = f"e{exists_idx}"
        exists_idx += 1
        exists_where = (
            f"{_make_employee_id_join('t', exists_alias)} "
            f"AND {exists_alias}.{_quote_ident(column_name)} = {_sql_literal(value)}"
        )
        where_parts.append(
            "EXISTS (\n"
            f"    SELECT 1\n"
            f"    FROM {_quote_ident(table_name)} {exists_alias}\n"
            f"    WHERE {exists_where}\n"
            ")"
        )

    filter_tables = {item["table"] for item in constraints if item["table"] != base_table}
    joined = _add_output_joins(
        schema_map=schema_map,
        base_table=base_table,
        from_clause=from_clause,
        alias_map=alias_map,
        selected_columns=selected_columns,
        blocked_tables=filter_tables,
    )
    if joined is None:
        return None
    from_clause, alias_map = joined

    select_clause = _build_select_clause_with_aliases(
        selected_columns,
        base_table=base_table,
        alias_map=alias_map,
        default_alias="t",
    )
    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    return f"SELECT {select_clause}\n{from_clause}\nWHERE {where_clause}"

def _group_constraints_for_sql(
    constraints: list[dict[str, str]],
    operator: str,
    alias: str | None = None,
) -> list[str] | None:
    by_column: dict[str, list[str]] = {}
    for item in constraints:
        by_column.setdefault(item["column"], []).append(item["value"])

    clauses: list[str] = []
    for column_name, values in by_column.items():
        unique_values: list[str] = []
        seen_values = set()
        for value in values:
            if value not in seen_values:
                unique_values.append(value)
                seen_values.add(value)

        lhs = f'{alias}.{_quote_ident(column_name)}' if alias else _quote_ident(column_name)
        if len(unique_values) > 1 and operator == "AND":
            return None
        if len(unique_values) == 1:
            clauses.append(f"{lhs} = {_sql_literal(unique_values[0])}")
        else:
            in_list = ", ".join(_sql_literal(value) for value in unique_values)
            clauses.append(f"{lhs} IN ({in_list})")

    return clauses


def _build_select_clause(
    selected_columns: list[tuple[str, str]],
    *,
    base_table: str,
    alias: str | None = None,
) -> str:
    if not selected_columns:
        return "*" if alias is None else f"{alias}.*"

    parts: list[str] = []
    for table_name, column_name in selected_columns:
        if table_name != base_table:
            continue
        lhs = f'{alias}.{_quote_ident(column_name)}' if alias else _quote_ident(column_name)
        parts.append(lhs)

    return ", ".join(parts) if parts else ("*" if alias is None else f"{alias}.*")


def _build_sql_from_bound_constraints(
    *,
    preferred_table: str | None,
    bound_constraints: list[dict[str, str]],
    user_request: str,
    schema_map: dict[str, dict[str, str]],
    mentioned_tables: list[str],
) -> str | None:
    constraints = _normalize_bound_constraints(bound_constraints)
    if not constraints or not preferred_table:
        return None
    if not _is_simple_filter_request(user_request):
        return None

    same_table = all(item["table"] == preferred_table for item in constraints)
    if not same_table:
        return None

    operator = _infer_boolean_operator(user_request)
    clauses = _group_constraints_for_sql(constraints, operator, alias="t")
    if not clauses:
        return None

    selected_columns = _infer_selected_columns(
        user_request=user_request,
        schema_map=schema_map,
        preferred_table=preferred_table,
        mentioned_tables=mentioned_tables,
        bound_constraints=constraints,
    )

    identity_table = _identity_join_for_request(
        user_request=user_request,
        selected_columns=selected_columns,
        schema_map=schema_map,
        base_table=preferred_table,
    )
    selected_columns = _add_default_identity_columns(
        user_request=user_request,
        selected_columns=selected_columns,
        schema_map=schema_map,
        base_table=preferred_table,
        identity_table=identity_table,
    )

    alias_map = {preferred_table: "t"}
    from_clause = f"FROM {_quote_ident(preferred_table)} t"
    if identity_table:
        alias_map[identity_table] = "h"
        from_clause += (
            f"\nJOIN {_quote_ident(identity_table)} h "
            f"ON {_make_employee_id_join('t', 'h')}"
        )

    joined = _add_output_joins(
        schema_map=schema_map,
        base_table=preferred_table,
        from_clause=from_clause,
        alias_map=alias_map,
        selected_columns=selected_columns,
    )
    if joined is None:
        return None
    from_clause, alias_map = joined

    select_clause = _build_select_clause_with_aliases(
        selected_columns,
        base_table=preferred_table,
        alias_map=alias_map,
        default_alias="t",
    )
    joiner = f" {operator} "
    where_clause = joiner.join(clauses)
    return f"SELECT {select_clause}\n{from_clause}\nWHERE {where_clause}"


def _build_cross_table_bound_sql(
    con,
    schema_map: dict[str, dict[str, str]],
    *,
    user_request: str,
    mentioned_tables: list[str],
    preferred_table: str | None,
    bound_constraints: list[dict[str, str]],
) -> str | None:
    """Build deterministic SQL when filters span two tables.

    Important behavior:
    - If the second table is only being used as a filter, use EXISTS instead of
      a plain JOIN. A normal JOIN duplicates base-table rows when the other
      table has multiple matching rows per employee/user/id.
    - Return only rows from the preferred/base table, unless the LLM path is
      needed for more complex cross-table output.
    """
    from .db import find_join_candidates

    constraints = _normalize_bound_constraints(bound_constraints)
    if not _is_simple_filter_request(user_request):
        return None

    mentioned_unique: list[str] = []
    seen_tables = set()
    for table_name in mentioned_tables:
        if table_name not in seen_tables:
            mentioned_unique.append(table_name)
            seen_tables.add(table_name)

    if len(mentioned_unique) != 2:
        return None

    base_table = preferred_table if preferred_table in mentioned_unique else mentioned_unique[0]
    other_table = mentioned_unique[1] if mentioned_unique[0] == base_table else mentioned_unique[0]

    base_constraints = [item for item in constraints if item["table"] == base_table]
    other_constraints = [item for item in constraints if item["table"] == other_table]

    # If there is nothing to filter on the other table, do not join at all.
    # The same-table deterministic path can handle the base-table filters.
    if not other_constraints:
        return None

    # Cross-table OR logic is ambiguous in this deterministic path. Let the LLM
    # path handle it rather than producing a misleading EXISTS query.
    operator = _infer_boolean_operator(user_request)
    if operator != "AND":
        return None

    base_clauses = _group_constraints_for_sql(base_constraints, "AND", alias="t") if base_constraints else []
    other_clauses = _group_constraints_for_sql(other_constraints, "AND", alias="o")
    if base_constraints and base_clauses is None:
        return None
    if not other_clauses:
        return None

    candidates = find_join_candidates(con, schema_map, base_table, other_table, sample_limit=200, min_overlap=0.05)
    if not candidates:
        return None
    left_col, right_col, _score = candidates[0]

    selected_columns = _infer_selected_columns(
        user_request=user_request,
        schema_map=schema_map,
        preferred_table=base_table,
        mentioned_tables=mentioned_unique,
        bound_constraints=constraints,
    )

    # If the request asks to display columns from the EXISTS/filter table,
    # this simple path is not the right fit because it can reintroduce duplicate
    # employees when the filter table has multiple rows per person.
    if any(table_name == other_table for table_name, _column_name in selected_columns):
        return None

    identity_table = _identity_join_for_request(
        user_request=user_request,
        selected_columns=selected_columns,
        schema_map=schema_map,
        base_table=base_table,
    )
    selected_columns = _add_default_identity_columns(
        user_request=user_request,
        selected_columns=selected_columns,
        schema_map=schema_map,
        base_table=base_table,
        identity_table=identity_table,
    )

    alias_map = {base_table: "t"}
    if identity_table:
        alias_map[identity_table] = "h"

    join_condition = f"lower(trim(t.{_quote_ident(left_col)})) = lower(trim(o.{_quote_ident(right_col)}))"
    exists_parts = [join_condition] + list(other_clauses)
    exists_where = " AND ".join(exists_parts)

    where_parts = list(base_clauses or [])
    where_parts.append(
        "EXISTS (\n"
        f"    SELECT 1\n"
        f"    FROM {_quote_ident(other_table)} o\n"
        f"    WHERE {exists_where}\n"
        ")"
    )
    where_clause = " AND ".join(where_parts)

    from_clause = f"FROM {_quote_ident(base_table)} t"
    if identity_table:
        from_clause += (
            f"\nJOIN {_quote_ident(identity_table)} h "
            f"ON {_make_employee_id_join('t', 'h')}"
        )

    joined = _add_output_joins(
        schema_map=schema_map,
        base_table=base_table,
        from_clause=from_clause,
        alias_map=alias_map,
        selected_columns=selected_columns,
        blocked_tables={other_table},
    )
    if joined is None:
        return None
    from_clause, alias_map = joined

    select_clause = _build_select_clause_with_aliases(
        selected_columns,
        base_table=base_table,
        alias_map=alias_map,
        default_alias="t",
    )

    return (
        f"SELECT {select_clause}\n"
        f"{from_clause}\n"
        f"WHERE {where_clause}"
    )

def _build_grounding_metadata(
    user_request_original: str,
    user_request_grounded: str,
    grounded_query: "GroundedQuery | None",
    bound_constraints: list[dict[str, str]] | None,
    preferred_table: str | None,
    mentioned_tables: list[str] | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "original_user_request": user_request_original,
        "grounded_user_request": user_request_grounded,
        "grounding_replacements": [],
        "grounding_changed_request": user_request_original != user_request_grounded,
        "preferred_table": preferred_table,
        "mentioned_tables": list(mentioned_tables or []),
        "bound_constraints": list(bound_constraints or []),
        "top_grounding_hits": {"tables": [], "columns": [], "values": []},
    }

    if grounded_query is None:
        return metadata

    metadata["grounding_replacements"] = list(grounded_query.replacements)
    metadata["top_grounding_hits"] = {
        "tables": _serialize_grounding_hits(grounded_query.table_hits),
        "columns": _serialize_grounding_hits(grounded_query.column_hits),
        "values": _serialize_grounding_hits(grounded_query.value_hits),
    }
    return metadata


def run_sql_query(
    con,
    model: str,
    schema_text: str,
    schema_map: dict[str, dict[str, str]],
    categorical_index: dict[tuple[str, str], list[str]],
    categorical_text: str,
    user_request_original: str,
    user_request_grounded: str,
    grounded_query: "GroundedQuery | None" = None,
    bound_constraints: list[dict[str, str]] | None = None,
    preferred_table: str | None = None,
    mentioned_tables: list[str] | None = None,
    rewrite_model: str = "llama3.2",
) -> RouterResult:
    raw = ""
    sql = ""
    final_sql = ""
    rewrite_raw = ""
    rewrite_sql = ""
    deterministic_sql = ""
    deterministic_join_sql = ""

    augmented_bound_constraints = _augment_bound_constraints_from_query(
        user_request=user_request_original,
        schema_map=schema_map,
        categorical_index=categorical_index,
        bound_constraints=bound_constraints,
    )
    normalized_bound_constraints = _normalize_bound_constraints(augmented_bound_constraints, categorical_index)

    effective_mentioned_tables = list(mentioned_tables or [])
    if not effective_mentioned_tables:
        effective_mentioned_tables = _infer_mentioned_tables(user_request_original, schema_map, normalized_bound_constraints)

    for item in normalized_bound_constraints:
        table_name = item["table"]
        if table_name not in effective_mentioned_tables:
            effective_mentioned_tables.append(table_name)

    inferred_preferred = _infer_preferred_table(user_request_original, effective_mentioned_tables)
    effective_preferred_table = inferred_preferred or preferred_table

    grounding_metadata = _build_grounding_metadata(
        user_request_original=user_request_original,
        user_request_grounded=user_request_grounded,
        grounded_query=grounded_query,
        bound_constraints=normalized_bound_constraints,
        preferred_table=effective_preferred_table,
        mentioned_tables=effective_mentioned_tables,
    )

    generation_request = user_request_grounded.strip() or user_request_original

    employee_lookup_sql = _build_employee_lookup_sql(
        schema_map=schema_map,
        user_request=user_request_original,
        preferred_table=effective_preferred_table,
        mentioned_tables=effective_mentioned_tables,
        bound_constraints=normalized_bound_constraints,
    ) or ""

    if employee_lookup_sql:
        try:
            final_sql, changed, missing, df = _try_execute_sql(con=con, sql=employee_lookup_sql, schema_map=schema_map)
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=True,
                message=f"Query returned {len(df)} row(s).",
                reason="Used deterministic employee lookup before model generation.",
                sql=final_sql,
                dataframe=df,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": "",
                    "initial_sql": employee_lookup_sql,
                    "auto_join_changed": changed,
                    "missing_columns": missing,
                    "row_count": len(df),
                    "execution_mode": "deterministic_employee_lookup_sql",
                    "rewrite_attempted": False,
                    "used_bound_sql": True,
                },
            ).with_query(user_request_original)
        except Exception as employee_lookup_exc:
            grounding_metadata["employee_lookup_sql_error"] = str(employee_lookup_exc)
            grounding_metadata["employee_lookup_sql"] = employee_lookup_sql

    deterministic_join_sql = _build_cross_table_bound_sql(
        con=con,
        schema_map=schema_map,
        user_request=user_request_original,
        mentioned_tables=effective_mentioned_tables,
        preferred_table=effective_preferred_table,
        bound_constraints=normalized_bound_constraints,
    ) or ""

    if deterministic_join_sql:
        try:
            final_sql, changed, missing, df = _try_execute_sql(con=con, sql=deterministic_join_sql, schema_map=schema_map)
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=True,
                message=f"Query returned {len(df)} row(s).",
                reason="Used deterministic cross-table binding before model generation.",
                sql=final_sql,
                dataframe=df,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": "",
                    "initial_sql": deterministic_join_sql,
                    "auto_join_changed": changed,
                    "missing_columns": missing,
                    "row_count": len(df),
                    "execution_mode": "deterministic_bound_join_sql",
                    "rewrite_attempted": False,
                    "used_bound_sql": True,
                },
            ).with_query(user_request_original)
        except Exception as bound_join_exc:
            grounding_metadata["deterministic_join_sql_error"] = str(bound_join_exc)
            grounding_metadata["deterministic_join_sql"] = deterministic_join_sql

    single_table_only = len(set(effective_mentioned_tables)) <= 1
    if single_table_only:
        deterministic_sql = _build_sql_from_bound_constraints(
            preferred_table=effective_preferred_table,
            bound_constraints=normalized_bound_constraints,
            user_request=user_request_original,
            schema_map=schema_map,
            mentioned_tables=effective_mentioned_tables,
        ) or ""
        if deterministic_sql:
            try:
                final_sql, changed, missing, df = _try_execute_sql(con=con, sql=deterministic_sql, schema_map=schema_map)
                return RouterResult(
                    route=RouteName.SQL_QUERY,
                    ok=True,
                    message=f"Query returned {len(df)} row(s).",
                    reason="Used deterministic categorical binding before model generation.",
                    sql=final_sql,
                    dataframe=df,
                    metadata={
                        **grounding_metadata,
                        "raw_model_output": "",
                        "initial_sql": deterministic_sql,
                        "auto_join_changed": changed,
                        "missing_columns": missing,
                        "row_count": len(df),
                        "execution_mode": "deterministic_bound_sql",
                        "rewrite_attempted": False,
                        "used_bound_sql": True,
                    },
                ).with_query(user_request_original)
            except Exception as bound_exc:
                grounding_metadata["deterministic_sql_error"] = str(bound_exc)
                grounding_metadata["deterministic_sql"] = deterministic_sql

    def _run_rewrite(first_error_text: str) -> RouterResult:
        nonlocal rewrite_raw, rewrite_sql, final_sql
        rewrite_raw = rewrite_failed_sql(
            schema_text=schema_text,
            categorical_text=categorical_text,
            user_request=generation_request,
            failed_sql=sql,
            error_text=first_error_text,
            model=rewrite_model,
        )
        rewrite_sql = _prepare_sql_candidate(rewrite_raw, categorical_index)
        if rewrite_sql == "-- I_DONT_KNOW":
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=False,
                message="SQL failed, and the repair model could not fix it.",
                reason="Initial SQL failed and repair returned I_DONT_KNOW.",
                sql=sql,
                error=first_error_text,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": raw,
                    "initial_sql": sql,
                    "rewrite_attempted": True,
                    "rewrite_model": rewrite_model,
                    "rewrite_model_output": rewrite_raw,
                    "rewrite_sql": rewrite_sql,
                    "execution_mode": "duckdb_then_repair_retry",
                    "used_bound_sql": False,
                },
            ).with_query(user_request_original)

        ok2, reason2 = is_select_only(rewrite_sql)
        if not ok2:
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=False,
                message=f"SQL failed, and the repair SQL was blocked: {reason2}",
                reason="Initial SQL failed and repair output did not pass validation.",
                sql=rewrite_sql,
                error=first_error_text,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": raw,
                    "initial_sql": sql,
                    "rewrite_attempted": True,
                    "rewrite_model": rewrite_model,
                    "rewrite_model_output": rewrite_raw,
                    "rewrite_sql": rewrite_sql,
                    "execution_mode": "duckdb_then_repair_retry",
                    "used_bound_sql": False,
                },
            ).with_query(user_request_original)

        try:
            final_sql, changed, missing, df = _try_execute_sql(con=con, sql=rewrite_sql, schema_map=schema_map)
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=True,
                message=f"Query returned {len(df)} row(s) after repair retry.",
                reason="Initial SQL failed, but the repair model succeeded.",
                sql=final_sql,
                dataframe=df,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": raw,
                    "initial_sql": sql,
                    "rewrite_attempted": True,
                    "rewrite_model": rewrite_model,
                    "rewrite_model_output": rewrite_raw,
                    "rewrite_sql": rewrite_sql,
                    "auto_join_changed": changed,
                    "missing_columns": missing,
                    "row_count": len(df),
                    "execution_mode": "duckdb_then_repair_retry",
                    "initial_error": first_error_text,
                    "used_bound_sql": False,
                },
            ).with_query(user_request_original)
        except Exception as second_exc:
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=False,
                message="SQL execution failed.",
                reason="Both the initial SQL and repair retry failed.",
                sql=rewrite_sql or sql or None,
                error=str(second_exc),
                metadata={
                    **grounding_metadata,
                    "raw_model_output": raw,
                    "initial_sql": sql,
                    "rewrite_attempted": True,
                    "rewrite_model": rewrite_model,
                    "rewrite_model_output": rewrite_raw,
                    "rewrite_sql": rewrite_sql,
                    "execution_mode": "duckdb_then_repair_retry",
                    "initial_error": first_error_text,
                    "rewrite_error": str(second_exc),
                    "used_bound_sql": False,
                },
            ).with_query(user_request_original)

    try:
        raw = nl_to_sql(
            model=model,
            schema_text=schema_text,
            categorical_text=categorical_text,
            user_request=generation_request,
        )
        sql = _prepare_sql_candidate(raw, categorical_index)

        if sql == "-- I_DONT_KNOW":
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=False,
                message="The model could not answer that from the current schema.",
                reason="nl_to_sql returned I_DONT_KNOW.",
                sql=sql,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": raw,
                    "rewrite_attempted": False,
                    "used_bound_sql": False,
                },
            ).with_query(user_request_original)

        ok, reason = is_select_only(sql)
        if not ok:
            return _run_rewrite(f"Validation failed before execution: {reason}")

        try:
            final_sql, changed, missing, df = _try_execute_sql(con=con, sql=sql, schema_map=schema_map)
            return RouterResult(
                route=RouteName.SQL_QUERY,
                ok=True,
                message=f"Query returned {len(df)} row(s).",
                reason="SQL route executed successfully.",
                sql=final_sql,
                dataframe=df,
                metadata={
                    **grounding_metadata,
                    "raw_model_output": raw,
                    "initial_sql": sql,
                    "auto_join_changed": changed,
                    "missing_columns": missing,
                    "row_count": len(df),
                    "execution_mode": "duckdb_first_pass",
                    "rewrite_attempted": False,
                    "used_bound_sql": False,
                },
            ).with_query(user_request_original)
        except Exception as first_exc:
            return _run_rewrite(str(first_exc))

    except Exception as exc:
        return RouterResult(
            route=RouteName.SQL_QUERY,
            ok=False,
            message="SQL execution failed.",
            reason="The SQL route was selected, but generation or execution raised an error.",
            sql=rewrite_sql or final_sql or sql or deterministic_join_sql or deterministic_sql or None,
            error=str(exc),
            metadata={
                **grounding_metadata,
                "raw_model_output": raw,
                "rewrite_model_output": rewrite_raw,
                "rewrite_model": rewrite_model,
                "execution_mode": "duckdb_then_repair_retry",
                "used_bound_sql": False,
            },
        ).with_query(user_request_original)
