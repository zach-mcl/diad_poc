from __future__ import annotations
from pathlib import Path
import threading
import pandas as pd

from UI.state import AppState

from app.db import connect, load_csvs, get_schema_map, get_schema_text, build_categorical_index
from app.llm import nl_to_sql
from app.validate import strip_code_fences, sanitize_sql, is_select_only


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

    def load_folder(self, folder: Path):
        """
        Load CSVs -> DuckDB -> schema -> categorical index.
        Runs in background thread so UI doesn't freeze.
        """
        def work():
            try:
                self._set_busy(True, None)

                csvs = sorted([p for p in folder.iterdir() if p.suffix.lower() == ".csv"])
                if not csvs:
                    self._set_busy(False, f"No CSV files found in: {folder}")
                    return

                self.con = connect()
                tables = load_csvs(self.con, csvs)

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

    def send_chat(self, user_text: str, model: str = "duckdb-nsql"):
        """
        Plain English -> LLM -> SQL -> validate -> execute -> preview -> export path.
        Runs in background thread.
        """
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
