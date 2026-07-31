"""Built-in synthetic test audio for the Engine Lab.

Every fixture is a short, pure-tone WAV with KNOWN expected notes, so
scoring.py can measure an engine's accuracy against ground truth instead of
just eyeballing the output. Deliberately simple/clean audio — these are
sanity checks, not a substitute for testing on a real recording (Mrs Magic).

Generated once on first request and cached on disk (regenerating is cheap
and deterministic, so a stale/corrupt cache file is just overwritten).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pretty_midi
import soundfile as sf

SAMPLE_RATE = 22050


def _midi_to_hz(pitch: int) -> float:
    return 440.0 * 2.0 ** ((pitch - 69) / 12.0)


def _tone(pitches: list[int], duration_s: float, amp: float = 0.85) -> np.ndarray:
    """A short percussive-ish tone (fundamental + quiet octave, decay envelope)."""
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    y = np.zeros_like(t)
    for pitch in pitches:
        f = _midi_to_hz(pitch)
        y += np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    y /= max(1, len(pitches))
    envelope = np.exp(-t * 1.3)
    attack = int(0.008 * SAMPLE_RATE)
    envelope[:attack] *= np.linspace(0, 1, attack)
    return amp * y * envelope


def _expected(pitch: int, start: float, duration: float) -> dict[str, Any]:
    return {
        "pitch": pitch,
        "pitch_name": pretty_midi.note_number_to_name(pitch),
        "start_time": round(start, 4),
        "duration": round(duration, 4),
    }


@dataclass
class Fixture:
    key: str
    label: str
    description: str
    audio: np.ndarray
    expected_notes: list[dict[str, Any]]


def _build_a4_tone() -> Fixture:
    audio = np.concatenate([_tone([69], 2.0), np.zeros(int(0.3 * SAMPLE_RATE))])
    return Fixture(
        key="a4_tone",
        label="A4 tone",
        description="A single held A4 note. Sanity check: melody-only detectors "
        "should find exactly one clean note and nothing else.",
        audio=audio,
        expected_notes=[_expected(69, 0.0, 2.0)],
    )


def _build_c_major_chord() -> Fixture:
    audio = np.concatenate([_tone([60, 64, 67], 2.0), np.zeros(int(0.3 * SAMPLE_RATE))])
    return Fixture(
        key="c_major_chord",
        label="C major chord (C4 E4 G4)",
        description="Three notes struck together and held. The core polyphony "
        "test: can the engine find all three, together, as one chord?",
        audio=audio,
        expected_notes=[_expected(p, 0.0, 2.0) for p in (60, 64, 67)],
    )


def _build_c_major_scale() -> Fixture:
    pitches = [60, 62, 64, 65, 67, 69, 71, 72]  # C4..C5
    step = 0.4
    parts = [_tone([p], step) for p in pitches]
    audio = np.concatenate(parts + [np.zeros(int(0.3 * SAMPLE_RATE))])
    expected = [_expected(p, i * step, step) for i, p in enumerate(pitches)]
    return Fixture(
        key="c_major_scale",
        label="C major scale",
        description="Eight sequential single notes, no overlap. Tests onset/"
        "pitch accuracy and repeated-note handling without any polyphony.",
        audio=audio,
        expected_notes=expected,
    )


def _build_block_chords() -> Fixture:
    chords = [(60, 64, 67), (53, 57, 60), (55, 59, 62)]  # C major, F major, G major
    step = 1.2
    parts = [_tone(list(c), step) for c in chords]
    audio = np.concatenate(parts + [np.zeros(int(0.3 * SAMPLE_RATE))])
    expected = []
    for i, chord in enumerate(chords):
        for p in chord:
            expected.append(_expected(p, i * step, step))
    return Fixture(
        key="block_chords",
        label="Simple piano block chords",
        description="Three block triads in sequence (C, F, G major). Tests "
        "whether polyphony holds up across several consecutive chord changes.",
        audio=audio,
        expected_notes=expected,
    )


def _build_bass_and_melody() -> Fixture:
    total_s = 3.6
    mix = np.zeros(int(SAMPLE_RATE * total_s))

    def add(y: np.ndarray, at: float) -> None:
        i = int(at * SAMPLE_RATE)
        mix[i : i + len(y)] += y[: len(mix) - i]

    # Left hand: a sustained low dyad under the whole phrase.
    add(_tone([36, 43], 3.4, amp=0.8), 0.0)  # C2 + G2
    # Right hand: a short melody on top, overlapping the bass throughout.
    melody = [(64, 0.0), (65, 0.5), (67, 1.0), (69, 1.5), (67, 2.0), (65, 2.5), (64, 3.0)]
    for pitch, start in melody:
        add(_tone([pitch], 0.45, amp=0.75), start)

    mix = 0.9 * mix / max(1e-9, np.abs(mix).max())
    expected = [_expected(36, 0.0, 3.4), _expected(43, 0.0, 3.4)]
    expected += [_expected(p, s, 0.45) for p, s in melody]
    return Fixture(
        key="bass_and_melody",
        label="Left-hand bass + right-hand melody",
        description="A held low bass dyad under a short right-hand melody line "
        "— the shape of a real simple piano part. Tests whether an engine keeps "
        "the bass sounding while also tracking the moving melody on top.",
        audio=mix.astype(np.float32),
        expected_notes=expected,
    )


def _build_octave_doubling() -> Fixture:
    total_s = 2.4
    mix = np.zeros(int(SAMPLE_RATE * total_s))

    def add(y: np.ndarray, at: float) -> None:
        i = int(at * SAMPLE_RATE)
        mix[i : i + len(y)] += y[: len(mix) - i]

    # Left hand: a bass note doubled an octave above — extremely common,
    # intentional piano writing (see v0.9.7 notes below), not a harmonic
    # ghost. Deliberately voiced UNEVENLY (the octave note quieter than the
    # root, as real playing often is) so this actually exercises the
    # harmonic-suppression confidence-ratio check rather than passing by
    # accident — a balanced-amplitude version of this fixture didn't
    # reproduce the real-world drop (both notes' confidence came back too
    # close together to trip HARMONIC_TOLERANCE either way).
    add(_tone([36], 2.2, amp=0.8), 0.0)  # C2, full strength
    add(_tone([48], 2.0, amp=0.18), 0.0)  # C3, the octave doubling, quieter
    melody = [(64, 0.0), (67, 0.6), (72, 1.2), (67, 1.8)]
    for pitch, start in melody:
        add(_tone([pitch], 0.55, amp=0.75), start)

    mix = 0.9 * mix / max(1e-9, np.abs(mix).max())
    expected = [_expected(36, 0.0, 2.2), _expected(48, 0.0, 2.2)]
    expected += [_expected(p, s, 0.55) for p, s in melody]
    return Fixture(
        key="octave_doubling",
        label="Octave-doubled bass + melody",
        description="A bass note played together with its own octave (C2+C3), "
        "under a short right-hand melody — v0.9.7: real-world feedback (the "
        "\"Mrs Magic\" benchmark) found Basic Pitch's harmonic-ghost filter was "
        "dropping real octave doublings like this one. Tests that both bass "
        "notes survive.",
        audio=mix.astype(np.float32),
        expected_notes=expected,
    )


_BUILDERS = {
    "a4_tone": _build_a4_tone,
    "c_major_chord": _build_c_major_chord,
    "c_major_scale": _build_c_major_scale,
    "block_chords": _build_block_chords,
    "bass_and_melody": _build_bass_and_melody,
    "octave_doubling": _build_octave_doubling,
}

# Display order matches the owner's benchmark order (steps 1-5; step 6 is
# the real-world Mrs Magic benchmark, which has no synthetic fixture).
# octave_doubling (v0.9.7) is appended last — a targeted regression check
# for the real-world octave-doubling fix, not part of the original order.
FIXTURE_KEYS = [
    "a4_tone",
    "c_major_chord",
    "c_major_scale",
    "block_chords",
    "bass_and_melody",
    "octave_doubling",
]


def list_fixtures() -> list[Fixture]:
    return [_BUILDERS[key]() for key in FIXTURE_KEYS]


def get_fixture(key: str) -> Fixture | None:
    builder = _BUILDERS.get(key)
    return builder() if builder else None


def ensure_fixture_audio(key: str, out_path: Path) -> Fixture | None:
    """Build the fixture and write its audio to out_path if not already there."""
    fixture = get_fixture(key)
    if fixture is None:
        return None
    if not out_path.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), fixture.audio.astype(np.float32), SAMPLE_RATE)
    return fixture
