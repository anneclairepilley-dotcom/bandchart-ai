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

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [transcribing, setTranscribing] = useState(false);
  const [transcribeError, setTranscribeError] = useState<string | null>(null);

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

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setUploadError("Choose an audio file first.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const updated = await uploadAudio(projectId, file);
      setProject(updated);
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : "Failed to upload audio."
      );
    } finally {
      setUploading(false);
    }
  }

  async function handleTranscribe() {
    setTranscribing(true);
    setTranscribeError(null);
    try {
      const updated = await transcribeProject(projectId);
      setProject(updated);
    } catch (err) {
      setTranscribeError(
        err instanceof ApiError ? err.message : "Failed to transcribe audio."
      );
      // The backend may still have flipped status to "failed"; refetch to
      // stay in sync either way.
      await refetchProject();
    } finally {
      setTranscribing(false);
    }
  }

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

      {project.status === "created" && (
        <section className="rounded border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-medium">Upload audio</h2>
          <form onSubmit={handleUpload} className="flex flex-col gap-3">
            <input
              type="file"
              accept=".wav,.mp3,.flac,.ogg,.m4a,.aiff,.aif"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm"
              disabled={uploading}
            />
            <button
              type="submit"
              disabled={uploading}
              className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? "Uploading…" : "Upload Audio"}
            </button>
          </form>
          {uploadError && (
            <p className="mt-2 text-sm text-red-600">{uploadError}</p>
          )}
        </section>
      )}

      {project.status === "uploaded" && (
        <section className="rounded border border-gray-200 p-4">
          <h2 className="mb-3 text-lg font-medium">Audio</h2>
          <audio controls src={audioUrl(projectId)} className="w-full">
            Your browser does not support the audio element.
          </audio>
          <button
            type="button"
            onClick={handleTranscribe}
            disabled={transcribing}
            className="mt-4 w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {transcribing ? "Transcribing…" : "Run Transcription"}
          </button>
          {transcribing && (
            <p className="mt-2 text-sm text-gray-500">
              Running real ML inference — this can take a little while for
              longer audio files. Please don&apos;t close this tab.
            </p>
          )}
          {transcribeError && (
            <p className="mt-2 text-sm text-red-600">{transcribeError}</p>
          )}
        </section>
      )}

      {project.status === "transcribing" && (
        <section className="flex items-center gap-3 rounded border border-yellow-200 bg-yellow-50 p-4">
          <span
            className="h-5 w-5 animate-spin rounded-full border-2 border-yellow-600 border-t-transparent"
            aria-hidden
          />
          <p className="text-sm text-yellow-800">Transcription in progress…</p>
        </section>
      )}

      {project.status === "failed" && (
        <section className="rounded border border-red-200 bg-red-50 p-4">
          <h2 className="mb-2 text-lg font-medium text-red-800">
            Transcription failed
          </h2>
          {project.error && (
            <p className="mb-3 whitespace-pre-wrap text-sm text-red-700">
              {project.error}
            </p>
          )}
          <button
            type="button"
            onClick={handleTranscribe}
            disabled={transcribing}
            className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {transcribing ? "Retrying…" : "Retry Transcription"}
          </button>
          {transcribeError && (
            <p className="mt-2 text-sm text-red-600">{transcribeError}</p>
          )}
        </section>
      )}

      {project.status === "transcribed" && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-4">
            <audio controls src={audioUrl(projectId)} className="w-full">
              Your browser does not support the audio element.
            </audio>
          </div>

          <div className="flex gap-4">
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
          </div>

          {notesError && (
            <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {notesError}
            </p>
          )}

          {!notesError && !notes && (
            <p className="text-sm text-gray-500">Loading notes…</p>
          )}

          {notes && (
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
