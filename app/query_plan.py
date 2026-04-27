from __future__ import annotations

import json
import re
from typing import Any


VALID_ACTIONS = {"select", "count"}
VALID_JOIN_TYPES = {"inner", "left"}
VALID_FILTER_OPERATORS = {
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "contains",
    "starts_with",
    "ends_with",
    "in",
    "not_in",
    "is_null",
    "is_not_null",
}
VALID_AGGREGATES = {"count", "count_distinct", "sum", "avg", "min", "max"}

DEFAULT_LIMIT = 200
MAX_LIMIT = 500


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"

    if isinstance(value, (int, float)):
        return str(value)

    return "'" + str(value).replace("'", "''") + "'"


def _normalize_text_sql(expr: str) -> str:
    return f"lower(trim(cast({expr} as varchar)))"


def _is_string_type(type_name: str | None) -> bool:
    t = str(type_name or "").lower()
    return any(token in t for token in ["char", "text", "string", "varchar"])


def strip_json_fences(text: str) -> str:
    text = str(text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    return text


def _extract_first_json_object(text: str) -> str:
    text = strip_json_fences(text)

    first = text.find("{")
    last = text.rfind("}")

    if first == -1 or last == -1 or last <= first:
        raise ValueError("Could not find a JSON object in model output.")

    return text[first:last + 1]


def parse_query_plan(raw: str) -> dict[str, Any]:
    cleaned = strip_json_fences(raw)

    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError:
        plan = json.loads(_extract_first_json_object(cleaned))

    if not isinstance(plan, dict):
        raise ValueError("Query plan must be a JSON object.")

    return plan


def normalize_query_plan(plan: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(plan)

    normalized["cannot_answer"] = bool(normalized.get("cannot_answer", False))
    normalized["action"] = str(normalized.get("action", "select")).lower()
    normalized["base_table"] = normalized.get("base_table")
    normalized["distinct"] = bool(normalized.get("distinct", False))
    normalized["select"] = normalized.get("select") or []
    normalized["joins"] = normalized.get("joins") or []
    normalized["filters"] = normalized.get("filters") or []
    normalized["group_by"] = normalized.get("group_by") or []
    normalized["order_by"] = normalized.get("order_by") or []

    raw_limit = normalized.get("limit", DEFAULT_LIMIT)
    if raw_limit is None:
        normalized["limit"] = None
    else:
        try:
            raw_limit = int(raw_limit)
        except Exception as exc:
            raise ValueError(f"Invalid limit: {raw_limit}") from exc

        if raw_limit <= 0:
            raise ValueError("limit must be positive if provided.")

        normalized["limit"] = min(raw_limit, MAX_LIMIT)

    if normalized["cannot_answer"]:
        normalized["select"] = []
        normalized["joins"] = []
        normalized["filters"] = []
        normalized["group_by"] = []
        normalized["order_by"] = []
        normalized["limit"] = None

    if not normalized["cannot_answer"] and not normalized["select"]:
        if normalized["action"] == "count":
            normalized["select"] = [
                {
                    "kind": "aggregate",
                    "function": "count",
                    "table": normalized["base_table"],
                    "column": "*",
                    "alias": "count",
                }
            ]
        else:
            normalized["select"] = [
                {
                    "kind": "column",
                    "table": normalized["base_table"],
                    "column": "*",
                }
            ]

    return normalized


def _validate_table(schema_map: dict[str, dict[str, str]], table: str | None) -> None:
    if not table or table not in schema_map:
        raise ValueError(f"Invalid table: {table}")


def _validate_column(
    schema_map: dict[str, dict[str, str]],
    table: str,
    column: str | None,
    *,
    allow_star: bool = False,
) -> None:
    if allow_star and column == "*":
        return

    if not column or column not in schema_map[table]:
        raise ValueError(f"Invalid column: {table}.{column}")


def validate_query_plan(
    plan: dict[str, Any],
    schema_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if plan.get("cannot_answer"):
        return plan

    action = plan.get("action")
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}")

    base_table = plan.get("base_table")
    _validate_table(schema_map, base_table)

    for join in plan.get("joins", []):
        join_type = str(join.get("join_type", "inner")).lower()
        if join_type not in VALID_JOIN_TYPES:
            raise ValueError(f"Invalid join_type: {join_type}")

        left_table = join.get("left_table")
        right_table = join.get("right_table")
        left_column = join.get("left_column")
        right_column = join.get("right_column")

        _validate_table(schema_map, left_table)
        _validate_table(schema_map, right_table)
        _validate_column(schema_map, left_table, left_column)
        _validate_column(schema_map, right_table, right_column)

    for item in plan.get("select", []):
        kind = item.get("kind", "column")

        if kind == "column":
            table = item.get("table", base_table)
            column = item.get("column")
            _validate_table(schema_map, table)
            _validate_column(schema_map, table, column, allow_star=True)

        elif kind == "aggregate":
            function = str(item.get("function", "")).lower()
            table = item.get("table", base_table)
            column = item.get("column")

            if function not in VALID_AGGREGATES:
                raise ValueError(f"Invalid aggregate function: {function}")

            _validate_table(schema_map, table)

            if function in {"count", "count_distinct"} and column == "*":
                pass
            else:
                _validate_column(schema_map, table, column)

        else:
            raise ValueError(f"Invalid select kind: {kind}")

    for filt in plan.get("filters", []):
        table = filt.get("table", base_table)
        column = filt.get("column")
        operator = str(filt.get("operator", "")).lower()

        _validate_table(schema_map, table)
        _validate_column(schema_map, table, column)

        if operator not in VALID_FILTER_OPERATORS:
            raise ValueError(f"Invalid filter operator: {operator}")

        if operator in {"in", "not_in"} and not isinstance(filt.get("value"), list):
            raise ValueError(f"Operator {operator} requires list value.")

    for ref in plan.get("group_by", []):
        table = ref.get("table", base_table)
        column = ref.get("column")

        _validate_table(schema_map, table)
        _validate_column(schema_map, table, column)

    for item in plan.get("order_by", []):
        direction = str(item.get("direction", "ASC")).upper()
        by = item.get("by", "column")

        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"Invalid order_by direction: {direction}")

        if by == "alias":
            alias = item.get("alias")
            if not alias:
                raise ValueError("order_by alias entry missing alias.")
        else:
            table = item.get("table", base_table)
            column = item.get("column")
            _validate_table(schema_map, table)
            _validate_column(schema_map, table, column)

    return plan


def _build_alias_map(plan: dict[str, Any]) -> dict[str, str]:
    base_table = plan["base_table"]
    alias_map: dict[str, str] = {base_table: "t0"}

    next_index = 1
    for join in plan.get("joins", []):
        right_table = join["right_table"]
        left_table = join["left_table"]

        if left_table not in alias_map:
            alias_map[left_table] = f"t{next_index}"
            next_index += 1

        if right_table not in alias_map:
            alias_map[right_table] = f"t{next_index}"
            next_index += 1

    return alias_map


def _column_sql(table: str, column: str, alias_map: dict[str, str]) -> str:
    if column == "*":
        return f"{alias_map[table]}.*"
    return f"{alias_map[table]}.{quote_ident(column)}"


def _default_select_alias(item: dict[str, Any]) -> str:
    kind = item.get("kind", "column")

    if kind == "column":
        return f'{item["table"]}.{item["column"]}'

    function = str(item["function"]).lower()
    column = item["column"]
    if column == "*":
        return function
    return f"{function}_{item['table']}_{column}"


def _build_select_expr(item: dict[str, Any], alias_map: dict[str, str]) -> str:
    kind = item.get("kind", "column")
    alias = item.get("alias") or _default_select_alias(item)

    if kind == "column":
        expr = _column_sql(item["table"], item["column"], alias_map)
        return f"{expr} AS {quote_ident(alias)}"

    function = str(item["function"]).lower()
    table = item["table"]
    column = item["column"]

    if column == "*":
        target = "*"
    else:
        target = _column_sql(table, column, alias_map)

    if function == "count":
        expr = f"COUNT({target})"
    elif function == "count_distinct":
        expr = f"COUNT(DISTINCT {target})"
    elif function == "sum":
        expr = f"SUM({target})"
    elif function == "avg":
        expr = f"AVG({target})"
    elif function == "min":
        expr = f"MIN({target})"
    elif function == "max":
        expr = f"MAX({target})"
    else:
        raise ValueError(f"Unsupported aggregate function: {function}")

    return f"{expr} AS {quote_ident(alias)}"


def _build_filter_expr(
    filt: dict[str, Any],
    alias_map: dict[str, str],
    schema_map: dict[str, dict[str, str]],
) -> str:
    table = filt["table"]
    column = filt["column"]
    operator = str(filt["operator"]).lower()
    value = filt.get("value")
    lhs = _column_sql(table, column, alias_map)

    if operator == "is_null":
        return f"{lhs} IS NULL"

    if operator == "is_not_null":
        return f"{lhs} IS NOT NULL"

    col_type = schema_map[table][column]
    lhs_text = _normalize_text_sql(lhs)

    if operator == "contains":
        return f"{lhs_text} LIKE {_normalize_text_sql(sql_literal('%' + str(value) + '%'))}"

    if operator == "starts_with":
        return f"{lhs_text} LIKE {_normalize_text_sql(sql_literal(str(value) + '%'))}"

    if operator == "ends_with":
        return f"{lhs_text} LIKE {_normalize_text_sql(sql_literal('%' + str(value)))}"

    if operator == "in":
        items = ", ".join(sql_literal(v) for v in value)
        return f"{lhs} IN ({items})"

    if operator == "not_in":
        items = ", ".join(sql_literal(v) for v in value)
        return f"{lhs} NOT IN ({items})"

    if _is_string_type(col_type) and isinstance(value, str):
        return f"{_normalize_text_sql(lhs)} {operator} {_normalize_text_sql(sql_literal(value))}"

    return f"{lhs} {operator} {sql_literal(value)}"


def _build_join_expr(
    join: dict[str, Any],
    alias_map: dict[str, str],
    schema_map: dict[str, dict[str, str]],
) -> str:
    join_type = str(join.get("join_type", "inner")).upper()
    left_table = join["left_table"]
    left_column = join["left_column"]
    right_table = join["right_table"]
    right_column = join["right_column"]

    left_expr = _column_sql(left_table, left_column, alias_map)
    right_expr = _column_sql(right_table, right_column, alias_map)

    left_type = schema_map[left_table][left_column]
    right_type = schema_map[right_table][right_column]

    if _is_string_type(left_type) or _is_string_type(right_type):
        on_expr = f"{_normalize_text_sql(left_expr)} = {_normalize_text_sql(right_expr)}"
    else:
        on_expr = f"{left_expr} = {right_expr}"

    return (
        f"{join_type} JOIN {quote_ident(right_table)} {alias_map[right_table]} "
        f"ON {on_expr}"
    )


def build_sql_from_plan(
    plan: dict[str, Any],
    schema_map: dict[str, dict[str, str]],
) -> str:
    if plan.get("cannot_answer"):
        raise ValueError("Cannot build SQL for a cannot_answer plan.")

    alias_map = _build_alias_map(plan)
    base_table = plan["base_table"]
    select_items = plan.get("select", [])

    select_sql = ", ".join(_build_select_expr(item, alias_map) for item in select_items)

    parts = [
        f"SELECT {'DISTINCT ' if plan.get('distinct') else ''}{select_sql}",
        f"FROM {quote_ident(base_table)} {alias_map[base_table]}",
    ]

    for join in plan.get("joins", []):
        parts.append(_build_join_expr(join, alias_map, schema_map))

    filters = plan.get("filters", [])
    if filters:
        where_sql = " AND ".join(
            _build_filter_expr(filt, alias_map, schema_map) for filt in filters
        )
        parts.append(f"WHERE {where_sql}")

    group_by = plan.get("group_by", [])
    if group_by:
        group_sql = ", ".join(
            _column_sql(ref["table"], ref["column"], alias_map)
            for ref in group_by
        )
        parts.append(f"GROUP BY {group_sql}")

    order_by = plan.get("order_by", [])
    if order_by:
        order_parts = []
        for item in order_by:
            direction = str(item.get("direction", "ASC")).upper()
            if item.get("by", "column") == "alias":
                order_parts.append(f'{quote_ident(item["alias"])} {direction}')
            else:
                order_parts.append(
                    f'{_column_sql(item["table"], item["column"], alias_map)} {direction}'
                )
        parts.append("ORDER BY " + ", ".join(order_parts))

    limit = plan.get("limit")
    if limit is not None:
        parts.append(f"LIMIT {int(limit)}")

    return "\n".join(parts)