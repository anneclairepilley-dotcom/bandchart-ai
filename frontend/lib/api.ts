// Typed fetch helpers for the BandChart AI backend API.
//
// By default the base URL is empty: requests go to this app's own origin
// (/api/...) and the Next.js server proxies them to the FastAPI backend
// (see next.config.ts). That way the browser never needs direct access to
// the backend's port, which matters in remote environments like GitHub
// Codespaces. Set NEXT_PUBLIC_API_BASE_URL only if the browser should hit
// a backend on a different host directly.

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "";

export type ProjectStatus =
  | "created"
  | "uploaded"
  | "transcribing"
  | "transcribed"
  | "failed";

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
  audio_filename: string | null;
  note_count: number | null;
  error: string | null;
}

export interface Note {
  pitch: number;
  pitch_name: string;
  start_time: number;
  duration: number;
  confidence: number;
}

export interface NotesResponse {
  project_id: string;
  project_name: string;
  source_audio: string;
  generated_at: string;
  note_count: number;
  notes: Note[];
}

/**
 * Error thrown when the backend responds with a non-OK status, or when
 * fetch itself fails (e.g. the backend is unreachable). Callers should
 * catch this and show a visible, user-friendly error message.
 */
export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
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
        typeof body?.detail === "string"
          ? body.detail
          : JSON.stringify(body?.detail ?? body);
    } catch {
      // response body wasn't JSON; fall back to status text
    }
    throw new ApiError(
      detail || `Request failed: ${response.status} ${response.statusText}`,
      response.status
    );
  }

  // Some endpoints (e.g. downloads) are not JSON, but every helper below
  // that calls request<T>() expects a JSON body.
  return (await response.json()) as T;
}

export function createProject(name: string): Promise<Project> {
  return request<Project>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}`);
}

export function uploadAudio(
  projectId: string,
  file: File
): Promise<Project> {
  const formData = new FormData();
  formData.append("file", file);
  return request<Project>(`/api/projects/${projectId}/audio`, {
    method: "POST",
    body: formData,
  });
}

export function transcribeProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}/transcribe`, {
    method: "POST",
  });
}

export function getNotes(projectId: string): Promise<NotesResponse> {
  return request<NotesResponse>(`/api/projects/${projectId}/notes`);
}

/** Direct URL for the HTML5 <audio> player (not fetched via JSON helper). */
export function audioUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${projectId}/audio`;
}

/** Direct URL for downloading the transcribed MIDI file. */
export function midiDownloadUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${projectId}/download/midi`;
}

/** Direct URL for downloading the transcription JSON file. */
export function jsonDownloadUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${projectId}/download/json`;
}

/** Direct URL for downloading the MusicXML file for a solo instrument. */
export function musicxmlDownloadUrl(
  projectId: string,
  instrumentKey: string
): string {
  return `${API_BASE_URL}/api/projects/${projectId}/download/musicxml?instrument=${encodeURIComponent(instrumentKey)}`;
}
