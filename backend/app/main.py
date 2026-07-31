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
from app.arrangement import run_solo_arrangement
from app.chords import (
    CHORD_NAME_HELP,
    KEY_CHOICES,
    chord_chart_text,
    is_valid_chord_name,
    suggest_chords,
)
from app.engine_lab.routes import router as engine_lab_router
from app.models import (
    ChordsUpdate,
    NotesUpdate,
    Project,
    ProjectCreate,
    ProjectSettings,
    YoutubeImport,
)
from app.musicxml import INSTRUMENTS, notes_to_musicxml
from app.pdf import musicxml_to_pdf
from app.tablature import TUNINGS, build_tab
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

# v0.9.4: Engine Lab — a side area for comparing transcription engines,
# isolated from the main /api/projects/* pipeline (see app/engine_lab/).
app.include_router(engine_lab_router)

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


VALID_MODES = {"direct_transcription", "solo_arrangement"}
VALID_TIME_SIGNATURES = {"predict", "4/4", "3/4", "6/8"}
VALID_RHYTHM_DETAILS = {"readable", "precise"}
VALID_NOTE_DETECTIONS = {"melody", "poly"}
VALID_ARRANGEMENT_FOCUSES = {"main_melody", "melody_support"}
VALID_ARRANGEMENT_DENSITIES = {"simple", "balanced", "detailed"}
# Quarter notes per bar at the fixed 120 BPM (0.5s per quarter).
_BAR_SECONDS = {"4/4": 2.0, "3/4": 1.5, "6/8": 1.5}


def _get_project_or_404(project_id: str) -> Project:
    project = storage.load_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _project_time_signature(project: Project) -> str:
    ts = project.time_signature
    return ts if ts in ("4/4", "3/4", "6/8") else "4/4"


def _project_seconds_per_bar(project: Project) -> float:
    return _BAR_SECONDS[_project_time_signature(project)]


