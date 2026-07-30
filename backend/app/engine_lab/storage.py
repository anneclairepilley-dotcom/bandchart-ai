"""Storage for the Engine Lab — deliberately separate from
backend/storage/projects/ so lab runs (and any experiment output) can
never collide with or corrupt real project data.

Layout:
  backend/storage/engine_lab/
    fixtures/<fixture_key>.wav       generated synthetic test audio (cached)
    audio/<audio_id>/<filename>      audio uploaded directly into the lab
    runs/<run_id>/
      meta.json                       engine, source, stats, messages, timing
      output.mid
      output.json
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
LAB_ROOT = BACKEND_DIR / "storage" / "engine_lab"
FIXTURES_DIR = LAB_ROOT / "fixtures"
AUDIO_DIR = LAB_ROOT / "audio"
RUNS_DIR = LAB_ROOT / "runs"


def new_id() -> str:
    return uuid.uuid4().hex


def fixture_audio_path(fixture_key: str) -> Path:
    return FIXTURES_DIR / f"{fixture_key}.wav"


def new_audio_dir(audio_id: str) -> Path:
    path = AUDIO_DIR / audio_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_uploaded_audio(audio_id: str) -> Optional[Path]:
    a_dir = AUDIO_DIR / audio_id
    if not a_dir.exists():
        return None
    files = [f for f in a_dir.iterdir() if f.is_file()]
    return files[0] if files else None


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def run_meta_path(run_id: str) -> Path:
    return run_dir(run_id) / "meta.json"


def run_midi_path(run_id: str) -> Path:
    return run_dir(run_id) / "output.mid"


def run_json_path(run_id: str) -> Path:
    return run_dir(run_id) / "output.json"


def save_run(run_id: str, meta: dict[str, Any]) -> None:
    run_dir(run_id).mkdir(parents=True, exist_ok=True)
    run_meta_path(run_id).write_text(json.dumps(meta, indent=2))


def load_run(run_id: str) -> Optional[dict[str, Any]]:
    path = run_meta_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    runs = []
    for entry in RUNS_DIR.iterdir():
        meta_path = entry / "meta.json"
        if meta_path.exists():
            try:
                runs.append(json.loads(meta_path.read_text()))
            except Exception:
                continue
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[:limit]
