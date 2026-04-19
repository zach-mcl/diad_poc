from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from .llm import nl_to_sql, rewrite_failed_sql
from .router_types import RouteName, RouterResult
from .validate import is_select_only, sanitize_sql, strip_ansi_and_control_chars, strip_code_fences

if TYPE_CHECKING:
    from .schema_aliases import GroundedQuery


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


def format_categorical_text(categorical_index: dict[tuple[str, str], list[str]]) -> str:
    lines: list[str] = []
    for (t, c) in sorted(categorical_index.keys(), key=lambda x: (x[0].lower(), x[1].lower())):
        vals = categorical_index[(t, c)]
        clean: list[str] = []
        seen = set()

        for v in vals:
            s = str(v).strip()
            if not s:
                continue
            if s not in seen:
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
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains_exact_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", text.lower()) is not None


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
    tokens = set(m.group(1) for m in re.finditer(r'(?<!\.)\b([A-Za-z_][A-Za-z0-9_]*)\b', sql))

    ignore = {
        "select", "from", "join", "left", "right", "inner", "outer", "full", "cross", "where",
        "group", "by", "order", "limit", "offset", "as", "on", "and", "or", "not", "null", "is",
        "in", "case", "when", "then", "else", "end", "distinct", "with", "union", "all", "true",
        "false", "like", "ilike", "between", "having", "lower", "upper", "trim", "ltrim", "rtrim",
        "cast", "date", "coalesce", "count", "sum", "avg", "min", "max", "exists", "intersect",
        "except",
    }
    tokens = {t for t in tokens if t.lower() not in ignore}

    missing: list[tuple[str, str]] = []
    for tok in tokens:
        owners = [t for t, cols in schema_map.items() if tok in cols]
        if len(owners) == 1:
            owner = owners[0]
            if owner not in present_tables:
                missing.append((tok, owner))

    out: list[tuple[str, str]] = []
    seen = set()
    for col, owner in missing:
        if (col, owner) not in seen:
            out.append((col, owner))
            seen.add((col, owner))
    return out


def qualify_base_columns_with_alias(
    sql: str,
    base_table: str,
    base_alias: str,
    schema_map: dict[str, dict[str, str]],
) -> str:
    out = sql
    for base_col in schema_map.get(base_table, {}).keys():
        pattern = rf'(?<![\."])\b{re.escape(base_col)}\b'
        out = re.sub(pattern, f'{base_alias}.{_quote_ident(base_col)}', out)
    return out


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

        left_col, right_col, score = candidates[0]

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
            rewritten = re.sub(
                rf'(?<![\."])\b{re.escape(col)}\b',
                f'o.{_quote_ident(col)}',
                rewritten,
            )

        rewritten = qualify_base_columns_with_alias(rewritten, base_table, "t", schema_map)

        print(
            f"\n[auto-join] Added JOIN {base_table} ↔ {owner_table} "
            f"using {left_col}={right_col} (overlap≈{score:.2f})"
        )

    return rewritten, changed


