from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class RouteName(str, Enum):
    SQL_QUERY = "SQL_QUERY"
    PYTHON_TOOL = "PYTHON_TOOL"
    DATA_QUESTION = "DATA_QUESTION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(slots=True)
class RouteDecision:
    route: RouteName
    reason: str
    tool_name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouterContext:
    con: Any
    model: str
    schema_text: str
    schema_map: dict[str, dict[str, str]]
    categorical_index: dict[tuple[str, str], list[str]]
    categorical_text: str
    alias_index: Any | None = None
    source_files: list[str] = field(default_factory=list)
    output_dir: str = "outputs"


@dataclass(slots=True)
class RouterResult:
    route: RouteName
    ok: bool
    message: str
    reason: str
    sql: str | None = None
    dataframe: Any = None
    output_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    original_query: str = ""
    tool_name: str | None = None

    def with_query(self, user_query: str) -> "RouterResult":
        self.original_query = user_query
        return self