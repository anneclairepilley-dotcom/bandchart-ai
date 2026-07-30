"""Shared types for Engine Lab adapters.

Every adapter wraps one transcription engine behind the same tiny interface
so the lab can run, time and compare them uniformly. Adapters never touch
project storage or the main transcription pipeline — they take an audio
path and return plain note dicts in BandChart's existing note schema
(pitch, pitch_name, start_time, duration, confidence, optional velocity/
group/source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class EngineRunOutput:
    notes: list[dict[str, Any]]
    messages: list[str] = field(default_factory=list)


@dataclass
class EngineAdapter:
    """One transcription engine, wired into the lab.

    availability_check() is called fresh on every /engines listing (cheap:
    it should only import-check, never load models or run inference) so the
    lab always reports current install state, e.g. right after the owner
    runs setup.command again.
    """

    key: str
    label: str
    description: str
    availability_check: Callable[[], tuple[bool, Optional[str]]]
    run_fn: Callable[[Path], EngineRunOutput]

    def is_available(self) -> tuple[bool, Optional[str]]:
        try:
            return self.availability_check()
        except Exception as exc:  # noqa: BLE001
            return False, f"Availability check failed: {exc}"

    def run(self, audio_path: Path) -> EngineRunOutput:
        return self.run_fn(audio_path)
