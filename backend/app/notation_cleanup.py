"""Cleans raw pYIN note events into something readable as sheet music.

The raw transcription is intentionally literal: every wobble of a voice or
instrument becomes its own short note, which engraves as a mess of ties,
sixteenths and accidentals. This module runs between transcription and
MusicXML/PDF export (never touching the stored transcription.json) and
applies, in order:

1. pitch smoothing  — a very short note whose neighbours agree on a
                      different pitch is treated as tracking wobble and
                      absorbed into that pitch
2. same-pitch merge — consecutive notes of the same pitch separated by a
                      tiny gap become one note
3. fragment removal — anything still shorter than a minimum duration is
                      dropped as noise
4. quantization     — starts and lengths snap to an eighth-note grid
                      (at the fixed 120 BPM used by the exporter)

All functions take and return the plain note dicts stored in
transcription.json: {pitch, pitch_name, start_time, duration, confidence}.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pretty_midi

Note = dict[str, Any]


@dataclass(frozen=True)
class CleanupSettings:
    tempo_bpm: float = 120.0
    grid_quarters: float = 0.5  # eighth-note grid
    min_duration_s: float = 0.2  # drop fragments shorter than this
    merge_gap_s: float = 0.2  # same-pitch notes closer than this merge
    wobble_max_s: float = 0.22  # notes at most this long can be wobble
    wobble_max_semitones: int = 3  # only nearby pitches count as wobble

    @property
    def seconds_per_quarter(self) -> float:
        return 60.0 / self.tempo_bpm

    @property
    def grid_seconds(self) -> float:
        return self.grid_quarters * self.seconds_per_quarter


def _make_note(pitch: int, start: float, duration: float, confidence: float) -> Note:
    return {
        "pitch": int(pitch),
        "pitch_name": pretty_midi.note_number_to_name(int(pitch)),
        "start_time": round(float(start), 4),
        "duration": round(float(duration), 4),
        "confidence": round(float(confidence), 4),
    }


def smooth_pitch_wobble(notes: list[Note], settings: CleanupSettings) -> list[Note]:
    """Relabel brief jump-and-return notes to their neighbours' pitch.

    If a very short note sits between two notes that agree on a nearby
    pitch (prev == next, small interval away), the tracker most likely
    wobbled rather than the player changing note.
    """
    if len(notes) < 3:
        return [dict(n) for n in notes]
    result = [dict(n) for n in notes]
    for i in range(1, len(result) - 1):
        cur, prev, nxt = result[i], result[i - 1], result[i + 1]
        if (
            cur["duration"] <= settings.wobble_max_s
            and prev["pitch"] == nxt["pitch"]
            and cur["pitch"] != prev["pitch"]
            and abs(cur["pitch"] - prev["pitch"]) <= settings.wobble_max_semitones
        ):
            cur["pitch"] = prev["pitch"]
            cur["pitch_name"] = prev["pitch_name"]
    return result


def merge_same_pitch(notes: list[Note], settings: CleanupSettings) -> list[Note]:
    """Fuse consecutive same-pitch notes separated by no more than merge_gap_s."""
    merged: list[Note] = []
    for note in notes:
        if merged:
            last = merged[-1]
            gap = note["start_time"] - (last["start_time"] + last["duration"])
            if note["pitch"] == last["pitch"] and gap <= settings.merge_gap_s:
                new_end = max(
                    last["start_time"] + last["duration"],
                    note["start_time"] + note["duration"],
                )
                total = last["duration"] + note["duration"]
                confidence = (
                    last["confidence"] * last["duration"]
                    + note["confidence"] * note["duration"]
                ) / max(total, 1e-9)
                merged[-1] = _make_note(
                    last["pitch"], last["start_time"], new_end - last["start_time"], confidence
                )
                continue
        merged.append(dict(note))
    return merged


def drop_fragments(notes: list[Note], settings: CleanupSettings) -> list[Note]:
    """Remove notes still shorter than min_duration_s after merging."""
    return [dict(n) for n in notes if n["duration"] >= settings.min_duration_s]


def quantize(notes: list[Note], settings: CleanupSettings) -> list[Note]:
    """Snap starts and durations to the grid; re-merge/clip collisions."""
    grid = settings.grid_seconds
    quantized: list[Note] = []
    for note in notes:
        start = round(note["start_time"] / grid) * grid
        duration = max(grid, round(note["duration"] / grid) * grid)
        quantized.append(_make_note(note["pitch"], start, duration, note["confidence"]))

    # Snapping can create overlaps or make same-pitch notes touch: merge
    # touching same-pitch notes, clip anything else that overlaps.
    cleaned: list[Note] = []
    for note in quantized:
        if cleaned:
            last = cleaned[-1]
            last_end = last["start_time"] + last["duration"]
            if note["pitch"] == last["pitch"] and note["start_time"] <= last_end:
                new_end = max(last_end, note["start_time"] + note["duration"])
                cleaned[-1] = _make_note(
                    last["pitch"],
                    last["start_time"],
                    new_end - last["start_time"],
                    max(last["confidence"], note["confidence"]),
                )
                continue
            if note["start_time"] < last_end:
                clipped = note["start_time"] - last["start_time"]
                if clipped < grid:
                    # Same grid slot as the previous note; keep the earlier one.
                    continue
                cleaned[-1] = _make_note(
                    last["pitch"], last["start_time"], clipped, last["confidence"]
                )
        cleaned.append(note)
    return cleaned


def clean_notes(
    notes: list[Note], settings: CleanupSettings | None = None
) -> list[Note]:
    """Full cleanup pipeline: wobble -> merge (twice over) -> drop fragments -> quantize.

    Smoothing runs a second time after the first merge: merging can turn a
    cluster of fragments into a clear neighbour pair, exposing wobbles the
    first pass couldn't see.
    """
    settings = settings or CleanupSettings()
    result = smooth_pitch_wobble(notes, settings)
    result = merge_same_pitch(result, settings)
    result = smooth_pitch_wobble(result, settings)
    result = merge_same_pitch(result, settings)
    result = drop_fragments(result, settings)
    result = merge_same_pitch(result, settings)  # dropping fragments can expose new gaps
    result = quantize(result, settings)
    return result
