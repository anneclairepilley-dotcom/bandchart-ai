"""Fit detected notes into an instrument's playable range (v0.9.8).

"Fit to instrument range" is the last Solo Arrangement pipeline step: some
notes come back higher or lower than the chosen instrument can actually
play (e.g. a vocal melody transcribed an octave above a bass's range).
Rather than clamp every note independently — which would mangle the tune's
shape with random-looking jumps — notes are grouped into PHRASES (runs
separated by a silence gap) and each phrase is shifted by ONE whole-octave
amount, chosen by majority vote among the notes that actually need it.
Whole octaves only: this keeps the melody in the same key, unlike an
arbitrary semitone transposition (never done here, and not something a
user can ask this module for — it only fixes range, it doesn't transpose
keys). Only a genuine straggler that's still out of range after its
phrase's shift gets clamped individually, with a warning either way.
"""

from __future__ import annotations

import pretty_midi

# A silence at least this long starts a new phrase — shifts are decided
# per phrase, never per individual note, so a melody doesn't jump around.
PHRASE_GAP_S = 1.0
# However many octaves out of range a note is, try shifts up to this many
# octaves before giving up and clamping to the nearest range boundary.
MAX_OCTAVE_SHIFT = 6


def _best_octave_shift(pitch: int, low: int, high: int) -> int | None:
    """Smallest-magnitude whole-octave shift bringing pitch into [low, high].

    None if no whole-octave shift within MAX_OCTAVE_SHIFT works (pitch is
    absurdly far from the instrument's range).
    """
    if low <= pitch <= high:
        return 0
    for octaves in range(1, MAX_OCTAVE_SHIFT + 1):
        for sign in (1, -1):
            if low <= pitch + 12 * octaves * sign <= high:
                return octaves * sign
    return None


def _group_phrases(notes: list[dict]) -> list[list[dict]]:
    ordered = sorted(notes, key=lambda n: n["start_time"])
    phrases: list[list[dict]] = []
    current: list[dict] = []
    last_end = None
    for note in ordered:
        if current and note["start_time"] - last_end > PHRASE_GAP_S:
            phrases.append(current)
            current = []
        current.append(note)
        last_end = max(last_end or 0.0, note["start_time"] + note["duration"])
    if current:
        phrases.append(current)
    return phrases


def fit_notes_to_range(
    notes: list[dict], low: int, high: int, instrument_label: str
) -> tuple[list[dict], list[str], str]:
    """Octave-shift notes (by phrase, not individually) to fit [low, high].

    Returns (notes, warnings, status) — status is one of "none" (nothing
    needed fixing), "octave_shifted" (whole phrases moved cleanly by an
    octave), or "simplified" (at least one straggler note needed an
    individual clamp beyond its phrase's shift) — the exact vocabulary the
    UI's "Range fitting" status line uses, so the caller never has to
    re-derive it from the warning text.
    """
    if not notes or low > high:
        return notes, [], "none"

    changed = False
    clamped = False
    result: list[dict] = []
    for phrase in _group_phrases(notes):
        # Which whole-octave shift would each out-of-range note need? The
        # phrase moves by whichever shift most of its out-of-range notes
        # agree on — a genuinely mixed-register phrase (rare) just keeps
        # the majority in range and lets the individual-clamp step below
        # catch the rest, rather than picking an arbitrary tie-break.
        votes: dict[int, int] = {}
        for note in phrase:
            if not (low <= note["pitch"] <= high):
                shift = _best_octave_shift(note["pitch"], low, high)
                if shift is not None:
                    votes[shift] = votes.get(shift, 0) + 1
        phrase_shift = 0
        if votes:
            winner = max(votes, key=lambda k: votes[k])
            # Only move the WHOLE phrase if that shift is actually what
            # most of it needs — an isolated outlier in an otherwise
            # in-range phrase must not drag every other note along with it
            # ("mostly out of range", not "one note out of range").
            if votes[winner] >= len(phrase) / 2:
                phrase_shift = winner
        if phrase_shift:
            changed = True

        for note in phrase:
            new_pitch = note["pitch"] + 12 * phrase_shift
            if not (low <= new_pitch <= high):
                # A straggler even after the phrase's shift — nudge just
                # this one note the rest of the way, or clamp to the
                # nearest edge of the range as a last resort.
                extra = _best_octave_shift(new_pitch, low, high)
                if extra is not None:
                    new_pitch += 12 * extra
                else:
                    new_pitch = min(max(new_pitch, low), high)
                clamped = True
            if new_pitch != note["pitch"]:
                note = dict(note)
                note["pitch"] = new_pitch
                note["pitch_name"] = pretty_midi.note_number_to_name(new_pitch)
            result.append(note)

    result.sort(key=lambda n: (n["start_time"], n["pitch"]))
    warnings: list[str] = []
    if changed or clamped:
        warnings.append(f"Some notes were octave-shifted to fit {instrument_label}.")
    status = "simplified" if clamped else ("octave_shifted" if changed else "none")
    return result, warnings, status
