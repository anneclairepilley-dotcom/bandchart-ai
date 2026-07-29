"""Turns the detected melody into simple text tablature for fretted instruments.

The transcription stores sounding (concert) pitches. Each note is placed on
one string of the selected instrument as a fret number, preferring low frets
(0-12) for readability. If the melody as a whole sits outside the instrument's
range (common for bass), it is shifted by whole octaves to fit — the shift is
reported as a warning so the player knows. Individual notes that still don't
fit are marked with "x" and listed in the warnings instead of crashing.

Output is deliberately plain v0.7 text tab (no rhythm stems, no engraving):
one column per note in time order, a bar line whenever a note starts in a new
4/4 measure at the app's fixed 120 BPM, systems wrapped to a readable width.
The same layout is returned both as plain text (for the .txt download) and as
per-line cells tagged with note indexes (so the web preview can highlight the
note being played).
"""

from __future__ import annotations

from typing import Any, Optional

MAX_FRET = 15  # highest fret we'll ask anyone to play
PREFERRED_MAX_FRET = 12  # frets 0-12 preferred, per the tab rules
OCTAVE_OFFSETS = (0, -12, 12, -24, 24)  # tried in order; first best wins
SECONDS_PER_MEASURE = 2.0  # one 4/4 bar at the fixed 120 BPM
MAX_SYSTEM_WIDTH = 56  # tab columns per line, excluding the "e|" prefix

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

    # Tab stays melody-first (v0.9.2): when several notes share the same
    # start time (polyphonic transcriptions), only the highest — the
    # melody note — goes on the tab. Original indexes are kept so the
    # play-along highlight still lines up with the full note list.
    keep_indexes: set[int] = set()
    dropped_chord_members = 0
    i = 0
    while i < len(notes):
        j = i
        best = i
        while (
            j < len(notes)
            and abs(notes[j]["start_time"] - notes[i]["start_time"]) < 1e-6
        ):
            if notes[j]["pitch"] > notes[best]["pitch"]:
                best = j
            j += 1
        keep_indexes.add(best)
        dropped_chord_members += (j - i) - 1
        i = j

    pitches = [int(n["pitch"]) for idx, n in enumerate(notes) if idx in keep_indexes]
    offset = _best_octave_offset(pitches, strings) if pitches else 0

    # Display order puts high strings first, but reentrant tunings (ukulele's
    # high G) mean the extremes must be found by pitch, not position.
    lowest_line = min(range(len(strings)), key=lambda i: strings[i]["midi"])
    highest_line = max(range(len(strings)), key=lambda i: strings[i]["midi"])

    entries: list[dict[str, Any]] = []
    unplayable: list[str] = []
    for index, note in enumerate(notes):
        if index not in keep_indexes:
            continue  # chord member below the melody note — not on the tab
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

    warnings: list[str] = []
    if dropped_chord_members > 0:
        warnings.append(
            "Chords were detected in the transcription — the tab shows the "
            "top (melody) note of each chord for now."
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

    header_lines = [
        f"{project_name} — {label} tab",
        f"Tuning: {spec['tuning']}",
        "Made with BandChart AI from the detected melody (one note at a time).",
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
    is a list of cells {"t": text, "i": note index or None}. Every cell of a
    note's column carries the note index so the preview can highlight the
    whole column while that note plays.
    """
    # One column per note, plus a 1-char bar column at each measure change.
    columns: list[dict[str, Any]] = []
    prev_measure: Optional[int] = None
    for entry in entries:
        measure = int(entry["start_time"] // seconds_per_bar)
        if prev_measure is not None and measure != prev_measure:
            columns.append({"bar": True, "width": 1})
        prev_measure = measure
        token = "x" if entry["out_of_range"] else str(entry["fret"])
        columns.append(
            {
                "bar": False,
                "token": token,
                "line": entry["string"],
                "note_index": entry["note_index"],
                # Three leading dashes per column (v0.8): breathing room makes
                # the fret numbers much easier to read.
                "width": 3 + len(token),
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
                elif col["line"] == line_index:
                    cells.append({"t": "---" + col["token"], "i": col["note_index"]})
                else:
                    cells.append({"t": "-" * col["width"], "i": col["note_index"]})
            cells.append({"t": "-|", "i": None})
            lines.append(cells)
        systems.append(lines)
    return systems
