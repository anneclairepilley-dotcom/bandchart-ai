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
# v0.9.3: notes whose average pYIN voicing probability is below this are
# treated as noise (never applied if it would empty the transcription).
CONFIDENCE_FLOOR = 0.35
# A split point inside a sustained note must be a real re-attack: loudness
# right after the onset at least this much louder than just before it
# (vibrato and harmonic wobble don't dip-and-rise like a new strike does).
REATTACK_RISE = 1.35
# Minimum spacing between split points (and from the note's edges).
SPLIT_MIN_GAP = 0.15


def _reattack_onsets(
    y: np.ndarray, sr: int, onset_times: np.ndarray
) -> list[float]:
    """Keep only onsets where loudness clearly rises — genuine re-strikes."""
    rms = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    rms_times = librosa.times_like(rms, sr=sr, hop_length=HOP_LENGTH)
    kept: list[float] = []
    for t in onset_times:
        t = float(t)
        before = rms[(rms_times >= t - 0.10) & (rms_times <= t - 0.02)]
        after = rms[(rms_times >= t) & (rms_times <= t + 0.08)]
        if before.size == 0 or after.size == 0:
            kept.append(t)  # at the very edges, trust the onset detector
            continue
        if float(after.mean()) >= REATTACK_RISE * float(before.mean()):
            kept.append(t)
    return kept


def _split_note_at_onsets(
    note: dict[str, Any], onset_times: list[float], hop_duration: float
) -> list[dict[str, Any]]:
    """Split one sustained same-pitch note where new attacks occur inside it.

    pYIN merges repeated notes of the same pitch (two quick C4s become one
    long C4). Re-attack onsets inside the note's span mark the re-strikes.
    Split points are spaced so every piece keeps a sensible length.
    """
    start, end = note["start"], note["end"]
    inner: list[float] = []
    last = start
    for t in onset_times:
        if t <= start or t >= end:
            continue
        if t - last >= SPLIT_MIN_GAP and end - t >= SPLIT_MIN_GAP:
            inner.append(t)
            last = t
    if not inner:
        return [note]

    pieces: list[dict[str, Any]] = []
    confidences = note["confidences"]
    boundaries = [start, *inner, end]
    for piece_index, (seg_start, seg_end) in enumerate(zip(boundaries, boundaries[1:])):
        i0 = int((seg_start - start) / hop_duration)
        i1 = max(i0 + 1, int((seg_end - start) / hop_duration))
        pieces.append(
            {
                "pitch": note["pitch"],
                "start": seg_start,
                "end": seg_end,
                "confidences": confidences[i0:i1] or confidences[-1:],
                # Mark deliberate re-strikes so the notation cleanup never
                # glues them back into one long note.
                "reattack": piece_index > 0,
            }
        )
    return pieces


def _detect_notes(audio_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Track pitch frame-by-frame with pYIN, then group same-pitch frames into notes.

    Returns (notes, messages): messages carry honest caveats (e.g. that
    low-confidence notes were removed).
    """
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

    # v0.9.3: percussive onsets inside a sustained same-pitch note mark
    # repeated strikes that pYIN glued together — split them apart. Only
    # onsets with a genuine loudness rise count (not vibrato wobble).
    onset_times = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=HOP_LENGTH, backtrack=False, units="time"
    )
    reattacks = _reattack_onsets(y, sr, onset_times)
    split_notes: list[dict[str, Any]] = []
    for note in raw_notes:
        split_notes.extend(_split_note_at_onsets(note, reattacks, hop_duration))

    notes = []
    for note in split_notes:
        duration = note["end"] - note["start"]
        if duration < MIN_NOTE_DURATION:
            continue
        assembled = {
            "pitch": note["pitch"],
            "pitch_name": pretty_midi.note_number_to_name(note["pitch"]),
            "start_time": round(note["start"], 4),
            "duration": round(duration, 4),
            "confidence": round(float(np.mean(note["confidences"])), 4),
        }
        if note.get("reattack"):
            assembled["reattack"] = True
        notes.append(assembled)

    # v0.9.3: drop notes the tracker itself doubted — unless that would
    # wipe the whole transcription (quiet recordings score low overall).
    messages: list[str] = []
    confident = [n for n in notes if n["confidence"] >= CONFIDENCE_FLOOR]
    if confident and len(confident) < len(notes):
        notes = confident
        messages.append("Low-confidence notes were removed.")

    notes.sort(key=lambda n: n["start_time"])
    return notes, messages


def write_midi_from_notes(notes: list[dict[str, Any]], midi_out_path: Path) -> None:
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0, name="Transcribed Melody")
    for note in notes:
        # v0.9.3: prefer the detector's loudness when present (poly notes);
        # older/melody notes keep the confidence-as-velocity behaviour.
        loudness = note.get("velocity")
        if loudness is None:
            loudness = note["confidence"]
        velocity = max(1, min(127, round(loudness * 127)))
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
                    "recording. Fell back to melody-only transcription."
                )
                if poly_messages:
                    # Keep the engine's own explanation (e.g. that the Basic
                    # Pitch model isn't installed) — it says WHY it was empty.
                    detection_note = " ".join([*poly_messages, detection_note])
        except Exception as exc:  # noqa: BLE001
            notes = None
            detection_note = (
                f"Multiple-note detection failed ({exc}). "
                "Fell back to melody-only transcription."
            )

    if notes is None:
        notes, melody_messages = _detect_notes(audio_path)
        if melody_messages:
            extra = " ".join(melody_messages)
            detection_note = f"{detection_note} {extra}" if detection_note else extra

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