@app.post("/api/projects/{project_id}/settings", response_model=Project)
def set_project_settings(project_id: str, body: ProjectSettings) -> Project:
    """Store the pre-transcription choices: instrument, mode, advanced settings."""
    project = _get_project_or_404(project_id)
    if body.instrument not in INSTRUMENTS:
        raise HTTPException(
            status_code=400,
            detail="Please choose an instrument first — "
            f"'{body.instrument}' isn't one of the supported instruments.",
        )
    if body.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail="Please choose a transcription mode first — either "
            "direct transcription or solo arrangement.",
        )
    if body.time_signature not in VALID_TIME_SIGNATURES:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.time_signature}' isn't a supported time signature. "
            "Choose Let us predict, 4/4, 3/4 or 6/8.",
        )
    if body.key_signature != "predict" and body.key_signature not in KEY_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.key_signature}' isn't a supported key. Choose Let us "
            "predict or one of: " + ", ".join(KEY_CHOICES) + ".",
        )
    if body.rhythm_detail not in VALID_RHYTHM_DETAILS:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.rhythm_detail}' isn't a rhythm detail option. "
            "Choose Readable or Precise.",
        )
    if body.note_detection not in VALID_NOTE_DETECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.note_detection}' isn't a note detection option. "
            "Choose Melody only, or Allow simple chords / multiple notes.",
        )
    if body.arrangement_focus not in VALID_ARRANGEMENT_FOCUSES:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.arrangement_focus}' isn't an arrangement focus option. "
            "Choose Main melody, or Melody + simple support.",
        )
    if body.arrangement_density not in VALID_ARRANGEMENT_DENSITIES:
        raise HTTPException(
            status_code=400,
            detail=f"'{body.arrangement_density}' isn't an arrangement density "
            "option. Choose Simple, Balanced or Detailed.",
        )
    project.instrument = body.instrument
    project.mode = body.mode
    project.time_signature = body.time_signature
    project.key_signature = body.key_signature
    project.rhythm_detail = body.rhythm_detail
    project.note_detection = body.note_detection
    project.arrangement_focus = body.arrangement_focus
    project.arrangement_density = body.arrangement_density
    project.updated_at = storage.now_iso()
    storage.save_project(project)
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
        saved_filename, info = download_audio_as_wav(url, tmp_dir)
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
    # Projects auto-created by the home screen get the video's real title.
    if project.name == "YouTube import" and (info or {}).get("title"):
        project.name = str(info["title"])[:200]
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
        if (project.mode or "direct_transcription") == "solo_arrangement":
            result = run_solo_arrangement(
                audio_path=audio_path,
                midi_out_path=storage.midi_path(project_id),
                json_out_path=storage.transcription_json_path(project_id),
                project_id=project.id,
                project_name=project.name,
                source_audio_filename=project.audio_filename,
                instrument=project.instrument or "concert",
                note_detection=project.note_detection or "melody",
                arrangement_focus=project.arrangement_focus or "main_melody",
                arrangement_density=project.arrangement_density or "simple",
            )
        else:
            result = run_transcription(
                audio_path=audio_path,
                midi_out_path=storage.midi_path(project_id),
                json_out_path=storage.transcription_json_path(project_id),
                project_id=project.id,
                project_name=project.name,
                source_audio_filename=project.audio_filename,
                detection=project.note_detection or "melody",
                instrument=project.instrument or "concert",
                mode=project.mode or "direct_transcription",
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


def _load_transcription_or_404(project_id: str) -> dict:
    json_path = storage.transcription_json_path(project_id)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")
    return json.loads(json_path.read_text())


def _save_working_notes(project: Project, notes: list[dict]) -> dict:
    """Write the working note list as the current transcription.

    transcription.json is the single source every export reads (JSON download
    directly; MusicXML/PDF generate from it on demand), so rewriting it plus
    the static MIDI file makes every download reflect the edit. Chord markers
    stored alongside the notes are preserved — editing the melody never
    touches the chords.
    """
    existing_chords: list[dict] = []
    existing_detection = "melody"
    existing_detection_note = None
    # v0.9.5 smart routing status — a note edit or reset changes WHICH
    # notes are stored, never which engine produced the original detection,
    # so these are preserved exactly like chords/detection/detection_note.
    existing_routing_fields = {
        "engine_used": "pyin",
        "routing_mode": "melody_only",
        "fallback_reason": None,
        "warnings": [],
        "difficulty": None,
        # v1.0 Solo Arrangement status — a note edit or reset never changes
        # which source/engine produced the original arrangement.
        "arrangement_source": None,
        "separation_engine": None,
        "arrangement_focus": None,
        "arrangement_density": None,
        # v0.9.8 range-fitting status ("none" | "octave_shifted" | "simplified").
        "range_fitting": None,
    }
    json_path = storage.transcription_json_path(project.id)
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text())
            existing_chords = existing.get("chords", [])
            existing_detection = existing.get("detection", "melody")
            existing_detection_note = existing.get("detection_note")
            for key in existing_routing_fields:
                if key in existing:
                    existing_routing_fields[key] = existing[key]
        except Exception:
            existing_chords = []

    notes = sorted(notes, key=lambda n: (n["start_time"], n["pitch"]))
    data = {
        "project_id": project.id,
        "project_name": project.name,
        "source_audio": project.audio_filename,
        "generated_at": storage.now_iso(),
        "note_count": len(notes),
        "notes": notes,
        "chords": existing_chords,
        "detection": existing_detection,
        "detection_note": existing_detection_note,
        **existing_routing_fields,
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
    # exclude_none keeps stored notes tidy: older/melody notes simply have
    # no velocity/group keys instead of nulls.
    data = _save_working_notes(
        project, [n.model_dump(exclude_none=True) for n in body.notes]
    )
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


def _save_chords(project_id: str, chords: list[dict]) -> dict:
    """Store the chord marker list inside transcription.json (kept sorted)."""
    data = _load_transcription_or_404(project_id)
    data["chords"] = sorted(chords, key=lambda c: c["start_time"])
    storage.transcription_json_path(project_id).write_text(json.dumps(data, indent=2))
    return data


@app.get("/api/projects/{project_id}/chords")
def get_chords(project_id: str) -> JSONResponse:
    _get_project_or_404(project_id)
    data = _load_transcription_or_404(project_id)
    return JSONResponse(content={"chords": data.get("chords", [])})


@app.put("/api/projects/{project_id}/chords")
def update_chords(project_id: str, body: ChordsUpdate) -> JSONResponse:
    _get_project_or_404(project_id)
    for marker in body.chords:
        if not is_valid_chord_name(marker.name.strip()):
            raise HTTPException(
                status_code=400,
                detail=f"'{marker.name}' isn't a valid chord name. {CHORD_NAME_HELP}",
            )
    chords = [
        {"name": c.name.strip(), "start_time": c.start_time} for c in body.chords
    ]
    data = _save_chords(project_id, chords)
    return JSONResponse(content={"chords": data["chords"]})


@app.post("/api/projects/{project_id}/chords/suggest")
def suggest_project_chords(project_id: str) -> JSONResponse:
    """Rough diatonic chord suggestions from the current melody (replaces the list)."""
    project = _get_project_or_404(project_id)
    data = _load_transcription_or_404(project_id)
    if not data.get("notes"):
        raise HTTPException(
            status_code=400,
            detail="There are no melody notes to suggest chords from — transcribe "
            "some audio (or add notes) first.",
        )
    chosen_key = (
        project.key_signature
        if project.key_signature and project.key_signature != "predict"
        else None
    )
    try:
        suggestions, uncertain = suggest_chords(
            data["notes"],
            key_name=chosen_key,
            seconds_per_bar=_project_seconds_per_bar(project),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't suggest chords ({exc}). You can still add chords by hand.",
        ) from exc
    data = _save_chords(project_id, suggestions)
    message = (
        "Chord suggestions are a rough starting point. Please check and edit them."
    )
    if chosen_key:
        message += f" (Using your chosen key: {chosen_key}.)"
    elif uncertain:
        message += (
            " The key was hard to detect from this melody, so C major was "
            "assumed — treat these as extra rough."
        )
    return JSONResponse(content={"chords": data["chords"], "message": message})


@app.get("/api/projects/{project_id}/download/chords")
def download_chord_chart(project_id: str) -> FileResponse:
    project = _get_project_or_404(project_id)
    data = _load_transcription_or_404(project_id)
    chords = data.get("chords", [])
    if not chords:
        raise HTTPException(
            status_code=400,
            detail="There are no chords yet — add some in the Chords section "
            "(or use Suggest chords) first.",
        )
    notes = data.get("notes", [])
    melody_end = max((n["start_time"] + n["duration"] for n in notes), default=0.0)
    try:
        text = chord_chart_text(
            project.name,
            chords,
            melody_end,
            time_signature=_project_time_signature(project),
            seconds_per_bar=_project_seconds_per_bar(project),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't build the chord chart ({exc}). Try again.",
        ) from exc
    out_p = storage.chord_chart_path(project_id)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(text)
    return FileResponse(path=str(out_p), media_type="text/plain", filename=out_p.name)


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


def _build_tab_or_error(project_id: str, instrument: str) -> dict:
    """Validate a tab request and build the tab from the current notes."""
    project = _get_project_or_404(project_id)
    if instrument not in TUNINGS:
        raise HTTPException(
            status_code=400,
            detail="Tab is only available for these instruments: "
            + ", ".join(sorted(TUNINGS))
            + f". '{instrument}' uses regular sheet music instead.",
        )
    json_p = storage.transcription_json_path(project_id)
    if not json_p.exists():
        raise HTTPException(status_code=404, detail="Project has not been transcribed yet")
    data = json.loads(json_p.read_text())
    try:
        return build_tab(
            data["notes"],
            instrument,
            project.name,
            seconds_per_bar=_project_seconds_per_bar(project),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Couldn't build the tab ({exc}). Try re-running the transcription.",
        ) from exc


@app.get("/api/projects/{project_id}/tab")
def get_tab(project_id: str, instrument: str = "guitar") -> JSONResponse:
    """Structured tab (entries, warnings, preview cells) for the web preview."""
    return JSONResponse(content=_build_tab_or_error(project_id, instrument))


@app.get("/api/projects/{project_id}/download/tab")
def download_tab(project_id: str, instrument: str = "guitar") -> FileResponse:
    tab = _build_tab_or_error(project_id, instrument)
    if tab["note_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail="There are no notes to export — the note list is empty. "
            "Reset to the original transcription or transcribe again first.",
        )
    out_p = storage.tab_path(project_id, instrument)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(tab["text"])
    return FileResponse(path=str(out_p), media_type="text/plain", filename=out_p.name)


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
            chords=data.get("chords", []),
            rhythm_detail=project.rhythm_detail or "readable",
            time_signature=_project_time_signature(project),
            key_signature=(
                project.key_signature
                if project.key_signature and project.key_signature != "predict"
                else None
            ),
            arrangement_label=(
                "solo arrangement" if project.mode == "solo_arrangement" else None
            ),
            detection=data.get("detection", "melody"),
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
