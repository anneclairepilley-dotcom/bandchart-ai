"""BandChart AI backend - FastAPI app exposing the /api project + transcription routes."""

from __future__ import annotations

import json
import mimetypes
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import storage
from app.models import NotesUpdate, Project, ProjectCreate, YoutubeImport
from app.musicxml import INSTRUMENTS, notes_to_musicxml
from app.pdf import musicxml_to_pdf
from app.transcription import run_transcription, write_midi_from_notes
from app.youtube import YoutubeImportError, download_audio_as_wav, is_valid_youtube_url

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


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> JSONResponse:
    _get_project_or_404(project_id)
    try:
        storage.delete_project(project_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't delete the project ({exc}). Try again.",
        ) from exc
    return JSONResponse(content={"deleted": project_id})


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

    _clear_audio_and_outputs(project_id)

    saved_filename = safe_name
    saved_path = storage.audio_dir(project_id) / saved_filename
    saved_path.write_bytes(contents)

    project.audio_filename = saved_filename
    project.status = "uploaded"
    project.note_count = None
    project.updated_at = storage.now_iso()
    project.error = None
    project.source_type = "upload"
    project.source_url = None
    project.rights_confirmed = None
    project.imported_at = None
    storage.save_project(project)
    return project


def _clear_audio_and_outputs(project_id: str) -> None:
    """Remove previous audio and all stale generated outputs for a project."""
    a_dir = storage.audio_dir(project_id)
    a_dir.mkdir(parents=True, exist_ok=True)
    for existing in a_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    out_dir = storage.output_dir(project_id)
    if out_dir.exists():
        for stale in out_dir.iterdir():
            if stale.is_file():
                stale.unlink()


@app.post("/api/projects/{project_id}/youtube", response_model=Project)
def import_youtube(project_id: str, body: YoutubeImport) -> Project:
    project = _get_project_or_404(project_id)

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Paste a YouTube link first.")
    if not is_valid_youtube_url(url):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a YouTube link. Expected something like "
            "https://www.youtube.com/watch?v=… or https://youtu.be/…",
        )
    if not body.rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Please tick the box confirming you have permission to process "
            "this content before importing.",
        )

    # Download into a temp folder inside the project first: the project's
    # existing audio and outputs are only replaced once the new audio has
    # fully arrived, so a failed import never destroys previous work.
    tmp_dir = storage.project_dir(project_id) / "import-tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    try:
        saved_filename, _info = download_audio_as_wav(url, tmp_dir)
    except YoutubeImportError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"YouTube import failed unexpectedly ({exc}). Try again, or "
            "upload an audio file instead.",
        ) from exc

    # The download can take a while — if the project was deleted meanwhile,
    # don't resurrect it from the recreated temp folder.
    if not storage.project_exists(project_id):
        shutil.rmtree(storage.project_dir(project_id), ignore_errors=True)
        raise HTTPException(
            status_code=404,
            detail="This project was deleted while the import was running.",
        )

    _clear_audio_and_outputs(project_id)
    shutil.move(str(tmp_dir / saved_filename), str(storage.audio_dir(project_id) / saved_filename))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    project.audio_filename = saved_filename
    project.status = "uploaded"
    project.note_count = None
    project.updated_at = storage.now_iso()
    project.error = None
    project.source_type = "youtube"
    project.source_url = url
    project.rights_confirmed = True
    project.imported_at = storage.now_iso()
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

    # Keep an untouched copy so note edits can always be undone.
    shutil.copyfile(
        storage.transcription_json_path(project_id),
        storage.original_transcription_json_path(project_id),
    )

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


def _save_working_notes(project: Project, notes: list[dict]) -> dict:
    """Write the working note list as the current transcription.

    transcription.json is the single source every export reads (JSON download
    directly; MusicXML/PDF generate from it on demand), so rewriting it plus
    the static MIDI file makes every download reflect the edit.
    """
    notes = sorted(notes, key=lambda n: n["start_time"])
    data = {
        "project_id": project.id,
        "project_name": project.name,
        "source_audio": project.audio_filename,
        "generated_at": storage.now_iso(),
        "note_count": len(notes),
        "notes": notes,
    }
    storage.transcription_json_path(project.id).write_text(json.dumps(data, indent=2))
    write_midi_from_notes(notes, storage.midi_path(project.id))

    project.note_count = len(notes)
    project.updated_at = storage.now_iso()
    storage.save_project(project)
    return data


@app.put("/api/projects/{project_id}/notes")
def update_notes(project_id: str, body: NotesUpdate) -> JSONResponse:
    project = _get_project_or_404(project_id)
    if not storage.transcription_json_path(project_id).exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")
    data = _save_working_notes(project, [n.model_dump() for n in body.notes])
    return JSONResponse(content=data)


@app.post("/api/projects/{project_id}/notes/reset")
def reset_notes(project_id: str) -> JSONResponse:
    project = _get_project_or_404(project_id)
    original = storage.original_transcription_json_path(project_id)
    if not original.exists():
        raise HTTPException(
            status_code=404,
            detail="No original transcription to reset to — run the transcription again.",
        )
    data = json.loads(original.read_text())
    data = _save_working_notes(project, data["notes"])
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


def _generate_musicxml_or_error(project_id: str, instrument: str, style: str) -> Path:
    """Validate parameters + transcription state and (re)generate the MusicXML file."""
    project = _get_project_or_404(project_id)
    if instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown instrument '{instrument}'. Valid choices: "
            + ", ".join(sorted(INSTRUMENTS)),
        )
    if style not in ("clean", "raw"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown style '{style}'. Valid choices: clean, raw",
        )
    json_p = storage.transcription_json_path(project_id)
    if not json_p.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")

    data = json.loads(json_p.read_text())
    out_p = storage.musicxml_path(project_id, instrument, style)
    try:
        notes_to_musicxml(
            notes=data["notes"],
            instrument_key=instrument,
            project_name=project.name,
            out_path=out_p,
            style=style,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't create the MusicXML file ({exc}). Try re-running the transcription.",
        ) from exc
    return out_p


@app.get("/api/projects/{project_id}/download/musicxml")
def download_musicxml(
    project_id: str, instrument: str = "concert", style: str = "clean"
) -> FileResponse:
    out_p = _generate_musicxml_or_error(project_id, instrument, style)
    return FileResponse(
        path=str(out_p),
        media_type="application/vnd.recordare.musicxml+xml",
        filename=out_p.name,
    )


@app.get("/api/projects/{project_id}/download/pdf")
def download_pdf(
    project_id: str, instrument: str = "concert", style: str = "clean"
) -> FileResponse:
    musicxml_p = _generate_musicxml_or_error(project_id, instrument, style)
    pdf_p = storage.pdf_path(project_id, instrument, style)
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
