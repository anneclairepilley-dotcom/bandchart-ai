"""Smart transcription routing (v0.9.5).

Decides, from the user's instrument/mode/note-detection choices, how the
polyphonic detector should behave for THIS project — and returns that
decision as plain data, so run_transcription can act on it and the result
can report exactly what happened. This module never runs detection itself.

Engine choice within "poly" mode (Basic Pitch first, built-in CQT fallback,
melody-only as the last resort) is unchanged and still lives in
app/polyphonic.py / app/transcription.py — routing only decides the
simultaneous-note cap and any instrument-specific caution note.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.instrument_profiles import PROFILES
from app.polyphonic import MAX_POLYPHONY

# v0.9.8: the simultaneous-note cap per instrument now comes straight from
# the central instrument profile table (piano=6, guitar=4, violin=2,
# bass/alto_sax/trumpet/voice=1 — melody-only instruments capped at 1 so
# even a manually-forced "poly" request degrades to monophonic output
# instead of producing nonsense chords on a melody instrument). Instruments
# with no profile (concert, flute, tenor_sax, clarinet, ukulele — hidden
# from the main picker but still backend-supported) fall back to the
# original global default via resolve_routing's .get(instrument, ...).
INSTRUMENT_MAX_POLYPHONY: dict[str, int] = {
    key: profile.max_simultaneous_notes for key, profile in PROFILES.items()
}

# Instruments where "Direct transcription" defaults straight to polyphonic
# detection without the user having to ask for it (a genuinely chordal
# instrument with an obvious grand-staff home).
DIRECT_AUTO_POLY_INSTRUMENTS = {"piano"}
# Instruments where "Solo arrangement" ALSO defaults to polyphonic
# detection: piano (v0.9.5, keeps its chords) and guitar (v0.9.8 — Solo
# Arrangement now attempts real playable multi-note TAB, so multiple-note
# detection is worth defaulting to instead of melody-only).
SOLO_AUTO_POLY_INSTRUMENTS = {"piano", "guitar"}

INSTRUMENT_POLY_NOTES: dict[str, str] = {
    # v0.9.8: guitar TAB now genuinely attempts a playable multi-note
    # voicing (backend/app/tablature.py) rather than always collapsing to
    # the top note — this caution reflects that it's still a best-effort,
    # not full chord-shape TAB.
    "guitar": (
        "Guitar TAB attempts a playable multi-note chord where it can. "
        "Some notes may be simplified if the detected chord isn't playable."
    ),
    "violin": "Violin output is limited to melody and simple double-stops for now.",
}

# v0.9.6: instruments with a specialist engine that's tried BEFORE the
# general polyphonic detector, when that engine is actually available.
# Piano Expert (ByteDance) is piano-specific; nothing else qualifies.
SPECIALIST_ENGINE_INSTRUMENTS: dict[str, str] = {"piano": "piano_expert"}


def specialist_engine_for(instrument: str) -> Optional[str]:
    """The specialist engine key to try first for this instrument, if any."""
    return SPECIALIST_ENGINE_INSTRUMENTS.get(instrument)


@dataclass(frozen=True)
class RoutingPlan:
    """What to run for one instrument+mode+note_detection combination."""

    routing_mode: str  # "melody_only" | "multiple_notes" | "double_stops"
    max_polyphony: int
    instrument_note: Optional[str]


def resolve_routing(instrument: str, mode: str, note_detection: str) -> RoutingPlan:
    """Decide the polyphony cap and routing label for this project.

    mode is accepted (not just instrument) because some instruments could
    plausibly route differently in Direct vs Solo arrangement in a future
    version; today the cap only depends on instrument + note_detection, but
    keeping mode in the signature avoids a breaking change later.
    """
    del mode  # not used yet — see docstring
    if note_detection != "poly":
        return RoutingPlan(routing_mode="melody_only", max_polyphony=1, instrument_note=None)

    max_polyphony = INSTRUMENT_MAX_POLYPHONY.get(instrument, MAX_POLYPHONY)
    routing_mode = "double_stops" if instrument == "violin" else "multiple_notes"
    instrument_note = INSTRUMENT_POLY_NOTES.get(instrument)
    return RoutingPlan(
        routing_mode=routing_mode, max_polyphony=max_polyphony, instrument_note=instrument_note
    )


def default_note_detection(instrument: str, mode: str) -> str:
    """The note-detection value to pre-select in the setup UI for this
    instrument+mode, before the user has touched the control themselves."""
    if mode == "direct_transcription" and instrument in DIRECT_AUTO_POLY_INSTRUMENTS:
        return "poly"
    if mode == "solo_arrangement" and instrument in SOLO_AUTO_POLY_INSTRUMENTS:
        return "poly"
    return "melody"


def describe_difficulty(
    notes: list[dict], messages: list[str], engine_used: str
) -> str:
    """A rough, honest density label from the actual detection result.

    Deliberately simple: a handful of blunt signals, not a model. A single
    clean chord (everything grouped, nothing trimmed) must read as simple —
    "overlapping" alone isn't density; overflow and weak, messy detections
    are what actually signal trouble. Never claims precision it doesn't have.
    """
    if not notes:
        return "No notes detected"
    if engine_used == "pyin":
        return "Simple melody"

    grouped = [n for n in notes if n.get("group")]
    group_ids = {n["group"] for n in grouped}
    joined_messages = " ".join(messages).lower()

    # The engine already said it hit the polyphony cap and had to simplify —
    # the single strongest, most honest density signal available.
    if "too dense" in joined_messages or "only the strongest" in joined_messages:
        return "Dense piano/audio — may need editing"

    avg_group_size = (len(grouped) / len(group_ids)) if group_ids else 0
    many_groups = len(group_ids) >= 3
    weak_dropped = "low-confidence notes were removed" in joined_messages

    dense_signals = 0
    if avg_group_size >= 3.5:
        dense_signals += 1
    if weak_dropped and many_groups:
        dense_signals += 1

    if dense_signals >= 2:
        return "Dense piano/audio — may need editing"
    if grouped:
        return "Some overlapping notes"
    return "Simple melody"
