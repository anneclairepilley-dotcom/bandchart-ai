"""Runs real pitch transcription with librosa's pYIN algorithm and converts
the result into our notes schema (MIDI file + notes JSON).

pYIN is a monophonic pitch tracker (it follows one melodic line at a time,
not full chords/polyphony). It's used here instead of a deep-learning model
because it's pure Python/numpy/C — no TensorFlow — so it installs reliably
everywhere (including GitHub Codespaces and other newer-Python environments)
while still being a real, well-established transcription algorithm.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pretty_midi

from app.storage import now_iso

SAMPLE_RATE = 22050
FRAME_LENGTH = 2048
HOP_LENGTH = 512
FMIN = librosa.note_to_hz("C2")  # ~65 Hz
FMAX = librosa.note_to_hz("C7")  # ~2093 Hz
MIN_NOTE_DURATION = 0.09  # seconds; drops single-frame blips


def _detect_notes(audio_path: Path) -> list[dict[str, Any]]:
    """Track pitch frame-by-frame with pYIN, then group same-pitch frames into notes."""
    y, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)

    f0, voiced_flag, voiced_prob = librosa.pyin(
        y,
        fmin=FMIN,
        fmax=FMAX,
        sr=sr,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=HOP_LENGTH)
    hop_duration = HOP_LENGTH / sr

    raw_notes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for t, freq, voiced, prob in zip(times, f0, voiced_flag, voiced_prob):
        is_voiced = bool(voiced) and not np.isnan(freq)
        pitch = int(round(librosa.hz_to_midi(freq))) if is_voiced else None

        if is_voiced and current is not None and pitch == current["pitch"]:
            current["end"] = float(t) + hop_duration
            current["confidences"].append(float(prob))
            continue

        if current is not None:
            raw_notes.append(current)
            current = None

        if is_voiced:
            current = {
                "pitch": pitch,
                "start": float(t),
                "end": float(t) + hop_duration,
                "confidences": [float(prob)],
            }

    if current is not None:
        raw_notes.append(current)

    notes = []
    for note in raw_notes:
        duration = note["end"] - note["start"]
        if duration < MIN_NOTE_DURATION:
            continue
        notes.append(
            {
                "pitch": note["pitch"],
                "pitch_name": pretty_midi.note_number_to_name(note["pitch"]),
                "start_time": round(note["start"], 4),
                "duration": round(duration, 4),
                "confidence": round(float(np.mean(note["confidences"])), 4),
            }
        )

    notes.sort(key=lambda n: n["start_time"])
    return notes


def write_midi_from_notes(notes: list[dict[str, Any]], midi_out_path: Path) -> None:
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0, name="Transcribed Melody")
    for note in notes:
        velocity = max(1, min(127, round(note["confidence"] * 127)))
        instrument.notes.append(
            pretty_midi.Note(
                velocity=velocity,
                pitch=note["pitch"],
                start=note["start_time"],
                end=note["start_time"] + note["duration"],
            )
        )
    midi.instruments.append(instrument)
    midi_out_path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(midi_out_path))


def run_transcription(
    audio_path: Path,
    midi_out_path: Path,
    json_out_path: Path,
    project_id: str,
    project_name: str,
    source_audio_filename: str,
    detection: str = "melody",
) -> dict[str, Any]:
    """Run pitch transcription on audio_path, write MIDI + notes JSON.

    detection="melody" (default) is the trusty pYIN single-line tracker.
    detection="poly" tries the experimental multi-pitch detector
    (app/polyphonic.py); on failure or an empty result it falls back to
    melody-only and records why in "detection_note".

    Returns the transcription result dict (same shape written to json_out_path).
    """
    detection_used = "melody"
    detection_note: str | None = None
    notes: list[dict[str, Any]] | None = None

    if detection == "poly":
        try:
            from app.polyphonic import detect_notes_poly

            notes, poly_messages = detect_notes_poly(audio_path)
            if notes:
                detection_used = "poly"
                if poly_messages:
                    detection_note = " ".join(poly_messages)
            else:
                notes = None
                detection_note = (
                    "Multiple-note detection found nothing usable in this "
                    "recording, so melody-only transcription was used instead."
                )
        except Exception as exc:  # noqa: BLE001
            notes = None
            detection_note = (
                f"Multiple-note detection failed ({exc}) — melody-only "
                "transcription was used instead."
            )

    if notes is None:
        notes = _detect_notes(audio_path)

    write_midi_from_notes(notes, midi_out_path)

    result = {
        "project_id": project_id,
        "project_name": project_name,
        "source_audio": source_audio_filename,
        "generated_at": now_iso(),
        "note_count": len(notes),
        "notes": notes,
        # Manual chord markers (v0.9) — a fresh transcription starts empty.
        "chords": [],
        # v0.9.2: which detector produced these notes, plus any honest
        # caveat (fallbacks, simplifications) to show the user.
        "detection": detection_used,
        "detection_note": detection_note,
    }

    json_out_path.parent.mkdir(parents=True, exist_ok=True)
    json_out_path.write_text(json.dumps(result, indent=2))

    return result
