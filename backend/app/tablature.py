"""Turns the detected melody into simple text tablature for fretted instruments.

The transcription stores sounding (concert) pitches. Each note is placed on
one string of the selected instrument as a fret number, preferring low frets
(0-12) for readability. If the melody as a whole sits outside the instrument's
range (common for bass), it is shifted by whole octaves to fit — the shift is
reported as a warning so the player knows. Individual notes that still don't
fit are marked with "x" and listed in the warnings instead of crashing.

Output is deliberately plain v0.7 text tab (no rhythm stems, no engraving):
one column per note (or per CHORD — see below) in time order, a bar line
whenever a note starts in a new 4/4 measure at the app's fixed 120 BPM,
systems wrapped to a readable width. The same layout is returned both as
plain text (for the .txt download) and as per-line cells tagged with note
indexes (so the web preview can highlight the note being played).

v0.9.8: Guitar can genuinely play more than one note at once, so its tab now
ATTEMPTS a playable multi-note chord for simultaneous-note clusters (see
_try_chord_assignment) instead of always keeping only the top note — Bass and
Ukulele stay on the original melody-first single-note-per-cluster behaviour
unchanged (a bassline is one note at a time; ukulele isn't part of this
version's scope).
"""

from __future__ import annotations

import itertools
from typing import Any, Optional

MAX_FRET = 15  # highest fret we'll ask anyone to play
PREFERRED_MAX_FRET = 12  # frets 0-12 preferred, per the tab rules
OCTAVE_OFFSETS = (0, -12, 12, -24, 24)  # tried in order; first best wins
SECONDS_PER_MEASURE = 2.0  # one 4/4 bar at the fixed 120 BPM
MAX_SYSTEM_WIDTH = 56  # tab columns per line, excluding the "e|" prefix
# Notes starting within this window count as "together" for chord/cluster
# purposes (v0.9.3: Basic Pitch spreads chord members over a few ms, so
# exact equality isn't enough).
CHORD_WINDOW_S = 0.04
# v0.9.8 (guitar only): a playable fretting keeps its non-open frets within
# this many frets of each other — open strings (fret 0) are free, matching
# how a guitarist actually uses them regardless of hand position.
MAX_HAND_SPAN = 4

# Strings are listed in display order: top tab line first (the convention is
# highest-pitched string on top). "midi" is the open string's sounding pitch.
TUNINGS: dict[str, dict[str, Any]] = {
    "guitar": {
        "label": "Guitar",
        "tuning": "E2 A2 D3 G3 B3 E4 (standard)",
        "strings": [
            {"name": "e", "midi": 64},
            {"name": "B", "midi": 59},
            {"name": "G", "midi": 55},
            {"name": "D", "midi": 50},
            {"name": "A", "midi": 45},
            {"name": "E", "midi": 40},
        ],
    },
    "bass": {
        "label": "Bass",
        "tuning": "E1 A1 D2 G2 (standard)",
        "strings": [
            {"name": "G", "midi": 43},
            {"name": "D", "midi": 38},
            {"name": "A", "midi": 33},
            {"name": "E", "midi": 28},
        ],
    },
    "ukulele": {
        "label": "Ukulele",
        "tuning": "G4 C4 E4 A4 (standard, high G)",
        "strings": [
            {"name": "A", "midi": 69},
            {"name": "E", "midi": 64},
            {"name": "C", "midi": 60},
            {"name": "G", "midi": 67},
        ],
    },
}


class TabError(ValueError):
    """A tab request that can't be fulfilled (bad instrument, no notes)."""


def _fret_for(midi: int, strings: list[dict[str, Any]]) -> Optional[tuple[int, int]]:
    """Lowest playable (string_index, fret) for a sounding pitch, or None."""
    best: Optional[tuple[int, int]] = None
    for idx, string in enumerate(strings):
        fret = midi - string["midi"]
        if 0 <= fret <= MAX_FRET and (best is None or fret < best[1]):
            best = (idx, fret)
    return best


