"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  createProject,
  deleteProject,
  importYoutube,
  listProjects,
  uploadAudio,
  type Project,
} from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

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

/** "my-song.mp3" -> "my-song" (fallback for empty/odd names). */
function projectNameFromFile(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, "").trim();
  return (base || "New transcription").slice(0, 200);
}

export default function HomePage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"upload" | "youtube" | null>(null);
  const [heroError, setHeroError] = useState<string | null>(null);

  const [ytUrl, setYtUrl] = useState("");
  const [ytRights, setYtRights] = useState(false);

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((data) => {
        if (!cancelled) setProjects(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError ? err.message : "Failed to load projects."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Create a project for the chosen file, upload it, go to the setup step. */
  async function handleFileChosen(file: File) {
    const lowerName = file.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
      setHeroError(
        `"${file.name}" doesn't look like a supported audio file. Please choose a file ending in ${ACCEPTED_EXTENSIONS.join(", ")}.`
      );
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setHeroError(
        `"${file.name}" is ${(file.size / (1024 * 1024)).toFixed(0)}MB, which is over the 50MB limit. Try a shorter recording, or export it as .mp3 to make it smaller.`
      );
      return;
    }
    if (file.size === 0) {
      setHeroError(
        `"${file.name}" is empty (0 bytes). Please pick the audio file again.`
      );
      return;
    }

    setBusy("upload");
    setHeroError(null);
    let created: Project | null = null;
    try {
      created = await createProject(projectNameFromFile(file.name));
      await uploadAudio(created.id, file);
      router.push(`/projects/${created.id}`);
    } catch (err) {
      // Don't leave an empty half-made project behind on failure.
      if (created) {
        try {
          await deleteProject(created.id);
        } catch {
          // best-effort cleanup only
        }
      }
      setHeroError(
        err instanceof ApiError
          ? err.message
          : "Uploading failed — check that the backend is running, then try again."
      );
      setBusy(null);
    }
  }

  /** Create a project, import the YouTube audio into it, go to setup. */
  async function handleYoutubeImport() {
    const url = ytUrl.trim();
    if (!url) {
      setHeroError("Paste a YouTube link first.");
      return;
    }
    if (!/youtube\.com|youtu\.be/i.test(url)) {
      setHeroError(
        "That doesn't look like a YouTube link. Expected something like " +
          "https://www.youtube.com/watch?v=… or https://youtu.be/…"
      );
      return;
    }
    if (!ytRights) {
      setHeroError(
        "Please tick the box confirming you have permission to process this content before importing."
      );
      return;
    }

    setBusy("youtube");
    setHeroError(null);
    let created: Project | null = null;
    try {
      created = await createProject("YouTube import");
      await importYoutube(created.id, url, true);
      router.push(`/projects/${created.id}`);
    } catch (err) {
      if (created) {
        try {
          await deleteProject(created.id);
        } catch {
          // best-effort cleanup only
        }
      }
      setHeroError(
        err instanceof ApiError
          ? err.message
          : "YouTube import failed — check that the backend is running, then try again."
      );
      setBusy(null);
    }
  }

  async function handleDelete(project: Project) {
    const confirmed = window.confirm(
      "Delete this transcription? This will remove its uploaded audio and generated files."
    );
    if (!confirmed) return;
    setDeletingId(project.id);
    setDeleteError(null);
    try {
      await deleteProject(project.id);
      setProjects((current) =>
        current ? current.filter((p) => p.id !== project.id) : current
      );
    } catch (err) {
      setDeleteError(
        err instanceof ApiError
          ? err.message
          : `Couldn't delete "${project.name}" — check that the backend is running, then try again.`
      );
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-8 p-6">
      <section className="rounded-lg border border-gray-300 bg-white p-6 text-center shadow-sm">
        <h1 className="text-3xl font-semibold">Turn sound into sheet music</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-gray-600">
          Upload audio or paste a YouTube link and BandChart will create sheet
          music, tab or a lead sheet.
        </p>

        <div className="mx-auto mt-6 flex max-w-md flex-col gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            data-testid="hero-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void handleFileChosen(file);
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy !== null}
            data-testid="hero-upload"
            className="flex items-center justify-center gap-2 rounded bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === "upload" && (
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
                aria-hidden
              />
            )}
            {busy === "upload" ? "Uploading…" : "Upload audio"}
          </button>

          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className="h-px flex-1 bg-gray-200" aria-hidden />
            or
            <span className="h-px flex-1 bg-gray-200" aria-hidden />
          </div>

          <div className="flex flex-col gap-2 text-left">
            <div className="flex gap-2">
              <input
                type="url"
                value={ytUrl}
                onChange={(e) => {
                  setYtUrl(e.target.value);
                  setHeroError(null);
                }}
                placeholder="https://www.youtube.com/watch?v=…"
                disabled={busy !== null}
                data-testid="hero-yt-url"
                className="flex-1 rounded border border-gray-400 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleYoutubeImport}
                disabled={busy !== null || !ytUrl.trim() || !ytRights}
                data-testid="hero-yt-import"
                className="flex items-center gap-2 rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy === "youtube" && (
                  <span
                    className="h-4 w-4 animate-spin rounded-full border-2 border-gray-500 border-t-transparent"
                    aria-hidden
                  />
                )}
                {busy === "youtube" ? "Importing…" : "Import"}
              </button>
            </div>
            <label className="flex items-start gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                checked={ytRights}
                onChange={(e) => setYtRights(e.target.checked)}
                disabled={busy !== null}
                data-testid="hero-yt-rights"
                className="mt-0.5"
              />
              <span>
                I confirm I own this content or have permission to process it
                for private transcription/arrangement use.
              </span>
            </label>
            <p className="text-xs text-gray-600">
              BandChart AI does not publish, share or create a public library
              from your transcription. If YouTube blocks the import (common on
              cloud servers), upload an audio file instead.
            </p>
          </div>

          {busy === "youtube" && (
            <p className="text-left text-xs text-gray-600">
              Importing from YouTube — checking the link, extracting the audio
              and converting it… this can take a minute for longer clips.
            </p>
          )}

          {heroError && (
            <p
              data-testid="hero-error"
              className="rounded border border-red-200 bg-red-50 p-2 text-left text-sm text-red-700"
            >
              {heroError}
            </p>
          )}
        </div>

        <p className="mt-4 text-xs text-gray-600">
          Works best with one clear melody — a voice, a whistle or a solo
          instrument. BandChart is melody-first; full band separation is
          coming later.
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Your projects</h2>

        {loadError && (
          <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {loadError}
          </p>
        )}

        {!loadError && projects === null && (
          <p className="text-sm text-gray-600">Loading projects…</p>
        )}

        {!loadError && projects !== null && projects.length === 0 && (
          <p className="text-sm text-gray-600">
            Nothing here yet — upload a recording or import a YouTube link
            above to get started.
          </p>
        )}

        {deleteError && (
          <p className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {deleteError}
          </p>
        )}

        {!loadError && projects !== null && projects.length > 0 && (
          <ul className="flex flex-col divide-y divide-gray-200 rounded border border-gray-300">
            {projects.map((project) => (
              <li
                key={project.id}
                className="flex items-center gap-2 pr-3 hover:bg-gray-50"
              >
                <Link
                  href={`/projects/${project.id}`}
                  className="flex flex-1 items-center justify-between gap-4 p-3"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{project.name}</span>
                    <span className="text-xs text-gray-600">
                      Created {new Date(project.created_at).toLocaleString()}
                    </span>
                  </div>
                  <StatusBadge status={project.status} />
                </Link>
                <button
                  type="button"
                  onClick={() => handleDelete(project)}
                  disabled={deletingId === project.id}
                  data-testid={`delete-project-${project.id}`}
                  className="shrink-0 rounded border border-red-200 px-3 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {deletingId === project.id ? "Deleting…" : "Delete"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
