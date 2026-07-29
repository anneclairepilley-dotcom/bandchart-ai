"""Pydantic schemas for BandChart AI backend."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ProjectStatus = Literal["created", "uploaded", "transcribing", "transcribed", "failed"]


class Project(BaseModel):
    id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str
    audio_filename: Optional[str] = None
    note_count: Optional[int] = None
    error: Optional[str] = None
    # Where the audio came from: "upload" or "youtube" (None on old projects).
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    rights_confirmed: Optional[bool] = None
    imported_at: Optional[str] = None
    # v0.9.1 setup choices (all None on older projects; sensible defaults
    # are applied wherever they're read).
    instrument: Optional[str] = None
    mode: Optional[str] = None  # "direct_transcription" | "solo_arrangement"
    time_signature: Optional[str] = None  # "predict" | "4/4" | "3/4" | "6/8"
    key_signature: Optional[str] = None  # "predict" | "C" | "G" | ... | "Dm"
    rhythm_detail: Optional[str] = None  # "readable" | "precise"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class Note(BaseModel):
    pitch: int = Field(..., ge=0, le=127)
    pitch_name: str
    start_time: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0, le=1)


class NotesUpdate(BaseModel):
    """Body of PUT /projects/{id}/notes — the edited working note list."""

    notes: list[Note]


class ChordMarker(BaseModel):
    """One manual chord symbol placed on the timeline (e.g. Am at 2.0s)."""

    name: str = Field(..., min_length=1, max_length=12)
    start_time: float = Field(..., ge=0)


class ChordsUpdate(BaseModel):
    """Body of PUT /projects/{id}/chords — the full chord marker list."""

    chords: list[ChordMarker]


class YoutubeImport(BaseModel):
    """Body of POST /projects/{id}/youtube."""

    url: str
    rights_confirmed: bool = False


class ProjectSettings(BaseModel):
    """Body of POST /projects/{id}/settings — the pre-transcription choices."""

    instrument: str
    mode: str
    time_signature: str = "predict"
    key_signature: str = "predict"
    rhythm_detail: str = "readable"


class TranscriptionResult(BaseModel):
    project_id: str
    project_name: str
    source_audio: str
    generated_at: str
    note_count: int
    notes: list[Note]
