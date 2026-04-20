from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Optional

import pandas as pd
from pandas.api.types import is_numeric_dtype

from .router_types import RouteName, RouterContext, RouterResult


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _fetch_table_df(con, table_name: str) -> pd.DataFrame:
    return con.execute(f'SELECT * FROM {_quote_ident(table_name)}').df()


def _extract_explicit_refs(
    query: str,
    schema_map: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []

    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", query):
        raw_table = match.group(1)
        raw_column = match.group(2)

        for table_name, cols in schema_map.items():
            if table_name.lower() != raw_table.lower():
                continue
            for col_name in cols.keys():
                if col_name.lower() == raw_column.lower():
                    refs.append((table_name, col_name))

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            deduped.append(ref)
    return deduped


def _find_table_mentions(query: str, schema_map: dict[str, dict[str, str]]) -> list[str]:
    normalized_query = _normalize(query)
    matches: list[str] = []

    for table_name in schema_map.keys():
        if re.search(rf"\b{re.escape(table_name.lower())}\b", normalized_query):
            matches.append(table_name)

    return matches


def _find_column_mentions(
    query: str,
    schema_map: dict[str, dict[str, str]],
    table_name: str | None = None,
) -> list[tuple[str, str]]:
    normalized_query = _normalize(query)
    matches: list[tuple[str, str]] = []

    tables = [table_name] if table_name else list(schema_map.keys())
    for t in tables:
        for col_name in schema_map.get(t, {}).keys():
            if re.search(rf"\b{re.escape(col_name.lower())}\b", normalized_query):
                matches.append((t, col_name))

    return matches


def _parse_threshold(query: str, default: float = 0.85) -> float:
    pct_match = re.search(r"(\d{1,3})\s*%", query)
    if pct_match:
        pct = max(0, min(100, int(pct_match.group(1))))
        return pct / 100.0

    dec_match = re.search(r"threshold\s*(?:=|of|to)?\s*(0(?:\.\d+)?|1(?:\.0+)?)", query.lower())
    if dec_match:
        value = float(dec_match.group(1))
        return max(0.0, min(1.0, value))

    return default


def canonicalize_email(value: Any) -> str:
    email = _normalize(value)
    if not email or "@" not in email:
        return email

    local, domain = email.split("@", 1)

    if domain == "googlemail.com":
        domain = "gmail.com"

    if domain == "gmail.com":
        local = local.split("+", 1)[0]
        local = local.replace(".", "")

    return f"{local}@{domain}"


def normalize_emails_in_dataframe(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        raise KeyError(f"Column '{column}' was not found in the dataframe.")

    result = df.copy()
    result[f"{column}__normalized"] = result[column].map(canonicalize_email)
    return result


def fuzzy_match_dataframes(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    left_on: str,
    right_on: str,
    threshold: float = 0.85,
) -> pd.DataFrame:
    if left_on not in left_df.columns:
        raise KeyError(f"Left column '{left_on}' was not found.")
    if right_on not in right_df.columns:
        raise KeyError(f"Right column '{right_on}' was not found.")

    threshold = threshold / 100.0 if threshold > 1 else threshold
    threshold = max(0.0, min(1.0, threshold))

    right_candidates: list[tuple[int, str, Any]] = []
    for idx, value in right_df[right_on].items():
        norm = _normalize(value)
        if norm:
            right_candidates.append((int(idx), norm, value))

    rows: list[dict[str, Any]] = []

    for left_idx, left_row in left_df.iterrows():
        left_value = left_row[left_on]
        left_norm = _normalize(left_value)

        best_score = 0.0
        best_right_idx: int | None = None
        best_right_value: Any = None

        if left_norm:
            for candidate_idx, right_norm, raw_right in right_candidates:
                score = SequenceMatcher(None, left_norm, right_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_right_idx = candidate_idx
                    best_right_value = raw_right

        matched = best_right_idx is not None and best_score >= threshold

        record: dict[str, Any] = {
            "left_index": left_idx,
            "left_value": left_value,
            "matched": matched,
            "match_score": round(best_score, 4),
            "right_index": best_right_idx if matched else None,
            "right_value": best_right_value if matched else None,
        }

        for col_name in left_df.columns:
            record[f"left_{col_name}"] = left_row[col_name]

        if matched and best_right_idx is not None:
            right_row = right_df.loc[best_right_idx]
            for col_name in right_df.columns:
                record[f"right_{col_name}"] = right_row[col_name]

        rows.append(record)

    return pd.DataFrame(rows)


def create_simple_graph(
    df: pd.DataFrame,
    x_col: str | None = None,
    y_col: str | None = None,
    kind: str = "bar",
    output_dir: str = "outputs",
) -> str:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for graph creation.") from exc

    if df.empty:
        raise ValueError("Cannot create a graph from an empty dataframe.")

    os.makedirs(output_dir, exist_ok=True)

    numeric_cols = [col for col in df.columns if is_numeric_dtype(df[col])]
    non_numeric_cols = [col for col in df.columns if col not in numeric_cols]

    kind = kind.lower().strip()
    if kind not in {"bar", "line", "scatter", "hist"}:
        kind = "bar"

    if kind == "hist":
        if y_col is None:
            if numeric_cols:
                y_col = numeric_cols[0]
            else:
                raise ValueError("Histogram needs a numeric column.")
        if y_col not in df.columns:
            raise KeyError(f"Column '{y_col}' was not found.")
    else:
        if x_col is None:
            if non_numeric_cols:
                x_col = non_numeric_cols[0]
            elif len(df.columns) > 0:
                x_col = str(df.columns[0])

        if y_col is None and kind in {"bar", "line", "scatter"}:
            if numeric_cols:
                choices = [col for col in numeric_cols if col != x_col]
                y_col = choices[0] if choices else numeric_cols[0]

        if x_col is not None and x_col not in df.columns:
            raise KeyError(f"Column '{x_col}' was not found.")
        if y_col is not None and y_col not in df.columns:
            raise KeyError(f"Column '{y_col}' was not found.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(output_dir, f"{kind}_{stamp}_{uuid.uuid4().hex[:8]}.png")

    plt.figure(figsize=(10, 6))

    if kind == "hist":
        series = df[y_col].dropna()
        plt.hist(series, bins=20)
        plt.xlabel(y_col)
        plt.ylabel("Count")
        plt.title(f"Histogram of {y_col}")

    elif kind == "scatter":
        if x_col is None or y_col is None:
            raise ValueError("Scatter plot needs both x and y columns.")
        plot_df = df[[x_col, y_col]].dropna()
        plt.scatter(plot_df[x_col], plot_df[y_col])
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        plt.title(f"{y_col} vs {x_col}")

    elif kind == "line":
        if x_col is None or y_col is None:
            raise ValueError("Line plot needs both x and y columns.")
        plot_df = df[[x_col, y_col]].dropna()
        plt.plot(plot_df[x_col], plot_df[y_col])
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        plt.title(f"{y_col} over {x_col}")
        plt.xticks(rotation=45, ha="right")

    else:
        if x_col is None:
            raise ValueError("Bar chart needs at least an x column.")
        if y_col is None:
            counts = df[x_col].astype(str).value_counts().head(20)
            plt.bar(counts.index.tolist(), counts.values.tolist())
            plt.xlabel(x_col)
            plt.ylabel("Count")
            plt.title(f"Top values for {x_col}")
            plt.xticks(rotation=45, ha="right")
        else:
            plot_df = df[[x_col, y_col]].dropna()
            grouped = plot_df.groupby(x_col, dropna=False)[y_col].sum().head(20)
            plt.bar(grouped.index.astype(str).tolist(), grouped.values.tolist())
            plt.xlabel(x_col)
            plt.ylabel(f"Sum of {y_col}")
            plt.title(f"{y_col} by {x_col}")
            plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(file_path, dpi=150)
    plt.close()

    return file_path


def _detect_tool_name(query: str) -> str | None:
    normalized_query = _normalize(query)

    if ("normalize" in normalized_query or "canonicalize" in normalized_query) and "email" in normalized_query:
        return "normalize_emails"

    if any(term in normalized_query for term in ["fuzzy match", "approximate match", "similarity", "dedupe similar"]):
        return "fuzzy_match"

    if any(term in normalized_query for term in ["graph", "plot", "chart", "visualize", "visualise"]):
        return "create_graph"

    return None


def _resolve_email_target(query: str, ctx: RouterContext) -> tuple[str | None, str | None, str | None]:
    refs = _extract_explicit_refs(query, ctx.schema_map)
    if refs:
        return refs[0][0], refs[0][1], None

    table_mentions = _find_table_mentions(query, ctx.schema_map)
    if table_mentions:
        table_name = table_mentions[0]
        email_cols = [c for c in ctx.schema_map[table_name].keys() if "email" in c.lower()]
        if len(email_cols) == 1:
            return table_name, email_cols[0], None
        if len(email_cols) > 1:
            return None, None, f'Table "{table_name}" has multiple email-like columns. Use table.column.'

    all_email_cols: list[tuple[str, str]] = []
    for table_name, cols in ctx.schema_map.items():
        for col_name in cols.keys():
            if "email" in col_name.lower():
                all_email_cols.append((table_name, col_name))

    if len(all_email_cols) == 1:
        return all_email_cols[0][0], all_email_cols[0][1], None

    return None, None, "Please specify which email column to normalize, ideally as table.column."


def _resolve_fuzzy_targets(
    query: str,
    ctx: RouterContext,
) -> tuple[tuple[str, str] | None, tuple[str, str] | None, str | None]:
    refs = _extract_explicit_refs(query, ctx.schema_map)
    if len(refs) >= 2:
        return refs[0], refs[1], None

    return None, None, (
        "For fuzzy matching, specify two columns like "
        "'fuzzy match left_table.name with right_table.full_name'."
    )


def _resolve_graph_target(
    query: str,
    ctx: RouterContext,
) -> tuple[str | None, str | None, str | None, str, str | None]:
    normalized_query = _normalize(query)

    if "scatter" in normalized_query:
        kind = "scatter"
    elif "line" in normalized_query:
        kind = "line"
    elif "hist" in normalized_query or "histogram" in normalized_query:
        kind = "hist"
    else:
        kind = "bar"

    refs = _extract_explicit_refs(query, ctx.schema_map)
    table_mentions = _find_table_mentions(query, ctx.schema_map)

    if refs:
        table_name = refs[0][0]
        same_table_cols = [col for tbl, col in refs if tbl == table_name]
        x_col = same_table_cols[0] if same_table_cols else None
        y_col = same_table_cols[1] if len(same_table_cols) > 1 else None
        return table_name, x_col, y_col, kind, None

    if table_mentions:
        table_name = table_mentions[0]
    elif len(ctx.schema_map) == 1:
        table_name = list(ctx.schema_map.keys())[0]
    else:
        return None, None, None, kind, "Please mention which table to graph."

    col_mentions = _find_column_mentions(query, ctx.schema_map, table_name)
    cols: list[str] = []
    for _, col_name in col_mentions:
        if col_name not in cols:
            cols.append(col_name)

    x_col = cols[0] if cols else None
    y_col = cols[1] if len(cols) > 1 else None
    return table_name, x_col, y_col, kind, None


def run_python_tool(user_request: str, ctx: RouterContext) -> RouterResult:
    tool_name = _detect_tool_name(user_request)
    if tool_name is None:
        return RouterResult(
            route=RouteName.PYTHON_TOOL,
            ok=False,
            message="I could not map that request to a supported Python tool.",
            reason="No supported Python tool keyword matched the request.",
        ).with_query(user_request)

    try:
        if tool_name == "normalize_emails":
            table_name, column_name, error_message = _resolve_email_target(user_request, ctx)
            if error_message:
                return RouterResult(
                    route=RouteName.PYTHON_TOOL,
                    ok=False,
                    message=error_message,
                    reason="Email normalization was requested, but the target column was too vague.",
                    tool_name=tool_name,
                ).with_query(user_request)

            df = _fetch_table_df(ctx.con, table_name)
            result_df = normalize_emails_in_dataframe(df, column_name)

            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f'Normalized email values from "{table_name}"."{column_name}".',
                reason="The request clearly asked for email normalization.",
                dataframe=result_df,
                metadata={"table": table_name, "column": column_name, "row_count": len(result_df)},
                tool_name=tool_name,
            ).with_query(user_request)

        if tool_name == "fuzzy_match":
            left_ref, right_ref, error_message = _resolve_fuzzy_targets(user_request, ctx)
            if error_message:
                return RouterResult(
                    route=RouteName.PYTHON_TOOL,
                    ok=False,
                    message=error_message,
                    reason="Fuzzy matching needs two explicit table.column targets.",
                    tool_name=tool_name,
                ).with_query(user_request)

            threshold = _parse_threshold(user_request)
            left_df = _fetch_table_df(ctx.con, left_ref[0])
            right_df = _fetch_table_df(ctx.con, right_ref[0])

            match_df = fuzzy_match_dataframes(
                left_df=left_df,
                right_df=right_df,
                left_on=left_ref[1],
                right_on=right_ref[1],
                threshold=threshold,
            )

            matched_count = int(match_df["matched"].sum()) if "matched" in match_df.columns else 0

            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=(
                    f'Ran fuzzy matching between "{left_ref[0]}"."{left_ref[1]}" and '
                    f'"{right_ref[0]}"."{right_ref[1]}" with threshold {threshold:.2f}. '
                    f"{matched_count} row(s) matched."
                ),
                reason="The request clearly asked for fuzzy matching.",
                dataframe=match_df,
                metadata={
                    "left": left_ref,
                    "right": right_ref,
                    "threshold": threshold,
                    "matched_count": matched_count,
                },
                tool_name=tool_name,
            ).with_query(user_request)

        if tool_name == "create_graph":
            table_name, x_col, y_col, kind, error_message = _resolve_graph_target(user_request, ctx)
            if error_message:
                return RouterResult(
                    route=RouteName.PYTHON_TOOL,
                    ok=False,
                    message=error_message,
                    reason="Graph creation needs a clear table target.",
                    tool_name=tool_name,
                ).with_query(user_request)

            df = _fetch_table_df(ctx.con, table_name)
            output_path = create_simple_graph(
                df=df,
                x_col=x_col,
                y_col=y_col,
                kind=kind,
                output_dir=ctx.output_dir,
            )

            return RouterResult(
                route=RouteName.PYTHON_TOOL,
                ok=True,
                message=f'Created a {kind} graph from "{table_name}".',
                reason="The request clearly asked for a graph or visualization.",
                dataframe=df,
                output_path=output_path,
                metadata={"table": table_name, "x_col": x_col, "y_col": y_col, "kind": kind},
                tool_name=tool_name,
            ).with_query(user_request)

        return RouterResult(
            route=RouteName.PYTHON_TOOL,
            ok=False,
            message="That Python tool route is not implemented.",
            reason="The tool name did not match a supported dispatcher branch.",
            tool_name=tool_name,
        ).with_query(user_request)

    except Exception as exc:
        return RouterResult(
            route=RouteName.PYTHON_TOOL,
            ok=False,
            message="Python tool execution failed.",
            reason="The tool route was selected, but execution raised an error.",
            error=str(exc),
            tool_name=tool_name,
        ).with_query(user_request)