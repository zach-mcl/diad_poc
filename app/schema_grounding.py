from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
from typing import Any

from .schema_aliases import ground_user_query


_TABLE_STOPWORDS = {
    "test", "export", "sheet", "sheet1", "sheet2", "sheet3", "table", "data"
}

_IDENTIFIER_HINTS = {
    "email", "user_email", "mail", "username", "user", "id", "user_id",
    "name", "full_name", "employee", "employee_id"
}


@dataclass
class GroundedConstraint:
    table: str
    column: str
    value: str
    source: str
    score: float = 1.0


@dataclass
class GroundedJoin:
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    score: float
    source: str = "schema_join_inference"


@dataclass
class SchemaGrounding:
    raw_query: str
    grounded_query_text: str
    preferred_table: str | None = None
    mentioned_tables: list[str] = field(default_factory=list)
    bound_constraints: list[GroundedConstraint] = field(default_factory=list)
    selected_columns: list[tuple[str, str]] = field(default_factory=list)
    likely_join_pairs: list[GroundedJoin] = field(default_factory=list)
    alias_replacements: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    used_llm_fallback: bool = False

    def constraints_as_dicts(self) -> list[dict[str, str]]:
        return [
            {
                "table": item.table,
                "column": item.column,
                "value": item.value,
                "source": item.source,
            }
            for item in self.bound_constraints
        ]

    def joins_as_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "left_table": item.left_table,
                "left_column": item.left_column,
                "right_table": item.right_table,
                "right_column": item.right_column,
                "score": item.score,
                "source": item.source,
            }
            for item in self.likely_join_pairs
        ]

    def metadata(self) -> dict[str, Any]:
        return {
            "schema_grounding": {
                "raw_query": self.raw_query,
                "grounded_query_text": self.grounded_query_text,
                "preferred_table": self.preferred_table,
                "mentioned_tables": self.mentioned_tables,
                "bound_constraints": self.constraints_as_dicts(),
                "selected_columns": [
                    {"table": table, "column": column}
                    for table, column in self.selected_columns
                ],
                "likely_join_pairs": self.joins_as_dicts(),
                "alias_replacements": self.alias_replacements,
                "confidence": self.confidence,
                "used_llm_fallback": self.used_llm_fallback,
            }
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _tokens(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-zA-Z0-9]+", text.lower()) if tok]


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(term.lower())}(?![A-Za-z0-9_])", text) is not None


def _similarity(a: str, b: str) -> float:
    a = a.lower().replace("_", " ").strip()
    b = b.lower().replace("_", " ").strip()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _table_keywords(table_name: str) -> list[str]:
    out: list[str] = []
    for token in _tokens(table_name):
        if token not in _TABLE_STOPWORDS and token not in out:
            out.append(token)
    return out


def _column_words(column_name: str) -> set[str]:
    return set(_tokens(column_name))


def _score_table(query: str, table_name: str) -> float:
    q = _normalize(query)
    score = 0.0

    if _contains_term(q, table_name.lower()):
        score += 1.0

    for token in _table_keywords(table_name):
        if _contains_term(q, token):
            score += 0.45
        else:
            score += max((_similarity(token, qtok) for qtok in _tokens(q)), default=0.0) * 0.15

        if re.search(rf"\b(users|people|rows|records|members)\s+in\s+{re.escape(token)}\b", q):
            score += 0.75
        if re.search(rf"\bfrom\s+{re.escape(token)}\b", q):
            score += 0.6
        if re.search(rf"\bin\s+{re.escape(token)}\b\s+who\b", q):
            score += 0.75

    return score


def _infer_mentioned_tables(query: str, schema_map: dict[str, dict[str, str]]) -> list[str]:
    scored = [
        (table, _score_table(query, table))
        for table in schema_map.keys()
    ]
    scored = [(table, score) for table, score in scored if score >= 0.35]
    scored.sort(key=lambda item: (-item[1], item[0].lower()))
    return [table for table, _ in scored]


def _infer_preferred_table(query: str, mentioned_tables: list[str]) -> str | None:
    if not mentioned_tables:
        return None
    if len(mentioned_tables) == 1:
        return mentioned_tables[0]

    q = _normalize(query)
    scored: list[tuple[float, str]] = []

    for table in mentioned_tables:
        score = 0.0
        for token in _table_keywords(table):
            if re.search(rf"\b(users|people|rows|records|members)\s+in\s+{re.escape(token)}\b", q):
                score += 2.0
            if re.search(rf"\bfind\s+.*\s+in\s+{re.escape(token)}\b", q):
                score += 1.0
            if re.search(rf"\bfrom\s+{re.escape(token)}\b", q):
                score += 1.0
            if re.search(rf"\bin\s+{re.escape(token)}\b\s+who\b", q):
                score += 1.5
        scored.append((score, table))

    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    if scored[0][0] > 0:
        return scored[0][1]

    return mentioned_tables[0]


