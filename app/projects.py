from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_projects_root() -> Path:
    root = _repo_root() / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clean_project_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(name or "").strip())
    if not cleaned:
        raise ValueError("Project name cannot be empty.")
    return cleaned


def _safe_project_dir_name(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    safe = re.sub(r"\s+", " ", safe)
    safe = safe.rstrip(". ")
    if not safe:
        raise ValueError("Project name is not valid.")
    return safe


def _normalize_source_paths(source_paths: list[str | Path]) -> list[Path]:
    normalized: list[Path] = []
    seen: set[Path] = set()

    for raw in source_paths:
        p = Path(raw).expanduser().resolve()
        if p in seen:
            continue
        seen.add(p)

        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        if not p.is_file():
            raise ValueError(f"Not a file: {p}")
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {p.name}")

        normalized.append(p)

    if not normalized:
        raise ValueError("Select at least one CSV or XLSX file.")

    return normalized


def _project_json_path(project_dir: Path) -> Path:
    return project_dir / "project.json"


def _project_files_dir(project_dir: Path) -> Path:
    return project_dir / "files"


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid project metadata: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_destination(files_dir: Path, filename: str) -> Path:
    base = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = files_dir / filename
    counter = 2

    while candidate.exists():
        candidate = files_dir / f"{base}_{counter}{suffix}"
        counter += 1

    return candidate


def load_project_metadata(project_dir: str | Path) -> dict[str, Any]:
    project_dir = Path(project_dir)
    meta_path = _project_json_path(project_dir)
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing project metadata: {meta_path}")

    data = _load_json(meta_path)
    data.setdefault("name", project_dir.name)
    data.setdefault("created_at", "")
    data.setdefault("files", [])
    data["path"] = str(project_dir)
    return data


def get_project_file_paths(project_dir: str | Path) -> list[Path]:
    project_dir = Path(project_dir)
    metadata = load_project_metadata(project_dir)
    files_dir = _project_files_dir(project_dir)

    paths: list[Path] = []
    seen: set[Path] = set()

    for rel_name in metadata.get("files", []):
        p = (files_dir / rel_name).resolve()
        if p.exists() and p.is_file() and p not in seen:
            paths.append(p)
            seen.add(p)

    if not paths and files_dir.exists():
        for p in sorted(files_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS and p not in seen:
                paths.append(p)
                seen.add(p)

    return paths


def list_projects() -> list[dict[str, Any]]:
    root = get_projects_root()
    projects: list[dict[str, Any]] = []

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue

        meta_path = _project_json_path(child)
        if not meta_path.exists():
            continue

        try:
            metadata = load_project_metadata(child)
        except Exception:
            continue

        files = get_project_file_paths(child)
        projects.append(
            {
                "name": metadata.get("name", child.name),
                "created_at": metadata.get("created_at", ""),
                "path": str(child),
                "file_count": len(files),
                "files": [p.name for p in files],
            }
        )

    projects.sort(key=lambda item: (item.get("created_at", ""), item.get("name", "").lower()), reverse=True)
    return projects


def create_project(project_name: str, source_paths: list[str | Path]) -> Path:
    clean_name = _clean_project_name(project_name)
    dir_name = _safe_project_dir_name(clean_name)
    project_dir = get_projects_root() / dir_name

    if project_dir.exists():
        raise ValueError(f'A project named "{clean_name}" already exists.')

    files = _normalize_source_paths(source_paths)

    project_dir.mkdir(parents=True, exist_ok=False)
    files_dir = _project_files_dir(project_dir)
    files_dir.mkdir(parents=True, exist_ok=True)

    stored_files: list[str] = []
    for src in files:
        dest = _unique_destination(files_dir, src.name)
        shutil.copy2(src, dest)
        stored_files.append(dest.name)

    metadata = {
        "name": clean_name,
        "created_at": _timestamp_now(),
        "files": stored_files,
    }
    _write_json(_project_json_path(project_dir), metadata)
    return project_dir


def add_files_to_project(project_dir: str | Path, source_paths: list[str | Path]) -> Path:
    project_dir = Path(project_dir)
    metadata = load_project_metadata(project_dir)
    files = _normalize_source_paths(source_paths)

    files_dir = _project_files_dir(project_dir)
    files_dir.mkdir(parents=True, exist_ok=True)

    stored_files = list(metadata.get("files", []))

    for src in files:
        dest = _unique_destination(files_dir, src.name)
        shutil.copy2(src, dest)
        stored_files.append(dest.name)

    metadata["files"] = stored_files
    _write_json(_project_json_path(project_dir), metadata)
    return project_dir