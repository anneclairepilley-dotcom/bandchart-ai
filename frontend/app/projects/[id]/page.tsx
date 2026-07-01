"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ApiError,
  audioUrl,
  getNotes,
  getProject,
  jsonDownloadUrl,
  midiDownloadUrl,
  transcribeProject,
  uploadAudio,
  type NotesResponse,
  type Project,
} from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import NotePreview from "@/components/NotePreview";

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
        if (!cancelled) setNotes(data);
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
            {startAgainButton}
          </div>

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

          {notes && notes.note_count > 0 && (
            <>
              <div>
                <h2 className="mb-2 text-lg font-medium">
                  Transcription preview ({notes.note_count} notes)
                </h2>
                <NotePreview notes={notes.notes} />
              </div>

              <div>
                <h2 className="mb-2 text-lg font-medium">Note detail</h2>
                <div className="max-h-96 overflow-y-auto rounded border border-gray-200">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-gray-50">
                      <tr>
                        <th className="p-2 font-medium">Pitch</th>
                        <th className="p-2 font-medium">Start (s)</th>
                        <th className="p-2 font-medium">Duration (s)</th>
                        <th className="p-2 font-medium">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {notes.notes.map((note, i) => (
                        <tr
                          key={i}
                          className="border-t border-gray-100 odd:bg-white even:bg-gray-50"
                        >
                          <td className="p-2">{note.pitch_name}</td>
                          <td className="p-2">{note.start_time.toFixed(3)}</td>
                          <td className="p-2">{note.duration.toFixed(3)}</td>
                          <td className="p-2">
                            {(note.confidence * 100).toFixed(0)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </section>
      )}
    </main>
  );
}
