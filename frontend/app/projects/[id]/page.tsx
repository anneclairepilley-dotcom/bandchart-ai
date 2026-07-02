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
  jsonDownloadUrl,
  midiDownloadUrl,
  musicxmlDownloadUrl,
  resetNotes,
  transcribeProject,
  updateNotes,
  uploadAudio,
  type NotesResponse,
  type Project,
  type SheetStyle,
} from "@/lib/api";
import { INSTRUMENTS, midiNoteName } from "@/lib/instruments";
import StatusBadge from "@/components/StatusBadge";
import NotePreview from "@/components/NotePreview";
import PlayAlong from "@/components/PlayAlong";
import SheetMusic from "@/components/SheetMusic";
import type { Note } from "@/lib/api";

// Memoized so the 60fps play-along position updates don't re-render every
// table row; the current-note index only changes when the note changes.
const NoteTable = memo(function NoteTable({
  notes,
  writtenLabel,
  writtenOffset,
  currentIndex,
  autoScroll,
  onDelete,
}: {
  notes: Note[];
  writtenLabel: string;
  writtenOffset: number;
  currentIndex: number | null;
  autoScroll: boolean;
  onDelete: (index: number) => void;
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
    <div ref={boxRef} className="max-h-96 overflow-y-auto rounded border border-gray-200">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-gray-50">
          <tr>
            <th className="p-2 font-medium">Concert pitch</th>
            <th className="p-2 font-medium">Written ({writtenLabel})</th>
            <th className="p-2 font-medium">Start (s)</th>
            <th className="p-2 font-medium">Duration (s)</th>
            <th className="p-2 font-medium">Confidence</th>
            <th className="p-2 font-medium">
              <span className="sr-only">Delete</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {notes.map((note, i) => (
            <tr
              key={`${note.start_time}-${note.pitch}-${i}`}
              data-playing={i === currentIndex ? "true" : undefined}
              className={
                i === currentIndex
                  ? "border-t border-orange-200 bg-orange-100"
                  : "border-t border-gray-100 odd:bg-white even:bg-gray-50"
              }
            >
              <td className="p-2">{note.pitch_name}</td>
              <td className="p-2">{midiNoteName(note.pitch + writtenOffset)}</td>
              <td className="p-2">{note.start_time.toFixed(3)}</td>
              <td className="p-2">{note.duration.toFixed(3)}</td>
              <td className="p-2">{(note.confidence * 100).toFixed(0)}%</td>
              <td className="p-2 text-right">
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

  const handleResetNotes = useCallback(async () => {
    setSaveState("saving");
    try {
      const data = await resetNotes(projectId);
      pendingSaveRef.current = false;
      setWorkingNotes(data.notes);
      setNotes(data);
      setSaveState("idle");
      setSaveError(null);
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

  const showUploadForm =
    project?.status === "created" || replacingAudio;

  const uploadForm = (
    <section className="rounded border border-gray-200 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-medium">
          {replacingAudio ? "Upload a different file" : "Upload audio"}
        </h2>
        {replacingAudio && (
          <button
            type="button"
            onClick={() => {
              setReplacingAudio(false);
              setUploadError(null);
              setFile(null);
            }}
            disabled={uploading}
            className="text-sm text-gray-500 hover:underline disabled:opacity-50"
          >
            Cancel
          </button>
        )}
      </div>
      <div className="mb-3">
        <TestFilesNote />
      </div>
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
        <p className="mt-2 text-sm text-gray-500">
          Sending {file?.name} to the server — large files can take a moment.
        </p>
      )}
      {uploadError && (
        <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {uploadError}
        </p>
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
      className="w-fit rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
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
        <p className="text-sm text-gray-500">Loading project…</p>
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
          <p className="text-xs text-gray-500">
            Created {new Date(project.created_at).toLocaleString()}
          </p>
        </div>
        <StatusBadge status={project.status} />
      </header>

      {showUploadForm && uploadForm}

      {project.status === "uploaded" && !replacingAudio && (
        <section className="rounded border border-gray-200 p-4">
          <h2 className="mb-1 text-lg font-medium">Audio</h2>
          {project.audio_filename && (
            <p className="mb-3 text-xs text-gray-500">
              File: {project.audio_filename}
            </p>
          )}
          <audio controls src={audioUrl(projectId)} className="w-full">
            Your browser does not support the audio element.
          </audio>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleTranscribe}
              disabled={transcribing}
              className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {transcribing ? "Transcribing…" : "Run Transcription"}
            </button>
            {startAgainButton}
          </div>
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
          <div className="flex items-center gap-4">
            <audio controls src={audioUrl(projectId)} className="w-full">
              Your browser does not support the audio element.
            </audio>
          </div>

          <div className="rounded border border-gray-200 p-4">
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
              className="rounded border border-gray-300 px-3 py-2 text-sm"
            >
              {INSTRUMENTS.map((inst) => (
                <option key={inst.key} value={inst.key}>
                  {inst.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-gray-500">
              {selectedInstrument.writtenOffset > 0
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
              className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Download MIDI
            </a>
            <a
              href={jsonDownloadUrl(projectId)}
              download
              className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Download JSON
            </a>
            <a
              href={musicxmlDownloadUrl(projectId, instrumentKey, sheetStyle)}
              download
              className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
            >
              Download MusicXML ({selectedInstrument.label})
            </a>
            <button
              type="button"
              onClick={handlePdfDownload}
              disabled={pdfDownloading}
              className="flex items-center gap-2 rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
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
            <p className="text-sm text-gray-500">Loading notes…</p>
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
                onTick={handlePlayTick}
                autoScroll={autoScroll}
                onAutoScrollChange={setAutoScroll}
              />

              <div>
                <h2 className="mb-2 text-lg font-medium">Sheet music</h2>
                <SheetMusic
                  projectId={projectId}
                  instrumentKey={instrumentKey}
                  sheetStyle={sheetStyle}
                  notesVersion={notesVersion}
                  playPosition={playPosition}
                  autoScroll={autoScroll}
                />
              </div>

              <details className="rounded border border-gray-200 p-3">
                <summary className="cursor-pointer text-sm font-medium text-gray-700">
                  Advanced note timeline ({workingNotes.length} notes)
                </summary>
                <div className="mt-3">
                  <NotePreview
                    notes={workingNotes}
                    playheadTime={playPosition}
                    currentNoteIndex={playNoteIndex}
                    autoScroll={autoScroll}
                  />
                </div>
              </details>

              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-medium">Note detail</h2>
                  <div className="flex items-center gap-3">
                    {saveState === "saving" && (
                      <span className="text-xs text-gray-500">Saving edits…</span>
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
                      className="rounded border border-gray-300 px-3 py-1 text-xs font-medium hover:bg-gray-50"
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
                <NoteTable
                  notes={workingNotes}
                  writtenLabel={selectedInstrument.label}
                  writtenOffset={selectedInstrument.writtenOffset}
                  currentIndex={playNoteIndex}
                  autoScroll={autoScroll}
                  onDelete={handleDeleteNote}
                />
                <p className="mt-1 text-xs text-gray-500">
                  Click ✕ to delete a wrongly detected note — the preview,
                  playback and all downloads update automatically.
                </p>
              </div>
            </>
          )}

          {notes && workingNotes && workingNotes.length === 0 && notes.note_count !== 0 && (
            <div className="rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
              <p className="mb-2">All notes have been deleted.</p>
              <button
                type="button"
                onClick={handleResetNotes}
                className="rounded border border-yellow-400 px-3 py-1 text-xs font-medium hover:bg-yellow-100"
              >
                Reset to original transcription
              </button>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
