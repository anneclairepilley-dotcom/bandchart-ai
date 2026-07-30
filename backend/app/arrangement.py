"""Solo Arrangement pipeline (v1.0).

Direct transcription (app/transcription.py, untouched by this module) is
for one clear instrument or voice. Solo Arrangement is different: it takes
a full song and tries to build a playable solo part for one chosen
instrument out of it — finding the strongest melody (the vocal, when one
can be isolated) rather than transcribing everything literally. This is an
arrangement, not a perfect transcription: dense songs are simplified into
something singable/playable, not dumped note-for-note.

Pipeline:
1. Prepare the audio (normalise, trim silence) into a scratch copy — the
   user's original upload is never touched.
2. Try optional vocal/accompaniment separation (app/separation.py). It
   never raises and returns None if Demucs isn't installed or fails, so
   this step always degrades gracefully to using the full mix.
3. Extract the main melody: the vocal stem when one was isolated (except
   for bass, which follows the low end of the accompaniment/full mix, not
   the singer), the full mix otherwise. Reuses the same pYIN / Basic Pitch
   engines as Direct transcription.
4. For piano and guitar only, when the arrangement focus calls for it,
   pull a small number of sparse low-register notes from the accompaniment
   as simple support — never a dense reduction of everything detected.
5. Merge, and report exactly what happened (source, engines, warnings) so
   the result is honest about being an arrangement, not magic.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Optional

import librosa
import soundfile as sf

from app.polyphonic import MAX_POLYPHONY, _assign_groups, detect_notes_poly
from app.routing import RoutingPlan, describe_difficulty, resolve_routing
from app.separation import separate_vocals
from app.storage import now_iso
from app.transcription import SAMPLE_RATE, _detect_notes, write_midi_from_notes

# Bass follows the low end of the song, not the singer — its melody source
# is the accompaniment (or full mix), never an isolated vocal stem.
BASS_PREFERS_ACCOMPANIMENT = {"bass"}
# Instruments with an obvious home for a second, supporting voice (piano's
# left hand, guitar's lower strings). Everything else stays melody-only —
# adding harmony notes to e.g. a single-line violin/sax/trumpet/voice part
# would just make it unplayable.
SUPPORT_CAPABLE_INSTRUMENTS = {"piano", "guitar"}
# Support notes are pulled from below this pitch so they sit under, and
# never duplicate, the melody.
SUPPORT_MAX_PITCH = 60  # middle C
# How many separate support notes to keep, and the minimum spacing between
# them, by difficulty — kept deliberately small so the result reads as a
# simple bassline/left hand, not a dense reduction of everything detected.
SUPPORT_NOTE_BUDGET = {"easy": 24, "medium": 48}
SUPPORT_MIN_GAP_S = {"easy": 0.6, "medium": 0.3}
# Generous cap for grouping the merged melody+support notes into chord ids
# for display/density purposes only — melody and support notes rarely land
# within the clustering window of each other, so this is not expected to
# trim anything in practice.
SUPPORT_GROUP_CAP = 8


def _prepare_audio(audio_path: Path, work_dir: Path) -> Path:
    """Peak-normalise and trim leading/trailing silence into a scratch WAV.

    The original upload is never modified — every downstream step in this
    pipeline reads this cleaned copy instead.
    """
    y, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    peak = float(abs(y).max()) if y.size else 0.0
    if peak > 1e-6:
        y = y / peak * 0.95
    trimmed, _ = librosa.effects.trim(y, top_db=40)
    if trimmed.size == 0:
        trimmed = y
    prepared_path = work_dir / "prepared.wav"
    sf.write(str(prepared_path), trimmed, sr)
    return prepared_path


def _detect_melody(
    audio_path: Path, instrument: str, note_detection: str
) -> tuple[
    list[dict[str, Any]], str, str, Optional[str], list[str], RoutingPlan
]:
    """The same engine dispatch as transcription.run_transcription (Basic
    Pitch/CQT for "poly", pYIN otherwise, with the same fallback rules) —
    just run on a caller-chosen source (a vocal stem, accompaniment stem,
    or the full mix) instead of always the original upload.

    Returns (notes, detection_used, engine_used, fallback_reason,
    engine_messages, routing_plan).
    """
    plan = resolve_routing(instrument, "solo_arrangement", note_detection)

    detection_used = "melody"
    engine_used = "pyin"
    fallback_reason: Optional[str] = None
    engine_messages: list[str] = []
    notes: Optional[list[dict[str, Any]]] = None

    if note_detection == "poly":
        try:
            notes, poly_messages = detect_notes_poly(
                audio_path, max_polyphony=plan.max_polyphony
            )
            if notes:
                detection_used = "poly"
                engine_used = notes[0].get("source") or "basic_pitch"
                engine_messages = poly_messages
                if engine_used == "cqt":
                    fallback_reason = (
                        "Basic Pitch unavailable — used the built-in simple "
                        "detector instead."
                    )
            else:
                notes = None
                engine_messages = poly_messages
        except Exception:  # noqa: BLE001
            notes = None

    if notes is None:
        notes, melody_messages = _detect_notes(audio_path)
        engine_used = "pyin"
        engine_messages = melody_messages
        if note_detection == "poly":
            fallback_reason = "Basic Pitch failed, used melody-only fallback."

    return notes, detection_used, engine_used, fallback_reason, engine_messages, plan


def _extract_support_notes(
    accompaniment_path: Path, difficulty: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """A small number of sparse, low-register notes to sit under the melody.

    Never dumps everything detected: thins to a fixed note budget with a
    minimum gap between kept notes, both driven by difficulty, so the
    result reads as a simple bassline/left hand rather than a wash of notes.
    """
    notes, messages = detect_notes_poly(accompaniment_path, max_polyphony=MAX_POLYPHONY)
    low_notes = sorted(
        (n for n in notes if n["pitch"] < SUPPORT_MAX_PITCH),
        key=lambda n: n["start_time"],
    )

    min_gap = SUPPORT_MIN_GAP_S.get(difficulty, SUPPORT_MIN_GAP_S["easy"])
    budget = SUPPORT_NOTE_BUDGET.get(difficulty, SUPPORT_NOTE_BUDGET["easy"])

    thinned: list[dict[str, Any]] = []
    last_kept_start = -min_gap
    for note in low_notes:
        if note["start_time"] - last_kept_start < min_gap:
            continue
        thinned.append(note)
        last_kept_start = note["start_time"]
        if len(thinned) >= budget:
            break

    for note in thinned:
        note["source"] = "accompaniment"
        note.pop("group", None)

    return thinned, messages


def run_solo_arrangement(
    audio_path: Path,
    midi_out_path: Path,
    json_out_path: Path,
    project_id: str,
    project_name: str,
    source_audio_filename: str,
    instrument: str = "concert",
    note_detection: str = "melody",
    arrangement_focus: str = "main_melody",
    arrangement_difficulty: str = "easy",
) -> dict[str, Any]:
    """Run the Solo Arrangement pipeline on audio_path, write MIDI + notes JSON.

    Returns the same result shape as run_transcription, plus arrangement_source
    ("vocal_stem" | "accompaniment" | "full_mix"), separation_engine ("demucs"
    or None), arrangement_focus and arrangement_difficulty — so the UI can
    show exactly what happened, never hidden.
    """
    with tempfile.TemporaryDirectory(prefix="bandchart_arrangement_") as tmp:
        work_dir = Path(tmp)
        prepared_path = _prepare_audio(audio_path, work_dir)

        separation_result = separate_vocals(prepared_path, work_dir)
        warnings: list[str] = [
            "Solo Arrangement finds the strongest melody and creates a "
            "playable part. Dense songs may need editing."
        ]
        separation_engine: Optional[str] = None
        if separation_result is not None:
            separation_engine = "demucs"
            vocal_source = separation_result.vocals_path
            accompaniment_source = separation_result.accompaniment_path
        else:
            vocal_source = prepared_path
            accompaniment_source = prepared_path
            warnings.append("Using full mix because no clear vocal stem was isolated.")

        if instrument in BASS_PREFERS_ACCOMPANIMENT:
            melody_source = accompaniment_source
            arrangement_source = "accompaniment" if separation_result else "full_mix"
        else:
            melody_source = vocal_source
            arrangement_source = "vocal_stem" if separation_result else "full_mix"
            if separation_result is not None:
                warnings.append("Using vocal stem for main melody.")

        (
            melody_notes,
            detection_used,
            engine_used,
            fallback_reason,
            engine_messages,
            plan,
        ) = _detect_melody(melody_source, instrument, note_detection)

        support_notes: list[dict[str, Any]] = []
        if instrument in SUPPORT_CAPABLE_INSTRUMENTS and arrangement_focus in (
            "melody_support",
            "piano_style",
        ):
            # "Piano-style" always aims for a fuller left hand, regardless
            # of the difficulty control.
            support_difficulty = (
                "medium" if arrangement_focus == "piano_style" else arrangement_difficulty
            )
            try:
                support_notes, support_messages = _extract_support_notes(
                    accompaniment_source, support_difficulty
                )
            except Exception:  # noqa: BLE001
                support_notes, support_messages = [], []
            if support_notes:
                warnings.append("Added simple support notes. Please check and edit.")
                engine_messages = [*engine_messages, *support_messages]

        combined_notes = melody_notes + support_notes
        if support_notes:
            # Merging in a second voice makes this a polyphonic result even
            # when the melody itself came from monophonic pYIN — the export
            # pipeline (grand staff, chord-aware cleanup) needs to know.
            detection_used = "poly"
            combined_notes, group_messages = _assign_groups(
                combined_notes, max_polyphony=SUPPORT_GROUP_CAP
            )
            engine_messages = [*engine_messages, *group_messages]
        combined_notes.sort(key=lambda n: (n["start_time"], n["pitch"]))

        if plan.instrument_note and engine_used != "pyin":
            warnings.append(plan.instrument_note)

        routing_mode = plan.routing_mode
        if support_notes:
            routing_mode = "multiple_notes"
        elif engine_used == "pyin" and note_detection == "poly":
            routing_mode = "melody_only"

        difficulty = describe_difficulty(combined_notes, engine_messages, engine_used)

        write_midi_from_notes(combined_notes, midi_out_path)

        result = {
            "project_id": project_id,
            "project_name": project_name,
            "source_audio": source_audio_filename,
            "generated_at": now_iso(),
            "note_count": len(combined_notes),
            "notes": combined_notes,
            # Manual chord markers (v0.9) — a fresh arrangement starts empty.
            "chords": [],
            "detection": detection_used,
            "detection_note": None,
            "engine_used": engine_used,
            "routing_mode": routing_mode,
            "fallback_reason": fallback_reason,
            "warnings": [*warnings, *engine_messages],
            "difficulty": difficulty,
            # v1.0 Solo Arrangement status — always reported, never hidden.
            "arrangement_source": arrangement_source,
            "separation_engine": separation_engine,
            "arrangement_focus": arrangement_focus,
            "arrangement_difficulty": arrangement_difficulty,
        }

        json_out_path.parent.mkdir(parents=True, exist_ok=True)
        json_out_path.write_text(json.dumps(result, indent=2))
        return result
