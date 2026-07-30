"""Optional piano-specialist transcription via ByteDance/Qiuqiang Kong's
"Piano Expert" model (PyPI package `piano_transcription_inference`).

Investigated for v0.9.4 and re-investigated for v0.9.6 specifically because
Basic Pitch, while a real improvement over pYIN, is not accurate enough on
dense piano recordings (the "Mrs Magic" benchmark). Piano Expert is a
piano-specific transcription model (onset/frame/velocity CNN) that should,
in principle, do meaningfully better on exactly this material.

Two blockers, both confirmed again in v0.9.6 (curl against the actual
hosts, not just re-reading old notes):
1. The package depends on PyTorch; only the default GPU-oriented PyPI wheel
   is reachable here (download.pytorch.org, the CPU-only wheel host, is
   403-blocked at the network level) — installing it pulls in several GB of
   unused CUDA packages.
2. Its pretrained checkpoint auto-downloads from zenodo.org on first use,
   which is also 403-blocked here. No checkpoint, no working model,
   regardless of the PyTorch question.

See PROJECT_NOTES.md for the full v0.9.6 investigation writeup (including
what was tried as a workaround). Piano Expert is therefore NOT a dependency
of this project (not in requirements.txt) and is never installed
automatically — exactly like Demucs (app/separation.py). If a user manually
installs `piano_transcription_inference` (and its checkpoint can actually
download) in an environment where those hosts are reachable, this module
will detect and use it automatically; every function here is defensive by
design and never raises, so the app keeps working unchanged when it can't.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pretty_midi

# piano_transcription_inference expects 16kHz mono audio.
PIANO_EXPERT_SAMPLE_RATE = 16000
# A real chordal model can legitimately sound more than Basic Pitch's 4-note
# cap at once (e.g. a full LH+RH piano chord) — group for chord-id/display
# purposes with a more generous cap, not to silently trim real chords.
GROUP_MAX_POLYPHONY = 8
# Very quiet or very short events are treated the same way Basic Pitch
# treats its own ghost detections — noise, not played notes.
MIN_VELOCITY_FRACTION = 0.15  # relative to this recording's loudest note
MIN_NOTE_DURATION = 0.05  # seconds
# Same-pitch events separated by no more than this merge into one sustained
# note — the model occasionally re-triggers mid-decay on a long-held key,
# same failure mode Basic Pitch has (see polyphonic.py's own rejoin pass).
REJOIN_GAP_S = 0.05


def _rejoin_same_pitch(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge same-pitch onset/offset events split mid-sustain."""
    ordered = sorted(events, key=lambda e: (int(round(e["midi_note"])), e["onset_time"]))
    merged: list[dict[str, Any]] = []
    for event in ordered:
        if merged:
            last = merged[-1]
            if (
                int(round(event["midi_note"])) == int(round(last["midi_note"]))
                and event["onset_time"] - last["offset_time"] <= REJOIN_GAP_S
            ):
                last["offset_time"] = max(last["offset_time"], event["offset_time"])
                last["velocity"] = max(last["velocity"], event["velocity"])
                continue
        merged.append(dict(event))
    return merged

_transcriptor = None  # lazy singleton: loading the model/checkpoint is slow


def is_available() -> tuple[bool, Optional[str]]:
    """Whether Piano Expert can plausibly run here, and why not if it can't.

    Only checks that the package imports — it does not guarantee the model
    checkpoint can actually be downloaded (discovered, gracefully, inside
    transcribe_piano on first real use).
    """
    try:
        import piano_transcription_inference  # noqa: F401
    except ImportError:
        return False, (
            "Piano Expert (ByteDance's piano_transcription_inference) isn't "
            "installed. It's optional — Piano falls back to Basic Pitch."
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Piano Expert is installed but failed to load ({exc})."
    return True, None


def _get_transcriptor():
    global _transcriptor
    if _transcriptor is None:
        from piano_transcription_inference import PianoTranscription

        _transcriptor = PianoTranscription(device="cpu")
    return _transcriptor


def transcribe_piano(audio_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Run Piano Expert and convert its output into BandChart's note schema.

    Raises on genuine failure (model/checkpoint unavailable, inference
    error) — callers (transcription.py / arrangement.py) wrap this in
    try/except and fall back to Basic Pitch, exactly like the existing
    Basic Pitch -> CQT fallback chain, so a failure here degrades
    gracefully instead of crashing the app.
    """
    import librosa

    from app.polyphonic import _assign_groups

    y, _sr = librosa.load(str(audio_path), sr=PIANO_EXPERT_SAMPLE_RATE, mono=True)
    transcriptor = _get_transcriptor()
    # midi_path=None: this call only needs the parsed note events, not a
    # MIDI file written to disk (write_midi_from_notes handles that later
    # from the converted notes, exactly like every other engine).
    result = transcriptor.transcribe(y, None)
    note_events = result.get("est_note_events") or []
    if not note_events:
        return [], []
    note_events = _rejoin_same_pitch(note_events)

    max_velocity = max((float(e["velocity"]) for e in note_events), default=1.0) or 1.0

    notes: list[dict[str, Any]] = []
    dropped = 0
    for event in note_events:
        start = float(event["onset_time"])
        end = float(event["offset_time"])
        duration = end - start
        pitch = int(round(event["midi_note"]))
        velocity_norm = float(event["velocity"]) / max_velocity
        if duration < MIN_NOTE_DURATION or velocity_norm < MIN_VELOCITY_FRACTION:
            dropped += 1
            continue
        confidence = round(min(1.0, max(0.0, velocity_norm)), 4)
        notes.append(
            {
                "pitch": pitch,
                "pitch_name": pretty_midi.note_number_to_name(pitch),
                "start_time": round(start, 4),
                "duration": round(duration, 4),
                "confidence": confidence,
                "velocity": confidence,
                "source": "piano_expert",
            }
        )

    notes, group_messages = _assign_groups(notes, max_polyphony=GROUP_MAX_POLYPHONY)
    messages = list(group_messages)
    if dropped:
        messages.append("Low-confidence notes were removed.")
    notes.sort(key=lambda n: (n["start_time"], n["pitch"]))
    return notes, messages
