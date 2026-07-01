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


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class Note(BaseModel):
    pitch: int
    pitch_name: str
    start_time: float
    duration: float
    confidence: float


class TranscriptionResult(BaseModel):
    project_id: str
    project_name: str
    source_audio: str
    generated_at: str
    note_count: int
    notes: list[Note]
