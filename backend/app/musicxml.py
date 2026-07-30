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
import math
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from music21 import (
    chord as m21_chord,
    clef,
    harmony,
    instrument,
    key,
    layout,
    metadata,
    meter,
    note,
    stream,
    tempo,
)

from app.chords import KEY_SHARPS, m21_chord_figure
from app.notation_cleanup import clean_notes, clean_notes_poly, make_readable

TEMPO_BPM = 120
SECONDS_PER_QUARTER = 60 / TEMPO_BPM
QUANT = 0.25  # sixteenth-note grid, in quarter lengths
MIN_QL = 0.25

VALID_TIME_SIGNATURES = ("4/4", "3/4", "6/8")
# Piano notes at/above middle C go on the treble staff, the rest on bass.
GRAND_STAFF_SPLIT_MIDI = 60

# Instrument key -> (display label, music21 instrument class or None for
# concert pitch, semitones from concert to written pitch). The offsets mirror
# the music21 transpositions and are duplicated in frontend/lib/instruments.ts.
INSTRUMENTS: dict[str, dict[str, Any]] = {
    "concert": {"label": "Concert pitch", "m21": None, "written_offset": 0},
    "piano": {"label": "Piano", "m21": instrument.Piano, "written_offset": 0},
    "flute": {"label": "Flute", "m21": instrument.Flute, "written_offset": 0},
    "violin": {"label": "Violin", "m21": instrument.Violin, "written_offset": 0},
    "voice": {"label": "Voice / Vocals", "m21": instrument.Vocalist, "written_offset": 0},
    "alto_sax": {"label": "Alto Sax", "m21": instrument.AltoSaxophone, "written_offset": 9},
    "tenor_sax": {"label": "Tenor Sax", "m21": instrument.TenorSaxophone, "written_offset": 14},
    "trumpet": {"label": "Trumpet", "m21": instrument.Trumpet, "written_offset": 2},
    "clarinet": {"label": "Clarinet", "m21": instrument.Clarinet, "written_offset": 2},
    # v0.7 fretted instruments: their main output is text tab (app/tablature.py),
    # but they keep working here so MusicXML/PDF still export staff notation.
    "guitar": {"label": "Guitar", "m21": instrument.Guitar, "written_offset": 0},
    "bass": {"label": "Bass", "m21": instrument.ElectricBass, "written_offset": 0},
    "ukulele": {"label": "Ukulele", "m21": instrument.Ukulele, "written_offset": 0},
}


def _quantize(value: float, grid: float) -> float:
    return round(value / grid) * grid


