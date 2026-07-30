"""Optional vocal/accompaniment source separation via Demucs (v1.0).

Meta's Demucs (PyPI package "demucs") was investigated for real vocal
isolation ahead of Solo Arrangement v1.0. Two blockers stack in this
project's deployment environments:

1. Demucs depends on PyTorch. Only the default PyPI torch wheel is
   reachable from this sandbox (the lighter CPU-only wheel host,
   download.pytorch.org, is blocked) — installing it pulls in ~4.7GB of
   unused CUDA packages (cublas, cudnn, cufft, cusolver, nccl, triton…)
   even though there's no GPU. Same root cause as an earlier finding for
   `piano_transcription_inference`.
2. Demucs' pretrained checkpoints (htdemucs etc.) download from
   dl.fbaipublicfiles.com and huggingface.co — both blocked outright here
   at the network level. Even a successful install couldn't fetch a model
   to run.

CPU inference itself is not the problem: a forward pass through the real
untrained HTDemucs architecture completed in ~1x realtime on modest
hardware during the investigation. So this module is written as a real,
working adapter — for an environment where those two hosts are reachable
— but Demucs is deliberately NOT added to requirements.txt and is never
installed automatically. See PROJECT_NOTES.md for the full writeup.

Both functions below are defensive by design: `separate_vocals` never
raises. If Demucs isn't installed, fails to import, or fails at any point
during separation, it returns None and the caller falls back to using the
full mix — Solo Arrangement must keep working either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEMUCS_MODEL = "htdemucs"


@dataclass(frozen=True)
class SeparationResult:
    vocals_path: Path
    accompaniment_path: Path


def is_available() -> tuple[bool, Optional[str]]:
    """Whether Demucs can plausibly run here, and why not if it can't.

    This only checks whether the package imports — it does not guarantee
    the model checkpoint can actually be downloaded (that's discovered,
    gracefully, inside separate_vocals).
    """
    try:
        import demucs.separate  # noqa: F401
    except ImportError:
        return False, (
            "Demucs isn't installed. Source separation is optional in "
            "BandChart AI — Solo Arrangement uses the full mix instead."
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Demucs is installed but failed to load ({exc})."
    return True, None


def separate_vocals(audio_path: Path, work_dir: Path) -> Optional[SeparationResult]:
    """Try to split audio_path into vocals + accompaniment stems with Demucs.

    work_dir is a scratch directory the caller owns (and cleans up) — the
    separated stems are written under it, never alongside the project's
    stored audio. Returns None (never raises) if Demucs isn't installed,
    the model checkpoint can't be fetched, or separation fails for any
    other reason.
    """
    available, _reason = is_available()
    if not available:
        return None

    try:
        import demucs.separate

        out_dir = work_dir / "demucs_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            demucs.separate.main(
                [
                    "-n",
                    DEMUCS_MODEL,
                    "--two-stems",
                    "vocals",
                    "-o",
                    str(out_dir),
                    str(audio_path),
                ]
            )
        except SystemExit as exc:
            if exc.code not in (0, None):
                return None

        stem_dir = out_dir / DEMUCS_MODEL / audio_path.stem
        vocals_path = stem_dir / "vocals.wav"
        accompaniment_path = stem_dir / "no_vocals.wav"
        if not vocals_path.exists() or not accompaniment_path.exists():
            return None
        return SeparationResult(vocals_path=vocals_path, accompaniment_path=accompaniment_path)
    except Exception:  # noqa: BLE001
        return None