def _best_octave_offset(pitches: list[int], strings: list[dict[str, Any]]) -> int:
    """Whole-octave shift that fits the most notes (then the most low frets)."""
    best_score: Optional[tuple[int, int, int]] = None
    best_offset = 0
    for offset in OCTAVE_OFFSETS:
        in_range = 0
        low_frets = 0
        for pitch in pitches:
            hit = _fret_for(pitch + offset, strings)
            if hit is not None:
                in_range += 1
                if hit[1] <= PREFERRED_MAX_FRET:
                    low_frets += 1
        score = (in_range, low_frets, -abs(offset))
        if best_score is None or score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


def _try_chord_assignment(
    pitches: list[int], strings: list[dict[str, Any]]
) -> Optional[list[tuple[int, int]]]:
    """Try to place every pitch on its own string within a playable hand span.

    Returns a list of (string_index, fret) IN THE SAME ORDER as `pitches`
    (parallel arrays — not keyed by pitch value, so two notes that happen
    to share a pitch after octave-fitting never collide), or None if no
    complete assignment exists — the caller then drops the least useful
    note and tries again with one fewer pitch (see build_tab). Small search
    (at most a handful of pitches on 6 strings), so brute-force permutations
    are cheap and exact.
    """
    if not pitches or len(pitches) > len(strings):
        return None
    best: Optional[list[tuple[int, int]]] = None
    best_score: Optional[tuple[int, int, int]] = None
    for string_combo in itertools.permutations(range(len(strings)), len(pitches)):
        placement: list[tuple[int, int]] = []
        frets: list[int] = []
        ok = True
        for pitch, string_index in zip(pitches, string_combo):
            fret = pitch - strings[string_index]["midi"]
            if fret < 0 or fret > MAX_FRET:
                ok = False
                break
            placement.append((string_index, fret))
            frets.append(fret)
        if not ok:
            continue
        fretted = [f for f in frets if f > 0]  # open strings don't cost hand span
        span = (max(fretted) - min(fretted)) if fretted else 0
        if span > MAX_HAND_SPAN:
            continue
        over_preferred = sum(1 for f in frets if f > PREFERRED_MAX_FRET)
        score = (over_preferred, span, sum(frets))
        if best_score is None or score < best_score:
            best_score = score
            best = placement
    return best