def _infer_selected_columns(
    query: str,
    schema_map: dict[str, dict[str, str]],
    mentioned_tables: list[str],
) -> list[tuple[str, str]]:
    q = _normalize(query)
    found: list[tuple[str, str]] = []
    search_tables = mentioned_tables or list(schema_map.keys())

    for table in search_tables:
        for column in schema_map.get(table, {}).keys():
            col_norm = column.lower()
            if _contains_term(q, col_norm):
                found.append((table, column))
                continue

            for word in _column_words(column):
                if len(word) >= 3 and _contains_term(q, word):
                    found.append((table, column))
                    break

    seen = set()
    out = []
    for item in found:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _value_matches_query(query: str, value: str) -> tuple[bool, float, str]:
    q = _normalize(query)
    v = _normalize(value)
    if not v:
        return False, 0.0, ""

    if _contains_term(q, v):
        return True, 1.0, "categorical_exact_match"

    value_tokens = _tokens(v)
    if value_tokens and all(_contains_term(q, tok) for tok in value_tokens):
        return True, 0.9, "categorical_token_match"

    best = max((_similarity(v, qtok) for qtok in _tokens(q)), default=0.0)
    if best >= 0.88:
        return True, best, "categorical_fuzzy_match"

    return False, 0.0, ""


def _column_context_score(query: str, table: str, column: str) -> float:
    q = _normalize(query)
    score = 0.0

    if _contains_term(q, table.lower()):
        score += 0.2
    for token in _table_keywords(table):
        if _contains_term(q, token):
            score += 0.25

    for word in _column_words(column):
        if len(word) >= 3 and _contains_term(q, word):
            score += 0.45

    return score


def _infer_constraints(
    query: str,
    categorical_index: dict[tuple[str, str], list[str]],
    preferred_table: str | None,
    mentioned_tables: list[str],
) -> list[GroundedConstraint]:
    matches: list[GroundedConstraint] = []

    for (table, column), values in categorical_index.items():
        for raw_value in values:
            value = str(raw_value).strip()
            matched, value_score, source = _value_matches_query(query, value)
            if not matched:
                continue

            owner_score = _column_context_score(query, table, column)
            if preferred_table and table == preferred_table:
                owner_score += 0.1
            if table in mentioned_tables:
                owner_score += 0.2

            total = value_score + owner_score
            matches.append(
                GroundedConstraint(
                    table=table,
                    column=column,
                    value=value,
                    source=source,
                    score=round(total, 4),
                )
            )

    grouped: dict[str, list[GroundedConstraint]] = {}
    for item in matches:
        grouped.setdefault(_normalize(item.value), []).append(item)

    final: list[GroundedConstraint] = []
    for _, items in grouped.items():
        items.sort(key=lambda item: (-item.score, item.table, item.column))
        if len(items) == 1 or items[0].score > items[1].score:
            final.append(items[0])

    seen = set()
    deduped = []
    for item in final:
        key = (item.table, item.column, item.value)
        if key not in seen:
            deduped.append(item)
            seen.add(key)

    return deduped


def _join_column_score(left_col: str, right_col: str) -> float:
    left = left_col.lower()
    right = right_col.lower()
    left_words = _column_words(left)
    right_words = _column_words(right)

    if left == right:
        return 1.0

    if left.replace("_", "") == right.replace("_", ""):
        return 0.95

    if "email" in left_words and "email" in right_words:
        return 0.9

    if left_words & right_words:
        score = 0.45 + (len(left_words & right_words) / max(len(left_words | right_words), 1))
        if left_words & _IDENTIFIER_HINTS or right_words & _IDENTIFIER_HINTS:
            score += 0.2
        return min(score, 0.85)

    sim = _similarity(left, right)
    if sim >= 0.78:
        return sim * 0.75

    return 0.0


def _infer_likely_joins(
    schema_map: dict[str, dict[str, str]],
    mentioned_tables: list[str],
) -> list[GroundedJoin]:
    joins: list[GroundedJoin] = []
    if len(mentioned_tables) < 2:
        return joins

    for i, left_table in enumerate(mentioned_tables):
        for right_table in mentioned_tables[i + 1:]:
            best: GroundedJoin | None = None
            for left_col in schema_map.get(left_table, {}).keys():
                for right_col in schema_map.get(right_table, {}).keys():
                    score = _join_column_score(left_col, right_col)
                    if score <= 0:
                        continue
                    candidate = GroundedJoin(
                        left_table=left_table,
                        left_column=left_col,
                        right_table=right_table,
                        right_column=right_col,
                        score=round(score, 4),
                    )
                    if best is None or candidate.score > best.score:
                        best = candidate
            if best and best.score >= 0.55:
                joins.append(best)

    joins.sort(key=lambda item: -item.score)
    return joins


