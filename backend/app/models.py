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
    note_detection: Optional[str] = None  # "melody" | "poly" (v0.9.2)
    # Solo Arrangement controls (ignored for Direct transcription).
    arrangement_focus: Optional[str] = None  # "main_melody" | "melody_support"
    # v0.9.8: renamed from arrangement_difficulty (easy/medium) to a 3-tier
    # density control.
    arrangement_density: Optional[str] = None  # "simple" | "balanced" | "detailed"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class Note(BaseModel):
    pitch: int = Field(..., ge=0, le=127)
    pitch_name: str
    start_time: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0, le=1)
    # v0.9.3 optional fields (absent on older notes): playback loudness from
    # the detector, and a chord-group id shared by simultaneous notes.
    velocity: Optional[float] = Field(None, ge=0, le=1)
    group: Optional[str] = Field(None, max_length=32)
    # True on a repeated note the melody detector split off at a re-strike —
    # tells the notation cleanup never to glue it back onto its predecessor.
    reattack: Optional[bool] = None
    # Which detector produced this note: "basic_pitch", "cqt" or "pyin"
    # (absent on notes from before v0.9.3 and on hand-added notes).
    source: Optional[str] = Field(None, max_length=16)


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
    note_detection: str = "melody"
    # Solo Arrangement controls (ignored for Direct transcription).
    arrangement_focus: str = "main_melody"
    arrangement_density: str = "simple"


class TranscriptionResult(BaseModel):
    project_id: str
    project_name: str
    source_audio: str
    generated_at: str
    note_count: int
    notes: list[Note]
