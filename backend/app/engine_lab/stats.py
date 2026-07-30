"""Comparable stats across engines, computed from raw note output.

Deliberately independent of any "group" field a given engine may or may
not set — clustering is redone here from start times alone so every
engine (including ones that only ever emit single notes) is measured the
same way.
"""

from __future__ import annotations

from typing import Any

import pretty_midi

# Notes starting within this window count as "together" for stats purposes
# (matches polyphonic.py's own GROUP_WINDOW_S).
CLUSTER_WINDOW_S = 0.04


def compute_stats(notes: list[dict[str, Any]]) -> dict[str, Any]:
    if not notes:
        return {
            "note_count": 0,
            "overlapping_notes": 0,
            "chord_groups": 0,
            "pitch_min": None,
            "pitch_max": None,
            "pitch_range_label": None,
        }

    ordered = sorted(notes, key=lambda n: (n["start_time"], n["pitch"]))
    overlapping = 0
    chord_groups = 0
    index = 0
    while index < len(ordered):
        cluster_start = ordered[index]["start_time"]
        cluster_size = 1
        index += 1
        while (
            index < len(ordered)
            and ordered[index]["start_time"] - cluster_start <= CLUSTER_WINDOW_S
        ):
            cluster_size += 1
            index += 1
        if cluster_size > 1:
            chord_groups += 1
            overlapping += cluster_size

    pitches = [int(n["pitch"]) for n in notes]
    pitch_min, pitch_max = min(pitches), max(pitches)
    return {
        "note_count": len(notes),
        "overlapping_notes": overlapping,
        "chord_groups": chord_groups,
        "pitch_min": pitch_min,
        "pitch_max": pitch_max,
        "pitch_range_label": (
            f"{pretty_midi.note_number_to_name(pitch_min)}"
            f"–{pretty_midi.note_number_to_name(pitch_max)}"
        ),
    }
