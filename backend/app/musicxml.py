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

from music21 import clef, instrument, key, metadata, meter, note, stream, tempo

from app.notation_cleanup import clean_notes

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


def _quantize(value: float, grid: float) -> float:
    return round(value / grid) * grid


def _respell_for_key(part: stream.Part, sharps: int) -> None:
    """Prefer simpler, key-consistent accidental spellings.

    Flat keys respell sharp accidentals as flats (C# -> Db) and vice versa;
    awkward spellings (E#, Cb, double accidentals) always get simplified.
    """
    awkward = {"E#", "B#", "C-", "F-"}
    for m21_note in part.recurse().notes:
        pitch = m21_note.pitch
        accidental = pitch.accidental
        if accidental is None:
            continue
        if accidental.alter == 0:
            # MIDI-derived pitches carry explicit "natural" accidental objects;
            # drop them so makeAccidentals only shows naturals where a measure
            # context genuinely requires one.
            pitch.accidental = None
            continue
        if abs(accidental.alter) >= 2 or pitch.name.replace("b", "-") in awkward:
            m21_note.pitch = pitch.getEnharmonic()
            continue
        if sharps < 0 and accidental.alter == 1:
            m21_note.pitch = pitch.getEnharmonic()
        elif sharps >= 0 and accidental.alter == -1:
            m21_note.pitch = pitch.getEnharmonic()


def notes_to_musicxml(
    notes: list[dict[str, Any]],
    instrument_key: str,
    project_name: str,
    out_path: Path,
    style: str = "clean",
) -> Path:
    """Write a MusicXML file for the given detected notes and instrument.

    style="clean" (default) runs the notation cleanup pipeline (pitch
    smoothing, merging, fragment removal, eighth-note quantization) and adds
    an estimated key signature; style="raw" engraves the detection literally
    on a sixteenth grid, exactly as v0.3 did.
    """
    spec = INSTRUMENTS[instrument_key]

    cleaned = style == "clean"
    if cleaned:
        notes = clean_notes(notes)
        grid_ql = 0.5  # eighth-note grid, matching the cleanup quantization
    else:
        grid_ql = QUANT

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
        offset_ql = _quantize(n["start_time"] / SECONDS_PER_QUARTER, grid_ql)
        dur_ql = max(grid_ql, _quantize(n["duration"] / SECONDS_PER_QUARTER, grid_ql))
        if placed:
            prev_offset, prev_dur, prev_pitch = placed[-1]
            if offset_ql < prev_offset + prev_dur:
                clipped = offset_ql - prev_offset
                if clipped < grid_ql:
                    # Same grid slot as the previous note; keep the earlier one.
                    continue
                placed[-1] = (prev_offset, clipped, prev_pitch)
        placed.append((offset_ql, dur_ql, int(n["pitch"])))

    for offset_ql, dur_ql, midi_pitch in placed:
        m21_note = note.Note(midi_pitch)
        m21_note.quarterLength = dur_ql
        part.insert(offset_ql, m21_note)

    # Cleaned scores get an estimated key signature so in-key notes engrave
    # without per-note accidentals. Estimated at concert pitch; transposition
    # below moves the signature along with the notes.
    if cleaned and placed:
        try:
            analyzed = part.analyze("key")
            part.insert(0, key.KeySignature(analyzed.sharps))
        except Exception:
            pass  # key estimation is best-effort; the score works without it

    # Stored pitches are concert pitch; convert transposing instruments to
    # written pitch so MuseScore shows the part as a player would read it.
    part.atSoundingPitch = True
    if m21_inst.transposition is not None:
        part.toWrittenPitch(inPlace=True)

    if cleaned:
        written_ks = part.recurse().getElementsByClass(key.KeySignature).first()
        _respell_for_key(part, written_ks.sharps if written_ks is not None else 0)

    part.insert(0, clef.bestClef(part, recurse=True))

    title = f"{project_name} — {spec['label']}"
    if not cleaned:
        title += " (raw transcription)"

    score = stream.Score()
    score.metadata = metadata.Metadata(title=title)
    score.insert(0, part)
    score.makeNotation(inPlace=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(out_path))
    return out_path


def load_notes_for_project(transcription_json_path: Path) -> dict[str, Any]:
    return json.loads(transcription_json_path.read_text())