def build_tab(
    notes: list[dict[str, Any]],
    instrument_key: str,
    project_name: str,
    seconds_per_bar: float = SECONDS_PER_MEASURE,
) -> dict[str, Any]:
    """Build the full tab: entries, warnings, preview cells and download text."""
    if instrument_key not in TUNINGS:
        raise TabError(
            "Tab is only available for guitar, bass and ukulele — "
            f"'{instrument_key}' uses regular sheet music instead."
        )
    spec = TUNINGS[instrument_key]
    strings = spec["strings"]
    label = spec["label"]
    # v0.9.8: Guitar attempts real multi-note chords; Bass/Ukulele stay
    # melody-first (one note at a time) exactly as before.
    multi_note = instrument_key == "guitar"

    # Cluster note INDEXES that start together (within CHORD_WINDOW_S) —
    # original indexes are kept throughout so the play-along highlight
    # always lines up with the real note list.
    clusters: list[list[int]] = []
    i = 0
    while i < len(notes):
        j = i
        while (
            j + 1 < len(notes)
            and notes[j + 1]["start_time"] - notes[i]["start_time"] <= CHORD_WINDOW_S
        ):
            j += 1
        clusters.append(list(range(i, j + 1)))
        i = j + 1

    if multi_note:
        # The octave-fit should account for every note a chord actually
        # contains, not just its top (melody) note.
        pitches = [int(notes[idx]["pitch"]) for cluster in clusters for idx in cluster]
    else:
        pitches = [
            int(notes[max(cluster, key=lambda idx: notes[idx]["pitch"])]["pitch"])
            for cluster in clusters
        ]
    offset = _best_octave_offset(pitches, strings) if pitches else 0

    # Display order puts high strings first, but reentrant tunings (ukulele's
    # high G) mean the extremes must be found by pitch, not position.
    lowest_line = min(range(len(strings)), key=lambda i: strings[i]["midi"])
    highest_line = max(range(len(strings)), key=lambda i: strings[i]["midi"])

    entries: list[dict[str, Any]] = []
    unplayable: list[str] = []
    dropped_chord_members = 0  # bass/ukulele: chord members collapsed to the melody note
    simplified_chords = 0  # guitar: notes dropped because the full chord wasn't playable

    def emit_single(index: int) -> None:
        note = notes[index]
        shifted = int(note["pitch"]) + offset
        hit = _fret_for(shifted, strings)
        if hit is None:
            too_low = shifted < strings[lowest_line]["midi"]
            entries.append(
                {
                    "note_index": index,
                    "pitch_name": note["pitch_name"],
                    "start_time": note["start_time"],
                    "string": lowest_line if too_low else highest_line,
                    "fret": None,
                    "out_of_range": True,
                }
            )
            if len(unplayable) < 4:
                unplayable.append(
                    f"{note['pitch_name']} at {note['start_time']:.1f}s "
                    f"({'too low' if too_low else 'too high'})"
                )
        else:
            string_index, fret = hit
            entries.append(
                {
                    "note_index": index,
                    "pitch_name": note["pitch_name"],
                    "start_time": note["start_time"],
                    "string": string_index,
                    "fret": fret,
                    "out_of_range": False,
                }
            )

    for cluster in clusters:
        if not multi_note:
            best_idx = max(cluster, key=lambda idx: notes[idx]["pitch"])
            dropped_chord_members += len(cluster) - 1
            emit_single(best_idx)
            continue

        # Guitar: try to place the WHOLE cluster as a chord (each note on
        # its own string, playable hand span). If that's not possible,
        # drop the least-confident note and try a smaller chord, down to
        # a single note — which still gets the normal single-note/out-of-
        # range handling, never silently vanishes without a warning.
        remaining = list(cluster)
        placement: Optional[list[tuple[int, int]]] = None
        while len(remaining) > 1:
            shifted_pitches = [int(notes[idx]["pitch"]) + offset for idx in remaining]
            placement = _try_chord_assignment(shifted_pitches, strings)
            if placement is not None:
                break
            weakest = min(remaining, key=lambda idx: notes[idx].get("confidence", 0.0))
            remaining.remove(weakest)
            simplified_chords += 1

        if placement is not None and len(remaining) > 1:
            for idx, (string_index, fret) in zip(remaining, placement):
                note = notes[idx]
                entries.append(
                    {
                        "note_index": idx,
                        "pitch_name": note["pitch_name"],
                        "start_time": note["start_time"],
                        "string": string_index,
                        "fret": fret,
                        "out_of_range": False,
                    }
                )
        else:
            emit_single(remaining[0])

    warnings: list[str] = []
    if dropped_chord_members > 0:
        warnings.append(
            "Chords were detected in the transcription — the tab shows the "
            "top (melody) note of each chord for now."
        )
    if simplified_chords > 0:
        warnings.append(
            "Some guitar notes were simplified because the detected chord "
            "was not playable."
        )
    if entries and offset != 0:
        octaves = abs(offset) // 12
        direction = "down" if offset < 0 else "up"
        warnings.append(
            f"To fit the {label}'s range, the whole melody is shifted "
            f"{direction} {octaves} octave{'s' if octaves > 1 else ''} in this tab."
        )
    out_count = sum(1 for e in entries if e["out_of_range"])
    if out_count:
        details = ", ".join(unplayable)
        if out_count > len(unplayable):
            details += ", …"
        warnings.append(
            f"{out_count} note{'s' if out_count > 1 else ''} can't be played on the "
            f"{label} in standard tuning — marked x in the tab ({details})."
        )

    systems = _layout_systems(entries, strings, seconds_per_bar)

    made_with_line = (
        "Made with BandChart AI from the detected notes — multi-note chords "
        "are attempted where playable."
        if multi_note
        else "Made with BandChart AI from the detected melody (one note at a time)."
    )
    header_lines = [
        f"{project_name} — {label} tab",
        f"Tuning: {spec['tuning']}",
        made_with_line,
    ]
    header_lines += [f"Note: {w}" for w in warnings]
    if not entries:
        body = "No notes to show — the note list is empty."
    else:
        body = "\n\n".join(
            "\n".join("".join(cell["t"] for cell in line) for line in system)
            for system in systems
        )
    text = "\n".join(header_lines) + "\n\n" + body + "\n"

    return {
        "instrument": instrument_key,
        "label": label,
        "tuning": spec["tuning"],
        "string_names": [s["name"] for s in strings],
        "octave_offset": offset,
        "note_count": len(notes),
        "entries": entries,
        "warnings": warnings,
        "systems": systems,
        "text": text,
    }


