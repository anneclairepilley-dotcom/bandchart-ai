// Typed fetch helpers for the Engine Lab (/api/engine-lab/*). Kept separate
// from lib/api.ts on purpose: the lab is an isolated side area, not part of
// the main project workflow.

import { API_BASE_URL, ApiError } from "@/lib/api";

export interface EngineInfo {
  key: string;
  label: string;
  description: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface FixtureInfo {
  key: string;
  label: string;
  description: string;
  expected_note_count: number;
}

export interface LabProjectSource {
  project_id: string;
  name: string;
  instrument: string | null;
}

export interface LabSources {
  projects: LabProjectSource[];
  fixtures: { fixture_key: string; label: string }[];
}

export interface LabNote {
  pitch: number;
  pitch_name: string;
  start_time: number;
  duration: number;
  confidence: number;
  velocity?: number | null;
  group?: string | null;
  source?: string | null;
}

export interface ScoringResult {
  expected_count: number;
  detected_count: number;
  correct_matches: number;
  missed_notes: number;
  extra_notes: number;
  simultaneous_notes_preserved: boolean | null;
  mean_timing_error_s: number | null;
  rough_score_percent: number;
}

export interface RunResult {
  run_id: string;
  engine_key: string;
  engine_label: string;
  source: {
    kind: "project" | "fixture" | "upload";
    project_id?: string | null;
    fixture_key?: string | null;
    audio_id?: string | null;
  };
  source_label: string;
  created_at: string;
  processing_time_s: number;
  error: string | null;
  messages: string[];
  notes: LabNote[];
  note_count: number;
  overlapping_notes: number;
  chord_groups: number;
  pitch_min: number | null;
  pitch_max: number | null;
  pitch_range_label: string | null;
  scoring: ScoringResult | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      API_BASE_URL
        ? `Could not reach backend at ${API_BASE_URL}. Is the server running?`
        : "Could not reach the backend. Is the backend server running on port 8000?"
    );
  }
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail =
        typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      // not JSON — fall through to the status text
    }
    throw new ApiError(
      detail || `Request failed: ${response.status} ${response.statusText}`,
      response.status
    );
  }
  return (await response.json()) as T;
}

export function listEngines(): Promise<EngineInfo[]> {
  return request<EngineInfo[]>("/api/engine-lab/engines");
}

export function listFixtures(): Promise<FixtureInfo[]> {
  return request<FixtureInfo[]>("/api/engine-lab/fixtures");
}

export function listSources(): Promise<LabSources> {
  return request<LabSources>("/api/engine-lab/sources");
}

export function fixtureAudioUrl(fixtureKey: string): string {
  return `${API_BASE_URL}/api/engine-lab/fixtures/${encodeURIComponent(fixtureKey)}/audio`;
}

export function uploadLabAudio(file: File): Promise<{ audio_id: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  return request<{ audio_id: string; filename: string }>("/api/engine-lab/audio", {
    method: "POST",
    body: formData,
  });
}

export type RunSource =
  | { kind: "project"; project_id: string }
  | { kind: "fixture"; fixture_key: string }
  | { kind: "upload"; audio_id: string };

export function runEngine(engine: string, source: RunSource): Promise<RunResult> {
  return request<RunResult>("/api/engine-lab/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ engine, source }),
  });
}

export function listRuns(): Promise<RunResult[]> {
  return request<RunResult[]>("/api/engine-lab/runs");
}

export function runMidiDownloadUrl(runId: string): string {
  return `${API_BASE_URL}/api/engine-lab/runs/${runId}/download/midi`;
}

export function runJsonDownloadUrl(runId: string): string {
  return `${API_BASE_URL}/api/engine-lab/runs/${runId}/download/json`;
}
