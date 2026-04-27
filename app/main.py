from __future__ import annotations

from pathlib import Path
import sys
import re

import pandas as pd

from app.db import (
    connect,
    load_csvs,
    load_xlsx, #added load_xlsx -jm
    load_json,
    get_schema_text,
    get_schema_map,
    build_categorical_index,
    find_join_candidates,
)
from app.llm import nl_to_sql
from app.validate import strip_code_fences, sanitize_sql, is_select_only

# changed find_csvs to find data and added .xlsx to bottom -jm
def find_data(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    return sorted([p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".xlsx", ".json")])






def format_categorical_text(categorical_index: dict[tuple[str, str], list[str]]) -> str:
    """
    Unambiguous categorical hints:
      - "table"."col" allowed_values=["A","B"]
    """
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


def print_catalog(schema_map: dict[str, dict[str, str]], categorical_text: str) -> None:
    print("\n=== Tables and columns ===")
    for t in sorted(schema_map.keys()):
        print(f'\nTABLE "{t}"')
        for c in sorted(schema_map[t].keys()):
            print(f'  - "{c}"')

    print("\n=== Categorical columns (unique values) ===")
    print(categorical_text if categorical_text else "(none detected)")


def extract_tables(sql: str) -> set[str]:
    """
    Extract table names used with FROM and JOIN.
    Handles optional quoting and schema-qualified names like schema.table.
    Returns set of plain table names (quotes removed; schema discarded).
    """
    # match FROM <maybe schema.>"table" or FROM "table" or FROM table
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
        # drop schema prefix if present
        if "." in name:
            name = name.split(".", 1)[-1]
        return name.strip('"')

    return {normalize(t) for t in (from_tables + join_tables) if t}


def find_missing_columns_tables(
    sql: str,
    schema_map: dict[str, dict[str, str]],
    present_tables: set[str],
) -> list[tuple[str, str]]:
    """
    Find unqualified column tokens referenced in SQL whose owning table is not present
    in FROM/JOIN. Returns [(column, owning_table), ...].

    Only considers *unqualified* identifiers (not like t.col or "t"."col") to reduce false positives.
    """
    # find all unqualified identifiers (not preceded by a dot)
    tokens = set(m.group(1) for m in re.finditer(r'(?<!\.)\b([A-Za-z_][A-Za-z0-9_]*)\b', sql))

    ignore = {
        "select","from","join","left","right","inner","outer","full","cross","where",
        "group","by","order","limit","offset","as","on","and","or","not","null","is",
        "in","case","when","then","else","end","distinct","with","union","all","true",
        "false","like","ilike","between","having","lower","upper","trim","ltrim","rtrim",
        "cast","date","coalesce","count","sum","avg","min","max"
    }
    tokens = {t for t in tokens if t.lower() not in ignore}

    missing: list[tuple[str, str]] = []
    for tok in tokens:
        # look for owners that contain this column name
        owners = [t for t, cols in schema_map.items() if tok in cols]
        if len(owners) == 1:
            owner = owners[0]
            if owner not in present_tables:
                missing.append((tok, owner))

    # de-dupe
    out: list[tuple[str, str]] = []
    seen = set()
    for col, owner in missing:
        if (col, owner) not in seen:
            out.append((col, owner))
            seen.add((col, owner))
    return out


def qualify_base_columns_with_alias(sql: str, base_table: str, base_alias: str, schema_map: dict[str, dict[str, str]]) -> str:
    """
    Once we introduce aliases, bare column names can break. This qualifies bare base columns with base_alias.
    Conservative: only qualify exact word matches that are not already qualified via a dot or a quote.
    """
    out = sql
    for base_col in schema_map.get(base_table, {}).keys():
        # only replace unqualified occurrences (not preceded by . or ")
        pattern = rf'(?<![\."])\\b{re.escape(base_col)}\\b'
        out = re.sub(pattern, f'{base_alias}."{base_col}"', out)
    return out


