"""Rough accuracy scoring: detected notes vs a fixture's known expected notes.

Deliberately simple (the owner asked not to overcomplicate this): exact
pitch match required, greedy nearest-start matching within a tolerance
window. Good enough to rank engines on clean synthetic audio; not a
substitute for judgment on real recordings.
"""

from __future__ import annotations

from typing import Any

START_TOLERANCE_S = 0.2


def _clusters(notes: list[dict[str, Any]], window_s: float = 0.04) -> list[list[int]]:
    """Group note INDEXES whose start times fall within window_s of the
    cluster's first member (mirrors polyphonic.py's own grouping window)."""
    ordered = sorted(range(len(notes)), key=lambda i: notes[i]["start_time"])
    clusters: list[list[int]] = []
    i = 0
    while i < len(ordered):
        start = notes[ordered[i]]["start_time"]
        cluster = [ordered[i]]
        i += 1
        while i < len(ordered) and notes[ordered[i]]["start_time"] - start <= window_s:
            cluster.append(ordered[i])
            i += 1
        clusters.append(cluster)
    return clusters


def score_against_expected(
    expected_notes: list[dict[str, Any]], detected_notes: list[dict[str, Any]]
) -> dict[str, Any]:
    used_detected: set[int] = set()
    matches: list[tuple[int, int]] = []  # (expected_index, detected_index)

    for e_index, expected in enumerate(expected_notes):
        best_index = None
        best_gap = None
        for d_index, detected in enumerate(detected_notes):
            if d_index in used_detected:
                continue
            if int(detected["pitch"]) != int(expected["pitch"]):
                continue
            gap = abs(detected["start_time"] - expected["start_time"])
            if gap > START_TOLERANCE_S:
                continue
            if best_gap is None or gap < best_gap:
                best_gap = gap
                best_index = d_index
        if best_index is not None:
            used_detected.add(best_index)
            matches.append((e_index, best_index))

    correct = len(matches)
    missed = len(expected_notes) - correct
    extra = len(detected_notes) - correct

    timing_errors = [
        abs(detected_notes[d]["start_time"] - expected_notes[e]["start_time"])
        for e, d in matches
    ]
    mean_timing_error = round(sum(timing_errors) / len(timing_errors), 4) if timing_errors else None

    # Simultaneity check: for every expected cluster of 2+ notes, were ALL of
    # its members matched to detected notes that ALSO cluster together?
    expected_clusters = [c for c in _clusters(expected_notes) if len(c) > 1]
    matched_expected = {e for e, _ in matches}
    match_map = dict(matches)
    detected_clusters = _clusters(detected_notes)
    detected_cluster_of = {}
    for cluster in detected_clusters:
        for idx in cluster:
            detected_cluster_of[idx] = frozenset(cluster)

    simultaneous_ok = True
    if expected_clusters:
        for cluster in expected_clusters:
            if not all(e in matched_expected for e in cluster):
                simultaneous_ok = False
                break
            detected_members = {match_map[e] for e in cluster}
            groups_hit = {detected_cluster_of.get(d) for d in detected_members}
            if len(groups_hit) != 1 or None in groups_hit:
                simultaneous_ok = False
                break
    else:
        simultaneous_ok = None  # nothing to check (no simultaneous expected notes)

    total_expected = len(expected_notes) or 1
    rough_score = round(100 * correct / total_expected - 10 * (extra / max(1, len(detected_notes) or 1)), 1)
    rough_score = max(0.0, min(100.0, rough_score))

    return {
        "expected_count": len(expected_notes),
        "detected_count": len(detected_notes),
        "correct_matches": correct,
        "missed_notes": missed,
        "extra_notes": extra,
        "simultaneous_notes_preserved": simultaneous_ok,
        "mean_timing_error_s": mean_timing_error,
        "rough_score_percent": rough_score,
    }
