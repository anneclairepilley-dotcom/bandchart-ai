"""Helpers for local JSON-file-backed project storage.

Layout:
  backend/storage/projects/<project_id>/
    project.json
    audio/<original_filename>
    output/transcription.mid
    output/transcription.json
    output/transcription-<instrument>.musicxml
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models import Project

# backend/app/storage.py -> backend/storage
BACKEND_DIR = Path(__file__).resolve().parent.parent
STORAGE_ROOT = BACKEND_DIR / "storage"
PROJECTS_ROOT = STORAGE_ROOT / "projects"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_project_id() -> str:
    return uuid.uuid4().hex


def project_dir(project_id: str) -> Path:
    return PROJECTS_ROOT / project_id


def audio_dir(project_id: str) -> Path:
    return project_dir(project_id) / "audio"


def output_dir(project_id: str) -> Path:
    return project_dir(project_id) / "output"


def project_json_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def midi_path(project_id: str) -> Path:
    return output_dir(project_id) / "transcription.mid"


def transcription_json_path(project_id: str) -> Path:
    return output_dir(project_id) / "transcription.json"


def original_transcription_json_path(project_id: str) -> Path:
    """Untouched copy of the transcription, kept so note edits can be undone."""
    return output_dir(project_id) / "transcription-original.json"


def _sheet_stem(instrument_key: str, style: str) -> str:
    stem = f"transcription-{instrument_key.replace('_', '-')}"
    if style == "raw":
        stem += "-raw"
    return stem


def musicxml_path(project_id: str, instrument_key: str, style: str = "clean") -> Path:
    return output_dir(project_id) / f"{_sheet_stem(instrument_key, style)}.musicxml"


def pdf_path(project_id: str, instrument_key: str, style: str = "clean") -> Path:
    return output_dir(project_id) / f"{_sheet_stem(instrument_key, style)}.pdf"


def project_exists(project_id: str) -> bool:
    return project_json_path(project_id).exists()


def create_project_dirs(project_id: str) -> None:
    audio_dir(project_id).mkdir(parents=True, exist_ok=True)
    output_dir(project_id).mkdir(parents=True, exist_ok=True)


def save_project(project: Project) -> None:
    path = project_json_path(project.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project.model_dump(), indent=2))


def load_project(project_id: str) -> Optional[Project]:
    path = project_json_path(project_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return Project(**data)


def list_projects() -> list[Project]:
    if not PROJECTS_ROOT.exists():
        return []
    projects: list[Project] = []
    for entry in PROJECTS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        pj = entry / "project.json"
        if pj.exists():
            try:
                data = json.loads(pj.read_text())
                projects.append(Project(**data))
            except Exception:
                continue
    projects.sort(key=lambda p: p.created_at, reverse=True)
    return projects


def delete_project(project_id: str) -> None:
    """Remove one project's folder (its audio, outputs and metadata) — and
    nothing else. Refuses any path that doesn't resolve to a directory
    directly inside storage/projects/."""
    root = PROJECTS_ROOT.resolve()
    target = project_dir(project_id).resolve()
    if target == root or target.parent != root:
        raise ValueError("Refusing to delete outside the projects folder")
    if target.exists():
        shutil.rmtree(target)


def find_existing_audio(project_id: str) -> Optional[Path]:
    """Return the currently stored audio file for a project, if any."""
    a_dir = audio_dir(project_id)
    if not a_dir.exists():
        return None
    files = [f for f in a_dir.iterdir() if f.is_file()]
    if not files:
        return None
    return files[0]
