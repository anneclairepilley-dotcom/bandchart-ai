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
    """Fuse consecutive same-pitch notes separated by no more than merge_gap_s.

    Notes flagged "reattack" (v0.9.3: a repeated note the detector split off
    at a genuine re-strike) are never fused back onto their predecessor.
    """
    merged: list[Note] = []
    for note in notes:
        if merged and not note.get("reattack"):
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
                fused = _make_note(
                    last["pitch"], last["start_time"], new_end - last["start_time"], confidence
                )
                if last.get("reattack"):
                    fused["reattack"] = True
                merged[-1] = fused
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
        snapped = _make_note(note["pitch"], start, duration, note["confidence"])
        if note.get("reattack"):
            snapped["reattack"] = True
        quantized.append(snapped)

    # Snapping can create overlaps or make same-pitch notes touch: merge
    # touching same-pitch notes (but never across a re-strike boundary —
    # a repeated note must stay two notes), clip anything else that overlaps.
    cleaned: list[Note] = []
    for note in quantized:
        if cleaned:
            last = cleaned[-1]
            last_end = last["start_time"] + last["duration"]
            if (
                note["pitch"] == last["pitch"]
                and note["start_time"] <= last_end
                and not note.get("reattack")
            ):
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
                shortened = _make_note(
                    last["pitch"], last["start_time"], clipped, last["confidence"]
                )
                if last.get("reattack"):
                    shortened["reattack"] = True
                cleaned[-1] = shortened
        cleaned.append(note)
    return cleaned


# Note lengths a beginner/intermediate reader is comfortable with, in
# quarter lengths: quaver, crotchet, dotted crotchet, minim, dotted minim,
# semibreve. Deliberately no sixteenths and no dotted quavers.
READABLE_DURATIONS_QL = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)


def make_readable(
    notes: list[Note], settings: CleanupSettings | None = None
) -> list[Note]:
    """Extra pass for the default "Readable" rhythm detail (v0.9.1).

    Runs AFTER clean_notes and pushes the timing further toward something a
    human would write down:
    - starts snap to the eighth grid (which also lands nearly-on-the-beat
      notes exactly on the beat)
    - durations snap to the nearest simple value (quaver, crotchet, dotted
      crotchet, minim, dotted minim, semibreve); anything LONGER than a
      semibreve keeps its grid-rounded length so long held notes are tied
      across bars by the engraver instead of being truncated
    - a gap of up to one quaver before the next note is absorbed by
      extending the note, as long as that still gives a simple length —
      so tiny awkward rests disappear
    - overlaps created by the snapping are clipped; two notes snapped into
      the same slot keep the earlier one (the codebase-wide convention)

    "Precise" mode skips this pass and keeps clean_notes' literal grid.
    """
    settings = settings or CleanupSettings()
    spq = settings.seconds_per_quarter
    longest_simple = READABLE_DURATIONS_QL[-1]

    snapped: list[Note] = []
    for note in notes:
        start = round((note["start_time"] / spq) * 2) / 2  # eighth grid

        duration_ql = note["duration"] / spq
        if duration_ql > longest_simple:
            # Long held note: keep it (rounded to the eighth grid), never
            # truncate it down to a semibreve.
            duration = max(0.5, round(duration_ql * 2) / 2)
        else:
            duration = min(READABLE_DURATIONS_QL, key=lambda v: abs(v - duration_ql))
        snapped.append(
            _make_note(note["pitch"], start * spq, duration * spq, note["confidence"])
        )

    # Same-slot collisions keep the EARLIER note (starts are monotone after
    # rounding, so equal starts are adjacent).
    deduped: list[Note] = []
    for note in snapped:
        if deduped and note["start_time"] <= deduped[-1]["start_time"] + 1e-9:
            continue
        deduped.append(note)

    result: list[Note] = []
    for index, note in enumerate(deduped):
        start_ql = note["start_time"] / spq
        duration_ql = note["duration"] / spq
        next_start_ql = (
            deduped[index + 1]["start_time"] / spq if index + 1 < len(deduped) else None
        )
        if next_start_ql is not None:
            room = next_start_ql - start_ql
            if duration_ql > room:
                duration_ql = room  # clip overlaps
            else:
                gap = room - duration_ql
                # Absorb a quaver-or-smaller rest when the stretched length
                # is still simple (or already long enough that it ties anyway).
                if 0 < gap <= 0.5 and (
                    room in READABLE_DURATIONS_QL or room > longest_simple
                ):
                    duration_ql = room
        if duration_ql < 0.5:
            duration_ql = 0.5
            if next_start_ql is not None and start_ql + duration_ql > next_start_ql:
                continue  # no room for even a quaver without overlapping
        result.append(
            _make_note(
                note["pitch"], start_ql * spq, duration_ql * spq, note["confidence"]
            )
        )
    return result


