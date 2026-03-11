from __future__ import annotations

import subprocess


SYSTEM_PROMPT = """You are a SQL generator for DuckDB.

Rules you MUST follow:
- Output ONLY a single SQL query. No explanations. No markdown. No code fences.
- The SQL MUST be read-only: SELECT or WITH only.
- Use ONLY the tables/columns provided in the schema.
- If the request cannot be answered from the schema, output exactly: -- I_DONT_KNOW
- Use double quotes around identifiers (tables/columns), because columns may be capitalized (e.g., "Email").
- When joining text keys, normalize with lower(trim(...)) on both sides.
- When filtering categorical columns, use ONLY the values shown in the categorical value list (match case exactly).
- Do NOT use functions incorrectly (e.g., left() must have two args; avoid left/right/substr unless needed).
- If filters/reference columns from multiple tables, you MUST include all required tables and JOIN them.
"""


def ollama_generate(model: str, prompt: str) -> str:
    """
    Runs: ollama run <model>
    Returns stdout text.
    """
    try:
        p = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError("Ollama not found. Install Ollama and ensure `ollama` is on PATH.")

    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()

    # If model prints nothing, surface stderr
    if not out and err:
        raise RuntimeError(f"Ollama error: {err}")

    return out


def nl_to_sql(
    *,
    model: str,
    schema_text: str,
    categorical_text: str,
    user_request: str,
) -> str:
    prompt = f"""{SYSTEM_PROMPT}

SCHEMA:
{schema_text}

CATEGORICAL VALUES:
{categorical_text if categorical_text.strip() else "(none detected)"}

USER REQUEST:
{user_request}

SQL:
"""
    return ollama_generate(model, prompt)


