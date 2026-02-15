from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class AppState:
    data_folder: Path | None = None
    csv_files: list[Path] = field(default_factory=list)

    tables: list[str] = field(default_factory=list)
    schema_map: dict[str, dict[str, str]] = field(default_factory=dict)
    categorical_index: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    messages: list[dict[str, str]] = field(default_factory=list)  # {"role": "...", "content": "..."}

    generated_sql: str | None = None
    result_preview: Any = None  # pandas DataFrame or None
    export_path: Path | None = None

    error: str | None = None
    is_busy: bool = False
