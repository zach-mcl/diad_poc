from __future__ import annotations
from pathlib import Path
import threading
import pandas as pd

from UI.state import AppState

from app.db import connect, load_csvs, load_xlsx, get_schema_map, get_schema_text, build_categorical_index
from app.llm import nl_to_sql
from app.validate import strip_code_fences, sanitize_sql, is_select_only
from app.schema_aliases import build_alias_index


def _format_categoricals_for_llm(cat_index: dict[tuple[str, str], list[str]], limit_vals: int = 30) -> str:
    # simple + unambiguous format
    lines = []
    for (t, c), vals in sorted(cat_index.items(), key=lambda x: (x[0][0].lower(), x[0][1].lower())):
        clean = []
        seen = set()
        for v in vals:
            s = str(v).strip()
            if not s:
                continue
            if s not in seen:
                clean.append(s)
                seen.add(s)
        if clean:
            shown = clean[:limit_vals]
            quoted = ", ".join(f'"{v.replace(chr(34), "")}"' for v in shown)
            suffix = " ..." if len(clean) > limit_vals else ""
            lines.append(f'- "{t}"."{c}" allowed_values=[{quoted}]{suffix}')
    return "\n".join(lines)


class Controller:
    def __init__(self, state: AppState, on_state_changed):
        self.state = state
        self.on_state_changed = on_state_changed
        self.con = None  # duckdb connection

    def _set_busy(self, busy: bool, error: str | None = None):
        self.state.is_busy = busy
        self.state.error = error
        self.on_state_changed()

<<<<<<< Updated upstream
    def load_folder(self, folder: Path):
        """
        Load CSVs -> DuckDB -> schema -> categorical index.
        Runs in background thread so UI doesn't freeze.
        """
=======
    def _build_router_context(self, model: str = "duckdb-nsql") -> RouterContext:
        if self.con is None:
            raise RuntimeError("DuckDB connection is not initialized.")

        schema_text = get_schema_text(self.con)
        schema_map = get_schema_map(self.con)
        categorical_index = build_categorical_index(
            self.con,
            schema_map,
            max_cols_total=60,
            values_limit=50,
        )
        categorical_text = format_categorical_text(categorical_index)

        alias_index = build_alias_index(
            schema_map=schema_map,
            categorical_index=categorical_index,
            model=model,
            schema_text=schema_text,
            categorical_text=categorical_text,
        )

        source_files = [str(p) for p in getattr(self.state, "csv_files", [])]
        source_files.extend(str(p) for p in getattr(self.state, "xlsx_files", []))

        return RouterContext(
            con=self.con,
            model=model,
            schema_text=schema_text,
            schema_map=schema_map,
            categorical_index=categorical_index,
            categorical_text=categorical_text,
            alias_index=alias_index,
            source_files=source_files,
            output_dir="outputs",
        )

    def load_folder(self, folder: Path, model: str = "duckdb-nsql"):
>>>>>>> Stashed changes
        def work():
            try:
                self._set_busy(True, None)
                #TODO add xlsx support
                csvs = sorted([p for p in folder.iterdir() if p.suffix.lower() == ".csv"])
                #added xlsx variable -jm
                xlsx = sorted([p for p in folder.iterdir() if p.suffix.lower() == ".xlsx"])
                if not csvs and not xlsx: # changed to also error check for no xlsx -jm
                    self._set_busy(False, f"No CSV OR XLSX files found in: {folder}")
                    return

                self.con = connect()
                #tables = load_csvs(self.con, csvs) - Old -jm
                tables =[]
                if csvs:
                    tables.extend(load_csvs(self.con, csvs))
                if xlsx:
                    tables.extend(load_xlsx(self.con, xlsx))
                #changed aboce to support xlsx -jm



                #in this block

                schema_map = get_schema_map(self.con)
                categorical_index = build_categorical_index(self.con, schema_map, max_cols_total=60, values_limit=50)

                self.state.data_folder = folder
                self.state.csv_files = csvs
                self.state.tables = tables
                self.state.schema_map = schema_map
                self.state.categorical_index = categorical_index
                self.state.generated_sql = None
                self.state.result_preview = None
                self.state.export_path = None
                self.state.error = None

                self._set_busy(False, None)
            except Exception as e:
                self._set_busy(False, str(e))

        threading.Thread(target=work, daemon=True).start()

<<<<<<< Updated upstream
    def send_chat(self, user_text: str, model: str = "duckdb-nsql"):
        """
        Plain English -> LLM -> SQL -> validate -> execute -> preview -> export path.
        Runs in background thread.
        """
