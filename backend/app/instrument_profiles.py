"""Central instrument profile data (v0.9.8).

Single source of truth for the 7 real instruments BandChart AI is now
focused around. Every range is CONCERT (sounding) MIDI — the number a
listener actually hears, not what a transposing player reads off the page.
Transposition to WRITTEN pitch for Alto Sax/Trumpet happens only at
MusicXML/PDF export time (app/musicxml.py, unchanged) and is never applied
to a stored range check — range fitting always happens against the
sounding range first, per the request.

Other instrument keys (concert, flute, tenor_sax, clarinet, ukulele) are
NOT deleted from the backend — MusicXML/PDF export, Engine Lab and old
projects still work with them (app/musicxml.py::INSTRUMENTS is untouched).
They're just absent from this profile table and from the user-facing
picker (frontend/lib/instruments.ts::MAIN_INSTRUMENTS), so anything that
looks them up here (routing caps, range fitting) falls back to sane
defaults rather than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InstrumentProfile:
    key: str
    display_name: str
    # Playable CONCERT (sounding) MIDI range, inclusive.
    range_low: int
    range_high: int
    # A narrower range most real playing sits within — used only as a
    # secondary preference signal, never a hard limit.
    comfortable_low: int
    comfortable_high: int
    # Semitones from concert to WRITTEN pitch (0 = non-transposing).
    # Mirrors frontend/lib/instruments.ts and musicxml.py's INSTRUMENTS
    # table — keep all three in sync.
    written_offset: int
    clef: str  # "treble" | "bass" | "grand_staff" | "tab"
    supports_multiple_notes: bool
    max_simultaneous_notes: int
    tab_support: bool
    # Short, human-readable description of the default Solo Arrangement
    # treatment — surfaced nowhere yet, but keeps the "why" next to the
    # data instead of scattered across routing.py/arrangement.py comments.
    solo_focus: str


PROFILES: dict[str, InstrumentProfile] = {
    "piano": InstrumentProfile(
        key="piano",
        display_name="Piano",
        range_low=21,  # A0
        range_high=108,  # C8
        comfortable_low=36,  # C2
        comfortable_high=84,  # C6
        written_offset=0,
        clef="grand_staff",
        supports_multiple_notes=True,
        max_simultaneous_notes=6,
        tab_support=False,
        solo_focus="Melody plus simple support notes, grand staff, chords preserved.",
    ),
    "guitar": InstrumentProfile(
        key="guitar",
        display_name="Guitar",
        range_low=40,  # E2, standard tuning's lowest open string
        range_high=88,  # E6
        comfortable_low=40,
        comfortable_high=76,
        written_offset=0,
        clef="tab",
        supports_multiple_notes=True,
        max_simultaneous_notes=4,
        tab_support=True,
        solo_focus="Melody-first TAB; attempts playable multi-note chords when it can.",
    ),
    "bass": InstrumentProfile(
        key="bass",
        display_name="Bass",
        range_low=28,  # E1, standard tuning's lowest open string
        range_high=67,  # G4
        comfortable_low=28,
        comfortable_high=55,
        written_offset=0,
        clef="tab",
        supports_multiple_notes=False,
        max_simultaneous_notes=1,
        tab_support=True,
        solo_focus="Bassline / strong low line, melody-only, octave-shifted down as needed.",
    ),
    "violin": InstrumentProfile(
        key="violin",
        display_name="Violin",
        range_low=55,  # G3, lowest open string
        range_high=105,  # A7
        comfortable_low=55,
        comfortable_high=93,
        written_offset=0,
        clef="treble",
        supports_multiple_notes=True,
        max_simultaneous_notes=2,
        tab_support=False,
        solo_focus="Main melody plus simple double-stops only, never dense chords.",
    ),
    "alto_sax": InstrumentProfile(
        key="alto_sax",
        display_name="Alto Sax",
        range_low=49,  # Db3 sounding
        range_high=81,  # A5 sounding
        comfortable_low=49,
        comfortable_high=81,
        written_offset=9,  # Eb instrument: written a major 6th above concert
        clef="treble",
        supports_multiple_notes=False,
        max_simultaneous_notes=1,
        tab_support=False,
        solo_focus="Main melody only, written part transposed for Eb alto sax.",
    ),
    "trumpet": InstrumentProfile(
        key="trumpet",
        display_name="Trumpet",
        range_low=52,  # E3 sounding
        range_high=84,  # C6 sounding
        comfortable_low=52,
        comfortable_high=84,
        written_offset=2,  # Bb instrument: written a major 2nd above concert
        clef="treble",
        supports_multiple_notes=False,
        max_simultaneous_notes=1,
        tab_support=False,
        solo_focus="Main melody only, written part transposed for Bb trumpet.",
    ),
    "voice": InstrumentProfile(
        key="voice",
        display_name="Voice",
        range_low=48,  # C3
        range_high=72,  # C5
        comfortable_low=48,
        comfortable_high=72,
        written_offset=0,
        clef="treble",
        supports_multiple_notes=False,
        max_simultaneous_notes=1,
        tab_support=False,
        solo_focus="Main vocal melody only, fit into a comfortable singable range.",
    ),
}

# The 7 real instruments the app is now focused around (v0.9.8) — the only
# ones shown in the user-facing instrument picker and the results-page
# solo-instrument selector. Order matches the request's list.
MAIN_INSTRUMENTS = ["guitar", "bass", "piano", "violin", "alto_sax", "trumpet", "voice"]


def get_profile(instrument: str) -> Optional[InstrumentProfile]:
    return PROFILES.get(instrument)
