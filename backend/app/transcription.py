"""Wraps basic-pitch inference and converts its output into our notes schema."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pretty_midi
from basic_pitch.inference import predict

from app.storage import now_iso


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def run_transcription(
    audio_path: Path,
    midi_out_path: Path,
    json_out_path: Path,
    project_id: str,
    project_name: str,
    source_audio_filename: str,
) -> dict[str, Any]:
    """Run real basic-pitch ML inference on audio_path, write MIDI + notes JSON.

    Returns the transcription result dict (same shape written to json_out_path).
    """
    model_output, midi_data, note_events = predict(str(audio_path))

    midi_out_path.parent.mkdir(parents=True, exist_ok=True)
    midi_data.write(str(midi_out_path))

    notes = []
    for event in note_events:
        start_time_s, end_time_s, pitch_midi, amplitude, _pitch_bends = event[:5]
        pitch = int(pitch_midi)
        start_time = round(float(start_time_s), 4)
        duration = round(float(end_time_s) - float(start_time_s), 4)
        confidence = float(_clamp(float(amplitude), 0.0, 1.0))
        notes.append(
            {
                "pitch": pitch,
                "pitch_name": pretty_midi.note_number_to_name(pitch),
                "start_time": start_time,
                "duration": duration,
                "confidence": confidence,
            }
        )

    notes.sort(key=lambda n: n["start_time"])

    result = {
        "project_id": project_id,
        "project_name": project_name,
        "source_audio": source_audio_filename,
        "generated_at": now_iso(),
        "note_count": len(notes),
        "notes": notes,
    }

    json_out_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    json_out_path.write_text(json.dumps(result, indent=2))

    return result
