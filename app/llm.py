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
- Use double quotes around table and column identifiers.
- Treat categorical values as belonging only to the columns where they appear in CATEGORICAL VALUES.
- If multiple filters are implied, combine them with AND unless the user explicitly says OR.
- Use JOIN when the request needs rows from one table filtered by values in another table.
- Do not use EXCEPT, INTERSECT, or UNION unless the user explicitly asks for set operations.
- If the request says to return rows from a preferred/main table, SELECT that table's rows, not the joined table's rows.
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
- Use JOIN when the request needs rows from one table filtered by values in another table.
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

ROUTER_LLM_PROMPT = """You are routing a request for a local DuckDB data assistant.

Valid routes:
- SQL_QUERY: user wants rows, counts, filters, joins, grouping, sorting, retrieval, or calculations from loaded data.
- DATA_QUESTION: user asks what tables, columns, schema, files, loaded data, or categorical values exist.
- PYTHON_TOOL: user asks for one supported non-SQL tool: normalize_emails, fuzzy_match, or create_graph.
- OUT_OF_SCOPE: request is unrelated to the loaded dataset or supported tools.

Return ONLY valid JSON with this exact shape:
{
  "route": "SQL_QUERY",
  "confidence": 0.0,
  "scores": {
    "SQL_QUERY": 0.0,
    "DATA_QUESTION": 0.0,
    "PYTHON_TOOL": 0.0,
    "OUT_OF_SCOPE": 0.0
  },
  "reason": "short reason",
  "tool_name": null
}

Rules:
- route must be exactly one of: SQL_QUERY, DATA_QUESTION, PYTHON_TOOL, OUT_OF_SCOPE.
- confidence must be a number from 0 to 1.
- scores must be numbers from 0 to 1 and should sum to about 1.
- tool_name must be null unless route is PYTHON_TOOL.
- tool_name may only be: normalize_emails, fuzzy_match, create_graph, or null.
- Use the deterministic hint as guidance, but override it if the user request clearly fits a different route.
- Use SQL_QUERY for normal data retrieval and analysis questions.
- Use DATA_QUESTION for metadata/schema questions.
- Use OUT_OF_SCOPE for general questions unrelated to the loaded dataset.
"""

METADATA_QA_PROMPT = """You answer metadata questions for a local DuckDB data assistant.

You may ONLY answer questions about:
- loaded table names
- column names / fields
- schema
- known categorical values
- which table or column likely matches a user's wording

You must NOT answer questions that require inspecting rows, filtering rows, counting rows, grouping rows, joining tables, comparing users, finding records, or analyzing actual data.

If the user asks for any row-level action or analysis, output exactly:
ROUTE_TO_SQL

Keep answers short and useful.
Use the exact table and column names from the schema.
If the user has a typo, infer the likely metadata meaning.
If the user says a friendly table name like "notion" or "okta", map it to the closest loaded table if obvious.
If the answer is not clear from the schema, say what you could not match and list the closest options.
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
- Return only one DuckDB SQL query.
- Use only the schema above.
- Use double quotes around identifiers.
- Map categorical values only to the columns where they appear in CATEGORICAL VALUES.
- If multiple filters are implied, use AND unless the user explicitly says OR.
- Use JOIN when the request needs rows from one table filtered by values in another table.
- Do not use EXCEPT, INTERSECT, or UNION unless the user explicitly asks for set operations.
- If the request says to return rows from a preferred/main table, SELECT that table's rows.

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


def route_request_with_llm(
    *,
    model: str,
    user_request: str,
    schema_text: str,
    categorical_text: str,
    deterministic_hint: dict,
) -> str:
    prompt = f"""{ROUTER_LLM_PROMPT}

SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_text if categorical_text.strip() else "(none detected)"}

DETERMINISTIC ROUTER HINT:
{json.dumps(deterministic_hint, indent=2)}

USER REQUEST:
{user_request}

JSON:
"""
    return ollama_generate(model, prompt)


def answer_metadata_question_with_llm(
    *,
    model: str,
    schema_text: str,
    categorical_text: str,
    user_request: str,
) -> str:
    prompt = f"""{METADATA_QA_PROMPT}

SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_text if categorical_text.strip() else "(none detected)"}

USER QUESTION:
{user_request}

ANSWER:
"""
    return ollama_generate(model, prompt)
