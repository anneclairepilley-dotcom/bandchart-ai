"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ApiError,
  audioUrl,
  fetchPdf,
  getNotes,
  getProject,
  importYoutube,
  jsonDownloadUrl,
  midiDownloadUrl,
  musicxmlDownloadUrl,
  resetNotes,
  saveProjectSettings,
  suggestChords as suggestChordsApi,
  tabDownloadUrl,
  transcribeProject,
  updateChords,
  updateNotes,
  uploadAudio,
  type ChordMarker,
  type NotesResponse,
  type Project,
  type SheetStyle,
} from "@/lib/api";
import { INSTRUMENTS, midiNoteName } from "@/lib/instruments";
import StatusBadge from "@/components/StatusBadge";
import NotePreview from "@/components/NotePreview";
import PlayAlong from "@/components/PlayAlong";
import SheetMusic from "@/components/SheetMusic";
import TabView from "@/components/TabView";
import ChordsPanel, {
  isValidChordName,
  MAX_CHORD_NAME_LEN,
} from "@/components/ChordsPanel";
import type { Note } from "@/lib/api";

/** Keep the working notes ordered by start time (then pitch, matching the
 * backend) — playback scheduling, the current-note highlight and the
 * backend all assume this order. */
function sortNotes(notes: Note[]): Note[] {
  return [...notes].sort(
    (a, b) => a.start_time - b.start_time || a.pitch - b.pitch
  );
}

const PITCH_CLASSES: Record<string, number> = {
  C: 0,
  D: 2,
  E: 4,
  F: 5,
  G: 7,
  A: 9,
  B: 11,
};

/** Accepts a note name ("G4", "F#3", "Bb3") or a MIDI number ("67"). */
// v0.9.5: display labels for the "Engine used" / "Mode" status line —
// mirrors the engine keys backend/app/transcription.py reports.
const ENGINE_LABELS: Record<string, string> = {
  basic_pitch: "Basic Pitch",
  cqt: "Built-in simple detector",
  pyin: "pYIN (melody)",
  piano_expert: "Piano Expert",
};
const ROUTING_MODE_LABELS: Record<string, string> = {
  melody_only: "Melody only",
  multiple_notes: "Multiple notes",
  double_stops: "Double-stops",
};
// v1.0 Solo Arrangement status labels — mirrors backend/app/arrangement.py.
const ARRANGEMENT_SOURCE_LABELS: Record<string, string> = {
  vocal_stem: "vocal stem",
  bass_stem: "bass stem",
  accompaniment: "accompaniment",
  full_mix: "full mix",
};
const ARRANGEMENT_FOCUS_LABELS: Record<string, string> = {
  main_melody: "Main melody",
  melody_support: "Melody + support",
  piano_style: "Piano-style arrangement",
};

/** Mirrors backend/app/routing.py::default_note_detection — the note
 * detection value to pre-select before the user touches the control
 * themselves. Piano defaults to polyphonic detection in BOTH modes
 * (v0.9.5): it's the one instrument with an obvious grand-staff home for
 * chords, whether transcribed directly or arranged as a solo piece. */
function defaultNoteDetection(instrument: string): "melody" | "poly" {
  return instrument === "piano" ? "poly" : "melody";
}

