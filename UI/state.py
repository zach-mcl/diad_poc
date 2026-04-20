from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppState:
    data_folder: Path | None = None
    csv_files: list[Path] = field(default_factory=list)
    xlsx_files: list[Path] = field(default_factory=list)

    tables: list[str] = field(default_factory=list)
    schema_map: dict[str, dict[str, str]] = field(default_factory=dict)
    categorical_index: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    messages: list[dict[str, str]] = field(default_factory=list)

    generated_sql: str | None = None
    result_preview: Any = None
    export_path: Path | None = None

    available_projects: list[dict[str, Any]] = field(default_factory=list)
    current_project_name: str | None = None
    current_project_path: Path | None = None
    current_project_created_at: str | None = None

    error: str | None = None
    is_busy: bool = False