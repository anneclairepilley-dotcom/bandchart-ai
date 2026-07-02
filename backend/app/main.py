"""BandChart AI backend - FastAPI app exposing the /api project + transcription routes."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import storage
from app.models import Project, ProjectCreate
from app.musicxml import INSTRUMENTS, notes_to_musicxml
from app.pdf import musicxml_to_pdf
from app.transcription import run_transcription

app = FastAPI(title="BandChart AI Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB

AUDIO_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}


def _get_project_or_404(project_id: str) -> Project:
    project = storage.load_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _friendly_transcription_error(exc: Exception) -> str:
    """Translate common failure modes into messages a non-technical user can act on."""
    raw = str(exc) or exc.__class__.__name__
    name = exc.__class__.__name__
    if name == "NoBackendError" or "audioread" in raw or "LibsndfileError" in name:
        return (
            "Couldn't read this audio file. It may be damaged, or — if it's an .mp3 or "
            ".m4a — the server may be missing ffmpeg (see the README's troubleshooting "
            "section). .wav, .flac and .ogg files work without ffmpeg. Try uploading "
            "the file again, or a different format."
        )
    if isinstance(exc, MemoryError):
        return "The computer ran out of memory while transcribing. Try a shorter recording."
    return (
        f"Transcription failed unexpectedly ({raw}). "
        "Try running it again, or upload the file afresh."
    )


@app.post("/api/projects", response_model=Project, status_code=201)
def create_project(body: ProjectCreate) -> Project:
    project_id = storage.new_project_id()
    ts = storage.now_iso()
    project = Project(
        id=project_id,
        name=body.name,
        status="created",
        created_at=ts,
        updated_at=ts,
        audio_filename=None,
        note_count=None,
        error=None,
    )
    storage.create_project_dirs(project_id)
    storage.save_project(project)
    return project


@app.get("/api/projects", response_model=list[Project])
def get_projects() -> list[Project]:
    return storage.list_projects()


@app.get("/api/projects/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    return _get_project_or_404(project_id)


@app.post("/api/projects/{project_id}/audio", response_model=Project)
async def upload_audio(project_id: str, file: UploadFile = File(...)) -> Project:
    project = _get_project_or_404(project_id)

    original_name = file.filename or ""
    # Use only the basename to avoid any path traversal from a crafted filename.
    safe_name = Path(original_name).name
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        received = f"a '{ext}' file" if ext else "a file with no extension"
        raise HTTPException(
            status_code=400,
            detail=f"That file type isn't supported (you uploaded {received}). "
            "Please choose an audio file ending in: "
            + ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS))
            + ".",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        size_mb = len(contents) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"This file is {size_mb:.0f}MB, which is over the 50MB limit. "
            "Try a shorter recording, or export it as .mp3 to make it smaller.",
        )
    if len(contents) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty (0 bytes). Please pick the audio file again.",
        )

    a_dir = storage.audio_dir(project_id)
    a_dir.mkdir(parents=True, exist_ok=True)

    # Remove any previously uploaded audio for this project before saving the new one.
    for existing in a_dir.iterdir():
        if existing.is_file():
            existing.unlink()

    saved_filename = safe_name
    saved_path = a_dir / saved_filename
    saved_path.write_bytes(contents)

    # Clear outputs from any earlier transcription (notes JSON, MIDI, any
    # generated MusicXML) so stale results are never served for the new audio.
    out_dir = storage.output_dir(project_id)
    if out_dir.exists():
        for stale in out_dir.iterdir():
            if stale.is_file():
                stale.unlink()

    project.audio_filename = saved_filename
    project.status = "uploaded"
    project.note_count = None
    project.updated_at = storage.now_iso()
    project.error = None
    storage.save_project(project)
    return project


@app.post("/api/projects/{project_id}/transcribe", response_model=Project)
def transcribe(project_id: str) -> Project:
    project = _get_project_or_404(project_id)

    if not project.audio_filename:
        raise HTTPException(status_code=400, detail="No audio uploaded for this project yet")

    audio_path = storage.audio_dir(project_id) / project.audio_filename
    if not audio_path.exists():
        raise HTTPException(status_code=400, detail="Uploaded audio file is missing on disk")

    project.status = "transcribing"
    project.updated_at = storage.now_iso()
    project.error = None
    storage.save_project(project)

    try:
        result = run_transcription(
            audio_path=audio_path,
            midi_out_path=storage.midi_path(project_id),
            json_out_path=storage.transcription_json_path(project_id),
            project_id=project.id,
            project_name=project.name,
            source_audio_filename=project.audio_filename,
        )
    except Exception as exc:  # noqa: BLE001
        message = _friendly_transcription_error(exc)
        project.status = "failed"
        project.error = message
        project.updated_at = storage.now_iso()
        storage.save_project(project)
        raise HTTPException(status_code=500, detail=message) from exc

    project.status = "transcribed"
    project.note_count = result["note_count"]
    project.error = None
    project.updated_at = storage.now_iso()
    storage.save_project(project)
    return project


@app.get("/api/projects/{project_id}/notes")
def get_notes(project_id: str) -> JSONResponse:
    _get_project_or_404(project_id)
    json_path = storage.transcription_json_path(project_id)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")
    data = json.loads(json_path.read_text())
    return JSONResponse(content=data)


@app.get("/api/projects/{project_id}/audio")
def get_audio(project_id: str) -> FileResponse:
    project = _get_project_or_404(project_id)
    if not project.audio_filename:
        raise HTTPException(status_code=404, detail="No audio uploaded for this project")
    audio_path = storage.audio_dir(project_id) / project.audio_filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
    ext = audio_path.suffix.lower()
    content_type = AUDIO_CONTENT_TYPES.get(ext) or mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"
    return FileResponse(path=str(audio_path), media_type=content_type, filename=audio_path.name)


@app.get("/api/projects/{project_id}/download/midi")
def download_midi(project_id: str) -> FileResponse:
    _get_project_or_404(project_id)
    midi_p = storage.midi_path(project_id)
    if not midi_p.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")
    return FileResponse(path=str(midi_p), media_type="audio/midi", filename="transcription.mid")


@app.get("/api/projects/{project_id}/download/json")
def download_json(project_id: str) -> FileResponse:
    _get_project_or_404(project_id)
    json_p = storage.transcription_json_path(project_id)
    if not json_p.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")
    return FileResponse(path=str(json_p), media_type="application/json", filename="transcription.json")


def _generate_musicxml_or_error(project_id: str, instrument: str) -> Path:
    """Validate instrument + transcription state and (re)generate the MusicXML file."""
    project = _get_project_or_404(project_id)
    if instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown instrument '{instrument}'. Valid choices: "
            + ", ".join(sorted(INSTRUMENTS)),
        )
    json_p = storage.transcription_json_path(project_id)
    if not json_p.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")

    data = json.loads(json_p.read_text())
    out_p = storage.musicxml_path(project_id, instrument)
    try:
        notes_to_musicxml(
            notes=data["notes"],
            instrument_key=instrument,
            project_name=project.name,
            out_path=out_p,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't create the MusicXML file ({exc}). Try re-running the transcription.",
        ) from exc
    return out_p


@app.get("/api/projects/{project_id}/download/musicxml")
def download_musicxml(project_id: str, instrument: str = "concert") -> FileResponse:
    out_p = _generate_musicxml_or_error(project_id, instrument)
    return FileResponse(
        path=str(out_p),
        media_type="application/vnd.recordare.musicxml+xml",
        filename=out_p.name,
    )


@app.get("/api/projects/{project_id}/download/pdf")
def download_pdf(project_id: str, instrument: str = "concert") -> FileResponse:
    musicxml_p = _generate_musicxml_or_error(project_id, instrument)
    pdf_p = storage.pdf_path(project_id, instrument)
    try:
        musicxml_to_pdf(musicxml_p, pdf_p)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't create the PDF ({exc}). The MusicXML download should still "
            "work — you can open that in MuseScore instead, or try the PDF again.",
        ) from exc
    return FileResponse(
        path=str(pdf_p),
        media_type="application/pdf",
        filename=pdf_p.name,
    )
