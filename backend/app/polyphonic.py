"""Experimental multi-pitch (polyphonic) note detection.

v0.9.3: the primary engine is Spotify's open-source **Basic Pitch** model
(ICASSP 2022), run through its bundled ONNX network on CPU — a real
learned transcription model that detects onsets, durations and several
simultaneous pitches. No TensorFlow: the package is installed WITHOUT its
(Python-3.12-incompatible) declared dependencies and driven purely via
onnxruntime; see README setup notes. Model output is post-filtered
(confidence floors, pitch range, ghost removal) and grouped into chord
events (max 4 simultaneous notes, strongest kept).

When Basic Pitch isn't installed or fails, the v0.9.2 fallback runs: slice
the recording at onsets, average a constant-Q spectrum per slice, and pick
up to four strong locally-peaked semitone bins — with thresholds that stop
most harmonics from being mistaken for extra notes.

Both engines are honest about being rough: quiet inner voices, dense
harmonies and noisy recordings will be missed or simplified. If everything
goes wrong the caller falls back to the reliable melody-only pYIN pipeline
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


# Notes starting within this window belong to the same chord group.
GROUP_WINDOW_S = 0.04
# Basic Pitch post-filters: drop clearly weak detections, and short+weak
# blips that are usually harmonic ghosts.
BP_MIN_AMPLITUDE = 0.32
BP_GHOST_AMPLITUDE = 0.42
BP_GHOST_DURATION_S = 0.18
# Same-pitch events separated by no more than this merge into one note,
# unless the audio shows a genuine re-attack (loudness dip-and-rise) at the
# junction — the model sometimes splits one long decaying note in two.
BP_REJOIN_GAP_S = 0.15
REATTACK_RISE = 1.35


def _assign_groups(
    notes: list[dict[str, Any]], max_polyphony: int = MAX_POLYPHONY
) -> tuple[list[dict[str, Any]], list[str]]:
    """Cluster near-simultaneous notes into chord groups; cap each group.

    Notes within GROUP_WINDOW_S of a cluster's first onset share a
    "chord_N" group id (single notes get no group). Groups larger than
    max_polyphony keep their strongest members.
    """
    notes = sorted(notes, key=lambda n: (n["start_time"], n["pitch"]))
    result: list[dict[str, Any]] = []
    messages: list[str] = []
    trimmed = 0
    trimmed_groups = 0
    total_groups = 0
    group_id = 0
    index = 0
    while index < len(notes):
        cluster_start = notes[index]["start_time"]
        cluster = [notes[index]]
        index += 1
        while (
            index < len(notes)
            and notes[index]["start_time"] - cluster_start <= GROUP_WINDOW_S
        ):
            cluster.append(notes[index])
            index += 1
        total_groups += 1
        if len(cluster) > max_polyphony:
            cluster.sort(key=lambda n: -n["confidence"])
            trimmed += len(cluster) - max_polyphony
            trimmed_groups += 1
            cluster = cluster[:max_polyphony]
            cluster.sort(key=lambda n: n["pitch"])
        if len(cluster) > 1:
            group_id += 1
            for member in cluster:
                member["group"] = f"chord_{group_id}"
        result.extend(cluster)
    if trimmed:
        messages.append(
            "Too many simultaneous notes were detected in places — only the "
            f"strongest {max_polyphony} were kept (simplified output)."
        )
        # When most moments overflow the cap, the recording is beyond what
        # this first polyphonic pass can represent — say so plainly.
        if total_groups and trimmed_groups >= max(3, total_groups // 2):
            messages.append("This audio is too dense for the current model.")
    result.sort(key=lambda n: (n["start_time"], n["pitch"]))
    return result, messages


def _rejoin_split_events(
    events: list[tuple[float, float, int, float]], audio_path: Path
) -> list[tuple[float, float, int, float]]:
    """Merge same-pitch events the model split mid-decay.

    Basic Pitch sometimes re-triggers on the tail of one long note. Two
    events of the same pitch separated by ≤ BP_REJOIN_GAP_S merge back into
    one — unless the recording really dips and rises in loudness at the
    junction (a genuine re-strike, which must stay two notes).
    """
    ordered = sorted(events, key=lambda e: (e[2], e[0]))
    candidates = any(
        a[2] == b[2] and b[0] - a[1] <= BP_REJOIN_GAP_S
        for a, b in zip(ordered, ordered[1:])
    )
    if not candidates:
        return events

    y, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
    rms_times = librosa.times_like(rms, sr=sr, hop_length=HOP_LENGTH)

    def is_reattack(t: float) -> bool:
        before = rms[(rms_times >= t - 0.10) & (rms_times <= t - 0.02)]
        after = rms[(rms_times >= t) & (rms_times <= t + 0.08)]
        if before.size == 0 or after.size == 0:
            return True  # can't tell — keep the split
        return float(after.mean()) >= REATTACK_RISE * float(before.mean())

    merged: list[tuple[float, float, int, float]] = []
    for event in ordered:
        if merged:
            last = merged[-1]
            if (
                event[2] == last[2]
                and event[0] - last[1] <= BP_REJOIN_GAP_S
                and not is_reattack(event[0])
            ):
                merged[-1] = (
                    last[0],
                    max(last[1], event[1]),
                    last[2],
                    max(last[3], event[3]),
                )
                continue
        merged.append(event)
    return merged


def _suppress_harmonics(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop weak harmonic ghosts inside chord clusters.

    Within notes starting together, a note +12/+19/+24/+28 semitones above
    a clearly stronger one is almost always that note's overtone leaking
    through, not a played pitch (same rule the CQT fallback uses).
    """
    kept: list[dict[str, Any]] = []
    notes = sorted(notes, key=lambda n: (n["start_time"], n["pitch"]))
    index = 0
    while index < len(notes):
        cluster_start = notes[index]["start_time"]
        cluster = [notes[index]]
        index += 1
        while (
            index < len(notes)
            and notes[index]["start_time"] - cluster_start <= GROUP_WINDOW_S
        ):
            cluster.append(notes[index])
            index += 1
        for note in cluster:
            ghost = any(
                note["pitch"] - other["pitch"] in HARMONIC_INTERVALS
                and note["confidence"] < HARMONIC_TOLERANCE * other["confidence"]
                for other in cluster
                if other is not note
            )
            if not ghost:
                kept.append(note)
    return kept