=======
    def _format_debug_message(self, user_text: str, result) -> str:
        metadata = result.metadata or {}

        parts: list[str] = []
        parts.append(f"Route: {result.route.value}")
        parts.append(f"Reason: {result.reason}")

        tool_name = getattr(result, "tool_name", None)
        if tool_name:
            parts.append(f"Tool: {tool_name}")

        execution_mode = metadata.get("execution_mode")
        if execution_mode:
            parts.append(f"Execution mode: {execution_mode}")

        parts.append("")
        parts.append("Original query:")
        parts.append(str(metadata.get("original_user_request") or user_text))

        grounded_user_request = metadata.get("grounded_user_request")
        if grounded_user_request:
            parts.append("")
            parts.append("Grounded query:")
            parts.append(str(grounded_user_request))

        grounding_replacements = metadata.get("grounding_replacements")
        if grounding_replacements:
            parts.append("")
            parts.append("Grounding replacements:")
            for item in grounding_replacements:
                parts.append(f"- {item}")

        preferred_table = metadata.get("preferred_table")
        if preferred_table:
            parts.append("")
            parts.append(f"Preferred table: {preferred_table}")

        mentioned_tables = metadata.get("mentioned_tables")
        if mentioned_tables:
            parts.append(f"Mentioned tables: {mentioned_tables}")

        bound_constraints = metadata.get("bound_constraints")
        if bound_constraints:
            parts.append("Bound constraints:")
            for item in bound_constraints:
                parts.append(f"- {item}")

        if result.message:
            parts.append("")
            parts.append("Message:")
            parts.append(result.message)

        raw_model_output = metadata.get("raw_model_output")
        if raw_model_output:
            parts.append("")
            parts.append("Raw model output:")
            parts.append(str(raw_model_output))

        initial_sql = metadata.get("initial_sql")
        if initial_sql:
            parts.append("")
            parts.append("Initial SQL:")
            parts.append(str(initial_sql))

        if result.sql:
            parts.append("")
            parts.append("Final SQL:")
            parts.append(result.sql)

        if "auto_join_changed" in metadata:
            parts.append("")
            parts.append(f"Auto join changed SQL: {metadata.get('auto_join_changed')}")

        missing_columns = metadata.get("missing_columns")
        if missing_columns:
            parts.append("Missing columns detected:")
            for item in missing_columns:
                parts.append(f"- {item}")

        rewrite_model_output = metadata.get("rewrite_model_output")
        if rewrite_model_output:
            parts.append("")
            parts.append("Rewrite model output:")
            parts.append(str(rewrite_model_output))

        row_count = metadata.get("row_count")
        if row_count is not None:
            parts.append("")
            parts.append(f"Row count: {row_count}")

        if result.output_path:
            parts.append("")
            parts.append(f"Output path: {result.output_path}")

        if result.error:
            parts.append("")
            parts.append("Error:")
            parts.append(str(result.error))

        return "\n".join(parts)

    def send_chat(self, user_text: str, model: str = "duckdb-nsql"):
>>>>>>> Stashed changes
        if not self.con:
            self.state.error = "Load a folder with CSVs first."
            self.on_state_changed()
            return

        def work():
            try:
                self._set_busy(True, None)
                self.state.messages.append({"role": "user", "content": user_text})
                self.on_state_changed()

                schema_text = get_schema_text(self.con)
                cats_text = _format_categoricals_for_llm(self.state.categorical_index)

                raw = nl_to_sql(
                    model=model,
                    schema_text=schema_text,
                    categorical_text=cats_text,
                    user_request=user_text,
                )

                sql = sanitize_sql(strip_code_fences(raw)).strip()

                if sql.strip() == "-- I_DONT_KNOW":
                    self.state.messages.append({"role": "assistant", "content": "Model could not answer from schema. Try being more specific."})
                    self._set_busy(False, None)
                    return

                ok, reason = is_select_only(sql)
                if not ok:
                    self.state.messages.append({"role": "assistant", "content": f"Blocked SQL: {reason}\n\nModel output:\n{raw}"})
                    self._set_busy(False, None)
                    return

                # Execute
                df = self.con.execute(sql).df()

                # Export
                out = Path("output.csv").resolve()
                df.to_csv(out, index=False)

                self.state.generated_sql = sql
                self.state.result_preview = df
                self.state.export_path = out
                self.state.messages.append({"role": "assistant", "content": f"Generated SQL:\n{sql}\n\nExported: {out} ({len(df)} rows)"})

                self._set_busy(False, None)

            except Exception as e:
                # Always show SQL if we had it
                msg = f"Error: {e}"
                if self.state.generated_sql:
                    msg += f"\n\nSQL was:\n{self.state.generated_sql}"
                self.state.messages.append({"role": "assistant", "content": msg})
                self._set_busy(False, str(e))

        threading.Thread(target=work, daemon=True).start()
