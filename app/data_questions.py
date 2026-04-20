from __future__ import annotations

import re
from typing import Optional

from .router_types import RouteName, RouterContext, RouterResult


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _table_names(schema_map: dict[str, dict[str, str]]) -> list[str]:
    return sorted(schema_map.keys())


def _column_names(schema_map: dict[str, dict[str, str]], table_name: str) -> list[str]:
    return sorted(schema_map.get(table_name, {}).keys())


def _match_table_name(query: str, schema_map: dict[str, dict[str, str]]) -> Optional[str]:
    normalized_query = _normalize(query)

    explicit = re.search(r"\btable\s+([A-Za-z_][A-Za-z0-9_]*)\b", normalized_query)
    if explicit:
        candidate = explicit.group(1)
        for table_name in schema_map.keys():
            if table_name.lower() == candidate.lower():
                return table_name

    for table_name in schema_map.keys():
        if re.search(rf"\b{re.escape(table_name.lower())}\b", normalized_query):
            return table_name

    return None


def _match_column_name(
    query: str,
    schema_map: dict[str, dict[str, str]],
    preferred_table: str | None = None,
) -> tuple[str | None, str | None]:
    explicit = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", query)
    if explicit:
        raw_table = explicit.group(1)
        raw_col = explicit.group(2)
        for table_name, cols in schema_map.items():
            if table_name.lower() != raw_table.lower():
                continue
            for col_name in cols.keys():
                if col_name.lower() == raw_col.lower():
                    return table_name, col_name

    normalized_query = _normalize(query)

    if preferred_table:
        for col_name in schema_map.get(preferred_table, {}).keys():
            if re.search(rf"\b{re.escape(col_name.lower())}\b", normalized_query):
                return preferred_table, col_name

    matches: list[tuple[str, str]] = []
    for table_name, cols in schema_map.items():
        for col_name in cols.keys():
            if re.search(rf"\b{re.escape(col_name.lower())}\b", normalized_query):
                matches.append((table_name, col_name))

    if len(matches) == 1:
        return matches[0]

    return None, None


def _categorical_values(
    categorical_index: dict[tuple[str, str], list[str]],
    table_name: str | None,
    column_name: str,
) -> list[str]:
    values: list[str] = []

    for (table_key, col_key), vals in categorical_index.items():
        if col_key.lower() != column_name.lower():
            continue
        if table_name is not None and table_key.lower() != table_name.lower():
            continue

        for value in vals:
            s = str(value).strip()
            if s:
                values.append(s)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        lowered = value.lower()
        if lowered not in seen:
            seen.add(lowered)
            deduped.append(value)
    return deduped


def _preview_values(values: list[str], limit: int = 20) -> str:
    if not values:
        return "(none found)"
    preview = values[:limit]
    suffix = "" if len(values) <= limit else f" ... ({len(values)} total)"
    return ", ".join(preview) + suffix


def _find_related_tables(keyword: str, schema_map: dict[str, dict[str, str]]) -> list[tuple[str, int]]:
    keyword = keyword.lower().strip()
    scored: list[tuple[str, int]] = []

    for table_name, cols in schema_map.items():
        score = 0
        if keyword in table_name.lower():
            score += 5

        for col_name in cols.keys():
            if keyword == col_name.lower():
                score += 6
            elif keyword in col_name.lower():
                score += 3

        if score > 0:
            scored.append((table_name, score))

    scored.sort(key=lambda x: (-x[1], x[0].lower()))
    return scored


def _summarize_loaded_data(ctx: RouterContext) -> str:
    tables = _table_names(ctx.schema_map)
    if not tables:
        return "No tables are currently loaded."

    lines = [f"{len(tables)} table(s) loaded:"]
    for table_name in tables:
        col_count = len(ctx.schema_map.get(table_name, {}))
        lines.append(f"- {table_name} ({col_count} columns)")

    if ctx.source_files:
        lines.append("")
        lines.append("Loaded source files:")
        for path in ctx.source_files:
            lines.append(f"- {path}")

    return "\n".join(lines)


