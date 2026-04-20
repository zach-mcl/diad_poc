from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

from .validate import sanitize_sql, strip_ansi_and_control_chars


LLAMA_SYSTEM_PROMPT = """You generate DuckDB SQL.

Rules:
- Return ONLY one SQL query.
- The query must be read-only: SELECT or WITH only.
- Use ONLY the provided schema.
- Use double quotes around identifiers.
- Treat categorical values as belonging only to the columns where they appear in CATEGORICAL VALUES.
- If multiple filters are implied, combine them with AND unless the user explicitly says OR.
- If SQL BINDING HINTS are present, obey them exactly.
- Do not use EXCEPT, INTERSECT, or UNION unless the user explicitly asks for set operations.
- For cross-system requests like Notion and Okta, prefer JOIN over set operators.
- If the request cannot be answered from the schema, output exactly: -- I_DONT_KNOW
"""

SQL_REWRITE_PROMPT = """You are repairing a failed DuckDB SQL query.

Rules:
- Return ONLY one corrected SQL query.
- The query must be read-only: SELECT or WITH only.
- Preserve the user's intent.
- Use ONLY the provided schema.
- Use double quotes around identifiers.
- Use DuckDB-compatible SQL.
- Fix the SQL using the user request, the failed SQL, and the DuckDB error.
- Do NOT preserve broken fragments, terminal artifacts, ANSI junk, duplicated keywords, or partial tokens.
- Do NOT add filters that are not implied by the user request.
- Do NOT change a categorical value to a different column than the one supported by CATEGORICAL VALUES.
- If SQL BINDING HINTS are present, obey them exactly.
- Do not use EXCEPT, INTERSECT, or UNION unless the user explicitly asks for set operations.
- Prefer JOIN when the request compares or filters records across tables.
- If you cannot fix it from the schema, output exactly: -- I_DONT_KNOW
"""

SYNONYM_PROMPT = """You are generating schema-grounding aliases for a local data assistant.

Return ONLY valid JSON with this exact shape:
{
  "tables": {
    "table_name": ["alias1", "alias2"]
  },
  "columns": {
    "table_name.column_name": ["alias1", "alias2"]
  },
  "categorical_values": {
    "table_name.column_name.value": ["alias1", "alias2"]
  }
}

Rules:
- Keep aliases short and natural.
- Do not invent facts not supported by the schema names or categorical values.
- Prefer business-friendly short names.
- For tables, suggest likely human references.
- For columns, suggest likely human references.
- For categorical values, suggest obvious paraphrases only.
- Do not include the exact original name if it is already obvious from the key.
- Keep each alias list short, usually 1 to 4 items.
- If unsure, return an empty list for that item.
"""

DEFAULT_SQL_REWRITE_MODEL = "llama3.2"
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")


def _ollama_api_generate(model: str, prompt: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        DEFAULT_OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama API error: {exc}") from exc

    data = json.loads(raw)
    out = str(data.get("response", "")).strip()
    out = strip_ansi_and_control_chars(out)

    if not out:
        raise RuntimeError(f"Ollama returned an empty response: {data}")

    return out


def _ollama_cli_generate(model: str, prompt: str) -> str:
    try:
        p = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Ollama not found. Install Ollama and ensure `ollama` is on PATH.") from exc

    out = strip_ansi_and_control_chars((p.stdout or "").strip())
    err = strip_ansi_and_control_chars((p.stderr or "").strip())

    if not out and err:
        raise RuntimeError(f"Ollama CLI error: {err}")
    if not out:
        raise RuntimeError("Ollama CLI returned an empty response.")

    return out


def ollama_generate(model: str, prompt: str) -> str:
    """
    Prefer the local Ollama HTTP API for cleaner, non-terminal output.
    Fall back to the CLI if the API is unavailable.
    """
    try:
        return _ollama_api_generate(model, prompt)
    except Exception:
        return _ollama_cli_generate(model, prompt)


def _is_duckdb_model(model: str) -> bool:
    normalized = model.strip().lower()
    return "duckdb" in normalized


def _build_sql_prompt(
    *,
    model: str,
    schema_text: str,
    categorical_text: str,
    user_request: str,
) -> str:
    categorical_block = categorical_text if categorical_text.strip() else "(none detected)"

    if _is_duckdb_model(model):
        return f"""SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_block}

RULES:
- Map categorical values only to the columns where they appear in CATEGORICAL VALUES.
- If multiple filters are implied, use AND unless the user explicitly says OR.
- If SQL BINDING HINTS are present, obey them exactly.
- Do not use EXCEPT, INTERSECT, or UNION unless the user explicitly asks for set operations.
- For cross-system requests like Notion and Okta, prefer JOIN over set operators.
- Return only one DuckDB SQL query.

USER REQUEST:
{user_request}

SQL:
"""

    return f"""{LLAMA_SYSTEM_PROMPT}

SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_block}

USER REQUEST:
{user_request}

SQL:
"""


def nl_to_sql(
    *,
    model: str,
    schema_text: str,
    categorical_text: str,
    user_request: str,
) -> str:
    prompt = _build_sql_prompt(
        model=model,
        schema_text=schema_text,
        categorical_text=categorical_text,
        user_request=user_request,
    )
    return ollama_generate(model, prompt)


def rewrite_failed_sql(
    *,
    schema_text: str,
    categorical_text: str,
    user_request: str,
    failed_sql: str,
    error_text: str,
    model: str = DEFAULT_SQL_REWRITE_MODEL,
) -> str:
    clean_failed_sql = sanitize_sql(failed_sql)
    clean_error_text = strip_ansi_and_control_chars(error_text).strip()

    prompt = f"""{SQL_REWRITE_PROMPT}

SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_text if categorical_text.strip() else "(none detected)"}

USER REQUEST:
{user_request}

FAILED SQL:
{clean_failed_sql}

DUCKDB ERROR:
{clean_error_text}

CORRECTED SQL:
"""
    return ollama_generate(model, prompt)


def generate_schema_synonyms(
    *,
    model: str,
    schema_text: str,
    categorical_text: str,
) -> str:
    prompt = f"""{SYNONYM_PROMPT}

SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_text if categorical_text.strip() else "(none detected)"}

JSON:
"""
    return ollama_generate(model, prompt)