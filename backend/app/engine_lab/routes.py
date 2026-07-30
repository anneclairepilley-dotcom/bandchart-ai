"""Engine Lab API: /api/engine-lab/*.

A side area, deliberately isolated from the main /api/projects/* routes and
the real transcription pipeline — nothing here writes to a project's
transcription.json or affects a normal transcribe run. It exists purely to
run one engine at a time against a chosen audio source and report what
happened, so engines can be compared honestly.
"""

from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import storage as project_storage
from app.engine_lab import fixtures, scoring, stats
from app.engine_lab import storage as lab_storage
from app.engine_lab.adapters import ADAPTERS, get_adapter
from app.transcription import write_midi_from_notes

router = APIRouter(prefix="/api/engine-lab", tags=["engine-lab"])

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.get("/engines")
def list_engines() -> list[dict[str, Any]]:
    result = []
    for adapter in ADAPTERS:
        available, reason = adapter.is_available()
        result.append(
            {
                "key": adapter.key,
                "label": adapter.label,
                "description": adapter.description,
                "available": available,
                "unavailable_reason": None if available else reason,
            }
        )
    return result


@router.get("/fixtures")
def list_fixtures_endpoint() -> list[dict[str, Any]]:
    return [
        {
            "key": f.key,
            "label": f.label,
            "description": f.description,
            "expected_note_count": len(f.expected_notes),
        }
        for f in fixtures.list_fixtures()
    ]


@router.get("/fixtures/{fixture_key}/audio")
def get_fixture_audio(fixture_key: str) -> FileResponse:
    path = lab_storage.fixture_audio_path(fixture_key)
    fixture = fixtures.ensure_fixture_audio(fixture_key, path)
    if fixture is None:
        raise HTTPException(status_code=404, detail=f"Unknown fixture '{fixture_key}'.")
    return FileResponse(path=str(path), media_type="audio/wav", filename=path.name)


@router.get("/sources")
def list_sources() -> dict[str, Any]:
    """Everything the lab can run an engine against: real projects with
    audio (already uploaded/imported), plus the built-in fixtures."""
    projects = [
        {"project_id": p.id, "name": p.name, "instrument": p.instrument}
        for p in project_storage.list_projects()
        if p.audio_filename
    ]
    fixture_list = [
        {"fixture_key": f.key, "label": f.label} for f in fixtures.list_fixtures()
    ]
    return {"projects": projects, "fixtures": fixture_list}


@router.post("/audio")
async def upload_lab_audio(file: UploadFile = File(...)) -> dict[str, Any]:
    original_name = file.filename or ""
    safe_name = Path(original_name).name
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="That file type isn't supported. Please choose an audio file "
            "ending in: " + ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS)) + ".",
        )
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="That file is over the 50MB limit.")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    audio_id = lab_storage.new_id()
    a_dir = lab_storage.new_audio_dir(audio_id)
    (a_dir / safe_name).write_bytes(contents)
    return {"audio_id": audio_id, "filename": safe_name}


class RunSource(BaseModel):
    kind: str  # "project" | "fixture" | "upload"
    project_id: Optional[str] = None
    fixture_key: Optional[str] = None
    audio_id: Optional[str] = None


class RunRequest(BaseModel):
    engine: str
    source: RunSource


def _resolve_source(source: RunSource) -> tuple[Path, str, Optional[list[dict[str, Any]]]]:
    """Returns (audio_path, human_label, expected_notes_or_none)."""
    if source.kind == "project":
        if not source.project_id:
            raise HTTPException(status_code=400, detail="project_id is required for a project source.")
        project = project_storage.load_project(source.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        audio_path = project_storage.find_existing_audio(source.project_id)
        if audio_path is None:
            raise HTTPException(status_code=400, detail="That project has no uploaded audio yet.")
        return audio_path, f"Project: {project.name}", None

    if source.kind == "fixture":
        if not source.fixture_key:
            raise HTTPException(status_code=400, detail="fixture_key is required for a fixture source.")
        path = lab_storage.fixture_audio_path(source.fixture_key)
        fixture = fixtures.ensure_fixture_audio(source.fixture_key, path)
        if fixture is None:
            raise HTTPException(status_code=404, detail=f"Unknown fixture '{source.fixture_key}'.")
        return path, f"Fixture: {fixture.label}", fixture.expected_notes

    if source.kind == "upload":
        if not source.audio_id:
            raise HTTPException(status_code=400, detail="audio_id is required for an upload source.")
        audio_path = lab_storage.find_uploaded_audio(source.audio_id)
        if audio_path is None:
            raise HTTPException(status_code=404, detail="Uploaded audio not found.")
        return audio_path, f"Uploaded: {audio_path.name}", None

    raise HTTPException(status_code=400, detail=f"Unknown source kind '{source.kind}'.")


@router.post("/runs")
def create_run(body: RunRequest) -> dict[str, Any]:
    adapter = get_adapter(body.engine)
    if adapter is None:
        raise HTTPException(status_code=400, detail=f"Unknown engine '{body.engine}'.")

    available, reason = adapter.is_available()
    if not available:
        raise HTTPException(status_code=400, detail=f"Engine unavailable: {reason}")

    audio_path, source_label, expected_notes = _resolve_source(body.source)

    started = time.monotonic()
    error: Optional[str] = None
    notes: list[dict[str, Any]] = []
    messages: list[str] = []
    try:
        output = adapter.run(audio_path)
        notes = output.notes
        messages = output.messages
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        messages = [f"Engine failed: {exc}"]
    processing_time_s = round(time.monotonic() - started, 3)

    run_id = lab_storage.new_id()
    write_midi_from_notes(notes, lab_storage.run_midi_path(run_id))
    lab_storage.run_json_path(run_id).parent.mkdir(parents=True, exist_ok=True)
    lab_storage.run_json_path(run_id).write_text(json.dumps(notes, indent=2))

    run_stats = stats.compute_stats(notes)
    score = scoring.score_against_expected(expected_notes, notes) if expected_notes else None

    meta = {
        "run_id": run_id,
        "engine_key": adapter.key,
        "engine_label": adapter.label,
        "source": body.source.model_dump(),
        "source_label": source_label,
        "created_at": project_storage.now_iso(),
        "processing_time_s": processing_time_s,
        "error": error,
        "messages": messages,
        "notes": notes,
        **run_stats,
        "scoring": score,
    }
    lab_storage.save_run(run_id, meta)
    return meta


@router.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    return lab_storage.list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = lab_storage.load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("/runs/{run_id}/download/midi")
def download_run_midi(run_id: str) -> FileResponse:
    if lab_storage.load_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    path = lab_storage.run_midi_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No MIDI output for this run.")
    return FileResponse(path=str(path), media_type="audio/midi", filename=f"engine-lab-{run_id}.mid")


@router.get("/runs/{run_id}/download/json")
def download_run_json(run_id: str) -> FileResponse:
    if lab_storage.load_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    path = lab_storage.run_json_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No JSON output for this run.")
    return FileResponse(path=str(path), media_type="application/json", filename=f"engine-lab-{run_id}.json")
