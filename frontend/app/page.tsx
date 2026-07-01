"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, createProject, listProjects, type Project } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

export default function HomePage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

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

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setCreateError("Project name is required.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const project = await createProject(trimmed);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.message : "Failed to create project."
      );
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-8 p-6">
      <header>
        <h1 className="text-2xl font-semibold">BandChart AI</h1>
        <p className="text-sm text-gray-500">
          Upload a song and get a basic audio-to-MIDI transcription.
        </p>
      </header>

      <section className="rounded border border-gray-200 p-4">
        <h2 className="mb-3 text-lg font-medium">New project</h2>
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name"
            maxLength={200}
            className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            disabled={creating}
          />
          <button
            type="submit"
            disabled={creating}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create Project"}
          </button>
        </form>
        {createError && (
          <p className="mt-2 text-sm text-red-600">{createError}</p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Projects</h2>

        {loadError && (
          <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {loadError}
          </p>
        )}

        {!loadError && projects === null && (
          <p className="text-sm text-gray-500">Loading projects…</p>
        )}

        {!loadError && projects !== null && projects.length === 0 && (
          <p className="text-sm text-gray-500">No projects yet.</p>
        )}

        {!loadError && projects !== null && projects.length > 0 && (
          <ul className="flex flex-col divide-y divide-gray-200 rounded border border-gray-200">
            {projects.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/projects/${project.id}`}
                  className="flex items-center justify-between gap-4 p-3 hover:bg-gray-50"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{project.name}</span>
                    <span className="text-xs text-gray-500">
                      Created {new Date(project.created_at).toLocaleString()}
                    </span>
                  </div>
                  <StatusBadge status={project.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