def _layout_systems(
    entries: list[dict[str, Any]],
    strings: list[dict[str, Any]],
    seconds_per_bar: float = SECONDS_PER_MEASURE,
) -> list[list[list[dict[str, Any]]]]:
    """Lay entries out as wrapped tab systems.

    Each system is a list of lines (one per string, display order); each line
    is a list of cells {"t": text, "i": note index or None}. v0.9.8: entries
    that start together (a guitar chord, several strings at once) share ONE
    column instead of each becoming its own — this used to be impossible
    since tab was always one note at a time, but a chord is one musical
    event and must read as one column, not several columns in a row.
    """
    # Group entries into columns: entries within CHORD_WINDOW_S of each
    # other share one column, one string per line that has a note in it.
    # For a single-note-per-cluster tab (bass/ukulele, or a guitar melody
    # line) this produces exactly one entry per column, same as before.
    ordered = sorted(entries, key=lambda e: e["start_time"])
    time_groups: list[list[dict[str, Any]]] = []
    for entry in ordered:
        if time_groups and entry["start_time"] - time_groups[-1][0]["start_time"] <= CHORD_WINDOW_S:
            time_groups[-1].append(entry)
        else:
            time_groups.append([entry])

    columns: list[dict[str, Any]] = []
    prev_measure: Optional[int] = None
    for group in time_groups:
        measure = int(group[0]["start_time"] // seconds_per_bar)
        if prev_measure is not None and measure != prev_measure:
            columns.append({"bar": True, "width": 1})
        prev_measure = measure
        by_line: dict[int, tuple[str, int]] = {}
        max_token_len = 1
        for entry in group:
            token = "x" if entry["out_of_range"] else str(entry["fret"])
            by_line[entry["string"]] = (token, entry["note_index"])
            max_token_len = max(max_token_len, len(token))
        columns.append(
            {
                "bar": False,
                "by_line": by_line,
                # The whole column highlights together while ANY of its
                # notes play — dash-filled (inactive-string) cells fall
                # back to the first note in time order.
                "primary_index": group[0]["note_index"],
                # Three leading dashes per column (v0.8): breathing room makes
                # the fret numbers much easier to read.
                "width": 3 + max_token_len,
            }
        )

    # Wrap into systems of at most MAX_SYSTEM_WIDTH characters of columns.
    grouped: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    width = 0
    for col in columns:
        if current and width + col["width"] > MAX_SYSTEM_WIDTH:
            grouped.append(current)
            current = []
            width = 0
        if not current and col["bar"]:
            continue  # never start a line with a dangling bar
        current.append(col)
        width += col["width"]
    if current:
        grouped.append(current)

    systems: list[list[list[dict[str, Any]]]] = []
    for group in grouped:
        lines: list[list[dict[str, Any]]] = []
        for line_index, string in enumerate(strings):
            cells: list[dict[str, Any]] = [{"t": f"{string['name']}|", "i": None}]
            for col in group:
                if col["bar"]:
                    cells.append({"t": "|", "i": None})
                elif line_index in col["by_line"]:
                    token, note_index = col["by_line"][line_index]
                    cells.append({"t": "-" * (col["width"] - len(token)) + token, "i": note_index})
                else:
                    cells.append({"t": "-" * col["width"], "i": col["primary_index"]})
            cells.append({"t": "-|", "i": None})
            lines.append(cells)
        systems.append(lines)
    return systems
