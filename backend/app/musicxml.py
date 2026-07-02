"""Converts detected notes into a simple MusicXML solo part via music21.

The transcription JSON stores concert (sounding) pitches. For transposing
instruments (E-flat / B-flat horns) the exported part is converted to
written pitch using music21's built-in instrument transpositions, so the
file opens in MuseScore with the part correctly transposed.

Rhythm is intentionally rough for v0.2: a fixed 120 BPM in 4/4, with note
starts and lengths quantized to sixteenth notes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from music21 import clef, instrument, metadata, meter, note, stream, tempo

TEMPO_BPM = 120
SECONDS_PER_QUARTER = 60 / TEMPO_BPM
QUANT = 0.25  # sixteenth-note grid, in quarter lengths
MIN_QL = 0.25

# Instrument key -> (display label, music21 instrument class or None for
# concert pitch, semitones from concert to written pitch). The offsets mirror
# the music21 transpositions and are duplicated in frontend/lib/instruments.ts.
INSTRUMENTS: dict[str, dict[str, Any]] = {
    "concert": {"label": "Concert pitch", "m21": None, "written_offset": 0},
    "piano": {"label": "Piano", "m21": instrument.Piano, "written_offset": 0},
    "flute": {"label": "Flute", "m21": instrument.Flute, "written_offset": 0},
    "violin": {"label": "Violin", "m21": instrument.Violin, "written_offset": 0},
    "alto_sax": {"label": "Alto Sax", "m21": instrument.AltoSaxophone, "written_offset": 9},
    "tenor_sax": {"label": "Tenor Sax", "m21": instrument.TenorSaxophone, "written_offset": 14},
    "trumpet": {"label": "Trumpet", "m21": instrument.Trumpet, "written_offset": 2},
    "clarinet": {"label": "Clarinet", "m21": instrument.Clarinet, "written_offset": 2},
}


def _quantize(value: float) -> float:
    return round(value / QUANT) * QUANT


def notes_to_musicxml(
    notes: list[dict[str, Any]],
    instrument_key: str,
    project_name: str,
    out_path: Path,
) -> Path:
    """Write a MusicXML file for the given detected notes and instrument."""
    spec = INSTRUMENTS[instrument_key]

    part = stream.Part()
    if spec["m21"] is not None:
        m21_inst = spec["m21"]()
    else:
        m21_inst = instrument.Instrument()
        m21_inst.instrumentName = "Concert pitch"
    part.partName = spec["label"]
    part.insert(0, m21_inst)
    part.insert(0, meter.TimeSignature("4/4"))
    part.insert(0, tempo.MetronomeMark(number=TEMPO_BPM))

    # Notes are stored sorted by start time and (being monophonic) should not
    # overlap; clip any stragglers so the exporter never sees overlapping notes.
    placed: list[tuple[float, float, int]] = []
    for n in notes:
        offset_ql = _quantize(n["start_time"] / SECONDS_PER_QUARTER)
        dur_ql = max(MIN_QL, _quantize(n["duration"] / SECONDS_PER_QUARTER))
        if placed:
            prev_offset, prev_dur, prev_pitch = placed[-1]
            if offset_ql < prev_offset + prev_dur:
                clipped = offset_ql - prev_offset
                if clipped < MIN_QL:
                    # Same grid slot as the previous note; keep the earlier one.
                    continue
                placed[-1] = (prev_offset, clipped, prev_pitch)
        placed.append((offset_ql, dur_ql, int(n["pitch"])))

    for offset_ql, dur_ql, midi_pitch in placed:
        m21_note = note.Note(midi_pitch)
        m21_note.quarterLength = dur_ql
        part.insert(offset_ql, m21_note)

    # Stored pitches are concert pitch; convert transposing instruments to
    # written pitch so MuseScore shows the part as a player would read it.
    part.atSoundingPitch = True
    if m21_inst.transposition is not None:
        part.toWrittenPitch(inPlace=True)

    part.insert(0, clef.bestClef(part, recurse=True))

    score = stream.Score()
    score.metadata = metadata.Metadata(title=f"{project_name} — {spec['label']}")
    score.insert(0, part)
    score.makeNotation(inPlace=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(out_path))
    return out_path


def load_notes_for_project(transcription_json_path: Path) -> dict[str, Any]:
    return json.loads(transcription_json_path.read_text())