def auto_join_and_qualify(
    con,
    sql: str,
    schema_map: dict[str, dict[str, str]],
    missing: list[tuple[str, str]],
) -> tuple[str, bool]:
    """
    If SQL is single-table and references columns from another table, auto-add JOIN and qualify.
    Returns (new_sql, changed_flag)
    """
    present = extract_tables(sql)
    if len(present) != 1 or not missing:
        return sql, False

    base_table = list(present)[0]

    # group missing cols by owner
    by_owner: dict[str, list[str]] = {}
    for col, owner in missing:
        by_owner.setdefault(owner, []).append(col)

    rewritten = sql
    changed = False

    for owner_table, cols in by_owner.items():
        candidates = find_join_candidates(
            con, schema_map, base_table, owner_table,
            sample_limit=200, min_overlap=0.05
        )
        if not candidates:
            continue

        left_col, right_col, score = candidates[0]

        # build a join clause using short aliases t (base) and o (owner)
        join_clause = (
            f'FROM "{base_table}" t '
            f'JOIN "{owner_table}" o '
            f'ON lower(trim(t."{left_col}")) = lower(trim(o."{right_col}"))'
        )

        # Replace the first FROM base_table occurrence (quoted or not), allow optional alias/AS after it
        rewritten2 = re.sub(
            rf'\bFROM\s+"?{re.escape(base_table)}"?(?:\s+AS\s+\w+)?\b',
            join_clause,
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )

        if rewritten2 == rewritten:
            # couldn't rewrite FROM; bail for this owner
            continue

        rewritten = rewritten2
        changed = True

        # qualify missing columns to o."col" (only unqualified occurrences)
        for col in cols:
            rewritten = re.sub(rf'(?<![\."])\\b{re.escape(col)}\\b', f'o."{col}"', rewritten)

        # qualify base columns to t."col" so aliases don't break bindings
        rewritten = qualify_base_columns_with_alias(rewritten, base_table, "t", schema_map)

        print(f"\n[auto-join] Added JOIN {base_table} ↔ {owner_table} using {left_col}={right_col} (overlap≈{score:.2f})")

    return rewritten, changed


def repair_categorical_literals(sql: str, categorical_index: dict[tuple[str, str], list[str]]) -> str:
    """
    Repairs col = 'A, B' when A and B are allowed values (turn into IN ('A','B')).
    Works only on unqualified or qualified column forms (tries to preserve lhs as-is).
    """
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
        # if the whole string is a single allowed value, leave it alone
        if val in allowed:
            return m.group(0)

        parts = [p.strip() for p in val.split(",") if p.strip()]
        if len(parts) >= 2 and all(p in allowed for p in parts):
            # safe SQL string literal quoting: single quote becomes doubled
            in_list = ", ".join("'" + p.replace("'", "''") + "'" for p in parts)
            return f"{lhs} IN ({in_list})"

        return m.group(0)

    return pattern.sub(repl, sql)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.main <folder_with_csvs> [ollama_model]")
        print("Example: python -m app.main data duckdb-nsql")
        return 1

    folder = Path(sys.argv[1]).expanduser()
    model = sys.argv[2] if len(sys.argv) >= 3 else "duckdb-nsql"

#TODO find csvs and find xlsx

    #changed csvs to Supported_Files -jm
    Supported_Files = find_data(folder)
    if not Supported_Files:
        print(f"No CSV, XLSX, or JSON files found in {folder}")
        return 1
    csvs = [p for p in Supported_Files if p.suffix.lower() == ".csv"]
    xlsx = [p for p in Supported_Files if p.suffix.lower() == ".xlsx"]
    jsons = [p for p in Supported_Files if p.suffix.lower() == ".json"]

    con = connect()
    tables = load_csvs(con, csvs)
    if xlsx:
        tables += load_xlsx(con, xlsx)
    if jsons:
        tables += load_json(con, jsons)

    print("\nLoaded tables:")
    for t in tables:
        print(f"  - {t}")

    schema_text = get_schema_text(con)
    schema_map = get_schema_map(con)

    categorical_index = build_categorical_index(con, schema_map, max_cols_total=60, values_limit=50)
    categorical_text = format_categorical_text(categorical_index)

    print_catalog(schema_map, categorical_text)

    print("\n=== Ask in plain English ===")
    print("Use the exact column names shown above.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_request = input("> ").strip()
        except EOFError:
            print("\nBye.")
            return 0

        if not user_request:
            continue
        if user_request.lower() in {"exit", "quit"}:
            print("Bye.")
            return 0

        raw = nl_to_sql(
            model=model,
            schema_text=schema_text,
            categorical_text=categorical_text,
            user_request=user_request,
        )

        sql = sanitize_sql(strip_code_fences(raw)).strip()

        if sql == "-- I_DONT_KNOW":
            print("\nModel could not answer from schema. Be more specific.\n")
            continue

        ok, reason = is_select_only(sql)
        if not ok:
            print("\nBlocked SQL:", reason)
            print("\nModel output was:\n", raw, "\n")
            continue

        # Fix common categorical literal mistake
        sql = repair_categorical_literals(sql, categorical_index)

        # Auto-join if SQL references a column from a table not in FROM/JOIN
        present = extract_tables(sql)
        missing = find_missing_columns_tables(sql, schema_map, present)
        sql2, changed = auto_join_and_qualify(con, sql, schema_map, missing)
        sql = sql2

        try:
            df = con.execute(sql).df()
        except Exception as e:
            print("\nSQL execution error:")
            print(e)
            print("\nFINAL SQL was:\n", sql, "\n")
            # allow user to inspect, correct request, and try again
            continue

        print("\nGenerated SQL:\n", sql)
        print("\nPreview (first 20 rows):")
        print(df.head(20).to_string(index=False))

        out_path = Path("output.csv")
        df.to_csv(out_path, index=False)
        print(f"\nExported: {out_path.resolve()} ({len(df)} rows)\n")


if __name__ == "__main__":
    raise SystemExit(main())