def _constraint_text(constraints: list[GroundedConstraint]) -> str:
    if not constraints:
        return ""
    parts = []
    for item in constraints:
        safe_value = item.value.replace("'", "''")
        parts.append(f"{item.table}.{item.column} = '{safe_value}'")
    return "; filters: " + ", ".join(parts)


def _join_text(joins: list[GroundedJoin]) -> str:
    if not joins:
        return ""
    parts = [
        f"{j.left_table}.{j.left_column} = {j.right_table}.{j.right_column}"
        for j in joins
    ]
    return "; joins: " + ", ".join(parts)


def _selected_columns_text(columns: list[tuple[str, str]]) -> str:
    if not columns:
        return ""
    return "; selected columns mentioned: " + ", ".join(
        f"{table}.{column}" for table, column in columns
    )


def _build_grounded_query_text(
    raw_query: str,
    preferred_table: str | None,
    mentioned_tables: list[str],
    constraints: list[GroundedConstraint],
    selected_columns: list[tuple[str, str]],
    joins: list[GroundedJoin],
) -> str:
    parts = [raw_query.strip()]

    if preferred_table:
        parts.append(f"Return rows from {preferred_table} as the main output table.")

    if mentioned_tables:
        parts.append("Schema tables referenced: " + ", ".join(mentioned_tables) + ".")

    if joins:
        join_sentences = [
            f"Join {j.left_table} to {j.right_table} on {j.left_column} = {j.right_column}"
            for j in joins
        ]
        parts.append(". ".join(join_sentences) + ".")

    if constraints:
        constraint_sentences = [
            f"Apply filter {c.table}.{c.column} = '{c.value}'"
            for c in constraints
        ]
        parts.append(". ".join(constraint_sentences) + ".")

    if selected_columns:
        parts.append(
            "Columns directly mentioned: "
            + ", ".join(f"{table}.{column}" for table, column in selected_columns)
            + "."
        )

    parts.append(
        "Use the exact table names, column names, join keys, and categorical values above."
    )

    return " ".join(part for part in parts if part).strip()


def ground_schema_for_sql(
    *,
    user_request: str,
    ctx,
    llm_fallback_model: str | None = None,
) -> SchemaGrounding:
    alias_grounding = ground_user_query(user_request, ctx.alias_index) if getattr(ctx, "alias_index", None) else None
    alias_query = (
        alias_grounding.rewritten_query.strip()
        if alias_grounding and alias_grounding.rewritten_query.strip()
        else user_request
    )

    mentioned_tables = _infer_mentioned_tables(alias_query, ctx.schema_map)

    if alias_grounding:
        for hit in alias_grounding.table_hits:
            table = hit.key
            if table in ctx.schema_map and table not in mentioned_tables:
                mentioned_tables.append(table)

    preferred_table = _infer_preferred_table(alias_query, mentioned_tables)

    constraints = _infer_constraints(
        alias_query,
        ctx.categorical_index,
        preferred_table,
        mentioned_tables,
    )

    for constraint in constraints:
        if constraint.table not in mentioned_tables:
            mentioned_tables.append(constraint.table)

    preferred_table = preferred_table or _infer_preferred_table(alias_query, mentioned_tables)

    selected_columns = _infer_selected_columns(alias_query, ctx.schema_map, mentioned_tables)
    joins = _infer_likely_joins(ctx.schema_map, mentioned_tables)

    grounded_query_text = _build_grounded_query_text(
        raw_query=user_request,
        preferred_table=preferred_table,
        mentioned_tables=mentioned_tables,
        constraints=constraints,
        selected_columns=selected_columns,
        joins=joins,
    )

    score = 0.0
    if mentioned_tables:
        score += 0.35
    if preferred_table:
        score += 0.2
    if constraints:
        score += 0.25
    if joins:
        score += 0.15
    if selected_columns:
        score += 0.05

    return SchemaGrounding(
        raw_query=user_request,
        grounded_query_text=grounded_query_text,
        preferred_table=preferred_table,
        mentioned_tables=mentioned_tables,
        bound_constraints=constraints,
        selected_columns=selected_columns,
        likely_join_pairs=joins,
        alias_replacements=list(alias_grounding.replacements) if alias_grounding else [],
        confidence=round(min(score, 1.0), 4),
        used_llm_fallback=False,
    )
