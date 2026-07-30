"""Engine adapters: thin wrappers around the app's existing detectors plus
any additional engines investigated for v0.9.4.

Each adapter reuses the SAME detection code the main app runs — the lab
never re-implements transcription, it just calls the real functions in
isolation (without the automatic melody-fallback chain in
transcription.run_transcription/polyphonic.detect_notes_poly) so each
engine's own output can be inspected on its own.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from app.engine_lab.base import EngineAdapter, EngineRunOutput


def _pyin_available() -> tuple[bool, Optional[str]]:
    return True, None


def _run_pyin(audio_path: Path) -> EngineRunOutput:
    from app.transcription import _detect_notes

    notes, messages = _detect_notes(audio_path)
    return EngineRunOutput(notes=notes, messages=messages)


def _basic_pitch_available() -> tuple[bool, Optional[str]]:
    try:
        import basic_pitch.inference  # noqa: F401
    except ImportError as exc:
        return False, (
            "The basic-pitch package isn't installed in this environment "
            f"({exc}). Install it with `pip install --no-deps basic-pitch==0.4.0` "
            "(see README)."
        )
    return True, None


def _run_basic_pitch(audio_path: Path) -> EngineRunOutput:
    from app.polyphonic import _detect_with_basic_pitch

    notes, messages = _detect_with_basic_pitch(audio_path)
    return EngineRunOutput(notes=notes, messages=messages)


def _cqt_available() -> tuple[bool, Optional[str]]:
    return True, None


def _run_cqt(audio_path: Path) -> EngineRunOutput:
    from app.polyphonic import _detect_with_cqt

    notes, messages = _detect_with_cqt(audio_path)
    return EngineRunOutput(notes=notes, messages=messages)


def _piano_expert_available() -> tuple[bool, Optional[str]]:
    return False, (
        "Not wired up in this version. Investigated for v0.9.4 (ByteDance's "
        "piano_transcription_inference): the package itself installs cleanly "
        "(no conflicts with numpy/librosa/scipy here), but it needs PyTorch "
        "(a heavy extra dependency) AND downloads a ~165MB checkpoint from "
        "Zenodo at first use — an external, unmaintained-repo dependency "
        "(archived Dec 2025) that couldn't be verified end-to-end from this "
        "environment. It will not become the default piano engine until it "
        "can be shown to actually pass the C major chord and simple piano "
        "tests here."
    )


def _run_piano_expert(audio_path: Path) -> EngineRunOutput:  # pragma: no cover
    raise NotImplementedError("Piano Expert (ByteDance) is not wired up yet — see README.")


def _omnizart_available() -> tuple[bool, Optional[str]]:
    return False, (
        "Not wired up in this version. Investigated for v0.9.4: Omnizart "
        "genuinely installs and runs on CPU (verified — real piano/chord/"
        "drum/vocal transcription on a synthetic test clip), but only on "
        "Python 3.10 (not this app's Python 3.12), needs the system "
        "'portaudio' library, and pulls in TensorFlow plus ~700MB of "
        "checkpoints (~3.5GB total). That doesn't fit safely into the main "
        "backend environment — it would need its own separate venv and a "
        "subprocess bridge, which is future work (see README)."
    )


def _run_omnizart(audio_path: Path) -> EngineRunOutput:  # pragma: no cover
    raise NotImplementedError("Omnizart is not wired up yet — see README.")


ADAPTERS: list[EngineAdapter] = [
    EngineAdapter(
        key="pyin",
        label="pYIN (melody baseline)",
        description=(
            "BandChart's original monophonic pitch tracker (librosa). Follows one "
            "melodic line at a time; the reliable baseline every other engine is "
            "measured against."
        ),
        availability_check=_pyin_available,
        run_fn=_run_pyin,
    ),
    EngineAdapter(
        key="basic_pitch",
        label="Basic Pitch (Spotify)",
        description=(
            "Spotify's open-source ICASSP-2022 model, run on CPU via ONNX. "
            "BandChart's current main polyphonic engine — detects several "
            "simultaneous notes, works best on clear piano or simple chords."
        ),
        availability_check=_basic_pitch_available,
        run_fn=_run_basic_pitch,
    ),
    EngineAdapter(
        key="cqt",
        label="Built-in simple detector (CQT)",
        description=(
            "BandChart's own constant-Q + onset-segmentation fallback (v0.9.2). "
            "No external model — used automatically when Basic Pitch is missing."
        ),
        availability_check=_cqt_available,
        run_fn=_run_cqt,
    ),
    EngineAdapter(
        key="piano_expert",
        label="Piano Expert (ByteDance, investigated)",
        description=(
            "A piano-specialist polyphonic transcription model, investigated for "
            "v0.9.4 as a stronger candidate for dense piano. Not active yet — see "
            "the unavailable reason."
        ),
        availability_check=_piano_expert_available,
        run_fn=_run_piano_expert,
    ),
    EngineAdapter(
        key="omnizart",
        label="Omnizart (investigated)",
        description=(
            "A general automatic music transcription toolkit (piano/vocal/chord/"
            "drum/beat), investigated for v0.9.4. Confirmed working on CPU, but "
            "needs its own separate environment — not active in this app yet."
        ),
        availability_check=_omnizart_available,
        run_fn=_run_omnizart,
    ),
]


def get_adapter(key: str) -> Optional[EngineAdapter]:
    for adapter in ADAPTERS:
        if adapter.key == key:
            return adapter
    return None