def _respell_for_key(part: stream.Part, sharps: int) -> None:
    """Prefer simpler, key-consistent accidental spellings.

    Flat keys respell sharp accidentals as flats (C# -> Db) and vice versa;
    awkward spellings (E#, Cb, double accidentals) always get simplified.
    """
    awkward = {"E#", "B#", "C-", "F-"}
    for m21_note in part.recurse().getElementsByClass(note.Note):
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
    chords: list[dict[str, Any]] | None = None,
    rhythm_detail: str = "readable",
    time_signature: str = "4/4",
    key_signature: str | None = None,
    arrangement_label: str | None = None,
    detection: str = "melody",
) -> Path:
    """Write a MusicXML file for the given detected notes and instrument.

    style="clean" (default) runs the notation cleanup pipeline and adds a
    key signature; style="raw" engraves the detection literally on a
    sixteenth grid. Within clean, rhythm_detail="readable" (default) runs
    the extra beginner-friendly rhythm pass; "precise" keeps the literal
    eighth grid of the cleanup.

    time_signature: "4/4" (default), "3/4" or "6/8". key_signature: one of
    the Advanced Settings keys to force the signature, None to estimate it.
    chords: manual chord markers, engraved as symbols above the (top) staff.
    arrangement_label: appended to the title (e.g. "solo arrangement").

    Piano gets a grand staff: two PartStaffs joined by a brace, split
    around middle C, with rests filling whichever staff has no melody.
    """
    spec = INSTRUMENTS[instrument_key]
    polyphonic = detection == "poly"

    cleaned = style == "clean"
    if cleaned:
        # The wobble/merge/readable passes assume ONE melody line — running
        # them on polyphonic notes would merge or drop chord members, so
        # polyphonic transcriptions get their own chord-preserving pass
        # (v0.9.3): grid starts, deduped pitches, readable durations.
        if polyphonic:
            notes = clean_notes_poly(notes, readable=rhythm_detail != "precise")
        else:
            notes = clean_notes(notes)
            if rhythm_detail != "precise":
                notes = make_readable(notes)
        grid_ql = 0.5  # eighth-note grid, matching the cleanup quantization
    else:
        grid_ql = QUANT

    ts_string = time_signature if time_signature in VALID_TIME_SIGNATURES else "4/4"
    ts = meter.TimeSignature(ts_string)
    quarters_per_bar = ts.barDuration.quarterLength

    grand = instrument_key == "piano"
    if grand:
        staves = [stream.PartStaff(), stream.PartStaff()]
    else:
        staves = [stream.Part()]
    main_staff = staves[0]

    if spec["m21"] is not None:
        m21_inst = spec["m21"]()
    else:
        m21_inst = instrument.Instrument()
        m21_inst.instrumentName = "Concert pitch"
    main_staff.partName = spec["label"]
    main_staff.insert(0, m21_inst)
    for staff in staves:
        staff.insert(0, meter.TimeSignature(ts_string))
    main_staff.insert(0, tempo.MetronomeMark(number=TEMPO_BPM))

    # placed: every (offset, duration, pitch) that ends up on paper — used
    # below for staff padding and key analysis regardless of the path taken.
    placed: list[tuple[float, float, int]] = []

    if polyphonic:
        # Polyphonic path (v0.9.2): notes sharing a grid slot become one
        # engraved chord (per staff on the piano grand staff). Durations
        # are clipped so an event never runs past the next one.
        groups: dict[float, dict[int, float]] = {}
        for n in notes:
            offset_ql = _quantize(n["start_time"] / SECONDS_PER_QUARTER, grid_ql)
            dur_ql = max(grid_ql, _quantize(n["duration"] / SECONDS_PER_QUARTER, grid_ql))
            slot = groups.setdefault(offset_ql, {})
            pitch_value = int(n["pitch"])
            slot[pitch_value] = max(slot.get(pitch_value, 0.0), dur_ql)

        offsets = sorted(groups)
        for index, offset_ql in enumerate(offsets):
            room = (
                offsets[index + 1] - offset_ql if index + 1 < len(offsets) else None
            )
            members = groups[offset_ql]
            per_staff: dict[int, list[int]] = {}
            for pitch_value in sorted(members):
                staff_index = (
                    1 if grand and pitch_value < GRAND_STAFF_SPLIT_MIDI else 0
                )
                per_staff.setdefault(staff_index, []).append(pitch_value)
            for staff_index, pitches in per_staff.items():
                dur_ql = max(members[p] for p in pitches)
                if room is not None:
                    dur_ql = min(dur_ql, room)
                dur_ql = max(grid_ql, dur_ql)
                if len(pitches) == 1:
                    element: note.NotRest = note.Note(pitches[0])
                else:
                    element = m21_chord.Chord(pitches)
                element.quarterLength = dur_ql
                staves[staff_index].insert(offset_ql, element)
                for pitch_value in pitches:
                    placed.append((offset_ql, dur_ql, pitch_value))
    else:
        # Melody path (unchanged): notes are monophonic and must not
        # overlap; clip any stragglers so the exporter never sees overlaps.
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
            if grand and midi_pitch < GRAND_STAFF_SPLIT_MIDI:
                staves[1].insert(offset_ql, m21_note)
            else:
                staves[0].insert(offset_ql, m21_note)

    # BOTH grand-staff sides must span the same whole number of bars, or
    # makeNotation gives them different measure counts — which misplaces
    # chord symbols and draws a "final" barline mid-piece. Pad each staff
    # with a trailing rest up to the common bar-aligned end (a side with no
    # melody at all becomes one long rest); makeNotation splits it per bar.
    if grand:
        total_ql = max((o + d for o, d, _ in placed), default=quarters_per_bar)
        total_ql = math.ceil(total_ql / quarters_per_bar - 1e-9) * quarters_per_bar
        for staff in staves:
            staff_end = max(
                (n.offset + n.quarterLength
                 for n in staff.recurse().getElementsByClass(note.NotRest)),
                default=0.0,
            )
            if staff_end < total_ql - 1e-9:
                rest = note.Rest()
                rest.quarterLength = total_ql - staff_end
                staff.insert(staff_end, rest)

    # Cleaned scores get a key signature so in-key notes engrave without
    # per-note accidentals — the user's Advanced Settings key when chosen,
    # otherwise estimated from the melody. Concert pitch here; transposition
    # below moves the signature along with the notes.
    if cleaned and placed:
        sharps: int | None = KEY_SHARPS.get(key_signature) if key_signature else None
        if sharps is None:
            try:
                analysis_stream = stream.Stream()
                for offset_ql, dur_ql, midi_pitch in placed:
                    analysis_note = note.Note(midi_pitch)
                    analysis_note.quarterLength = dur_ql
                    analysis_stream.insert(offset_ql, analysis_note)
                sharps = analysis_stream.analyze("key").sharps
            except Exception:
                sharps = None  # best-effort; the score works without it
        if sharps is not None:
            for staff in staves:
                staff.insert(0, key.KeySignature(sharps))

    # Stored pitches are concert pitch; convert transposing instruments to
    # written pitch so MuseScore shows the part as a player would read it.
    # (Piano never transposes, so the grand staff never hits this.)
    for staff in staves:
        staff.atSoundingPitch = True
    if m21_inst.transposition is not None:
        main_staff.toWrittenPitch(inPlace=True)

    if cleaned:
        written_ks = main_staff.recurse().getElementsByClass(key.KeySignature).first()
        for staff in staves:
            _respell_for_key(staff, written_ks.sharps if written_ks is not None else 0)

    if grand:
        staves[0].insert(0, clef.TrebleClef())
        staves[1].insert(0, clef.BassClef())
    else:
        main_staff.insert(0, clef.bestClef(main_staff, recurse=True))

    # Manual chord markers become chord symbols above the (top) staff.
    # Inserted AFTER key analysis / respelling / clef choice so an added
    # chord never changes how the melody itself engraves; transposing
    # instruments get the symbols transposed to written pitch by hand
    # (toWrittenPitch has already run). Unparseable names are skipped rather
    # than failing the export — they still appear in JSON and the chart.
    for chord_marker in chords or []:
        try:
            symbol = harmony.ChordSymbol(m21_chord_figure(chord_marker["name"]))
            if m21_inst.transposition is not None:
                symbol.transpose(m21_inst.transposition.reverse(), inPlace=True)
        except Exception:
            continue
        offset_ql = max(
            0.0, _quantize(chord_marker["start_time"] / SECONDS_PER_QUARTER, grid_ql)
        )
        main_staff.insert(offset_ql, symbol)

    title = f"{project_name} — {spec['label']}"
    if arrangement_label:
        title += f" ({arrangement_label})"
    if not cleaned:
        title += " (raw transcription)"

    score = stream.Score()
    score.metadata = metadata.Metadata(title=title)
    for staff in staves:
        score.insert(0, staff)
    if grand:
        score.insert(0, layout.StaffGroup(staves, symbol="brace"))
    score.makeNotation(inPlace=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a unique temp file, then swap it in atomically: two
    # concurrent requests (e.g. the sheet view and a download) must never
    # see each other's half-written file.
    tmp_path = out_path.with_name(f".{uuid4().hex}-{out_path.name}")
    try:
        score.write("musicxml", fp=str(tmp_path))
        os.replace(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return out_path


def load_notes_for_project(transcription_json_path: Path) -> dict[str, Any]:
    return json.loads(transcription_json_path.read_text())