def _detect_with_basic_pitch(
    audio_path: Path, max_polyphony: int = MAX_POLYPHONY
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run the Basic Pitch model (ONNX, CPU) and post-filter its notes."""
    from basic_pitch.inference import predict  # heavy import kept lazy

    _model_output, _midi, note_events = predict(str(audio_path))

    events = [
        (float(start), float(end), int(pitch), float(amplitude))
        for start, end, pitch, amplitude, _bends in note_events
        if 24 <= int(pitch) <= 100 and float(end) > float(start)
    ]
    events = _rejoin_split_events(events, audio_path)

    notes: list[dict[str, Any]] = []
    dropped_weak = 0
    for start, end, pitch, amplitude in events:
        duration = end - start
        if amplitude < BP_MIN_AMPLITUDE or (
            amplitude < BP_GHOST_AMPLITUDE and duration < BP_GHOST_DURATION_S
        ):
            dropped_weak += 1
            continue
        confidence = round(float(min(1.0, max(0.0, amplitude))), 4)
        notes.append(
            {
                "pitch": pitch,
                "pitch_name": pretty_midi.note_number_to_name(pitch),
                "start_time": round(start, 4),
                "duration": round(duration, 4),
                "confidence": confidence,
                "velocity": confidence,
                "source": "basic_pitch",
            }
        )

    before_harmonics = len(notes)
    notes = _suppress_harmonics(notes)
    dropped_weak += before_harmonics - len(notes)

    notes, messages = _assign_groups(notes, max_polyphony=max_polyphony)
    if dropped_weak:
        messages.append("Low-confidence notes were removed.")
    return notes, messages


def detect_notes_poly(
    audio_path: Path, max_polyphony: int = MAX_POLYPHONY
) -> tuple[list[dict[str, Any]], list[str]]:
    """Detect simultaneous notes: Basic Pitch model first, CQT fallback.

    max_polyphony caps how many notes can share a chord group (v0.9.5:
    routing.py passes a lower cap for instruments limited to double-stops,
    e.g. violin=2; everything else keeps the default of 4).

    Returns (notes, messages). Notes may share or overlap start times and
    are sorted by (start_time, pitch); simultaneous notes share a chord
    group id. Messages report which engine ran and any simplifications.
    """
    try:
        return _detect_with_basic_pitch(audio_path, max_polyphony=max_polyphony)
    except ImportError:
        notes, messages = _detect_with_cqt(audio_path, max_polyphony=max_polyphony)
        messages.insert(
            0,
            "The Basic Pitch model isn't installed, so the built-in simple "
            "detector was used instead (see the README to enable the model).",
        )
        return notes, messages
    except Exception as exc:  # noqa: BLE001
        notes, messages = _detect_with_cqt(audio_path, max_polyphony=max_polyphony)
        messages.insert(
            0,
            f"The Basic Pitch model failed ({exc}) — the built-in simple "
            "detector was used instead.",
        )
        return notes, messages


def _detect_with_cqt(
    audio_path: Path, max_polyphony: int = MAX_POLYPHONY
) -> tuple[list[dict[str, Any]], list[str]]:
    """v0.9.2 fallback: up to max_polyphony notes per onset segment via CQT."""
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
        if len(accepted) > max_polyphony:
            overflowed = True
            accepted = accepted[:max_polyphony]

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
            cqt_note = _make_note(FMIN_MIDI + bin_index, start_s, duration_s, value / top)
            cqt_note["source"] = "cqt"
            notes.append(cqt_note)

    notes, messages = _assign_groups(notes, max_polyphony=max_polyphony)
    if overflowed and not messages:
        messages.append(
            f"Some moments had more than {max_polyphony} simultaneous notes — "
            f"only the strongest {max_polyphony} were kept."
        )
    return notes, messages
