from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import duckdb


# ----------------------------
# Loading CSVs into DuckDB
# ----------------------------

def _safe_table_name(filename: str) -> str:
    base = Path(filename).stem.lower()
    base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_")
    if not base:
        base = "table"
    if base[0].isdigit():
        base = f"t_{base}"
    return base


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    if db_path is None:
        return duckdb.connect(database=":memory:")
    return duckdb.connect(str(db_path))


def load_csvs(con: duckdb.DuckDBPyConnection, csv_paths: list[Path]) -> list[str]:
    table_names: list[str] = []
    for p in csv_paths:
        t = _safe_table_name(p.name)
        con.execute(
            f"""
            CREATE OR REPLACE TABLE "{t}" AS
            SELECT * FROM read_csv_auto(?, SAMPLE_SIZE=-1, HEADER=true);
            """,
            [str(p)],
        )
        table_names.append(t)
    return table_names


# ----------------------------
# Schema helpers
# ----------------------------

def get_schema_text(con: duckdb.DuckDBPyConnection) -> str:
    rows = con.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position;
        """
    ).fetchall()

    if not rows:
        return "No tables loaded."

    out: list[str] = []
    cur = None
    for t, c, dt in rows:
        if t != cur:
            cur = t
            out.append(f"\nTABLE {t}:")
        out.append(f"  - {c} ({dt})")
    return "\n".join(out).strip()


def get_schema_map(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, str]]:
    rows = con.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='main'
        """
    ).fetchall()

    m: dict[str, dict[str, str]] = {}
    for t, c, dt in rows:
        m.setdefault(t, {})[c] = dt
    return m


# ----------------------------
# Data-driven profiling
# ----------------------------

@dataclass(frozen=True)
class ColumnProfile:
    table: str
    column: str
    dtype: str
    rows: int
    distinct: int
    nulls: int
    avg_len: float | None


def profile_column(con: duckdb.DuckDBPyConnection, table: str, column: str) -> ColumnProfile:
    q = f'''
    SELECT
      COUNT(*) AS rows,
      COUNT(DISTINCT "{column}") AS distinct_vals,
      SUM(CASE WHEN "{column}" IS NULL THEN 1 ELSE 0 END) AS nulls,
      AVG(CASE WHEN typeof("{column}")='VARCHAR' THEN length("{column}") ELSE NULL END) AS avg_len
    FROM "{table}"
    '''
    rows, distinct_vals, nulls, avg_len = con.execute(q).fetchone()

    dtype_row = con.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema='main' AND table_name=? AND column_name=?
        """,
        [table, column],
    ).fetchone()
    dtype = dtype_row[0] if dtype_row else "UNKNOWN"

    return ColumnProfile(
        table=table,
        column=column,
        dtype=dtype,
        rows=int(rows),
        distinct=int(distinct_vals),
        nulls=int(nulls),
        avg_len=float(avg_len) if avg_len is not None else None,
    )


def detect_categorical_columns_dynamic(
    con: duckdb.DuckDBPyConnection,
    schema_map: dict[str, dict[str, str]],
    *,
    max_distinct: int = 50,
    max_ratio: float = 0.30,
    max_avg_len: float = 40.0,
    max_cols_total: int = 30,
    small_table_rows: int = 30,
    small_table_max_distinct: int = 12,
) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []

    for table, cols in schema_map.items():
        for col in cols.keys():
            try:
                p = profile_column(con, table, col)
            except Exception:
                continue

            if p.rows <= 0:
                continue

            # skip key-like columns (almost all unique)
            if p.distinct >= int(0.95 * p.rows):
                continue

            ratio = p.distinct / max(p.rows, 1)
            is_small_table = p.rows <= small_table_rows

            ok_normal = (p.distinct <= max_distinct and ratio <= max_ratio)
            ok_small = (is_small_table and p.distinct <= small_table_max_distinct)

            if ok_normal or ok_small:
                if p.avg_len is not None and p.avg_len > max_avg_len:
                    continue
                profiles.append(p)

    profiles.sort(key=lambda x: (x.distinct / max(x.rows, 1), x.distinct))
    return profiles[:max_cols_total]


def get_unique_values_safe(
    con: duckdb.DuckDBPyConnection,
    schema_map: dict[str, dict[str, str]],
    table: str,
    column: str,
    *,
    limit: int = 50,
) -> list[str]:
    if table not in schema_map:
        raise ValueError(f"Unknown table: {table}")
    if column not in schema_map[table]:
        raise ValueError(f"Unknown column '{column}' for table '{table}'")

    limit = max(1, min(int(limit), 200))

    q = f'''
    SELECT DISTINCT "{column}" AS v
    FROM "{table}"
    WHERE "{column}" IS NOT NULL
    ORDER BY v
    LIMIT {limit}
    '''
    rows = con.execute(q).fetchall()
    return [str(r[0]) for r in rows]


def build_categorical_index(
    con: duckdb.DuckDBPyConnection,
    schema_map: dict[str, dict[str, str]],
    *,
    max_cols_total: int = 30,
    values_limit: int = 50,
) -> dict[tuple[str, str], list[str]]:
    cats = detect_categorical_columns_dynamic(
        con,
        schema_map,
        max_cols_total=max_cols_total,
    )

    idx: dict[tuple[str, str], list[str]] = {}
    for p in cats:
        try:
            vals = get_unique_values_safe(con, schema_map, p.table, p.column, limit=values_limit)
        except Exception:
            continue
        if vals:
            idx[(p.table, p.column)] = vals
    return idx


# ----------------------------
# Dynamic join inference (overlap-based)
# ----------------------------

def _is_string_type(dtype: str) -> bool:
    d = dtype.lower()
    return ("varchar" in d) or ("string" in d) or ("text" in d)


def find_join_candidates(
    con: duckdb.DuckDBPyConnection,
    schema_map: dict[str, dict[str, str]],
    left_table: str,
    right_table: str,
    *,
    sample_limit: int = 200,
    min_overlap: float = 0.05,
) -> list[tuple[str, str, float]]:
    results: list[tuple[str, str, float]] = []

    left_cols = schema_map.get(left_table, {})
    right_cols = schema_map.get(right_table, {})

    left_candidates = [c for c, dt in left_cols.items() if _is_string_type(dt)]
    right_candidates = [c for c, dt in right_cols.items() if _is_string_type(dt)]

    def sample_values(table: str, col: str) -> set[str]:
        q = f'''
        SELECT DISTINCT lower(trim("{col}")) AS v
        FROM "{table}"
        WHERE "{col}" IS NOT NULL
        LIMIT {sample_limit}
        '''
        return {r[0] for r in con.execute(q).fetchall() if r[0]}

    left_samples: dict[str, set[str]] = {}
    for lc in left_candidates:
        try:
            left_samples[lc] = sample_values(left_table, lc)
        except Exception:
            left_samples[lc] = set()

    for rc in right_candidates:
        try:
            rset = sample_values(right_table, rc)
        except Exception:
            continue
        if not rset:
            continue

        for lc, lset in left_samples.items():
            if not lset:
                continue
            inter = len(lset & rset)
            union = len(lset | rset)
            score = inter / union if union else 0.0
            if score >= min_overlap:
                results.append((lc, rc, score))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:5]
