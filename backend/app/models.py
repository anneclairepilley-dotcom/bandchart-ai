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


class YoutubeImport(BaseModel):
    """Body of POST /projects/{id}/youtube."""

    url: str
    rights_confirmed: bool = False


class TranscriptionResult(BaseModel):
    project_id: str
    project_name: str
    source_audio: str
    generated_at: str
    note_count: int
    notes: list[Note]
