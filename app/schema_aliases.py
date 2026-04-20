from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Any, Optional

from .llm import generate_schema_synonyms


_STOPWORDS = {
    "the", "a", "an", "for", "of", "to", "in", "on", "with", "from", "by", "and",
    "table", "data", "sheet", "sheet1", "sheet2", "sheet3", "export", "test",
    "row", "rows", "user", "users", "matching", "find", "show", "count",
}


@dataclass(slots=True)
class AliasHit:
    kind: str
    key: str
    alias: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GroundedQuery:
    original_query: str
    rewritten_query: str
    table_hits: list[AliasHit] = field(default_factory=list)
    column_hits: list[AliasHit] = field(default_factory=list)
    value_hits: list[AliasHit] = field(default_factory=list)
    replacements: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AliasIndex:
    table_aliases: dict[str, set[str]]
    column_aliases: dict[str, set[str]]
    value_aliases: dict[str, set[str]]
    schema_hash: str


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("__", " ")
    text = text.replace("_", " ")
    text = re.sub(r"[^a-z0-9@.\- /]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokenize(text: str) -> list[str]:
    return [tok for tok in _normalize(text).split() if tok]


def _schema_hash(
    schema_map: dict[str, dict[str, str]],
    categorical_index: dict[tuple[str, str], list[str]],
) -> str:
    payload = {
        "schema_map": {t: dict(cols) for t, cols in sorted(schema_map.items())},
        "categorical_index": {
            f"{t}.{c}": list(vals) for (t, c), vals in sorted(categorical_index.items())
        },
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _add_alias(bucket: dict[str, set[str]], key: str, alias: str) -> None:
    alias_n = _normalize(alias)
    if not alias_n:
        return
    bucket.setdefault(key, set()).add(alias_n)


def _table_alias_candidates(table_name: str) -> set[str]:
    base = _normalize(table_name)
    tokens = [t for t in _tokenize(table_name) if t not in {"sheet", "sheet1", "sheet2", "sheet3"}]

    aliases = {base}
    aliases.add(base.replace(" ", "_"))

    for token in tokens:
        aliases.add(token)

    trimmed = [t for t in tokens if t not in {"test", "export", "data", "table"}]
    if trimmed:
        aliases.add(" ".join(trimmed))
        aliases.add("_".join(trimmed))
        aliases.add(trimmed[0])
        if len(trimmed) >= 2:
            aliases.add(" ".join(trimmed[:2]))
            aliases.add("_".join(trimmed[:2]))

    for i in range(len(trimmed)):
        for j in range(i + 1, len(trimmed) + 1):
            chunk = trimmed[i:j]
            if chunk:
                aliases.add(" ".join(chunk))
                aliases.add("_".join(chunk))

    return {_normalize(a) for a in aliases if _normalize(a)}


def _column_alias_candidates(table_name: str, column_name: str) -> set[str]:
    col_tokens = _tokenize(column_name)
    table_tokens = [t for t in _tokenize(table_name) if t not in {"test", "export", "data", "table"}]

    aliases = {_normalize(column_name), _normalize(column_name).replace(" ", "_")}

    for token in col_tokens:
        aliases.add(token)

    if col_tokens:
        aliases.add(" ".join(col_tokens))
        aliases.add("_".join(col_tokens))

    if table_tokens and col_tokens:
        aliases.add(f"{table_tokens[0]} {' '.join(col_tokens)}")
        aliases.add(f"{table_tokens[0]}_{'_'.join(col_tokens)}")

    col_joined = " ".join(col_tokens)
    if col_joined == "user email":
        aliases.update({"email", "user email", "okta email"})
    if col_joined == "email":
        aliases.update({"email", "notion email"})
    if col_joined == "status":
        aliases.update({"status", "okta status"})
    if col_joined == "notion role":
        aliases.update({"role", "notion role"})
    if col_joined == "team":
        aliases.update({"team", "department"})

    return {_normalize(a) for a in aliases if _normalize(a)}


def _value_alias_candidates(table_name: str, column_name: str, value: str) -> set[str]:
    value_n = _normalize(value)
    aliases = {value_n}

    if value_n == "inactive":
        aliases.update({"inactive", "deactivated", "disabled", "not active"})
    elif value_n == "active":
        aliases.update({"active", "enabled", "current"})
    elif value_n == "admin":
        aliases.update({"admin", "administrator"})
    elif value_n == "user":
        aliases.update({"user", "member", "standard user"})

    col_n = _normalize(column_name)
    if col_n == "status":
        aliases.add(f"status {value_n}")
        aliases.add(f"{value_n} status")

    table_tokens = [t for t in _tokenize(table_name) if t not in {"test", "export", "data", "table"}]
    if table_tokens:
        aliases.add(f"{table_tokens[0]} {value_n}")

    return {_normalize(a) for a in aliases if _normalize(a)}


def _safe_parse_synonym_json(raw: str) -> dict[str, Any]:
    text = raw.strip()

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Synonym JSON root must be an object.")
    return data


def build_alias_index(
    schema_map: dict[str, dict[str, str]],
    categorical_index: dict[tuple[str, str], list[str]],
    *,
    model: str | None = None,
    schema_text: str = "",
    categorical_text: str = "",
    enable_llm_synonyms: bool = True,
) -> AliasIndex:
    table_aliases: dict[str, set[str]] = {}
    column_aliases: dict[str, set[str]] = {}
    value_aliases: dict[str, set[str]] = {}

    for table_name, columns in schema_map.items():
        for alias in _table_alias_candidates(table_name):
            _add_alias(table_aliases, table_name, alias)

        for column_name in columns.keys():
            col_key = f"{table_name}.{column_name}"
            for alias in _column_alias_candidates(table_name, column_name):
                _add_alias(column_aliases, col_key, alias)

    for (table_name, column_name), values in categorical_index.items():
        value_key_prefix = f"{table_name}.{column_name}"
        for value in values:
            full_key = f"{value_key_prefix}.{value}"
            for alias in _value_alias_candidates(table_name, column_name, str(value)):
                _add_alias(value_aliases, full_key, alias)

    if enable_llm_synonyms and model and schema_text:
        try:
            raw = generate_schema_synonyms(
                model=model,
                schema_text=schema_text,
                categorical_text=categorical_text,
            )
            data = _safe_parse_synonym_json(raw)

            for table_name, aliases in data.get("tables", {}).items():
                if table_name in schema_map and isinstance(aliases, list):
                    for alias in aliases:
                        _add_alias(table_aliases, table_name, str(alias))

            for column_key, aliases in data.get("columns", {}).items():
                if isinstance(aliases, list) and "." in column_key:
                    table_name, column_name = column_key.split(".", 1)
                    if table_name in schema_map and column_name in schema_map[table_name]:
                        for alias in aliases:
                            _add_alias(column_aliases, column_key, str(alias))

            for value_key, aliases in data.get("categorical_values", {}).items():
                if isinstance(aliases, list) and value_key.count(".") >= 2:
                    table_name, column_name, value = value_key.split(".", 2)
                    if (table_name, column_name) in categorical_index:
                        if value in [str(v) for v in categorical_index[(table_name, column_name)]]:
                            for alias in aliases:
                                _add_alias(value_aliases, value_key, str(alias))
        except Exception:
            pass

    return AliasIndex(
        table_aliases=table_aliases,
        column_aliases=column_aliases,
        value_aliases=value_aliases,
        schema_hash=_schema_hash(schema_map, categorical_index),
    )


def _best_alias_score(text: str, alias: str) -> float:
    text_n = _normalize(text)
    alias_n = _normalize(alias)
    if not text_n or not alias_n:
        return 0.0

    if text_n == alias_n:
        return 1.0

    if re.search(rf"\b{re.escape(alias_n)}\b", text_n):
        return 0.98

    if re.search(rf"\b{re.escape(text_n)}\b", alias_n):
        return 0.95

    return SequenceMatcher(None, text_n, alias_n).ratio()


def find_table_hits(
    user_text: str,
    alias_index: AliasIndex,
    *,
    threshold: float = 0.88,
) -> list[AliasHit]:
    normalized = _normalize(user_text)
    hits: list[AliasHit] = []

    for table_name, aliases in alias_index.table_aliases.items():
        best_alias = ""
        best_score = 0.0

        for alias in aliases:
            score = _best_alias_score(normalized, alias)
            for token in _tokenize(normalized):
                score = max(score, _best_alias_score(token, alias))
            if score > best_score:
                best_score = score
                best_alias = alias

        if best_score >= threshold:
            hits.append(
                AliasHit(
                    kind="table",
                    key=table_name,
                    alias=best_alias,
                    score=best_score,
                )
            )

    hits.sort(key=lambda h: (-h.score, h.key.lower()))
    return hits


def find_column_hits(
    user_text: str,
    alias_index: AliasIndex,
    *,
    threshold: float = 0.90,
) -> list[AliasHit]:
    normalized = _normalize(user_text)
    hits: list[AliasHit] = []

    for column_key, aliases in alias_index.column_aliases.items():
        best_alias = ""
        best_score = 0.0

        for alias in aliases:
            score = _best_alias_score(normalized, alias)
            for token in _tokenize(normalized):
                score = max(score, _best_alias_score(token, alias))
            if score > best_score:
                best_score = score
                best_alias = alias

        if best_score >= threshold:
            hits.append(
                AliasHit(
                    kind="column",
                    key=column_key,
                    alias=best_alias,
                    score=best_score,
                )
            )

    hits.sort(key=lambda h: (-h.score, h.key.lower()))
    return hits


def find_value_hits(
    user_text: str,
    alias_index: AliasIndex,
    *,
    threshold: float = 0.93,
) -> list[AliasHit]:
    normalized = _normalize(user_text)
    hits: list[AliasHit] = []

    for value_key, aliases in alias_index.value_aliases.items():
        best_alias = ""
        best_score = 0.0

        for alias in aliases:
            score = _best_alias_score(normalized, alias)
            for token in _tokenize(normalized):
                score = max(score, _best_alias_score(token, alias))
            if score > best_score:
                best_score = score
                best_alias = alias

        if best_score >= threshold:
            table_name, column_name, value = value_key.split(".", 2)
            hits.append(
                AliasHit(
                    kind="value",
                    key=value_key,
                    alias=best_alias,
                    score=best_score,
                    metadata={
                        "table": table_name,
                        "column": column_name,
                        "value": value,
                    },
                )
            )

    hits.sort(key=lambda h: (-h.score, h.key.lower()))
    return hits


def ground_user_query(
    user_text: str,
    alias_index: AliasIndex,
) -> GroundedQuery:
    grounded = GroundedQuery(
        original_query=user_text,
        rewritten_query=user_text,
    )

    grounded.table_hits = find_table_hits(user_text, alias_index)
    grounded.column_hits = find_column_hits(user_text, alias_index)
    grounded.value_hits = find_value_hits(user_text, alias_index)

    rewritten = user_text
    replacements: list[tuple[str, str, float, str]] = []

    for hit in grounded.table_hits:
        if hit.score >= 0.96 and re.search(rf"\b{re.escape(hit.alias)}\b", _normalize(rewritten)):
            replacements.append((hit.alias, hit.key, hit.score, "table"))

    for hit in grounded.column_hits:
        if hit.score >= 0.97 and re.search(rf"\b{re.escape(hit.alias)}\b", _normalize(rewritten)):
            replacements.append((hit.alias, hit.key, hit.score, "column"))

    for hit in grounded.value_hits:
        value = hit.metadata["value"]
        if hit.score >= 0.98 and re.search(rf"\b{re.escape(hit.alias)}\b", _normalize(rewritten)):
            replacements.append((hit.alias, value, hit.score, "value"))

    replacements.sort(key=lambda item: (-len(item[0]), -item[2]))

    for source, target, score, kind in replacements:
        pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)
        if pattern.search(rewritten):
            rewritten = pattern.sub(target, rewritten)
            grounded.replacements.append(
                {
                    "kind": kind,
                    "source": source,
                    "target": target,
                    "score": round(score, 4),
                }
            )

    grounded.rewritten_query = rewritten
    return grounded