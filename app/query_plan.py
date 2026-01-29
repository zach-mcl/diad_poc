from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Op = Literal["=", "!=", "IN", "NOT IN", "LIKE", "ILIKE"]


@dataclass(frozen=True)
class ColumnRef:
    table: str
    column: str

    def sql(self, alias_map: dict[str, str]) -> str:
        a = alias_map[self.table]
        return f'{a}."{self.column}"'


@dataclass(frozen=True)
class Filter:
    col: ColumnRef
    op: Op
    value: str | list[str]

    def sql(self, alias_map: dict[str, str]) -> str:
        lhs = self.col.sql(alias_map)

        if self.op in ("IN", "NOT IN"):
            assert isinstance(self.value, list)
            vals = ", ".join([_sql_literal(v) for v in self.value])
            return f"{lhs} {self.op} ({vals})"

        assert isinstance(self.value, str)
        return f"{lhs} {self.op} {_sql_literal(self.value)}"


@dataclass
class Join:
    left_table: str
    left_col: str
    right_table: str
    right_col: str

    def sql(self, alias_map: dict[str, str]) -> str:
        la = alias_map[self.left_table]
        ra = alias_map[self.right_table]
        return f'lower(trim({la}."{self.left_col}")) = lower(trim({ra}."{self.right_col}"))'


@dataclass
class QueryPlan:
    selected: list[ColumnRef] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    joins: list[Join] = field(default_factory=list)

    def referenced_tables(self) -> set[str]:
        ts = {c.table for c in self.selected}
        ts |= {f.col.table for f in self.filters}
        for j in self.joins:
            ts.add(j.left_table)
            ts.add(j.right_table)
        return ts


def _sql_literal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def compile_sql(plan: QueryPlan) -> tuple[str, dict[str, str]]:
    tables = sorted(plan.referenced_tables())
    if not tables:
        raise ValueError("No tables referenced.")

    alias_map = {t: f"t{i}" for i, t in enumerate(tables)}

    if plan.selected:
        select_list = ",\n  ".join(
            [c.sql(alias_map) + f' AS "{c.table}.{c.column}"' for c in plan.selected]
        )
    else:
        base = tables[0]
        select_list = f'{alias_map[base]}.*'

    base_table = tables[0]
    sql = [f"SELECT\n  {select_list}\nFROM \"{base_table}\" {alias_map[base_table]}"]

    joined = {base_table}
    for j in plan.joins:
        if j.left_table in joined and j.right_table not in joined:
            new_t = j.right_table
        elif j.right_table in joined and j.left_table not in joined:
            new_t = j.left_table
        else:
            new_t = j.right_table

        sql.append(f'JOIN "{new_t}" {alias_map[new_t]} ON {j.sql(alias_map)}')
        joined.add(new_t)

    if plan.filters:
        where_clause = "\n  AND ".join([f.sql(alias_map) for f in plan.filters])
        sql.append("WHERE " + where_clause)

    return "\n".join(sql), alias_map