def answer_data_question(user_request: str, ctx: RouterContext) -> RouterResult:
    normalized_query = _normalize(user_request)

    if any(
        phrase in normalized_query
        for phrase in [
            "what tables",
            "which tables",
            "list tables",
            "show tables",
            "what is loaded",
            "what data is loaded",
            "loaded data",
            "schema",
            "summarize loaded data",
        ]
    ):
        return RouterResult(
            route=RouteName.DATA_QUESTION,
            ok=True,
            message=_summarize_loaded_data(ctx),
            reason="Answered using loaded schema metadata.",
            metadata={"table_count": len(ctx.schema_map)},
        ).with_query(user_request)

    if "columns" in normalized_query or "fields" in normalized_query or "column" in normalized_query:
        table_name = _match_table_name(user_request, ctx.schema_map)
        if table_name:
            columns = _column_names(ctx.schema_map, table_name)
            if columns:
                return RouterResult(
                    route=RouteName.DATA_QUESTION,
                    ok=True,
                    message=f'Columns in "{table_name}":\n- ' + "\n- ".join(columns),
                    reason="Answered with schema_map column names.",
                    metadata={"table": table_name, "column_count": len(columns)},
                ).with_query(user_request)

        table_name, column_name = _match_column_name(user_request, ctx.schema_map)
        if table_name and column_name:
            values = _categorical_values(ctx.categorical_index, table_name, column_name)
            return RouterResult(
                route=RouteName.DATA_QUESTION,
                ok=True,
                message=(
                    f'The column "{table_name}"."{column_name}" exists.\n'
                    f"Sample categorical values: {_preview_values(values)}"
                ),
                reason="Matched a specific column in the schema.",
                metadata={"table": table_name, "column": column_name},
            ).with_query(user_request)

        return RouterResult(
            route=RouteName.DATA_QUESTION,
            ok=False,
            message="I could not confidently match that table or column. Try using an exact table name or table.column.",
            reason="This looked like a metadata question, but the target was ambiguous.",
        ).with_query(user_request)

    if any(
        phrase in normalized_query
        for phrase in [
            "possible values",
            "distinct values",
            "what values",
            "allowed values",
            "categorical values",
        ]
    ):
        preferred_table = _match_table_name(user_request, ctx.schema_map)
        table_name, column_name = _match_column_name(user_request, ctx.schema_map, preferred_table)

        if column_name:
            values = _categorical_values(ctx.categorical_index, table_name, column_name)
            label = f'"{table_name}"."{column_name}"' if table_name else f'"{column_name}"'
            return RouterResult(
                route=RouteName.DATA_QUESTION,
                ok=True,
                message=f"Likely categorical values for {label}:\n{_preview_values(values)}",
                reason="Answered from categorical_index without SQL.",
                metadata={
                    "table": table_name,
                    "column": column_name,
                    "value_count": len(values),
                },
            ).with_query(user_request)

        return RouterResult(
            route=RouteName.DATA_QUESTION,
            ok=False,
            message="I could not tell which column you meant. Try an exact table.column reference.",
            reason="The request asked for values, but no column could be matched safely.",
        ).with_query(user_request)

    if "what table" in normalized_query or "which table" in normalized_query or "contains" in normalized_query:
        keyword_match = re.search(
            r"(?:contains?|has|for|with)\s+([A-Za-z_][A-Za-z0-9_]*)",
            normalized_query,
        )
        keyword = keyword_match.group(1) if keyword_match else ""

        if not keyword:
            table_name, column_name = _match_column_name(user_request, ctx.schema_map)
            if column_name:
                keyword = column_name

        if keyword:
            matches = _find_related_tables(keyword, ctx.schema_map)
            if matches:
                lines = [f"Likely tables related to '{keyword}':"]
                for table_name, _score in matches[:5]:
                    related_cols = [
                        col for col in ctx.schema_map[table_name].keys()
                        if keyword.lower() in col.lower()
                    ]
                    if related_cols:
                        lines.append(f'- {table_name} (matching columns: {", ".join(related_cols[:5])})')
                    else:
                        lines.append(f"- {table_name}")
                return RouterResult(
                    route=RouteName.DATA_QUESTION,
                    ok=True,
                    message="\n".join(lines),
                    reason="Found likely related tables by table and column names.",
                    metadata={"keyword": keyword, "matches": matches[:5]},
                ).with_query(user_request)

        return RouterResult(
            route=RouteName.DATA_QUESTION,
            ok=False,
            message="I could not find a strong table match for that keyword.",
            reason="This looked like a table-discovery question, but there was no strong schema match.",
        ).with_query(user_request)

    return RouterResult(
        route=RouteName.DATA_QUESTION,
        ok=True,
        message=_summarize_loaded_data(ctx),
        reason="Fell back to a general schema summary.",
        metadata={"table_count": len(ctx.schema_map)},
    ).with_query(user_request)