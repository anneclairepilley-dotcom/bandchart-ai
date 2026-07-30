"""Optional source separation via Demucs (v1.0, 4-stem since v0.9.6).

Meta's Demucs (PyPI package "demucs") was investigated for real vocal
isolation ahead of Solo Arrangement v1.0, and re-checked for full 4-stem
separation (vocals/bass/drums/other) in v0.9.6. Two blockers stack in this
project's deployment environments:

1. Demucs depends on PyTorch. Only the default PyPI torch wheel is
   reachable from this sandbox (the lighter CPU-only wheel host,
   download.pytorch.org, is blocked) — installing it pulls in ~4.7GB of
   unused CUDA packages (cublas, cudnn, cufft, cusolver, nccl, triton…)
   even though there's no GPU. Same root cause as an earlier finding for
   `piano_transcription_inference`.
2. Demucs' pretrained checkpoints (htdemucs etc.) download from
   dl.fbaipublicfiles.com and huggingface.co — both blocked outright here
   at the network level (re-confirmed via curl in v0.9.6 — still 403 on
   CONNECT). Even a successful install couldn't fetch a model to run.

CPU inference itself is not the problem: a forward pass through the real
untrained HTDemucs architecture completed in ~1x realtime on modest
hardware during the v1.0 investigation. So this module is written as a
real, working adapter — for an environment where those two hosts are
reachable — but Demucs is deliberately NOT added to requirements.txt and
is never installed automatically. See PROJECT_NOTES.md for the full
writeup.

Every function below is defensive by design: separation never raises. If
Demucs isn't installed, fails to import, or fails at any point during
separation, the caller gets None and falls back to using the full mix —
Solo Arrangement must keep working either way. Separated stems are always
written under a caller-owned scratch work_dir, never committed or kept
around — never inside backend/storage/projects/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEMUCS_MODEL = "htdemucs"


@dataclass(frozen=True)
class SeparationResult:
    """All four htdemucs stems, plus vocals/accompaniment for callers that
    only care about the vocals-vs-everything-else split (Solo Arrangement's
    existing v1.0 usage)."""

    vocals_path: Path
    drums_path: Path
    bass_path: Path
    other_path: Path

    @property
    def accompaniment_path(self) -> Path:
        """Everything except vocals is not on disk as one file in 4-stem
        mode — "other" (the non-vocal, non-drum, non-bass instrumentation,
        e.g. piano/guitar/synths) is the closest single stem to "the rest
        of the band" and is what v1.0's two-stem callers expect here."""
        return self.other_path


def is_available() -> tuple[bool, Optional[str]]:
    """Whether Demucs can plausibly run here, and why not if it can't.

    This only checks whether the package imports — it does not guarantee
    the model checkpoint can actually be downloaded (that's discovered,
    gracefully, inside separate_full).
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


def separate_full(audio_path: Path, work_dir: Path) -> Optional[SeparationResult]:
    """Try to split audio_path into vocals/drums/bass/other with Demucs.

    work_dir is a scratch directory the caller owns (and cleans up) — the
    separated stems are written under it, never alongside the project's
    stored audio. Returns None (never raises) if Demucs isn't installed,
    the model checkpoint can't be fetched, or separation fails for any
    other reason. Runs htdemucs' default 4-stem mode (no --two-stems flag)
    so one call yields every stem the app might want, for any instrument.
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
                ["-n", DEMUCS_MODEL, "-o", str(out_dir), str(audio_path)]
            )
        except SystemExit as exc:
            if exc.code not in (0, None):
                return None

        stem_dir = out_dir / DEMUCS_MODEL / audio_path.stem
        paths = {
            "vocals_path": stem_dir / "vocals.wav",
            "drums_path": stem_dir / "drums.wav",
            "bass_path": stem_dir / "bass.wav",
            "other_path": stem_dir / "other.wav",
        }
        if not all(p.exists() for p in paths.values()):
            return None
        return SeparationResult(**paths)
    except Exception:  # noqa: BLE001
        return None


def separate_vocals(audio_path: Path, work_dir: Path) -> Optional[SeparationResult]:
    """Back-compat alias for separate_full — kept so existing callers that
    only care about vocals-vs-accompaniment (arrangement.py) don't need to
    change; SeparationResult now carries all 4 stems either way."""
    return separate_full(audio_path, work_dir)
