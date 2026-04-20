from __future__ import annotations

from pathlib import Path
import threading

from UI.state import AppState

from app.db import connect, load_csvs, get_schema_map, get_schema_text, build_categorical_index
from app.projects import add_files_to_project, create_project, get_project_file_paths, list_projects, load_project_metadata
from app.schema_aliases import build_alias_index

try:
    from app.db import load_xlsx
except ImportError:
    load_xlsx = None

from app.router import route_request
from app.router_types import RouterContext
from app.sql_flow import format_categorical_text


class Controller:
    def __init__(self, state: AppState, on_state_changed):
        self.state = state
        self.on_state_changed = on_state_changed
        self.con = None
        self.router_ctx: RouterContext | None = None

    def _set_busy(self, busy: bool, error: str | None = None):
        self.state.is_busy = busy
        self.state.error = error
        self.on_state_changed()

    def refresh_projects(self):
        self.state.available_projects = list_projects()
        self.on_state_changed()

    def _close_connection(self):
        if self.con is not None:
            try:
                self.con.close()
            except Exception:
                pass
            self.con = None

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

    def _load_project_into_state(self, project_dir: Path, model: str = "duckdb-nsql"):
        metadata = load_project_metadata(project_dir)
        file_paths = get_project_file_paths(project_dir)

        csvs = sorted([p for p in file_paths if p.suffix.lower() == ".csv"])
        xlsxs = sorted([p for p in file_paths if p.suffix.lower() == ".xlsx"])

        if not csvs and not xlsxs:
            raise RuntimeError(f"No CSV or XLSX files found in project: {metadata.get('name', project_dir.name)}")

        self._close_connection()
        self.con = connect()

        tables: list[str] = []

        if csvs:
            tables.extend(load_csvs(self.con, csvs))

        skipped_xlsx = False
        if xlsxs:
            if load_xlsx is None:
                skipped_xlsx = True
            else:
                tables.extend(load_xlsx(self.con, xlsxs))

        schema_map = get_schema_map(self.con)
        categorical_index = build_categorical_index(
            self.con,
            schema_map,
            max_cols_total=60,
            values_limit=50,
        )

        self.state.data_folder = project_dir
        self.state.csv_files = csvs
        self.state.xlsx_files = xlsxs
        self.state.tables = tables
        self.state.schema_map = schema_map
        self.state.categorical_index = categorical_index
        self.state.generated_sql = None
        self.state.result_preview = None
        self.state.export_path = None
        self.state.error = None

        self.state.current_project_name = metadata.get("name", project_dir.name)
        self.state.current_project_path = project_dir
        self.state.current_project_created_at = metadata.get("created_at")

        self.router_ctx = self._build_router_context(model=model)
        self.state.available_projects = list_projects()

        intro_lines = [
            f"Loaded project: {self.state.current_project_name}",
            f"Project path: {project_dir}",
            f"Files: {len(csvs) + len(xlsxs)}",
            f"Tables: {', '.join(tables) if tables else '(none)'}",
            f"CSV files: {len(csvs)}",
            f"XLSX files: {len(xlsxs)}",
        ]

        if skipped_xlsx:
            intro_lines.append("Warning: XLSX files were found, but app.db.load_xlsx does not exist yet. Those files were skipped.")

        self.state.messages = [
            {
                "role": "assistant",
                "content": "\n".join(intro_lines),
            }
        ]

    def create_project(self, project_name: str, file_paths: list[str | Path], model: str = "duckdb-nsql"):
        def work():
            try:
                self._set_busy(True, None)
                project_dir = create_project(project_name, file_paths)
                self._load_project_into_state(project_dir, model=model)
                self._set_busy(False, None)
            except Exception as exc:
                self.state.available_projects = list_projects()
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def open_project(self, project_dir: str | Path, model: str = "duckdb-nsql"):
        def work():
            try:
                self._set_busy(True, None)
                self._load_project_into_state(Path(project_dir), model=model)
                self._set_busy(False, None)
            except Exception as exc:
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def add_files_to_current_project(self, file_paths: list[str | Path], model: str = "duckdb-nsql"):
        if not self.state.current_project_path:
            self.state.error = "Open or create a project first."
            self.on_state_changed()
            return

        project_dir = self.state.current_project_path

        def work():
            try:
                self._set_busy(True, None)
                add_files_to_project(project_dir, file_paths)
                self._load_project_into_state(project_dir, model=model)
                self._set_busy(False, None)
            except Exception as exc:
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

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
        if not self.con:
            self.state.error = "Open or create a project first."
            self.on_state_changed()
            return

        def work():
            try:
                self._set_busy(True, None)

                self.state.messages.append({"role": "user", "content": user_text})
                self.on_state_changed()

                self.router_ctx = self._build_router_context(model=model)
                result = route_request(user_text, self.router_ctx)

                self.state.generated_sql = result.sql
                self.state.export_path = None
                self.state.result_preview = None

                if result.output_path:
                    self.state.export_path = Path(result.output_path)

                if result.dataframe is not None:
                    df = result.dataframe
                    self.state.result_preview = df

                    out = Path("output.csv").resolve()
                    df.to_csv(out, index=False)
                    self.state.export_path = out

                debug_message = self._format_debug_message(user_text, result)

                if result.dataframe is not None:
                    debug_message += f"\n\nExported: {self.state.export_path} ({len(result.dataframe)} rows)"

                self.state.messages.append(
                    {
                        "role": "assistant",
                        "content": debug_message,
                    }
                )

                self._set_busy(False, None)

            except Exception as exc:
                msg = f"Error: {exc}"
                if self.state.generated_sql:
                    msg += f"\n\nSQL was:\n{self.state.generated_sql}"
                self.state.messages.append({"role": "assistant", "content": msg})
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()