function parsePitchInput(raw: string): number | null {
  const s = raw.trim();
  if (/^\d+$/.test(s)) {
    const n = parseInt(s, 10);
    return n >= 0 && n <= 127 ? n : null;
  }
  const m = /^([A-Ga-g])([#♯b♭]?)(-?\d+)$/.exec(s);
  if (!m) return null;
  const base = PITCH_CLASSES[m[1].toUpperCase()];
  const accidental = m[2] === "#" || m[2] === "♯" ? 1 : m[2] ? -1 : 0;
  const midi = (parseInt(m[3], 10) + 1) * 12 + base + accidental;
  return midi >= 0 && midi <= 127 ? midi : null;
}

// Memoized so the 60fps play-along position updates don't re-render every
// table row; the current-note index only changes when the note changes.
const NoteTable = memo(function NoteTable({
  notes,
  writtenLabel,
  writtenOffset,
  currentIndex,
  autoScroll,
  onDelete,
  onEdit,
  onSeekNote,
  onAddAt,
  showAddAt,
}: {
  notes: Note[];
  writtenLabel: string;
  writtenOffset: number;
  currentIndex: number | null;
  autoScroll: boolean;
  onDelete: (index: number) => void;
  onEdit: (
    index: number,
    field: "pitch" | "start_time" | "duration",
    raw: string
  ) => void;
  /** Row click (not on an input/button) moves the playhead to that note. */
  onSeekNote: (index: number) => void;
  /** "+" button: add a new note starting at the same time as this row. */
  onAddAt: (index: number) => void;
  /** Only polyphonic transcriptions show the per-row "+" — on melody
   * projects the engraved sheet keeps one note per moment, so a stacked
   * note would silently vanish from the MusicXML/PDF. */
  showAddAt: boolean;
}) {
  const boxRef = useRef<HTMLDivElement>(null);

  // Keep the highlighted row in view while playing, scrolling only this
  // container (never the page).
  useEffect(() => {
    if (!autoScroll || currentIndex === null || !boxRef.current) return;
    const box = boxRef.current;
    const row = box.querySelector<HTMLTableRowElement>('tr[data-playing="true"]');
    if (!row) return;
    const rowTop = row.offsetTop;
    const viewTop = box.scrollTop;
    const viewBottom = viewTop + box.clientHeight;
    if (rowTop < viewTop + 40 || rowTop + row.clientHeight > viewBottom - 20) {
      box.scrollTo({
        top: Math.max(0, rowTop - box.clientHeight / 2),
        behavior: "smooth",
      });
    }
  }, [currentIndex, autoScroll]);

  return (
    <div ref={boxRef} className="max-h-96 overflow-y-auto rounded border border-gray-300">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-gray-50">
          <tr>
            <th className="p-2 font-medium">Concert pitch</th>
            <th className="p-2 font-medium">Written ({writtenLabel})</th>
            <th className="p-2 font-medium">Start (s)</th>
            <th className="p-2 font-medium">Duration (s)</th>
            <th className="p-2 font-medium">Confidence</th>
            <th className="p-2 font-medium">Chord</th>
            <th className="p-2 font-medium">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {notes.map((note, i) => (
            <tr
              // Values in the key re-mount the row's uncontrolled inputs
              // whenever a note actually changes (edit commit, reset).
              key={`${note.start_time}-${note.pitch}-${note.duration}-${i}`}
              data-playing={i === currentIndex ? "true" : undefined}
              onClick={(e) => {
                // Inputs and the delete button keep their own behaviour.
                if ((e.target as HTMLElement).closest("input,button")) return;
                onSeekNote(i);
              }}
              title="Click the row to move the playhead to this note"
              className={`cursor-pointer ${
                i === currentIndex
                  ? "border-t border-orange-200 bg-orange-100"
                  : "border-t border-gray-100 odd:bg-white even:bg-gray-50"
              }`}
            >
              <td className="p-2">
                <input
                  type="text"
                  defaultValue={note.pitch_name}
                  onBlur={(e) => onEdit(i, "pitch", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  data-testid={`pitch-input-${i}`}
                  aria-label={`Pitch of note ${i + 1}`}
                  className="w-16 rounded border border-gray-400 px-2 py-1 text-sm"
                />
              </td>
              <td className="p-2">{midiNoteName(note.pitch + writtenOffset)}</td>
              <td className="p-2">
                <input
                  type="number"
                  step={0.01}
                  min={0}
                  defaultValue={note.start_time.toFixed(3)}
                  onBlur={(e) => onEdit(i, "start_time", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  data-testid={`start-input-${i}`}
                  aria-label={`Start time of note ${i + 1}`}
                  className="w-24 rounded border border-gray-400 px-2 py-1 text-sm"
                />
              </td>
              <td className="p-2">
                <input
                  type="number"
                  step={0.01}
                  min={0.01}
                  defaultValue={note.duration.toFixed(3)}
                  onBlur={(e) => onEdit(i, "duration", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  data-testid={`duration-input-${i}`}
                  aria-label={`Duration of note ${i + 1}`}
                  className="w-24 rounded border border-gray-400 px-2 py-1 text-sm"
                />
              </td>
              <td className="p-2">{(note.confidence * 100).toFixed(0)}%</td>
              <td className="p-2 text-xs text-gray-500">{note.group ?? ""}</td>
              <td className="p-2 text-right whitespace-nowrap">
                {showAddAt && (
                  <button
                    type="button"
                    onClick={() => onAddAt(i)}
                    title={`Add a note starting at ${note.start_time.toFixed(2)}s (stack a chord)`}
                    data-testid={`add-note-at-${i}`}
                    className="rounded px-2 py-0.5 text-xs text-blue-700 hover:bg-blue-50"
                  >
                    +
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onDelete(i)}
                  title={`Delete ${note.pitch_name} at ${note.start_time.toFixed(2)}s`}
                  data-testid={`delete-note-${i}`}
                  className="rounded px-2 py-0.5 text-xs text-red-600 hover:bg-red-50"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

const ACCEPTED_EXTENSIONS = [
  ".wav",
  ".mp3",
  ".flac",
  ".ogg",
  ".m4a",
  ".aiff",
  ".aif",
];
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

type TranscriptionMode = "direct_transcription" | "solo_arrangement";

const MODE_OPTIONS: {
  key: TranscriptionMode;
  label: string;
  description: string;
}[] = [
  {
    key: "direct_transcription",
    label: "Direct transcription",
    description: "Transcribe one clear instrument or voice.",
  },
  {
    key: "solo_arrangement",
    label: "Solo arrangement",
    description:
      "Turn the main melody into a playable solo piece for your chosen instrument.",
  },
];

const TIME_SIGNATURE_OPTIONS = ["predict", "4/4", "3/4", "6/8"];
const KEY_OPTIONS = [
  "predict",
  "C",
  "G",
  "D",
  "A",
  "F",
  "Bb",
  "Eb",
  "Am",
  "Em",
  "Dm",
];

function TestFilesNote() {
  return (
    <div className="rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
      <p className="font-medium">What works best</p>
      <ul className="mt-1 list-disc pl-5">
        <li>
          A single melody line — one voice or one instrument at a time
          (singing, whistling, a flute, a piano playing one note at a time).
        </li>
        <li>
          Full songs with drums and many instruments won&apos;t transcribe
          well yet.
        </li>
        <li>
          .wav, .flac and .ogg files always work; .mp3 and .m4a also work if
          the server has ffmpeg installed. Maximum size 50MB.
        </li>
      </ul>
    </div>
  );
}

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [replacingAudio, setReplacingAudio] = useState(false);

  const [transcribing, setTranscribing] = useState(false);
  const [transcribeError, setTranscribeError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const [notes, setNotes] = useState<NotesResponse | null>(null);
  const [notesError, setNotesError] = useState<string | null>(null);

  const [instrumentKey, setInstrumentKey] = useState("concert");
  const selectedInstrument =
    INSTRUMENTS.find((i) => i.key === instrumentKey) ?? INSTRUMENTS[0];

  // ----- v0.9.1 pre-transcription setup (instrument, mode, advanced).
  const [setupInstrument, setSetupInstrument] = useState<string | null>(null);
  const [setupMode, setSetupMode] = useState<TranscriptionMode | null>(null);
  const [setupTs, setSetupTs] = useState("predict");
  const [setupKey, setSetupKey] = useState("predict");
  const [setupRhythm, setSetupRhythm] = useState<"readable" | "precise">(
    "readable"
  );
  const [setupError, setSetupError] = useState<string | null>(null);
  // Guards Start transcription while the settings save is in flight (the
  // transcribing flag only flips once the transcription request starts).
  const [startBusy, setStartBusy] = useState(false);
  // v0.9.2: melody-only vs experimental multiple-note detection. Follows
  // the piano default (both modes, since v0.9.5 — see defaultNoteDetection)
  // until the user touches the control.
  const [setupDetection, setSetupDetection] = useState<"melody" | "poly">(
    "melody"
  );
  const detectionTouchedRef = useRef(false);
  // v1.0 Solo Arrangement controls — ignored by Direct transcription.
  // Defaults: Main melody, Easy (Readable rhythm already defaults on above).
  const [setupFocus, setSetupFocus] = useState<
    "main_melody" | "melody_support" | "piano_style"
  >("main_melody");
  const [setupDifficulty, setSetupDifficulty] = useState<"easy" | "medium">(
    "easy"
  );

  // v0.9.2 click-to-seek: PlayAlong registers its seek function here and
  // the sheet / timeline / tab / note table call it.
  const seekRef = useRef<((positionSeconds: number) => void) | null>(null);
  const registerSeek = useCallback(
    (seek: (positionSeconds: number) => void) => {
      seekRef.current = seek;
    },
    []
  );
  const handleSeek = useCallback((positionSeconds: number) => {
    seekRef.current?.(positionSeconds);
  }, []);

  const [sheetStyle, setSheetStyle] = useState<SheetStyle>("clean");

  const [pdfDownloading, setPdfDownloading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const [playPosition, setPlayPosition] = useState<number | null>(null);
  const [playNoteIndex, setPlayNoteIndex] = useState<number | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const handlePlayTick = useCallback(
    (position: number | null, noteIndex: number | null) => {
      setPlayPosition(position);
      setPlayNoteIndex(noteIndex);
    },
    []
  );

  // Editable working copy of the notes. Deletes apply here instantly and are
  // auto-saved to the backend (debounced), which rewrites the transcription
  // JSON + MIDI so every download reflects the edit; notesVersion bumps make
  // the sheet-music viewer re-fetch.
  const [workingNotes, setWorkingNotes] = useState<Note[] | null>(null);
  const handleSeekNote = useCallback(
    (index: number) => {
      const target = workingNotes?.[index];
      if (target) seekRef.current?.(target.start_time);
    },
    [workingNotes]
  );
  const [notesVersion, setNotesVersion] = useState(0);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const pendingSaveRef = useRef(false);


  useEffect(() => {
    if (!pendingSaveRef.current || workingNotes === null) return;
    const timer = setTimeout(async () => {
      try {
        await updateNotes(projectId, workingNotes);
        pendingSaveRef.current = false;
        setSaveState("saved");
        setSaveError(null);
        setNotesVersion((v) => v + 1);
      } catch (err) {
        setSaveState("error");
        setSaveError(
          err instanceof ApiError
            ? err.message
            : "Couldn't save the edit — check that the backend is running."
        );
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [workingNotes, projectId]);

  const handleDeleteNote = useCallback((index: number) => {
    pendingSaveRef.current = true;
    setSaveState("saving");
    setWorkingNotes((current) =>
      current ? current.filter((_, i) => i !== index) : current
    );
  }, []);

  // Validation errors from inline note edits (invalid pitch/start/duration).
  const [editError, setEditError] = useState<string | null>(null);

  const handleEditNote = useCallback(
    (index: number, field: "pitch" | "start_time" | "duration", raw: string) => {
      const current = workingNotes?.[index];
      if (!current) return;

      let patch: Partial<Note>;
      if (field === "pitch") {
        const midi = parsePitchInput(raw);
        if (midi === null) {
          setEditError(
            `"${raw.trim() || "(empty)"}" isn't a valid pitch. Use a note name ` +
              "like G4, F#3 or Bb3, or a MIDI number from 0 to 127."
          );
          return;
        }
        if (midi === current.pitch) {
          setEditError(null);
          return;
        }
        patch = { pitch: midi, pitch_name: midiNoteName(midi) };
      } else {
        const value = Number(raw);
        if (field === "start_time") {
          if (raw.trim() === "" || !Number.isFinite(value) || value < 0) {
            setEditError(
              "Start time must be a number of seconds, 0 or more (e.g. 1.5)."
            );
            return;
          }
        } else if (raw.trim() === "" || !Number.isFinite(value) || value <= 0) {
          setEditError(
            "Duration must be a number of seconds greater than 0 (e.g. 0.5)."
          );
          return;
        }
        if (Math.abs(value - current[field]) < 1e-9) {
          setEditError(null);
          return;
        }
        patch = { [field]: value };
      }

      setEditError(null);
      pendingSaveRef.current = true;
      setSaveState("saving");
      setWorkingNotes((notes) =>
        notes
          ? sortNotes(notes.map((n, i) => (i === index ? { ...n, ...patch } : n)))
          : notes
      );
    },
    [workingNotes]
  );

  const handleAddNote = useCallback(() => {
    setEditError(null);
    pendingSaveRef.current = true;
    setSaveState("saving");
    setWorkingNotes((current) => {
      const list = current ?? [];
      const last = list.length > 0 ? list[list.length - 1] : null;
      const pitch = last ? last.pitch : 60;
      const newNote: Note = {
        pitch,
        pitch_name: midiNoteName(pitch),
        start_time: last
          ? Number((last.start_time + last.duration).toFixed(3))
          : 0,
        duration: 0.5,
        confidence: 1,
      };
      return sortNotes([...list, newNote]);
    });
  }, []);

  // v0.9.3: "+" on a row stacks a new note at the SAME start time (a third
  // above), so chords can be built or extended right in the editor.
  const handleAddNoteAt = useCallback((index: number) => {
    setEditError(null);
    pendingSaveRef.current = true;
    setSaveState("saving");
    setWorkingNotes((current) => {
      if (!current || !current[index]) return current;
      const source = current[index];
      const pitch = Math.min(127, source.pitch + 4);
      const newNote: Note = {
        pitch,
        pitch_name: midiNoteName(pitch),
        start_time: source.start_time,
        duration: source.duration,
        confidence: 1,
        ...(source.group ? { group: source.group } : {}),
        // Match the source's loudness so the new note blends into the chord.
        ...(source.velocity != null ? { velocity: source.velocity } : {}),
      };
      return sortNotes([...current, newNote]);
    });
  }, []);

  // ----- Chord markers (v0.9): a working copy with its own debounced save.
  // Chords live alongside the notes in transcription.json; note edits never
  // touch them, and every export (JSON/MusicXML/PDF/chart) includes them.
  const [chords, setChords] = useState<ChordMarker[] | null>(null);
  const [chordSaveState, setChordSaveState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [chordsError, setChordsError] = useState<string | null>(null);
  const [suggestBusy, setSuggestBusy] = useState(false);
  const [suggestNote, setSuggestNote] = useState<string | null>(null);
  const pendingChordSaveRef = useRef(false);

  useEffect(() => {
    if (!pendingChordSaveRef.current || chords === null) return;
    const timer = setTimeout(async () => {
      try {
        await updateChords(projectId, chords);
        pendingChordSaveRef.current = false;
        setChordSaveState("saved");
        setChordsError(null);
        // Sheet/tab re-fetch so the engraved chord symbols update too.
        setNotesVersion((v) => v + 1);
      } catch (err) {
        setChordSaveState("error");
        setChordsError(
          err instanceof ApiError
            ? err.message
            : "Couldn't save the chords — check that the backend is running."
        );
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [chords, projectId]);

  const applyChords = useCallback(
    (updater: (list: ChordMarker[]) => ChordMarker[]) => {
      pendingChordSaveRef.current = true;
      setChordSaveState("saving");
      setSuggestNote(null);
      setChords((current) =>
        current
          ? [...updater(current)].sort((a, b) => a.start_time - b.start_time)
          : current
      );
    },
    []
  );

  const handleEditChord = useCallback(
    (index: number, field: "name" | "start_time", raw: string) => {
      const current = chords?.[index];
      if (!current) return;
      if (field === "name") {
        const name = raw.trim();
        if (!isValidChordName(name)) {
          setChordsError(
            `"${name || "(empty)"}" isn't a valid chord name. Chord names ` +
              "start with a letter A–G, like C, Am, F#m7, Bb or G/B " +
              `(up to ${MAX_CHORD_NAME_LEN} characters).`
          );
          return;
        }
        if (name === current.name) {
          setChordsError(null);
          return;
        }
        setChordsError(null);
        applyChords((list) =>
          list.map((c, i) => (i === index ? { ...c, name } : c))
        );
      } else {
        const value = Number(raw);
        if (raw.trim() === "" || !Number.isFinite(value) || value < 0) {
          setChordsError(
            "Chord start time must be a number of seconds, 0 or more (e.g. 2 or 2.5)."
          );
          return;
        }
        if (Math.abs(value - current.start_time) < 1e-9) {
          setChordsError(null);
          return;
        }
        setChordsError(null);
        applyChords((list) =>
          list.map((c, i) => (i === index ? { ...c, start_time: value } : c))
        );
      }
    },
    [chords, applyChords]
  );

  const handleAddChord = useCallback(() => {
    setChordsError(null);
    applyChords((list) => [
      ...list,
      {
        name: "C",
        start_time: list.length
          ? Number((list[list.length - 1].start_time + 2).toFixed(3))
          : 0,
      },
    ]);
  }, [applyChords]);

  const handleDeleteChord = useCallback(
    (index: number) => {
      setChordsError(null);
      applyChords((list) => list.filter((_, i) => i !== index));
    },
    [applyChords]
  );

  const handleResetChords = useCallback(() => {
    if (
      !window.confirm(
        "Remove all chords? This clears the chord list (the melody is not affected)."
      )
    ) {
      return;
    }
    setChordsError(null);
    applyChords(() => []);
  }, [applyChords]);

  const handleSuggestChords = useCallback(async () => {
    if (
      chords &&
      chords.length > 0 &&
      !window.confirm("Replace the current chords with fresh suggestions?")
    ) {
      return;
    }
    setSuggestBusy(true);
    setChordsError(null);
    try {
      const result = await suggestChordsApi(projectId);
      pendingChordSaveRef.current = false; // the backend already saved them
      setChords(result.chords);
      setSuggestNote(result.message);
      setChordSaveState("saved");
      setNotesVersion((v) => v + 1);
    } catch (err) {
      setChordSaveState("error");
      setChordsError(
        err instanceof ApiError
          ? err.message
          : "Couldn't suggest chords — check that the backend is running."
      );
    } finally {
      setSuggestBusy(false);
    }
  }, [chords, projectId]);

  const handleResetNotes = useCallback(async () => {
    setSaveState("saving");
    try {
      const data = await resetNotes(projectId);
      pendingSaveRef.current = false;
      setWorkingNotes(data.notes);
      setNotes(data);
      setSaveState("idle");
      setSaveError(null);
      setEditError(null);
      // Resetting notes keeps the chords (the backend preserves them).
      setChords(data.chords ?? []);
      setNotesVersion((v) => v + 1);
    } catch (err) {
      setSaveState("error");
      setSaveError(
        err instanceof ApiError
          ? err.message
          : "Couldn't reset the notes — check that the backend is running."
      );
    }
  }, [projectId]);

  async function handlePdfDownload() {
    setPdfDownloading(true);
    setPdfError(null);
    try {
      const blob = await fetchPdf(projectId, instrumentKey, sheetStyle);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `transcription-${instrumentKey.replace(/_/g, "-")}${sheetStyle === "raw" ? "-raw" : ""}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setPdfError(
        err instanceof ApiError
          ? err.message
          : "Couldn't download the PDF. Check that the backend is still running, then try again."
      );
    } finally {
      setPdfDownloading(false);
    }
  }

  // Reusable refetch for event handlers (e.g. re-syncing status after a
  // transcribe attempt). Not called directly from an effect body.
  const refetchProject = useCallback(async () => {
    try {
      const data = await getProject(projectId);
      setProject(data);
      setLoadError(null);
      return data;
    } catch (err) {
      setLoadError(
        err instanceof ApiError ? err.message : "Failed to load project."
      );
      return null;
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    getProject(projectId)
      .then((data) => {
        if (!cancelled) {
          setProject(data);
          setLoadError(null);
          // Adopt any setup choices already stored on the project.
          if (
            data.instrument &&
            INSTRUMENTS.some((i) => i.key === data.instrument)
          ) {
            setSetupInstrument(data.instrument);
            setInstrumentKey(data.instrument);
          }
          if (
            data.mode === "direct_transcription" ||
            data.mode === "solo_arrangement"
          ) {
            setSetupMode(data.mode);
          }
          if (data.time_signature) setSetupTs(data.time_signature);
          if (data.key_signature) setSetupKey(data.key_signature);
          if (data.rhythm_detail === "precise") setSetupRhythm("precise");
          if (data.note_detection === "poly" || data.note_detection === "melody") {
            setSetupDetection(data.note_detection);
            detectionTouchedRef.current = true;
          }
          if (
            data.arrangement_focus === "main_melody" ||
            data.arrangement_focus === "melody_support" ||
            data.arrangement_focus === "piano_style"
          ) {
            setSetupFocus(data.arrangement_focus);
          }
          if (
            data.arrangement_difficulty === "easy" ||
            data.arrangement_difficulty === "medium"
          ) {
            setSetupDifficulty(data.arrangement_difficulty);
          }
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError ? err.message : "Failed to load project."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (project?.status !== "transcribed") {
      return;
    }
    let cancelled = false;
    getNotes(projectId)
      .then((data) => {
        if (!cancelled) {
          setNotes(data);
          setWorkingNotes(data.notes);
          pendingSaveRef.current = false;
          setSaveState("idle");
          setChords(data.chords ?? []);
          pendingChordSaveRef.current = false;
          setChordSaveState("idle");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setNotesError(
            err instanceof ApiError ? err.message : "Failed to load notes."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [project?.status, projectId]);

  // Ticks a visible elapsed-time counter while transcription is in flight.
  // The counter is reset in handleTranscribe, not here, so the effect only
  // manages the interval.
  useEffect(() => {
    if (!transcribing) {
      return;
    }
    const interval = setInterval(
      () => setElapsedSeconds((s) => s + 1),
      1000
    );
    return () => clearInterval(interval);
  }, [transcribing]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setUploadError("Choose an audio file first.");
      return;
    }
    // Instant client-side checks so the user isn't left waiting for the
    // server to reject an obviously wrong file.
    const lowerName = file.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
      setUploadError(
        `"${file.name}" doesn't look like a supported audio file. Please choose a file ending in ${ACCEPTED_EXTENSIONS.join(", ")}.`
      );
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError(
        `"${file.name}" is ${(file.size / (1024 * 1024)).toFixed(0)}MB, which is over the 50MB limit. Try a shorter recording, or export it as .mp3 to make it smaller.`
      );
      return;
    }
    if (file.size === 0) {
      setUploadError(
        `"${file.name}" is empty (0 bytes). Please pick the audio file again.`
      );
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const updated = await uploadAudio(projectId, file);
      setProject(updated);
      // A new file makes any previous results and errors stale.
      setNotes(null);
      setWorkingNotes(null);
      pendingSaveRef.current = false;
      setSaveState("idle");
      setNotesError(null);
      setTranscribeError(null);
      setChords(null);
      pendingChordSaveRef.current = false;
      setChordSaveState("idle");
      setChordsError(null);
      setSuggestNote(null);
      setSetupError(null);
      setFile(null);
      setReplacingAudio(false);
    } catch (err) {
      setUploadError(
        err instanceof ApiError
          ? err.message
          : "Uploading failed — check that the backend is still running, then try again."
      );
    } finally {
      setUploading(false);
    }
  }

  /** Validate the setup choices, save them, then run the transcription. */
  async function handleStartTranscription() {
    if (startBusy || transcribing) return; // no double-starts
    if (!setupInstrument) {
      setSetupError(
        "Choose an instrument first — click one of the instrument cards above."
      );
      return;
    }
    if (!setupMode) {
      setSetupError(
        "Choose a transcription mode — Direct transcription or Solo arrangement."
      );
      return;
    }
    setSetupError(null);
    setStartBusy(true);
    try {
      const updated = await saveProjectSettings(projectId, {
        instrument: setupInstrument,
        mode: setupMode,
        time_signature: setupTs,
        key_signature: setupKey,
        rhythm_detail: setupRhythm,
        note_detection: setupDetection,
        arrangement_focus: setupFocus,
        arrangement_difficulty: setupDifficulty,
      });
      setProject(updated);
      setInstrumentKey(setupInstrument);
    } catch (err) {
      setSetupError(
        err instanceof ApiError
          ? err.message
          : "Couldn't save the settings — check that the backend is running."
      );
      setStartBusy(false);
      return;
    }
    try {
      await handleTranscribe();
    } finally {
      setStartBusy(false);
    }
  }

  async function handleTranscribe() {
    setElapsedSeconds(0);
    setTranscribing(true);
    setTranscribeError(null);
    try {
      const updated = await transcribeProject(projectId);
      setProject(updated);
    } catch (err) {
      setTranscribeError(
        err instanceof ApiError
          ? err.message
          : "Transcription was interrupted — check that the backend is still running, then try again."
      );
      // The backend may still have flipped status to "failed"; refetch to
      // stay in sync either way.
      await refetchProject();
    } finally {
      setTranscribing(false);
    }
  }

  const [sourceMode, setSourceMode] = useState<"file" | "youtube">("file");
  const [ytUrl, setYtUrl] = useState("");
  const [ytRights, setYtRights] = useState(false);
  const [ytImporting, setYtImporting] = useState(false);
  const [ytError, setYtError] = useState<string | null>(null);

  async function handleYoutubeImport() {
    setYtImporting(true);
    setYtError(null);
    try {
      const updated = await importYoutube(projectId, ytUrl.trim(), ytRights);
      setProject(updated);
      // Fresh audio: clear anything from a previous transcription/edit.
      setNotes(null);
      setWorkingNotes(null);
      pendingSaveRef.current = false;
      setSaveState("idle");
      setSaveError(null);
      setNotesError(null);
      setTranscribeError(null);
      setChords(null);
      pendingChordSaveRef.current = false;
      setChordSaveState("idle");
      setChordsError(null);
      setSuggestNote(null);
      setSetupError(null);
      setReplacingAudio(false);
      setYtUrl("");
      setYtRights(false);
      // Land on the setup step (instrument, mode, advanced settings) —
      // transcription starts when the user clicks Start transcription.
    } catch (err) {
      setYtError(
        err instanceof ApiError
          ? err.message
          : "YouTube import failed — check that the backend is running, then try again."
      );
    } finally {
      setYtImporting(false);
    }
  }

  const melodyEnd =
    workingNotes && workingNotes.length > 0
      ? Math.max(...workingNotes.map((n) => n.start_time + n.duration))
      : 0;

  // Bar grid for chords/strip copy: 4/4 bars are 2s, 3/4 and 6/8 are 1.5s
  // (fixed 120 BPM) — mirrors the backend's _project_seconds_per_bar.
  const projectTimeSignature =
    project?.time_signature === "3/4" || project?.time_signature === "6/8"
      ? project.time_signature
      : "4/4";
  const secondsPerBar = projectTimeSignature === "4/4" ? 2 : 1.5;

  const showUploadForm =
    project?.status === "created" || replacingAudio;

  const sourceBusy = uploading || ytImporting;

  const uploadForm = (
    <section className="rounded border border-gray-300 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-medium">
          {replacingAudio ? "Replace the audio" : "Add audio"}
        </h2>
        {replacingAudio && (
          <button
            type="button"
            onClick={() => {
              setReplacingAudio(false);
              setUploadError(null);
              setYtError(null);
              setFile(null);
            }}
            disabled={sourceBusy}
            className="text-sm text-gray-600 hover:underline disabled:opacity-50"
          >
            Cancel
          </button>
        )}
      </div>

      <div className="mb-3 flex gap-2">
        <button
          type="button"
          onClick={() => setSourceMode("file")}
          disabled={sourceBusy}
          data-testid="source-file"
          className={`rounded px-3 py-1.5 text-sm font-medium ${
            sourceMode === "file"
              ? "bg-blue-600 text-white"
              : "border border-gray-400 hover:bg-gray-50"
          }`}
        >
          Upload audio file
        </button>
        <button
          type="button"
          onClick={() => setSourceMode("youtube")}
          disabled={sourceBusy}
          data-testid="source-youtube"
          className={`rounded px-3 py-1.5 text-sm font-medium ${
            sourceMode === "youtube"
              ? "bg-blue-600 text-white"
              : "border border-gray-400 hover:bg-gray-50"
          }`}
        >
          Import from YouTube
        </button>
      </div>

      <div className="mb-3">
        <TestFilesNote />
      </div>

      {sourceMode === "file" && (
        <>
          <form onSubmit={handleUpload} className="flex flex-col gap-3">
            <input
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(",")}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setUploadError(null);
              }}
              className="text-sm"
              disabled={uploading}
            />
            <button
              type="submit"
              disabled={uploading}
              className="flex w-fit items-center gap-2 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading && (
                <span
                  className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
                  aria-hidden
                />
              )}
              {uploading ? "Uploading…" : "Upload Audio"}
            </button>
          </form>
          {uploading && (
            <p className="mt-2 text-sm text-gray-600">
              Sending {file?.name} to the server — large files can take a moment.
            </p>
          )}
          {uploadError && (
            <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {uploadError}
            </p>
          )}
        </>
      )}

      {sourceMode === "youtube" && (
        <div className="flex flex-col gap-3">
          <input
            type="url"
            value={ytUrl}
            onChange={(e) => {
              setYtUrl(e.target.value);
              setYtError(null);
            }}
            placeholder="https://www.youtube.com/watch?v=…"
            disabled={ytImporting}
            data-testid="yt-url"
            className="rounded border border-gray-400 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <label className="flex items-start gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={ytRights}
              onChange={(e) => setYtRights(e.target.checked)}
              disabled={ytImporting}
              data-testid="yt-rights"
              className="mt-0.5"
            />
            <span>
              I confirm I own this content or have permission to process it
              for private transcription/arrangement use.
            </span>
          </label>
          <p className="text-xs text-gray-600">
            BandChart AI does not publish, share or create a public library
            from your transcription.
          </p>
          <button
            type="button"
            onClick={handleYoutubeImport}
            disabled={ytImporting || !ytUrl.trim() || !ytRights}
            data-testid="yt-import"
            className="flex w-fit items-center gap-2 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {ytImporting && (
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
                aria-hidden
              />
            )}
            {ytImporting ? "Importing…" : "Import YouTube audio"}
          </button>
          {ytImporting && (
            <p className="text-sm text-gray-600">
              Importing from YouTube — checking the link, extracting the audio
              and converting it to WAV… this can take a minute for longer
              clips. When it&apos;s done you&apos;ll choose your instrument
              and start the transcription.
            </p>
          )}
          {ytError && (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              <p>{ytError}</p>
              <button
                type="button"
                onClick={() => setSourceMode("file")}
                data-testid="yt-switch-to-upload"
                className="mt-2 rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
              >
                Switch to Upload audio file
              </button>
            </div>
          )}
          <p className="text-xs text-gray-600">
            If YouTube blocks import, download or record the audio yourself
            and use Upload audio file instead.
          </p>
          <p className="text-xs text-gray-600">
            YouTube import uses the same transcription engine as uploads. It
            works best on clear single melody lines or simple piano chords,
            not full band mixes. Videos longer than 10 minutes are rejected
            for now — short clips work best.
          </p>
        </div>
      )}
    </section>
  );

  const transcribeProgress = transcribing && (
    <div className="mt-4 flex items-center gap-3 rounded border border-yellow-200 bg-yellow-50 p-3">
      <span
        className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-yellow-600 border-t-transparent"
        aria-hidden
      />
      <p className="text-sm text-yellow-800">
        Transcribing… {elapsedSeconds}s elapsed. This usually takes a fraction
        of the recording&apos;s length — a 3-minute song is often done in
        about a minute. Keep this tab open.
      </p>
    </div>
  );

  const startAgainButton = !transcribing && !replacingAudio && (
    <button
      type="button"
      onClick={() => {
        setReplacingAudio(true);
        setUploadError(null);
      }}
      className="w-fit rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50"
    >
      Start again with a different file
    </button>
  );

  if (loadError) {
    return (
      <main className="mx-auto max-w-2xl p-6">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to projects
        </Link>
        <p className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {loadError}
        </p>
      </main>
    );
  }

  if (!project) {
    return (
      <main className="mx-auto max-w-2xl p-6">
        <p className="text-sm text-gray-600">Loading project…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <div>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to projects
        </Link>
      </div>

      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          <p className="text-xs text-gray-600">
            Created {new Date(project.created_at).toLocaleString()}
          </p>
        </div>
        <StatusBadge status={project.status} />
      </header>

      {showUploadForm && uploadForm}

      {project.status === "uploaded" && !replacingAudio && (
        <section className="rounded border border-gray-300 p-4">
          <h2 className="mb-1 text-lg font-medium">Set up your sheet music</h2>
          {project.audio_filename && (
            <p className="mb-3 text-xs text-gray-600">
              {project.source_type === "youtube" && project.source_url
                ? `Imported from YouTube: ${project.source_url}`
                : `File: ${project.audio_filename}`}
            </p>
          )}
          <audio controls src={audioUrl(projectId)} className="w-full">
            Your browser does not support the audio element.
          </audio>

          <div className="mt-5">
            <h3 className="mb-2 text-sm font-semibold">
              1. Choose your instrument
            </h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
              {INSTRUMENTS.map((inst) => (
                <button
                  key={inst.key}
                  type="button"
                  onClick={() => {
                    setSetupInstrument(inst.key);
                    setSetupError(null);
                    if (!detectionTouchedRef.current) {
                      setSetupDetection(defaultNoteDetection(inst.key));
                    }
                  }}
                  data-testid={`pick-${inst.key}`}
                  className={`rounded border px-3 py-2 text-left text-sm ${
                    setupInstrument === inst.key
                      ? "border-blue-600 bg-blue-50 font-medium text-blue-900"
                      : "border-gray-400 hover:bg-gray-50"
                  }`}
                >
                  {inst.label}
                  {inst.fretted && (
                    <span className="block text-[11px] font-normal text-gray-600">
                      shows TAB
                    </span>
                  )}
                  {inst.key === "piano" && (
                    <span className="block text-[11px] font-normal text-gray-600">
                      grand staff
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5">
            <h3 className="mb-2 text-sm font-semibold">
              2. How should we transcribe it?
            </h3>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {MODE_OPTIONS.map((mode) => (
                <button
                  key={mode.key}
                  type="button"
                  onClick={() => {
                    setSetupMode(mode.key);
                    setSetupError(null);
                    if (!detectionTouchedRef.current) {
                      setSetupDetection(defaultNoteDetection(setupInstrument ?? "concert"));
                    }
                  }}
                  data-testid={`mode-${mode.key === "direct_transcription" ? "direct" : "solo"}`}
                  className={`rounded border px-3 py-2 text-left ${
                    setupMode === mode.key
                      ? "border-blue-600 bg-blue-50"
                      : "border-gray-400 hover:bg-gray-50"
                  }`}
                >
                  <span className="block text-sm font-medium">
                    {mode.label}
                  </span>
                  <span className="block text-xs text-gray-600">
                    {mode.description}
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-600">
              BandChart is melody-first. Full band separation is coming later.
            </p>
          </div>

          <details className="mt-5 rounded border border-gray-300 p-3">
            <summary className="cursor-pointer text-sm font-semibold">
              3. Advanced settings (optional)
            </summary>
            <div className="mt-3 flex flex-col gap-3 text-sm">
              <label className="flex items-center gap-2">
                <span className="w-32 text-gray-600">Time signature</span>
                <select
                  value={setupTs}
                  onChange={(e) => setSetupTs(e.target.value)}
                  data-testid="setup-ts"
                  className="rounded border border-gray-400 px-2 py-1"
                >
                  {TIME_SIGNATURE_OPTIONS.map((ts) => (
                    <option key={ts} value={ts}>
                      {ts === "predict"
                        ? "Let us predict (assumes 4/4 for now)"
                        : ts}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2">
                <span className="w-32 text-gray-600">Key signature</span>
                <select
                  value={setupKey}
                  onChange={(e) => setSetupKey(e.target.value)}
                  data-testid="setup-key"
                  className="rounded border border-gray-400 px-2 py-1"
                >
                  {KEY_OPTIONS.map((k) => (
                    <option key={k} value={k}>
                      {k === "predict" ? "Let us predict" : k}
                    </option>
                  ))}
                </select>
              </label>
              <fieldset>
                <legend className="mb-1 text-gray-600">Rhythm detail</legend>
                <div className="flex flex-col gap-1">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="rhythmDetail"
                      checked={setupRhythm === "readable"}
                      onChange={() => setSetupRhythm("readable")}
                      data-testid="rhythm-readable"
                    />
                    Readable (recommended) — smoother, simpler notation
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="rhythmDetail"
                      checked={setupRhythm === "precise"}
                      onChange={() => setSetupRhythm("precise")}
                      data-testid="rhythm-precise"
                    />
                    Precise — closer to the detected timings
                  </label>
                </div>
              </fieldset>
              <fieldset>
                <legend className="mb-1 text-gray-700">Note detection</legend>
                <div className="flex flex-col gap-1">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="noteDetection"
                      checked={setupDetection === "melody"}
                      onChange={() => {
                        detectionTouchedRef.current = true;
                        setSetupDetection("melody");
                      }}
                      data-testid="detection-melody"
                    />
                    Melody only (recommended for most instruments)
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="noteDetection"
                      checked={setupDetection === "poly"}
                      onChange={() => {
                        detectionTouchedRef.current = true;
                        setSetupDetection("poly");
                      }}
                      data-testid="detection-poly"
                    />
                    Basic Pitch / multiple notes
                  </label>
                </div>
                <p className="mt-1 text-xs text-gray-600">
                  Multiple-note detection works best with clear piano or
                  simple chords. Dense songs may still need editing. Piano +
                  Direct transcription turns it on automatically.
                </p>
              </fieldset>

              {setupMode === "solo_arrangement" && (
                <>
                  <fieldset>
                    <legend className="mb-1 text-gray-700">
                      Arrangement focus
                    </legend>
                    <div className="flex flex-col gap-1">
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="arrangementFocus"
                          checked={setupFocus === "main_melody"}
                          onChange={() => setSetupFocus("main_melody")}
                          data-testid="focus-main-melody"
                        />
                        Main melody (recommended)
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="arrangementFocus"
                          checked={setupFocus === "melody_support"}
                          onChange={() => setSetupFocus("melody_support")}
                          data-testid="focus-melody-support"
                        />
                        Melody + simple support
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="arrangementFocus"
                          checked={setupFocus === "piano_style"}
                          onChange={() => setSetupFocus("piano_style")}
                          data-testid="focus-piano-style"
                        />
                        Piano-style arrangement
                      </label>
                    </div>
                    <p className="mt-1 text-xs text-gray-600">
                      Support notes are only added for Piano and Guitar — a
                      small number of simple notes under the melody, not a
                      full reduction of everything detected.
                    </p>
                  </fieldset>
                  <fieldset>
                    <legend className="mb-1 text-gray-700">
                      Arrangement difficulty
                    </legend>
                    <div className="flex flex-col gap-1">
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="arrangementDifficulty"
                          checked={setupDifficulty === "easy"}
                          onChange={() => setSetupDifficulty("easy")}
                          data-testid="difficulty-easy"
                        />
                        Easy (recommended)
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="arrangementDifficulty"
                          checked={setupDifficulty === "medium"}
                          onChange={() => setSetupDifficulty("medium")}
                          data-testid="difficulty-medium"
                        />
                        Medium
                      </label>
                    </div>
                  </fieldset>
                </>
              )}
            </div>
          </details>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleStartTranscription}
              disabled={startBusy || transcribing}
              data-testid="start-transcription"
              className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {transcribing
                ? "Transcribing…"
                : startBusy
                  ? "Starting…"
                  : "Start transcription"}
            </button>
            {startAgainButton}
          </div>
          {setupError && (
            <p
              data-testid="setup-error"
              className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700"
            >
              {setupError}
            </p>
          )}
          {transcribeProgress}
          {transcribeError && (
            <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {transcribeError}
            </p>
          )}
        </section>
      )}

      {project.status === "transcribing" && !transcribing && (
        <section className="flex items-center gap-3 rounded border border-yellow-200 bg-yellow-50 p-4">
          <span
            className="h-5 w-5 animate-spin rounded-full border-2 border-yellow-600 border-t-transparent"
            aria-hidden
          />
          <p className="text-sm text-yellow-800">
            Transcription in progress… Reload this page in a little while to
            see the result.
          </p>
        </section>
      )}

      {project.status === "failed" && !replacingAudio && (
        <section className="rounded border border-red-200 bg-red-50 p-4">
          <h2 className="mb-2 text-lg font-medium text-red-800">
            Transcription failed
          </h2>
          {project.error && (
            <p className="mb-3 whitespace-pre-wrap text-sm text-red-700">
              {project.error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleTranscribe}
              disabled={transcribing}
              className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {transcribing ? "Retrying…" : "Retry Transcription"}
            </button>
            {startAgainButton}
          </div>
          {transcribeProgress}
          {transcribeError && !transcribing && (
            <p className="mt-2 text-sm text-red-600">{transcribeError}</p>
          )}
        </section>
      )}

      {project.status === "transcribed" && !replacingAudio && (
        <section className="flex flex-col gap-4">
          <div>
            <audio controls src={audioUrl(projectId)} className="w-full">
              Your browser does not support the audio element.
            </audio>
            {project.source_type === "youtube" && project.source_url && (
              <p className="mt-1 text-xs text-gray-600">
                Imported from YouTube: {project.source_url}
              </p>
            )}
            {project.mode === "solo_arrangement" && (
              <p className="mt-1 text-xs text-gray-700" data-testid="solo-badge">
                Solo arrangement — the main melody arranged as a playable solo
                for your instrument (melody-first).
              </p>
            )}
            {notes?.detection === "poly" && (
              <p
                className="mt-2 rounded border border-blue-200 bg-blue-50 p-2 text-xs text-blue-900"
                data-testid="poly-note"
              >
                Multiple-note detection works best with clear piano or simple
                chords. Dense songs may still need editing.
              </p>
            )}
            {notes?.detection_note && (
              <p
                className="mt-2 rounded border border-yellow-300 bg-yellow-50 p-2 text-sm text-yellow-900"
                data-testid="detection-note"
              >
                {notes.detection_note}
              </p>
            )}
            {notes?.engine_used && (
              <div
                className="mt-2 rounded border border-gray-300 bg-gray-50 p-2 text-xs text-gray-700"
                data-testid="engine-status"
              >
                <p>Engine used: {ENGINE_LABELS[notes.engine_used] ?? notes.engine_used}</p>
                <p>Mode: {ROUTING_MODE_LABELS[notes.routing_mode ?? ""] ?? "Melody only"}</p>
                <p>Fallback: {notes.fallback_reason ?? "none"}</p>
                <p>
                  Warnings:{" "}
                  {[
                    notes.difficulty &&
                    notes.difficulty !== "Simple melody" &&
                    notes.difficulty !== "No notes detected"
                      ? notes.difficulty
                      : null,
                    ...(notes.warnings ?? []),
                  ]
                    .filter(Boolean)
                    .join("; ") || "none"}
                </p>
              </div>
            )}
            {notes?.arrangement_source && (
              <div
                className="mt-2 rounded border border-blue-200 bg-blue-50 p-2 text-xs text-blue-900"
                data-testid="arrangement-status"
              >
                <p>Mode: Solo arrangement</p>
                <p>
                  Source:{" "}
                  {ARRANGEMENT_SOURCE_LABELS[notes.arrangement_source] ??
                    notes.arrangement_source}
                </p>
                <p>
                  Engine:{" "}
                  {notes.separation_engine === "demucs" ? "Demucs + " : ""}
                  {ENGINE_LABELS[notes.engine_used ?? ""] ?? notes.engine_used}
                </p>
                <p>
                  Arrangement focus:{" "}
                  {ARRANGEMENT_FOCUS_LABELS[notes.arrangement_focus ?? ""] ??
                    notes.arrangement_focus}
                </p>
                <p>
                  Warnings:{" "}
                  {[
                    notes.difficulty &&
                    notes.difficulty !== "Simple melody" &&
                    notes.difficulty !== "No notes detected"
                      ? notes.difficulty
                      : null,
                    ...(notes.warnings ?? []),
                  ]
                    .filter(Boolean)
                    .join("; ") || "none"}
                </p>
              </div>
            )}
          </div>

          <div className="rounded border border-gray-300 p-4">
            <label
              htmlFor="instrument"
              className="mb-1 block text-sm font-medium"
            >
              Solo instrument
            </label>
            <select
              id="instrument"
              value={instrumentKey}
              onChange={(e) => setInstrumentKey(e.target.value)}
              className="rounded border border-gray-400 px-3 py-2 text-sm"
            >
              {INSTRUMENTS.map((inst) => (
                <option key={inst.key} value={inst.key}>
                  {inst.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-gray-600">
              {selectedInstrument.fretted
                ? `${selectedInstrument.label} shows tab output below — string lines with fret numbers, in ${selectedInstrument.tuning} tuning. Notes that don't fit the instrument's range are flagged clearly.`
                : selectedInstrument.writtenOffset > 0
                  ? `${selectedInstrument.label} is a transposing instrument — its written part is ${selectedInstrument.writtenOffset} semitones above the detected concert pitch. The note table and MusicXML download below use the written pitch.`
                  : "This instrument reads at concert pitch, so written and detected pitches are the same."}
            </p>

            <fieldset className="mt-4">
              <legend className="mb-1 block text-sm font-medium">
                Sheet music style
              </legend>
              <div className="flex flex-col gap-1 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sheetStyle"
                    value="clean"
                    checked={sheetStyle === "clean"}
                    onChange={() => setSheetStyle("clean")}
                  />
                  Cleaned sheet music (recommended) — smooths wobbles, merges
                  repeated notes, simpler rhythms and key
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sheetStyle"
                    value="raw"
                    checked={sheetStyle === "raw"}
                    onChange={() => setSheetStyle("raw")}
                  />
                  Raw transcription — every detected note, exactly as heard
                </label>
              </div>
            </fieldset>
          </div>

          <div className="flex flex-wrap gap-4">
            <a
              href={midiDownloadUrl(projectId)}
              download
              className="rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Download MIDI
            </a>
            <a
              href={jsonDownloadUrl(projectId)}
              download
              className="rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Download JSON
            </a>
            <a
              href={musicxmlDownloadUrl(projectId, instrumentKey, sheetStyle)}
              download
              className="rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Download MusicXML ({selectedInstrument.label})
            </a>
            {selectedInstrument.fretted && (
              <a
                href={tabDownloadUrl(projectId, instrumentKey)}
                download
                data-testid="download-tab"
                className="rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50"
              >
                Download TAB ({selectedInstrument.label})
              </a>
            )}
            <button
              type="button"
              onClick={handlePdfDownload}
              disabled={pdfDownloading}
              className="flex items-center gap-2 rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pdfDownloading && (
                <span
                  className="h-4 w-4 animate-spin rounded-full border-2 border-gray-500 border-t-transparent"
                  aria-hidden
                />
              )}
              {pdfDownloading
                ? "Preparing PDF…"
                : `Download PDF (${selectedInstrument.label})`}
            </button>
            {startAgainButton}
          </div>

          {selectedInstrument.fretted && (
            <p className="text-xs text-gray-600">
              For {selectedInstrument.label.toLowerCase()}, the MusicXML and
              PDF downloads still use staff notation — a proper tab PDF is
              coming in a later version. The TAB download is a plain text
              file you can open anywhere.
            </p>
          )}

          {pdfError && (
            <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {pdfError}
            </p>
          )}

          {notesError && (
            <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {notesError}
            </p>
          )}

          {!notesError && !notes && (
            <p className="text-sm text-gray-600">Loading notes…</p>
          )}

          {notes && notes.note_count === 0 && (
            <div className="rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              <p className="font-medium">No notes were detected.</p>
              <p className="mt-1">
                This usually means the recording was too quiet, too noisy, or
                not a single melody line. Try a recording of one voice or one
                instrument on its own, then use &quot;Start again with a
                different file&quot;.
              </p>
            </div>
          )}

          {notes && workingNotes && workingNotes.length > 0 && (
            <>
              <PlayAlong
                notes={workingNotes}
                instrumentKey={instrumentKey}
                onTick={handlePlayTick}
                registerSeek={registerSeek}
                autoScroll={autoScroll}
                onAutoScrollChange={setAutoScroll}
              />

              {selectedInstrument.fretted ? (
                <div>
                  <h2 className="mb-2 text-lg font-medium">Tab output</h2>
                  <TabView
                    projectId={projectId}
                    instrumentKey={instrumentKey}
                    notesVersion={notesVersion}
                    currentNoteIndex={playNoteIndex}
                    onSeekNote={handleSeekNote}
                    autoScroll={autoScroll}
                  />
                </div>
              ) : (
                <div>
                  <h2 className="mb-2 text-lg font-medium">Sheet music</h2>
                  <SheetMusic
                    projectId={projectId}
                    instrumentKey={instrumentKey}
                    sheetStyle={sheetStyle}
                    notesVersion={notesVersion}
                    playPosition={playPosition}
                    onSeek={handleSeek}
                    autoScroll={autoScroll}
                  />
                </div>
              )}

              <details className="rounded border border-gray-300 p-3">
                <summary className="cursor-pointer text-sm font-medium text-gray-700">
                  Advanced note timeline ({workingNotes.length} notes)
                </summary>
                <div className="mt-3">
                  <NotePreview
                    notes={workingNotes}
                    playheadTime={playPosition}
                    currentNoteIndex={playNoteIndex}
                    autoScroll={autoScroll}
                    onSeek={handleSeek}
                  />
                </div>
              </details>

              {/* v0.9.3: the rough chord tools are parked here, out of the
                  main flow, while the version focus is note detection. */}
              <details
                className="rounded border border-gray-300 p-3"
                data-testid="experimental-tools"
              >
                <summary className="cursor-pointer text-sm font-medium text-gray-700">
                  Experimental tools (chord markers)
                </summary>
                <div className="mt-3 space-y-3">
                  <p className="text-xs text-gray-600">
                    These chord tools are an early experiment and stay hidden
                    here for now. Proper Ultimate Guitar-style chord sheets
                    are a much later feature, probably v5.0.
                  </p>
                  <ChordsPanel
                    projectId={projectId}
                    chords={chords ?? []}
                    melodyEnd={melodyEnd}
                    secondsPerBar={secondsPerBar}
                    timeSignature={projectTimeSignature}
                    saveState={chordSaveState}
                    errorMessage={chordsError}
                    suggestBusy={suggestBusy}
                    suggestNote={suggestNote}
                    onEditChord={handleEditChord}
                    onAddChord={handleAddChord}
                    onDeleteChord={handleDeleteChord}
                    onResetChords={handleResetChords}
                    onSuggestChords={handleSuggestChords}
                  />
                </div>
              </details>

              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-medium">Note detail</h2>
                  <div className="flex items-center gap-3">
                    {saveState === "saving" && (
                      <span className="text-xs text-gray-600">Saving edits…</span>
                    )}
                    {saveState === "saved" && (
                      <span className="text-xs text-green-700" data-testid="edits-saved">
                        Edits saved — downloads use the edited notes.
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={handleResetNotes}
                      data-testid="reset-notes"
                      className="rounded border border-gray-400 px-3 py-1 text-xs font-medium hover:bg-gray-50"
                    >
                      Reset to original transcription
                    </button>
                  </div>
                </div>
                {saveError && (
                  <p className="mb-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                    {saveError}
                  </p>
                )}
                {editError && (
                  <p
                    data-testid="edit-error"
                    className="mb-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700"
                  >
                    {editError}
                  </p>
                )}
                <NoteTable
                  notes={workingNotes}
                  writtenLabel={selectedInstrument.label}
                  writtenOffset={selectedInstrument.writtenOffset}
                  currentIndex={playNoteIndex}
                  autoScroll={autoScroll}
                  onDelete={handleDeleteNote}
                  onEdit={handleEditNote}
                  onSeekNote={handleSeekNote}
                  onAddAt={handleAddNoteAt}
                  showAddAt={notes.detection === "poly"}
                />
                <div className="mt-2 flex flex-wrap items-start justify-between gap-2">
                  <p className="text-xs text-gray-600">
                    Type in a pitch (like G4 or F#3), start time or duration
                    and press Enter (or click away) to fix a wrong note.
                    Click ✕ to delete one. The preview, playback, tab and all
                    downloads update automatically.
                  </p>
                  <button
                    type="button"
                    onClick={handleAddNote}
                    data-testid="add-note"
                    className="rounded border border-gray-400 px-3 py-1 text-xs font-medium hover:bg-gray-50"
                  >
                    + Add a note
                  </button>
                </div>
              </div>
            </>
          )}

          {notes && workingNotes && workingNotes.length === 0 && notes.note_count !== 0 && (
            <div className="rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              <p className="mb-2">All notes have been deleted.</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleResetNotes}
                  className="rounded border border-yellow-400 px-3 py-1 text-xs font-medium hover:bg-yellow-100"
                >
                  Reset to original transcription
                </button>
                <button
                  type="button"
                  onClick={handleAddNote}
                  className="rounded border border-yellow-400 px-3 py-1 text-xs font-medium hover:bg-yellow-100"
                >
                  + Add a note
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
