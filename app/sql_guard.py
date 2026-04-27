from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass
class SqlGuardResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alias_to_table: dict[str, str] = field(default_factory=dict)
    tables: list[str] = field(default_factory=list)

    def feedback(self, schema_map: dict[str, dict[str, str]]) -> str:
        lines: list[str] = []

        if self.errors:
            lines.append("SCHEMA VALIDATION ERRORS:")
            for error in self.errors:
                lines.append(f"- {error}")

        if self.warnings:
            lines.append("SCHEMA VALIDATION WARNINGS:")
            for warning in self.warnings:
                lines.append(f"- {warning}")

        if self.alias_to_table:
            lines.append("ALIASES IN FAILED SQL:")
            for alias, table in sorted(self.alias_to_table.items()):
                columns = ", ".join(schema_map.get(table, {}).keys())
                lines.append(f'- {alias} maps to "{table}" with columns: {columns}')

        return "\n".join(lines).strip()


def _clean_identifier(name: str) -> str:
    name = str(name or "").strip()
    if "." in name:
        name = name.split(".")[-1]
    return name.strip('"')


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _extract_aliases(sql: str, schema_map: dict[str, dict[str, str]]) -> tuple[dict[str, str], list[str]]:
    alias_to_table: dict[str, str] = {}
    tables: list[str] = []

    pattern = re.compile(
        r'\b(?:FROM|JOIN)\s+'
        r'(?P<table>(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)(?:\.(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*))?)'
        r'(?:\s+(?:AS\s+)?(?P<alias>"?[_A-Za-z][_A-Za-z0-9]*"?))?',
        flags=re.IGNORECASE,
    )

    stop_aliases = {
        "on", "where", "join", "left", "right", "inner", "outer", "full",
        "cross", "group", "order", "limit", "having", "union"
    }

    for match in pattern.finditer(sql):
        table = _clean_identifier(match.group("table"))
        alias = match.group("alias")

        if table not in schema_map:
            tables.append(table)
            continue

        tables.append(table)

        if alias:
            alias_clean = alias.strip('"')
            if alias_clean.lower() in stop_aliases:
                alias_clean = table
        else:
            alias_clean = table

        alias_to_table[alias_clean] = table

    return alias_to_table, tables


def _column_exists(schema_map: dict[str, dict[str, str]], table: str, column: str) -> bool:
    return column in schema_map.get(table, {})


def _find_column_owners(schema_map: dict[str, dict[str, str]], column: str) -> list[str]:
    return [
        table
        for table, columns in schema_map.items()
        if column in columns
    ]


def _extract_qualified_refs(sql: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []

    quoted_pattern = re.compile(
        r'(?P<alias>"?[_A-Za-z][_A-Za-z0-9]*"?)\s*\.\s*"(?P<column>[^"]+)"'
    )
    bare_pattern = re.compile(
        r'(?P<alias>\b[_A-Za-z][_A-Za-z0-9]*)\s*\.\s*(?P<column>\b[_A-Za-z][_A-Za-z0-9]*)'
    )

    for match in quoted_pattern.finditer(sql):
        refs.append((match.group("alias").strip('"'), match.group("column").strip('"')))

    for match in bare_pattern.finditer(sql):
        alias = match.group("alias").strip('"')
        column = match.group("column").strip('"')
        if (alias, column) not in refs:
            refs.append((alias, column))

    return refs


def _extract_output_select_text(sql: str) -> str:
    match = re.search(r'\bSELECT\b(?P<select>.*?)\bFROM\b', sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group("select")


def _looks_like_duplicate_accidental_table_use(sql: str, table_counts: dict[str, int]) -> bool:
    select_text = _extract_output_select_text(sql)
    if not select_text:
        return False

    # If the same table appears multiple times with different aliases and the selected
    # columns are not self-join style comparisons, this is usually hallucinated duplication.
    for table, count in table_counts.items():
        if count >= 2:
            return True

    return False


def validate_sql_against_schema(sql: str, schema_map: dict[str, dict[str, str]]) -> SqlGuardResult:
    errors: list[str] = []
    warnings: list[str] = []

    alias_to_table, tables = _extract_aliases(sql, schema_map)

    if not tables:
        errors.append("No FROM/JOIN table could be identified.")

    for table in tables:
        if table not in schema_map:
            errors.append(f'Table "{table}" does not exist in the loaded schema.')

    table_counts: dict[str, int] = {}
    for table in tables:
        if table in schema_map:
            table_counts[table] = table_counts.get(table, 0) + 1

    if _looks_like_duplicate_accidental_table_use(sql, table_counts):
        duplicates = [table for table, count in table_counts.items() if count >= 2]
        warnings.append(
            "The same table appears more than once: "
            + ", ".join(f'"{table}"' for table in duplicates)
            + ". Only keep duplicate table joins when the user clearly asked for a self-join."
        )

    for alias, column in _extract_qualified_refs(sql):
        if alias not in alias_to_table:
            # Skip common schema prefixes or function-like false positives.
            if alias.lower() in {"date", "time", "timestamp"}:
                continue
            errors.append(f'Alias "{alias}" is used but is not defined in FROM/JOIN.')
            continue

        table = alias_to_table[alias]
        if not _column_exists(schema_map, table, column):
            owners = _find_column_owners(schema_map, column)
            if owners:
                owner_text = ", ".join(f'"{owner}"' for owner in owners)
                errors.append(
                    f'Alias "{alias}" maps to "{table}", but "{table}" does not have column "{column}". '
                    f'Column "{column}" exists on: {owner_text}.'
                )
            else:
                available = ", ".join(schema_map.get(table, {}).keys())
                errors.append(
                    f'Alias "{alias}" maps to "{table}", but column "{column}" does not exist anywhere. '
                    f'Columns on "{table}": {available}.'
                )

    return SqlGuardResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        alias_to_table=alias_to_table,
        tables=tables,
    )


def repair_sql_alias_columns(sql: str, schema_map: dict[str, dict[str, str]]) -> tuple[str, bool, list[str]]:
    """Small deterministic repair for the common model mistake:
    alias.column is wrong, but the same column exists on exactly one other alias.
    """
    guard = validate_sql_against_schema(sql, schema_map)
    if guard.ok:
        return sql, False, []

    replacements: dict[tuple[str, str], str] = {}
    notes: list[str] = []

    for alias, column in _extract_qualified_refs(sql):
        if alias not in guard.alias_to_table:
            continue

        table = guard.alias_to_table[alias]
        if _column_exists(schema_map, table, column):
            continue

        candidate_aliases = [
            other_alias
            for other_alias, other_table in guard.alias_to_table.items()
            if _column_exists(schema_map, other_table, column)
        ]

        if len(candidate_aliases) == 1:
            replacements[(alias, column)] = candidate_aliases[0]
            notes.append(
                f'Moved "{alias}"."{column}" to "{candidate_aliases[0]}"."{column}" because that alias owns the column.'
            )

    if not replacements:
        return sql, False, notes

    repaired = sql

    for (bad_alias, column), good_alias in replacements.items():
        repaired = re.sub(
            rf'"?{re.escape(bad_alias)}"?\s*\.\s*"{re.escape(column)}"',
            f'{good_alias}.{_quote_ident(column)}',
            repaired,
        )
        repaired = re.sub(
            rf'\b{re.escape(bad_alias)}\s*\.\s*\b{re.escape(column)}\b',
            f'{good_alias}.{_quote_ident(column)}',
            repaired,
        )

    return repaired, repaired != sql, notes
