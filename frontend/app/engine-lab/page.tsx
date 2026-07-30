"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import {
  EngineInfo,
  FixtureInfo,
  LabSources,
  RunResult,
  RunSource,
  applyRunToProject,
  fixtureAudioUrl,
  listEngines,
  listFixtures,
  listSources,
  runEngine,
  runJsonDownloadUrl,
  runMidiDownloadUrl,
  uploadLabAudio,
} from "@/lib/engineLab";
import EngineLabPianoRoll from "@/components/EngineLabPianoRoll";

type SourceKind = "fixture" | "project" | "upload";

// The owner's named benchmark order (steps 1-5 have synthetic fixtures;
// step 6, Mrs Magic, is real audio — import it as a normal project, then
// pick it here under "Project").
const BENCHMARK_ORDER: Record<string, number> = {
  a4_tone: 1,
  c_major_chord: 2,
  c_major_scale: 3,
  block_chords: 4,
  bass_and_melody: 5,
};

export default function EngineLabPage() {
  const [engines, setEngines] = useState<EngineInfo[] | null>(null);
  const [fixtures, setFixtures] = useState<FixtureInfo[] | null>(null);
  const [sources, setSources] = useState<LabSources | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [sourceKind, setSourceKind] = useState<SourceKind>("fixture");
  const [selectedFixture, setSelectedFixture] = useState<string>("a4_tone");
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [uploadedAudioId, setUploadedAudioId] = useState<string | null>(null);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [selectedEngine, setSelectedEngine] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunResult[]>([]);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [applyingRunId, setApplyingRunId] = useState<string | null>(null);
  const [appliedRunId, setAppliedRunId] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);

  const refreshLists = useCallback(() => {
    let cancelled = false;
    Promise.all([listEngines(), listFixtures(), listSources()])
      .then(([engineList, fixtureList, sourceList]) => {
        if (cancelled) return;
        setEngines(engineList);
        setFixtures(fixtureList);
        setSources(sourceList);
        setSelectedEngine((current) => {
          if (current) return current;
          const firstAvailable = engineList.find((e) => e.available);
          return firstAvailable ? firstAvailable.key : engineList[0]?.key ?? "";
        });
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError ? err.message : "Failed to load Engine Lab data."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => refreshLists(), [refreshLists]);

  const handleUpload = useCallback(async (file: File) => {
    setUploadBusy(true);
    setUploadError(null);
    try {
      const result = await uploadLabAudio(file);
      setUploadedAudioId(result.audio_id);
      setUploadedFilename(result.filename);
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploadBusy(false);
    }
  }, []);

  const currentSource: RunSource | null = (() => {
    if (sourceKind === "fixture" && selectedFixture) {
      return { kind: "fixture", fixture_key: selectedFixture };
    }
    if (sourceKind === "project" && selectedProject) {
      return { kind: "project", project_id: selectedProject };
    }
    if (sourceKind === "upload" && uploadedAudioId) {
      return { kind: "upload", audio_id: uploadedAudioId };
    }
    return null;
  })();

  const handleRun = useCallback(async () => {
    if (!selectedEngine || !currentSource) return;
    setRunning(true);
    setRunError(null);
    try {
      const result = await runEngine(selectedEngine, currentSource);
      setRuns((prev) => [result, ...prev]);
      setExpandedRunId(result.run_id);
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "The run failed.");
    } finally {
      setRunning(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEngine, sourceKind, selectedFixture, selectedProject, uploadedAudioId]);

  const handleApply = useCallback(async (run: RunResult) => {
    if (run.source.kind !== "project" || !run.source.project_id) return;
    setApplyingRunId(run.run_id);
    setApplyError(null);
    try {
      await applyRunToProject(run.run_id, run.source.project_id);
      setAppliedRunId(run.run_id);
    } catch (err) {
      setApplyError(err instanceof ApiError ? err.message : "Applying this output failed.");
    } finally {
      setApplyingRunId(null);
    }
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Engine Lab</h1>
          <p className="mt-1 text-sm text-gray-600">
            A developer tool for comparing transcription engines on the same
            audio. Running engines here is separate from the main app and
            never affects a project — the one exception is the explicit
            &quot;Use this output&quot; button, which is the only way a lab
            result becomes a project&apos;s active transcription.
          </p>
        </div>
        <Link href="/" className="shrink-0 text-sm text-blue-700 underline hover:text-blue-900">
          ← Back to BandChart AI
        </Link>
      </div>

      <div className="mb-6 rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
        <p className="font-medium">Suggested benchmark order</p>
        <ol className="mt-1 list-decimal pl-5">
          <li>A4 tone</li>
          <li>C major chord</li>
          <li>C major scale</li>
          <li>Simple piano block chords</li>
          <li>Left-hand bass + right-hand melody</li>
          <li>
            <strong>Mrs Magic hard piano benchmark</strong> — import it as a normal
            project first (upload or YouTube), then pick it under
            &quot;Project&quot; below. This is a genuinely hard real-world test;
            no engine is expected to solve it perfectly.
          </li>
        </ol>
      </div>

      {loadError && (
        <p className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {loadError}
        </p>
      )}

      <section className="mb-6 rounded border border-gray-300 p-4">
        <h2 className="mb-3 text-lg font-medium">1. Choose audio</h2>
        <div className="mb-3 flex flex-wrap gap-4 text-sm">
          {(["fixture", "project", "upload"] as SourceKind[]).map((kind) => (
            <label key={kind} className="flex items-center gap-1.5">
              <input
                type="radio"
                name="sourceKind"
                checked={sourceKind === kind}
                onChange={() => setSourceKind(kind)}
                data-testid={`source-kind-${kind}`}
              />
              {kind === "fixture"
                ? "Built-in test audio"
                : kind === "project"
                ? "An existing project's audio"
                : "Upload a file"}
            </label>
          ))}
        </div>

        {sourceKind === "fixture" && fixtures && (
          <div>
            <select
              value={selectedFixture}
              onChange={(e) => setSelectedFixture(e.target.value)}
              data-testid="fixture-select"
              className="w-full rounded border border-gray-400 px-2 py-1.5 text-sm"
            >
              {fixtures.map((f) => (
                <option key={f.key} value={f.key}>
                  {BENCHMARK_ORDER[f.key] ? `${BENCHMARK_ORDER[f.key]}. ` : ""}
                  {f.label} ({f.expected_note_count} expected notes)
                </option>
              ))}
            </select>
            {fixtures.find((f) => f.key === selectedFixture) && (
              <p className="mt-1 text-xs text-gray-600">
                {fixtures.find((f) => f.key === selectedFixture)?.description}
              </p>
            )}
            <audio
              key={selectedFixture}
              controls
              src={fixtureAudioUrl(selectedFixture)}
              className="mt-2 w-full"
              data-testid="fixture-audio-preview"
            />
          </div>
        )}

        {sourceKind === "project" && sources && (
          <div>
            {sources.projects.length === 0 ? (
              <p className="text-sm text-gray-600">
                No projects with audio yet — upload or import one from the home
                page first.
              </p>
            ) : (
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                data-testid="project-select"
                className="w-full rounded border border-gray-400 px-2 py-1.5 text-sm"
              >
                <option value="">Choose a project…</option>
                {sources.projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.name} {p.instrument ? `(${p.instrument})` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {sourceKind === "upload" && (
          <div>
            <input
              type="file"
              accept=".wav,.mp3,.flac,.ogg,.m4a,.aiff,.aif"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleUpload(file);
              }}
              disabled={uploadBusy}
              data-testid="lab-upload-input"
              className="text-sm"
            />
            {uploadBusy && <p className="mt-1 text-xs text-gray-600">Uploading…</p>}
            {uploadedFilename && !uploadBusy && (
              <p className="mt-1 text-xs text-green-700" data-testid="upload-confirmed">
                Uploaded: {uploadedFilename}
              </p>
            )}
            {uploadError && (
              <p className="mt-1 text-xs text-red-700">{uploadError}</p>
            )}
          </div>
        )}
      </section>

      <section className="mb-6 rounded border border-gray-300 p-4">
        <h2 className="mb-3 text-lg font-medium">2. Choose an engine</h2>
        {!engines && <p className="text-sm text-gray-600">Loading engines…</p>}
        <div className="flex flex-col gap-2">
          {engines?.map((engine) => (
            <label
              key={engine.key}
              className={`flex items-start gap-2 rounded border p-2 text-sm ${
                engine.available
                  ? "border-gray-300"
                  : "border-gray-200 bg-gray-50 text-gray-500"
              }`}
            >
              <input
                type="radio"
                name="engine"
                checked={selectedEngine === engine.key}
                onChange={() => setSelectedEngine(engine.key)}
                disabled={!engine.available}
                data-testid={`engine-radio-${engine.key}`}
                className="mt-0.5"
              />
              <span>
                <span className="font-medium">{engine.label}</span>
                <span className="block text-xs text-gray-600">{engine.description}</span>
                {!engine.available && (
                  <span
                    className="mt-1 block text-xs font-medium text-amber-700"
                    data-testid={`engine-unavailable-${engine.key}`}
                  >
                    Engine unavailable: {engine.unavailable_reason}
                  </span>
                )}
              </span>
            </label>
          ))}
        </div>

        <button
          type="button"
          onClick={handleRun}
          disabled={running || !selectedEngine || !currentSource}
          data-testid="run-engine-button"
          className="mt-4 rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Running…" : "Run engine"}
        </button>
        {runError && (
          <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
            {runError}
          </p>
        )}
      </section>

      {runs.length > 0 && (
        <section className="rounded border border-gray-300 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-medium">Results ({runs.length})</h2>
            <button
              type="button"
              onClick={() => setRuns([])}
              data-testid="clear-runs"
              className="text-xs text-gray-600 underline hover:text-gray-800"
            >
              Clear list
            </button>
          </div>
          {applyError && (
            <p className="mb-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {applyError}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-gray-300 text-xs text-gray-600">
                  <th className="p-2">Engine</th>
                  <th className="p-2">Source</th>
                  <th className="p-2">Time</th>
                  <th className="p-2">Notes</th>
                  <th className="p-2">Overlap</th>
                  <th className="p-2">Chords</th>
                  <th className="p-2">Pitch range</th>
                  <th className="p-2">Score</th>
                  <th className="p-2">Downloads</th>
                  <th className="p-2">Use output</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <Fragment key={run.run_id}>
                    <tr
                      className="cursor-pointer border-b border-gray-100 odd:bg-white even:bg-gray-50 hover:bg-blue-50"
                      onClick={() =>
                        setExpandedRunId((current) => (current === run.run_id ? null : run.run_id))
                      }
                      data-testid={`run-row-${run.run_id}`}
                    >
                      <td className="p-2 font-medium">{run.engine_label}</td>
                      <td className="p-2 text-xs text-gray-600">{run.source_label}</td>
                      <td className="p-2">{run.processing_time_s.toFixed(2)}s</td>
                      <td className="p-2">{run.note_count}</td>
                      <td className="p-2">{run.overlapping_notes}</td>
                      <td className="p-2">{run.chord_groups}</td>
                      <td className="p-2 text-xs">{run.pitch_range_label ?? "—"}</td>
                      <td className="p-2">
                        {run.scoring ? `${run.scoring.rough_score_percent}%` : "—"}
                      </td>
                      <td className="p-2">
                        <a
                          href={runMidiDownloadUrl(run.run_id)}
                          onClick={(e) => e.stopPropagation()}
                          className="mr-2 text-blue-700 underline hover:text-blue-900"
                          data-testid={`download-midi-${run.run_id}`}
                        >
                          MIDI
                        </a>
                        <a
                          href={runJsonDownloadUrl(run.run_id)}
                          onClick={(e) => e.stopPropagation()}
                          className="text-blue-700 underline hover:text-blue-900"
                          data-testid={`download-json-${run.run_id}`}
                        >
                          JSON
                        </a>
                      </td>
                      <td className="p-2">
                        {run.source.kind === "project" ? (
                          appliedRunId === run.run_id ? (
                            <span
                              className="text-xs font-medium text-green-700"
                              data-testid={`applied-${run.run_id}`}
                            >
                              ✓ Applied
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleApply(run);
                              }}
                              disabled={applyingRunId === run.run_id || !!run.error}
                              data-testid={`apply-run-${run.run_id}`}
                              className="rounded border border-blue-300 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {applyingRunId === run.run_id ? "Applying…" : "Use this output"}
                            </button>
                          )
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                    </tr>
                    {expandedRunId === run.run_id && (
                      <tr className="border-b border-gray-200 bg-gray-50">
                        <td colSpan={10} className="p-3">
                          {run.error && (
                            <p className="mb-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                              {run.error}
                            </p>
                          )}
                          {run.messages.length > 0 && (
                            <ul className="mb-2 list-disc pl-5 text-xs text-yellow-800">
                              {run.messages.map((m, i) => (
                                <li key={i}>{m}</li>
                              ))}
                            </ul>
                          )}
                          {run.scoring && (
                            <div className="mb-2 text-xs text-gray-700">
                              <span className="font-medium">Scoring against known notes: </span>
                              {run.scoring.correct_matches} correct,{" "}
                              {run.scoring.missed_notes} missed,{" "}
                              {run.scoring.extra_notes} extra
                              {run.scoring.simultaneous_notes_preserved !== null && (
                                <>
                                  , simultaneous notes preserved:{" "}
                                  {run.scoring.simultaneous_notes_preserved ? "yes" : "no"}
                                </>
                              )}
                              {run.scoring.mean_timing_error_s !== null && (
                                <>
                                  {" "}
                                  (mean timing error {(run.scoring.mean_timing_error_s * 1000).toFixed(0)}ms)
                                </>
                              )}
                            </div>
                          )}
                          <EngineLabPianoRoll notes={run.notes} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