def repair_categorical_literals(
    sql: str,
    categorical_index: dict[tuple[str, str], list[str]],
) -> str:
    allowed_by_col: dict[str, set[str]] = {}
    for (_t, c), vals in categorical_index.items():
        allowed_by_col.setdefault(c, set())
        for v in vals:
            s = str(v).strip()
            if s:
                allowed_by_col[c].add(s)

    pattern = re.compile(
        r'(?P<lhs>(?:[A-Za-z_][A-Za-z0-9_]*\.)?"?(?P<col>[A-Za-z_][A-Za-z0-9_]*)"?)(?P<ws>\s*=\s*)\'(?P<val>[^\']*)\'',
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


def _prepare_sql_candidate(
    sql: str,
    categorical_index: dict[tuple[str, str], list[str]],
) -> str:
    sql = strip_ansi_and_control_chars(sql)
    sql = sanitize_sql(strip_code_fences(sql)).strip()
    sql = repair_categorical_literals(sql, categorical_index)
    return sql


def _try_execute_sql(
    con,
    sql: str,
    schema_map: dict[str, dict[str, str]],
) -> tuple[str, bool, list[tuple[str, str]], object]:
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


def _normalize_bound_constraints(
    bound_constraints: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for item in bound_constraints or []:
        table_name = str(item.get("table", "")).strip()
        column_name = str(item.get("column", "")).strip()
        value = str(item.get("value", "")).strip()
        source = str(item.get("source", "")).strip() or "router_binding"

        if not table_name or not column_name:
            continue

        key = (table_name, column_name, value)
        if key in seen:
            continue
        seen.add(key)

        cleaned.append(
            {
                "table": table_name,
                "column": column_name,
                "value": value,
                "source": source,
            }
        )

    return cleaned


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
                if token in {"notion", "okta"}:
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


def _infer_preferred_table(
    query: str,
    mentioned_tables: list[str],
) -> str | None:
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

            if re.search(
                rf"\b(users|people|rows|records|members)\s+in\s+{re.escape(token)}\b",
                normalized_query,
            ):
                score += 8

            if re.search(
                rf"\bin\s+{re.escape(token)}\b\s+who\b",
                normalized_query,
            ):
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
    q = user_request.lower()
    blockers = [
        " count ",
        " sum ",
        " avg ",
        " average ",
        " min ",
        " max ",
        " group ",
        " order ",
        " sort ",
        " distinct ",
        " top ",
        " bottom ",
        " join ",
        " compare ",
        " chart ",
        " plot ",
        " graph ",
    ]
    padded = f" {q} "
    return not any(token in padded for token in blockers)


def _infer_boolean_operator(user_request: str) -> str:
    lowered = f" {user_request.lower()} "
    has_and = " and " in lowered
    has_or = " or " in lowered

    if has_or and not has_and:
        return "OR"
    return "AND"


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


def _build_sql_from_bound_constraints(
    *,
    preferred_table: str | None,
    bound_constraints: list[dict[str, str]],
    user_request: str,
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
    clauses = _group_constraints_for_sql(constraints, operator)
    if not clauses:
        return None

    joiner = f" {operator} "
    where_clause = joiner.join(clauses)
    return f'SELECT * FROM {_quote_ident(preferred_table)} WHERE {where_clause}'


def _build_cross_table_bound_sql(
    con,
    schema_map: dict[str, dict[str, str]],
    *,
    user_request: str,
    mentioned_tables: list[str],
    preferred_table: str | None,
    bound_constraints: list[dict[str, str]],
) -> str | None:
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

    if not base_constraints and not other_constraints:
        return None

    operator = _infer_boolean_operator(user_request)

    base_clauses = _group_constraints_for_sql(base_constraints, operator, alias="t") if base_constraints else []
    other_clauses = _group_constraints_for_sql(other_constraints, operator, alias="o") if other_constraints else []

    if base_constraints and base_clauses is None:
        return None
    if other_constraints and other_clauses is None:
        return None

    candidates = find_join_candidates(
        con,
        schema_map,
        base_table,
        other_table,
        sample_limit=200,
        min_overlap=0.05,
    )
    if not candidates:
        return None

    left_col, right_col, _score = candidates[0]

    where_parts = list(base_clauses or []) + list(other_clauses or [])
    if not where_parts:
        return None

    joiner = f" {operator} "
    where_clause = joiner.join(where_parts)

    return (
        f'SELECT t.*\n'
        f'FROM {_quote_ident(base_table)} t\n'
        f'JOIN {_quote_ident(other_table)} o\n'
        f'  ON lower(trim(t.{_quote_ident(left_col)})) = lower(trim(o.{_quote_ident(right_col)}))\n'
        f'WHERE {where_clause}'
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
        "top_grounding_hits": {
            "tables": [],
            "columns": [],
            "values": [],
        },
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

    normalized_bound_constraints = _normalize_bound_constraints(bound_constraints)

    effective_mentioned_tables = list(mentioned_tables or [])
    if not effective_mentioned_tables:
        effective_mentioned_tables = _infer_mentioned_tables(
            user_request_original,
            schema_map,
            normalized_bound_constraints,
        )

    for item in normalized_bound_constraints:
        table_name = item["table"]
        if table_name not in effective_mentioned_tables:
            effective_mentioned_tables.append(table_name)

    inferred_preferred = _infer_preferred_table(
        user_request_original,
        effective_mentioned_tables,
    )
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
            final_sql, changed, missing, df = _try_execute_sql(
                con=con,
                sql=deterministic_join_sql,
                schema_map=schema_map,
            )

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
        ) or ""

        if deterministic_sql:
            try:
                final_sql, changed, missing, df = _try_execute_sql(
                    con=con,
                    sql=deterministic_sql,
                    schema_map=schema_map,
                )

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
            final_sql, changed, missing, df = _try_execute_sql(
                con=con,
                sql=rewrite_sql,
                schema_map=schema_map,
            )

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
            final_sql, changed, missing, df = _try_execute_sql(
                con=con,
                sql=sql,
                schema_map=schema_map,
            )

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