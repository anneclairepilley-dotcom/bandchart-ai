"""Experimental multi-pitch (polyphonic) note detection.

The main pipeline (transcription.py) uses pYIN, which by design follows ONE
melody line. This module adds a deliberately simple alternative for clear
piano tones and simple chords: it slices the recording at onsets, averages a
constant-Q spectrum over each slice, and picks up to four strong, locally
peaked semitone bins as simultaneous notes — with thresholds that stop most
harmonics from being mistaken for extra notes.

It is honest about being rough: quiet inner voices, dense harmonies and
noisy recordings will be missed or simplified. Anything that goes wrong
raises, and the caller falls back to the reliable melody-only pYIN pipeline
with a clear message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import librosa
import numpy as np
import pretty_midi

SAMPLE_RATE = 22050
HOP_LENGTH = 512
FMIN_MIDI = 36  # C2 — matching the melody pipeline's range
N_BINS = 60  # C2..B6, one bin per semitone
MAX_POLYPHONY = 4
MIN_NOTE_DURATION = 0.09  # seconds, matching the melody pipeline

# A bin must reach this fraction of the segment's strongest bin to count.
RELATIVE_FLOOR = 0.25
# ...and this fraction of the loudest moment in the whole recording (kills
# "notes" detected inside near-silence).
ABSOLUTE_FLOOR = 0.02
# A candidate this interval above an accepted note is treated as a harmonic
# (octave, twelfth, double octave, major-third-over-two-octaves) unless it
# is nearly as strong as the note itself.
HARMONIC_INTERVALS = (12, 19, 24, 28)
HARMONIC_TOLERANCE = 0.8


def _make_note(pitch: int, start: float, duration: float, confidence: float) -> dict[str, Any]:
    return {
        "pitch": int(pitch),
        "pitch_name": pretty_midi.note_number_to_name(int(pitch)),
        "start_time": round(float(start), 4),
        "duration": round(float(duration), 4),
        "confidence": round(float(min(1.0, max(0.0, confidence))), 4),
    }


def detect_notes_poly(audio_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Detect up to MAX_POLYPHONY simultaneous notes per onset segment.

    Returns (notes, messages). Notes may share or overlap start times and
    are sorted by (start_time, pitch). Messages report simplifications
    (e.g. more simultaneous notes than we keep).
    """
    y, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    if y.size == 0:
        return [], []

    cqt = np.abs(
        librosa.cqt(
            y,
            sr=sr,
            hop_length=HOP_LENGTH,
            fmin=librosa.midi_to_hz(FMIN_MIDI),
            n_bins=N_BINS,
            bins_per_octave=12,
        )
    )
    n_frames = cqt.shape[1]
    if n_frames == 0:
        return [], []
    global_max = float(cqt.max())
    if global_max <= 0:
        return [], []

    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=HOP_LENGTH, backtrack=True
    )
    min_frames = max(2, int(round(MIN_NOTE_DURATION * sr / HOP_LENGTH)))
    boundaries = sorted({0, n_frames, *(int(f) for f in onset_frames)})
    segments = [
        (a, b) for a, b in zip(boundaries, boundaries[1:]) if b - a >= min_frames
    ]

    frame_time = HOP_LENGTH / sr
    notes: list[dict[str, Any]] = []
    overflowed = False

    for seg_start, seg_end in segments:
        segment = cqt[:, seg_start:seg_end]
        profile = segment.mean(axis=1)
        top = float(profile.max())
        if top < ABSOLUTE_FLOOR * global_max:
            continue  # effectively silence

        # Candidate pitches: semitone bins that are local maxima.
        candidates = []
        for bin_index in range(N_BINS):
            value = float(profile[bin_index])
            if value < RELATIVE_FLOOR * top or value < ABSOLUTE_FLOOR * global_max:
                continue
            if bin_index > 0 and profile[bin_index - 1] > value:
                continue
            if bin_index < N_BINS - 1 and profile[bin_index + 1] > value:
                continue
            candidates.append((value, bin_index))
        candidates.sort(reverse=True)

        accepted: list[tuple[int, float]] = []
        for value, bin_index in candidates:
            is_harmonic = False
            for accepted_bin, accepted_value in accepted:
                if (
                    bin_index - accepted_bin in HARMONIC_INTERVALS
                    and value < HARMONIC_TOLERANCE * accepted_value
                ):
                    is_harmonic = True
                    break
            if is_harmonic:
                continue
            accepted.append((bin_index, value))
        if len(accepted) > MAX_POLYPHONY:
            overflowed = True
            accepted = accepted[:MAX_POLYPHONY]

        seg_length_s = (seg_end - seg_start) * frame_time
        start_s = seg_start * frame_time
        for bin_index, value in accepted:
            # Sustain: how long this pitch actually rings within the segment.
            row = segment[bin_index]
            row_peak = float(row.max())
            ringing = np.nonzero(row >= 0.25 * row_peak)[0]
            duration_s = (
                (int(ringing[-1]) + 1) * frame_time if ringing.size else seg_length_s
            )
            duration_s = min(max(duration_s, MIN_NOTE_DURATION), seg_length_s)
            notes.append(
                _make_note(FMIN_MIDI + bin_index, start_s, duration_s, value / top)
            )

    notes.sort(key=lambda n: (n["start_time"], n["pitch"]))
    messages: list[str] = []
    if overflowed:
        messages.append(
            "Some moments had more than 4 simultaneous notes — only the "
            "strongest 4 were kept."
        )
    return notes, messages