def clean_notes_poly(
    notes: list[Note],
    settings: CleanupSettings | None = None,
    readable: bool = True,
    max_polyphony: int = 4,
) -> list[Note]:
    """Rhythm cleanup for polyphonic transcriptions (v0.9.3).

    The mono pipeline (wobble smoothing, same-pitch merging, gap
    absorption) would eat chord members, so poly gets its own pass:
    - starts snap to the eighth grid; notes landing in the same slot form
      one chord event
    - duplicate pitches within an event merge (longest ring wins)
    - an event keeps at most max_polyphony pitches (strongest confidence)
    - durations snap to readable lengths (readable=True) or stay on the
      literal grid (Precise mode), and are clipped so no event rings past
      the next one
    - chord group ids are reassigned per event so exports stay in sync
    """
    settings = settings or CleanupSettings()
    spq = settings.seconds_per_quarter
    grid_ql = settings.grid_quarters
    longest_simple = READABLE_DURATIONS_QL[-1]

    # slot -> pitch -> (duration_ql, source note)
    events: dict[float, dict[int, tuple[float, Note]]] = {}
    for n in notes:
        start_ql = round((n["start_time"] / spq) / grid_ql) * grid_ql
        dur_ql = max(grid_ql, round((n["duration"] / spq) / grid_ql) * grid_ql)
        slot = events.setdefault(start_ql, {})
        pitch = int(n["pitch"])
        prev = slot.get(pitch)
        if (
            prev is None
            or dur_ql > prev[0]
            or (dur_ql == prev[0] and n["confidence"] > prev[1]["confidence"])
        ):
            slot[pitch] = (dur_ql, n)

    offsets = sorted(events)
    result: list[Note] = []
    group_id = 0
    for index, start_ql in enumerate(offsets):
        members = sorted(events[start_ql].items())  # by pitch
        if len(members) > max_polyphony:
            members.sort(key=lambda kv: -kv[1][1]["confidence"])
            members = members[:max_polyphony]
            members.sort(key=lambda kv: kv[0])
        room = offsets[index + 1] - start_ql if index + 1 < len(offsets) else None
        group_label = None
        if len(members) > 1:
            group_id += 1
            group_label = f"chord_{group_id}"
        for pitch, (dur_ql, source) in members:
            if readable and dur_ql <= longest_simple:
                snapped = min(READABLE_DURATIONS_QL, key=lambda v: abs(v - dur_ql))
            else:
                # Longer than a semibreve (or Precise mode): keep the
                # grid-rounded length and let the engraver tie it.
                snapped = dur_ql
            if room is not None:
                snapped = min(snapped, room)
            snapped = max(grid_ql, snapped)
            cleaned = _make_note(pitch, start_ql * spq, snapped * spq, source["confidence"])
            if source.get("velocity") is not None:
                cleaned["velocity"] = source["velocity"]
            if group_label:
                cleaned["group"] = group_label
            result.append(cleaned)
    return result


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
