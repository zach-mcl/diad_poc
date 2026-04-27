from __future__ import annotations

from pathlib import Path
import os
import threading

from UI.state import AppState

from app.db import connect, load_csvs, get_schema_map, get_schema_text, build_categorical_index
from app.projects import add_files_to_project, create_project, delete_project as delete_project_folder, get_project_file_paths, list_projects, load_project_metadata
from app.schema_aliases import build_alias_index

try:
    from app.db import load_xlsx
except ImportError:
    load_xlsx = None

try:
    from app.db import load_json
except ImportError:
    load_json = None

from app.router import route_request
from app.router_types import RouterContext
from app.sql_flow import format_categorical_text


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class Controller:
    def __init__(self, state: AppState, on_state_changed):
        self.state = state
        self.on_state_changed = on_state_changed
        self.con = None
        self.router_ctx: RouterContext | None = None

    def format_schema_insert_text(
        self,
        table: str,
        column: str | None = None,
        value: object | None = None,
    ) -> str:
        """Return the text inserted when a Data Guide item is dropped into chat."""
        if value is not None and column:
            clean_value = str(value).replace('"', '\"')
            return f'{column} is "{clean_value}"'
        if column:
            return str(column)
        return str(table)

    def format_schema_search_text(
        self,
        table: str,
        column: str | None = None,
        value: object | None = None,
    ) -> str:
        """Return the text used when a Data Guide item is dropped into guide search."""
        if value is not None:
            return str(value)
        if column:
            return str(column)
        return str(table)

    def _set_busy(self, busy: bool, error: str | None = None, status: str | None = None):
        self.state.is_busy = busy
        self.state.error = error
        self.state.status_message = status if busy else None
        self.on_state_changed()

    def _set_status(self, status: str):
        self.state.status_message = status
        self.on_state_changed()

    def refresh_projects(self):
        self.state.available_projects = list_projects()
        self.on_state_changed()

    def delete_project(self, project_dir: str | Path):
        target = Path(project_dir).resolve()

        def work():
            try:
                self._set_busy(True, None, "Deleting project...")

                current = self.state.current_project_path
                deleting_current = current is not None and Path(current).resolve() == target

                delete_project_folder(target)

                if deleting_current:
                    self._clear_open_project_state()

                self.state.available_projects = list_projects()
                self._set_busy(False, None)
            except Exception as exc:
                self.state.available_projects = list_projects()
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _close_connection(self):
        if self.con is not None:
            try:
                self.con.close()
            except Exception:
                pass
            self.con = None

    def _clear_open_project_state(self):
        self._close_connection()
        self.router_ctx = None
        self.state.data_folder = None
        self.state.csv_files = []
        self.state.xlsx_files = []
        self.state.json_files = []
        self.state.tables = []
        self.state.schema_map = {}
        self.state.categorical_index = {}
        self.state.generated_sql = None
        self.state.result_preview = None
        self.state.export_path = None
        self.state.artifact_path = None
        self.state.artifact_kind = None
        self.state.auto_open_artifact_path = None
        self.state.current_project_name = None
        self.state.current_project_path = None
        self.state.current_project_created_at = None
        self.state.messages = []

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
        source_files.extend(str(p) for p in getattr(self.state, "json_files", []))

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
        jsons = sorted([p for p in file_paths if p.suffix.lower() == ".json"])

        if not csvs and not xlsxs and not jsons:
            raise RuntimeError(f"No CSV, XLSX, or JSON files found in project: {metadata.get('name', project_dir.name)}")

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

        skipped_json = False
        if jsons:
            if load_json is None:
                skipped_json = True
            else:
                tables.extend(load_json(self.con, jsons))

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
        self.state.json_files = jsons
        self.state.tables = tables
        self.state.schema_map = schema_map
        self.state.categorical_index = categorical_index
        self.state.generated_sql = None
        self.state.result_preview = None
        self.state.export_path = None
        self.state.artifact_path = None
        self.state.artifact_kind = None
        self.state.auto_open_artifact_path = None
        self.state.error = None

        self.state.current_project_name = metadata.get("name", project_dir.name)
        self.state.current_project_path = project_dir
        self.state.current_project_created_at = metadata.get("created_at")

        self.router_ctx = self._build_router_context(model=model)
        self.state.available_projects = list_projects()

        intro_lines = [
            f"You're ready to chat with {self.state.current_project_name}.",
            "",
            f"I loaded {len(csvs) + len(xlsxs) + len(jsons)} file(s) and created {len(tables)} table(s).",
        ]

        if tables:
            intro_lines.append("")
            intro_lines.append("Tables available:")
            for table in tables:
                intro_lines.append(f"- {table}")

        intro_lines.append("")
        intro_lines.append("You can ask for rows, counts, filters, joins, charts, or just ask what tables and columns are available.")

        warnings: list[str] = []
        if skipped_xlsx:
            warnings.append("Some XLSX files were skipped because app.db.load_xlsx is not available.")
        if skipped_json:
            warnings.append("Some JSON files were skipped because app.db.load_json is not available.")
        if warnings:
            intro_lines.append("")
            intro_lines.append("Heads up:")
            intro_lines.extend(f"- {warning}" for warning in warnings)

        if skipped_json:
            intro_lines.append("Warning: JSON files were found, but app.db.load_xlsx does not exist yet. Those files were skipped.")

        self.state.messages = [
            {
                "role": "assistant",
                "content": "\n".join(intro_lines),
            }
        ]

    def create_project(self, project_name: str, file_paths: list[str | Path], model: str = "duckdb-nsql"):
        def work():
            try:
                self._set_busy(True, None, "Creating project...")
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
                self._set_busy(True, None, "Opening project...")
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
                self._set_busy(True, None, "Adding files...")
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

    def _clean_display_value(self, value) -> str:
        text = str(value)
        parts = text.split(".")
        if len(parts) >= 3:
            # Internal alias values sometimes look like table.column.Value.
            # For normal users, show just the actual value.
            return parts[-1]
        return text

    def _format_applied_filters(self, metadata: dict) -> list[str]:
        filters: list[str] = []
        seen: set[str] = set()

        for item in metadata.get("bound_constraints") or []:
            if not isinstance(item, dict):
                continue
            column = str(item.get("column") or "").strip()
            value = self._clean_display_value(item.get("value", "")).strip()
            if not column or not value:
                continue
            line = f"- {column}: {value}"
            if line not in seen:
                seen.add(line)
                filters.append(line)

        return filters

    def _format_columns_included(self, df) -> str | None:
        try:
            columns = [str(col) for col in list(df.columns)]
        except Exception:
            return None

        if not columns:
            return None

        if len(columns) <= 8:
            return ", ".join(columns)

        return ", ".join(columns[:8]) + f", and {len(columns) - 8} more"

    def _format_friendly_message(self, user_text: str, result) -> str:
        metadata = result.metadata or {}
        route = getattr(result.route, "value", str(result.route))
        route = str(route)

        if result.error:
            message = result.message or str(result.error)
            return (
                "I could not finish that request.\n\n"
                f"What happened: {message}\n\n"
                "Try rewording the question or check the table and column names in the Data Guide."
            )

        if route == "OUT_OF_SCOPE":
            return result.message or "I can only answer questions about the data loaded in this project."

        if route == "DATA_QUESTION":
            return result.message or "Here is what I found in the loaded project metadata."

        if route == "PYTHON_TOOL":
            parts = [result.message or "I ran that data tool for you."]
            output_path = Path(result.output_path) if result.output_path else None
            is_chart = bool(output_path and output_path.suffix.lower() in _IMAGE_EXTENSIONS)
            if is_chart:
                parts.append("")
                parts.append("I opened the chart for you. You can also use Download Chart to save the image.")
                if result.dataframe is not None:
                    parts.append("Open Output will show the chart again, and the chart data is also available as a CSV export.")
            elif result.output_path:
                parts.append("")
                parts.append("The output is ready to open or download.")
            elif result.dataframe is not None:
                parts.append("")
                parts.append("You can use Open Output to preview the results, or Download CSV to save them.")
            return "\n".join(parts)

        if route == "SQL_QUERY":
            df = result.dataframe
            row_count = metadata.get("row_count")

            if df is not None:
                try:
                    rows, cols = df.shape
                except Exception:
                    rows = row_count if row_count is not None else 0
                    cols = 0
            else:
                rows = row_count
                cols = 0

            if rows == 0:
                parts = [
                    "I did not find any matching rows.",
                    "",
                    "That usually means the filters were valid, but no records matched them.",
                ]
            elif rows is not None:
                row_word = "row" if rows == 1 else "rows"
                parts = [f"I found {rows} matching {row_word}."]
            else:
                parts = ["I ran the query successfully."]

            filters = self._format_applied_filters(metadata)
            if filters:
                parts.append("")
                parts.append("Filters I used:")
                parts.extend(filters)

            if df is not None:
                columns_text = self._format_columns_included(df)
                if columns_text:
                    parts.append("")
                    parts.append(f"Columns included: {columns_text}")

                parts.append("")
                parts.append("You can use Open Output to preview the results, or Download CSV to save them.")

            if result.message and rows is None:
                parts.append("")
                parts.append(result.message)

            return "\n".join(parts)

        return result.message or "Done."

    def _should_show_debug_messages(self) -> bool:
        value = os.environ.get("DIAD_DEBUG_MESSAGES", "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def send_chat(self, user_text: str, model: str = "duckdb-nsql"):
        if not self.con:
            self.state.error = "Open or create a project first."
            self.on_state_changed()
            return

        def work():
            try:
                self._set_busy(True, None, "Starting request...")

                self.state.messages.append({"role": "user", "content": user_text})
                self._set_status("Reading your data setup...")

                self.router_ctx = self._build_router_context(model=model)
                self._set_status("Choosing the right way to answer...")
                result = route_request(user_text, self.router_ctx)
                self._set_status("Preparing the answer...")

                self.state.generated_sql = result.sql
                self.state.export_path = None
                self.state.result_preview = None
                self.state.artifact_path = None
                self.state.artifact_kind = None
                self.state.auto_open_artifact_path = None

                if result.output_path:
                    output_path = Path(result.output_path).resolve()
                    if output_path.suffix.lower() in _IMAGE_EXTENSIONS:
                        self.state.artifact_path = output_path
                        self.state.artifact_kind = "image"
                        self.state.auto_open_artifact_path = output_path
                    else:
                        self.state.export_path = output_path

                if result.dataframe is not None:
                    df = result.dataframe
                    self.state.result_preview = df

                    out = Path("output.csv").resolve()
                    df.to_csv(out, index=False)
                    self.state.export_path = out

                if self._should_show_debug_messages():
                    assistant_message = self._format_debug_message(user_text, result)
                    if result.dataframe is not None:
                        assistant_message += f"\n\nExported CSV: {self.state.export_path} ({len(result.dataframe)} rows)"
                    if self.state.artifact_path:
                        assistant_message += f"\nChart image: {self.state.artifact_path}"
                else:
                    assistant_message = self._format_friendly_message(user_text, result)

                self.state.messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message,
                    }
                )

                self._set_busy(False, None)

            except Exception as exc:
                if self._should_show_debug_messages():
                    msg = f"Error: {exc}"
                    if self.state.generated_sql:
                        msg += f"\n\nSQL was:\n{self.state.generated_sql}"
                else:
                    msg = (
                        "I ran into an error while answering that.\n\n"
                        f"What happened: {exc}\n\n"
                        "Try rewording the request, or use the Data Guide to confirm the table and column names."
                    )
                self.state.messages.append({"role": "assistant", "content": msg})
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()