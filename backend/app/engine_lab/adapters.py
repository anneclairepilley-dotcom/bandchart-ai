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
    from app.piano_expert import is_available as piano_expert_is_available

    return piano_expert_is_available()


def _run_piano_expert(audio_path: Path) -> EngineRunOutput:
    from app.piano_expert import transcribe_piano

    notes, messages = transcribe_piano(audio_path)
    return EngineRunOutput(notes=notes, messages=messages)


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


def _mt3_available() -> tuple[bool, Optional[str]]:
    return False, (
        "Research-only, not installed. Investigated for v0.9.4: MT3 "
        "(Magenta) has no PyPI package — installing it means cloning a repo "
        "and building JAX/T5X/TensorFlow largely from source, plus fetching "
        "checkpoints from Google Cloud Storage via gsutil. The project is in "
        "caretaker mode (occasional trivial commits, no real feature work "
        "since ~2022). Not practical for a CPU-only, no-fuss local setup."
    )


def _run_mt3(audio_path: Path) -> EngineRunOutput:  # pragma: no cover
    raise NotImplementedError("MT3 is not wired up — see README.")


def _demucs_available() -> tuple[bool, Optional[str]]:
    from app.separation import is_available as demucs_is_available

    return demucs_is_available()


def _run_demucs_vocals(audio_path: Path) -> EngineRunOutput:
    """Separate with Demucs, then run Basic Pitch on the isolated vocal
    stem — lets the lab compare "separation + detection" against running
    detection on the full mix directly, on the exact same source audio."""
    import tempfile

    from app.polyphonic import _detect_with_basic_pitch
    from app.separation import separate_full

    with tempfile.TemporaryDirectory(prefix="engine_lab_demucs_") as tmp:
        work_dir = Path(tmp)
        result = separate_full(audio_path, work_dir)
        if result is None:
            raise RuntimeError("Source separation failed. Using full mix instead.")
        notes, messages = _detect_with_basic_pitch(result.vocals_path)
        return EngineRunOutput(
            notes=notes,
            messages=["Demucs separated the vocal stem before Basic Pitch ran.", *messages],
        )


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
        label="Piano Expert (ByteDance)",
        description=(
            "A piano-specialist polyphonic transcription model (onset/frame/velocity "
            "CNN), the strongest candidate for dense piano/full-song piano parts. "
            "Real, working adapter — active automatically when installed and its "
            "checkpoint can download; otherwise Piano falls back to Basic Pitch, "
            "here and in the main app. See the unavailable reason if it's off."
        ),
        availability_check=_piano_expert_available,
        run_fn=_run_piano_expert,
    ),
    EngineAdapter(
        key="demucs_vocals",
        label="Demucs + Basic Pitch (vocal separation)",
        description=(
            "Separates the source into vocals/drums/bass/other with Meta's Demucs, "
            "then runs Basic Pitch on the isolated vocal stem — compare against "
            "running Basic Pitch on the full mix directly to see what separation "
            "actually buys you on a given recording."
        ),
        availability_check=_demucs_available,
        run_fn=_run_demucs_vocals,
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
    EngineAdapter(
        key="mt3",
        label="MT3 (Magenta, investigated)",
        description=(
            "Google Magenta's general-purpose multi-instrument transcription "
            "model, investigated for v0.9.4. Research-only — not installed."
        ),
        availability_check=_mt3_available,
        run_fn=_run_mt3,
    ),
]


def get_adapter(key: str) -> Optional[EngineAdapter]:
    for adapter in ADAPTERS:
        if adapter.key == key:
            return adapter
    return None
