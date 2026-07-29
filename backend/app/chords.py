"""Manual chord markers and the simple chord-chart / suggestion helpers.

Chord markers are stored inside the project's transcription.json under a
"chords" key: [{"name": "Am", "start_time": 2.0}, ...], kept sorted by time.
They are deliberately independent of the melody notes — editing or deleting
notes never touches them (only "Reset chords" or a fresh upload does).

Everything here assumes the app's fixed 120 BPM in 4/4, so one bar is
exactly 2 seconds — the same grid the sheet music and tab already use.

Chord SUGGESTION is intentionally rough and honest about it: it estimates a
key from the melody (music21), then per bar picks the diatonic triad that
best covers the melody notes sounding in that bar. It is a starting point
for the user to edit, not real chord detection from the recording.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

SECONDS_PER_BAR = 2.0  # one 4/4 bar at the fixed 120 BPM
MAX_CHORD_NAME_LEN = 12

# C, Am, F#m7, Bb, G7, Cmaj7, Dm7b5, Esus4, Cadd9, G/B, ...
_CHORD_NAME_RE = re.compile(
    r"^[A-G][#b]?[A-Za-z0-9°ø+#b]*(/[A-G][#b]?)?$"
)

CHORD_NAME_HELP = (
    "Chord names must start with a letter A–G, like C, Am, F#m7, Bb or G/B "
    f"(up to {MAX_CHORD_NAME_LEN} characters)."
)


def is_valid_chord_name(name: str) -> bool:
    return (
        0 < len(name) <= MAX_CHORD_NAME_LEN
        and _CHORD_NAME_RE.match(name) is not None
    )


def bar_number(start_time: float) -> int:
    """1-based bar number for a time, on the fixed 120 BPM 4/4 grid."""
    return int(math.floor(max(0.0, start_time) / SECONDS_PER_BAR)) + 1


def m21_chord_figure(name: str) -> str:
    """User chord name -> music21 figure ("Bbm7" -> "B-m7", "G/Bb" -> "G/B-").

    music21 spells flats with '-', not 'b'; only the root (and slash bass)
    letter's flat needs converting — 'b' elsewhere (e.g. Dm7b5) stays.
    """

    def fix(part: str) -> str:
        if len(part) >= 2 and part[1] == "b":
            return part[0] + "-" + part[2:]
        return part

    if "/" in name:
        main, _, bass = name.partition("/")
        return fix(main) + "/" + fix(bass)
    return fix(name)


def chord_chart_text(
    project_name: str, chords: list[dict[str, Any]], melody_end: float
) -> str:
    """Plain-text chord chart: a bar grid plus a timing list."""
    chords = sorted(chords, key=lambda c: c["start_time"])
    last_bar = bar_number(chords[-1]["start_time"]) if chords else 1
    if melody_end > 0:
        last_bar = max(last_bar, bar_number(max(0.0, melody_end - 1e-9)))

    by_bar: dict[int, list[str]] = {}
    for c in chords:
        by_bar.setdefault(bar_number(c["start_time"]), []).append(c["name"])

    cells = [" ".join(by_bar.get(bar, [])) or " " for bar in range(1, last_bar + 1)]
    grid = "| " + " | ".join(cells) + " |"

    lines = [
        f"{project_name} — Chord chart",
        "Tempo: 120 bpm, 4/4 time (one bar = 2 seconds)",
        "Made with BandChart AI. Chords are the user's own markers.",
        "",
        grid,
        "",
    ]
    for c in chords:
        lines.append(f"{c['start_time']:.1f}s (bar {bar_number(c['start_time'])}): {c['name']}")
    return "\n".join(lines) + "\n"


_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def suggest_chords(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rough per-bar diatonic chord suggestions from the melody notes.

    Estimate the key, then for each 2-second bar pick the key's triad
    (I ii iii IV V vi, or their minor-key equivalents) that best covers the
    melody, weighting by how long each pitch sounds in the bar and favouring
    the chord root. Consecutive repeats are merged. Rough by design.
    """
    if not notes:
        return []

    tonic_pc = 0
    mode = "major"
    flats = False
    try:
        from music21 import note as m21_note, stream

        s = stream.Stream()
        for n in notes:
            m = m21_note.Note(int(n["pitch"]))
            m.quarterLength = max(0.25, float(n["duration"]) / 0.5)
            s.insert(float(n["start_time"]) / 0.5, m)
        analyzed = s.analyze("key")
        tonic_pc = analyzed.tonic.pitchClass
        mode = analyzed.mode
        flats = analyzed.sharps < 0
    except Exception:
        pass  # fall back to C major — still a usable rough starting point

    names = _FLAT_NAMES if flats else _SHARP_NAMES
    if mode == "minor":
        # i, III, iv, v, VI, VII
        degrees = [(0, "m"), (3, ""), (5, "m"), (7, "m"), (8, ""), (10, "")]
    else:
        # I, ii, iii, IV, V, vi
        degrees = [(0, ""), (2, "m"), (4, "m"), (5, ""), (7, ""), (9, "m")]

    triads: list[tuple[str, set[int], int]] = []
    for offset, quality in degrees:
        root = (tonic_pc + offset) % 12
        third = (root + (3 if quality == "m" else 4)) % 12
        fifth = (root + 7) % 12
        triads.append((names[root] + quality, {root, third, fifth}, root))

    melody_end = max(float(n["start_time"]) + float(n["duration"]) for n in notes)
    suggestions: list[dict[str, Any]] = []
    for bar_index in range(int(math.floor((melody_end - 1e-9) / SECONDS_PER_BAR)) + 1):
        t0 = bar_index * SECONDS_PER_BAR
        t1 = t0 + SECONDS_PER_BAR
        weights: dict[int, float] = {}
        for n in notes:
            overlap = min(float(n["start_time"]) + float(n["duration"]), t1) - max(
                float(n["start_time"]), t0
            )
            if overlap > 1e-6:
                pc = int(n["pitch"]) % 12
                weights[pc] = weights.get(pc, 0.0) + overlap
        if not weights:
            continue

        best_name: Optional[str] = None
        best_score = 0.0
        for name, pcs, root in triads:
            score = sum(w for pc, w in weights.items() if pc in pcs)
            score += 0.25 * weights.get(root, 0.0)  # favour the root note
            if score > best_score:
                best_score = score
                best_name = name
        if best_name is None:
            continue
        if suggestions and suggestions[-1]["name"] == best_name:
            continue  # merge repeats: one marker until the chord changes
        suggestions.append({"name": best_name, "start_time": round(t0, 3)})
    return suggestions
