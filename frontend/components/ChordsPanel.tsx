"use client";

import type { ChordMarker } from "@/lib/api";
import { chordChartDownloadUrl } from "@/lib/api";

// One 4/4 bar = 2 seconds at the app's fixed 120 BPM (3/4 and 6/8 bars are
// 1.5s) — the same grid the sheet music, tab and chord chart use.
export const SECONDS_PER_BAR = 2;

export function chordBarNumber(
  startTime: number,
  secondsPerBar: number = SECONDS_PER_BAR
): number {
  return Math.floor(Math.max(0, startTime) / secondsPerBar) + 1;
}

// Mirrors the backend's chord-name rule (backend/app/chords.py):
// C, Am, F#m7, Bb, G7, Cmaj7, Dm7b5, Esus4, Cadd9, G/B ...
export const CHORD_NAME_RE = /^[A-G][#b]?[A-Za-z0-9°ø+#b]*(\/[A-G][#b]?)?$/;
export const MAX_CHORD_NAME_LEN = 12;

export function isValidChordName(name: string): boolean {
  return (
    name.length > 0 &&
    name.length <= MAX_CHORD_NAME_LEN &&
    CHORD_NAME_RE.test(name)
  );
}

/** Compact bar-grid line like "| C | G | Am F |" shown above sheet and tab. */
export function ChordStrip({
  chords,
  melodyEnd,
  secondsPerBar = SECONDS_PER_BAR,
}: {
  chords: ChordMarker[];
  melodyEnd: number;
  secondsPerBar?: number;
}) {
  if (chords.length === 0) return null;
  const lastBar = Math.max(
    chordBarNumber(chords[chords.length - 1].start_time, secondsPerBar),
    melodyEnd > 0 ? chordBarNumber(Math.max(0, melodyEnd - 1e-9), secondsPerBar) : 1
  );
  const byBar = new Map<number, string[]>();
  for (const c of chords) {
    const bar = chordBarNumber(c.start_time, secondsPerBar);
    byBar.set(bar, [...(byBar.get(bar) ?? []), c.name]);
  }
  const cells: string[] = [];
  for (let bar = 1; bar <= lastBar; bar++) {
    cells.push((byBar.get(bar) ?? []).join(" ") || " ");
  }
  return (
    <div
      data-testid="chord-strip"
      className="mb-2 overflow-x-auto rounded border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-sm text-gray-900"
    >
      {"| " + cells.join(" | ") + " |"}
    </div>
  );
}

interface ChordsPanelProps {
  projectId: string;
  chords: ChordMarker[];
  /** End of the melody in seconds — used to warn about chords past the end. */
  melodyEnd: number;
  /** Bar length in seconds (2 for 4/4, 1.5 for 3/4 and 6/8). */
  secondsPerBar?: number;
  /** The project's time signature, for the helper copy. */
  timeSignature?: string;
  saveState: "idle" | "saving" | "saved" | "error";
  errorMessage: string | null;
  suggestBusy: boolean;
  /** The rough-starting-point reminder returned after Suggest chords. */
  suggestNote: string | null;
  onEditChord: (
    index: number,
    field: "name" | "start_time",
    raw: string
  ) => void;
  onAddChord: () => void;
  onDeleteChord: (index: number) => void;
  onResetChords: () => void;
  onSuggestChords: () => void;
}

/**
 * Beginner-friendly manual chord editor: one row per chord marker with a
 * name box, a start-time box (the matching bar number is shown alongside),
 * and a delete button — plus add / suggest / reset / download-chart actions.
 */
export default function ChordsPanel({
  projectId,
  chords,
  melodyEnd,
  secondsPerBar = SECONDS_PER_BAR,
  timeSignature = "4/4",
  saveState,
  errorMessage,
  suggestBusy,
  suggestNote,
  onEditChord,
  onAddChord,
  onDeleteChord,
  onResetChords,
  onSuggestChords,
}: ChordsPanelProps) {
  const outOfRange = chords.filter((c) => c.start_time > melodyEnd + 1e-6);

  return (
    <section className="rounded border border-gray-300 p-4">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-medium">Chords</h2>
        <div className="flex items-center gap-3">
          {saveState === "saving" && (
            <span className="text-xs text-gray-600">Saving chords…</span>
          )}
          {saveState === "saved" && (
            <span className="text-xs text-green-700" data-testid="chords-saved">
              Chords saved — exports include them.
            </span>
          )}
        </div>
      </div>
      <p className="mb-3 text-xs text-gray-600">
        Add chord names above your melody — like C, Am, F#m7, Bb or G/B. One
        bar is {secondsPerBar} seconds (the app&apos;s fixed 120 bpm,{" "}
        {timeSignature}). Chords appear on the sheet music, in the chord
        line, and in the downloads.
      </p>

      {errorMessage && (
        <p
          data-testid="chords-error"
          className="mb-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700"
        >
          {errorMessage}
        </p>
      )}

      {suggestNote && (
        <p
          data-testid="chords-suggest-note"
          className="mb-2 rounded border border-blue-200 bg-blue-50 p-2 text-sm text-blue-800"
        >
          {suggestNote}
        </p>
      )}

      {outOfRange.length > 0 && (
        <p
          data-testid="chords-warning"
          className="mb-2 rounded border border-yellow-200 bg-yellow-50 p-2 text-sm text-yellow-800"
        >
          {outOfRange.length === 1
            ? `1 chord starts after the melody ends (${melodyEnd.toFixed(1)}s): `
            : `${outOfRange.length} chords start after the melody ends (${melodyEnd.toFixed(1)}s): `}
          {outOfRange.map((c) => `${c.name} at ${c.start_time.toFixed(1)}s`).join(", ")}
          . They stay saved, but won&apos;t sit over any notes.
        </p>
      )}

      {chords.length === 0 ? (
        <p className="mb-3 text-sm text-gray-600" data-testid="chords-empty">
          No chords yet. Click <span className="font-medium">+ Add chord</span>,
          or try <span className="font-medium">Suggest chords from melody</span>.
        </p>
      ) : (
        <div className="mb-3 flex flex-col gap-2">
          {chords.map((chord, i) => (
            <div
              key={`${chord.name}-${chord.start_time}-${i}`}
              className="flex flex-wrap items-center gap-2 text-sm"
            >
              <label className="flex items-center gap-1">
                <span className="text-gray-600">Chord</span>
                <input
                  type="text"
                  defaultValue={chord.name}
                  onBlur={(e) => onEditChord(i, "name", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  data-testid={`chord-name-${i}`}
                  aria-label={`Name of chord ${i + 1}`}
                  className="w-20 rounded border border-gray-400 px-2 py-1"
                />
              </label>
              <label className="flex items-center gap-1">
                <span className="text-gray-600">starts at</span>
                <input
                  type="number"
                  step={0.5}
                  min={0}
                  defaultValue={chord.start_time.toFixed(1)}
                  onBlur={(e) => onEditChord(i, "start_time", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  data-testid={`chord-start-${i}`}
                  aria-label={`Start time of chord ${i + 1}`}
                  className="w-24 rounded border border-gray-400 px-2 py-1"
                />
                <span className="text-gray-600">seconds</span>
              </label>
              <span className="text-xs text-gray-600">
                (bar {chordBarNumber(chord.start_time, secondsPerBar)})
              </span>
              <button
                type="button"
                onClick={() => onDeleteChord(i)}
                title={`Delete ${chord.name}`}
                data-testid={`delete-chord-${i}`}
                className="rounded px-2 py-0.5 text-xs text-red-600 hover:bg-red-50"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onAddChord}
          data-testid="add-chord"
          className="rounded border border-gray-400 px-3 py-1.5 text-sm font-medium hover:bg-gray-50"
        >
          + Add chord
        </button>
        <button
          type="button"
          onClick={onSuggestChords}
          disabled={suggestBusy}
          data-testid="suggest-chords"
          className="flex items-center gap-2 rounded border border-gray-400 px-3 py-1.5 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {suggestBusy && (
            <span
              className="h-3 w-3 animate-spin rounded-full border-2 border-gray-500 border-t-transparent"
              aria-hidden
            />
          )}
          Suggest chords from melody (rough)
        </button>
        {chords.length > 0 ? (
          <a
            href={chordChartDownloadUrl(projectId)}
            download
            data-testid="download-chords"
            className="rounded border border-gray-400 px-3 py-1.5 text-sm font-medium hover:bg-gray-50"
          >
            Download Chord Chart
          </a>
        ) : (
          <button
            type="button"
            disabled
            title="Add at least one chord first"
            className="cursor-not-allowed rounded border border-gray-400 px-3 py-1.5 text-sm font-medium opacity-50"
          >
            Download Chord Chart
          </button>
        )}
        {chords.length > 0 && (
          <button
            type="button"
            onClick={onResetChords}
            data-testid="reset-chords"
            className="rounded border border-gray-400 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            Reset chords (remove all)
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-gray-600">
        Chord suggestions are a rough starting point. Please check and edit
        them. This is not automatic chord detection from the recording — the
        app still hears one melody line at a time.
      </p>
    </section>
  );
}
