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
  source_type?: "upload" | "youtube" | null;
  source_url?: string | null;
  rights_confirmed?: boolean | null;
  imported_at?: string | null;
  // v0.9.1 setup choices (absent/null on older projects).
  instrument?: string | null;
  mode?: "direct_transcription" | "solo_arrangement" | null;
  time_signature?: string | null;
  key_signature?: string | null;
  rhythm_detail?: "readable" | "precise" | null;
}

/** Pre-transcription choices saved via POST /projects/{id}/settings. */
export interface ProjectSettingsPayload {
  instrument: string;
  mode: "direct_transcription" | "solo_arrangement";
  time_signature: string;
  key_signature: string;
  rhythm_detail: "readable" | "precise";
}

export interface Note {
  pitch: number;
  pitch_name: string;
  start_time: number;
  duration: number;
  confidence: number;
}

/** One manual chord symbol on the timeline (e.g. Am starting at 2.0s). */
export interface ChordMarker {
  name: string;
  start_time: number;
}

export interface NotesResponse {
  project_id: string;
  project_name: string;
  source_audio: string;
  generated_at: string;
  note_count: number;
  notes: Note[];
  /** Chord markers (v0.9); absent on projects transcribed before then. */
  chords?: ChordMarker[];
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

/** Permanently delete a project and its uploaded audio + generated files. */
export function deleteProject(projectId: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
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

/** Save the instrument / mode / advanced-settings choices for a project. */
export function saveProjectSettings(
  projectId: string,
  settings: ProjectSettingsPayload
): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

/**
 * Import the audio of a YouTube video into a project. The backend extracts
 * the audio with yt-dlp, converts it to WAV, and stores it exactly like an
 * uploaded file. Requires the rights confirmation to be true.
 */
export function importYoutube(
  projectId: string,
  url: string,
  rightsConfirmed: boolean
): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}/youtube`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, rights_confirmed: rightsConfirmed }),
  });
}

export function getNotes(projectId: string): Promise<NotesResponse> {
  return request<NotesResponse>(`/api/projects/${projectId}/notes`);
}

/**
 * Save an edited note list as the project's working transcription. The
 * backend rewrites transcription.json and the MIDI file, so every download
 * (JSON, MIDI, MusicXML, PDF) reflects the edit afterwards.
 */
export function updateNotes(
  projectId: string,
  notes: Note[]
): Promise<NotesResponse> {
  return request<NotesResponse>(`/api/projects/${projectId}/notes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
}

/** Restore the untouched original transcription (undo all note edits). */
export function resetNotes(projectId: string): Promise<NotesResponse> {
  return request<NotesResponse>(`/api/projects/${projectId}/notes/reset`, {
    method: "POST",
  });
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

/** Sheet-music rendering style: cleaned-up notation or the literal detection. */
export type SheetStyle = "clean" | "raw";

/** Direct URL for downloading the MusicXML file for a solo instrument. */
export function musicxmlDownloadUrl(
  projectId: string,
  instrumentKey: string,
  style: SheetStyle = "clean"
): string {
  return `${API_BASE_URL}/api/projects/${projectId}/download/musicxml?instrument=${encodeURIComponent(instrumentKey)}&style=${style}`;
}

/** Save the full chord marker list (replaces what's stored). */
export function updateChords(
  projectId: string,
  chords: ChordMarker[]
): Promise<{ chords: ChordMarker[] }> {
  return request<{ chords: ChordMarker[] }>(
    `/api/projects/${projectId}/chords`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chords }),
    }
  );
}

/**
 * Ask the backend for rough diatonic chord suggestions from the current
 * melody. Replaces the stored chord list and returns it with a reminder
 * that suggestions are only a starting point.
 */
export function suggestChords(
  projectId: string
): Promise<{ chords: ChordMarker[]; message: string }> {
  return request<{ chords: ChordMarker[]; message: string }>(
    `/api/projects/${projectId}/chords/suggest`,
    { method: "POST" }
  );
}

/** Direct URL for downloading the plain-text chord chart. */
export function chordChartDownloadUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${projectId}/download/chords`;
}

/** One cell of the tab preview grid; `i` is the note index it belongs to. */
export interface TabCell {
  t: string;
  i: number | null;
}

export interface TabEntry {
  note_index: number;
  pitch_name: string;
  start_time: number;
  string: number;
  fret: number | null;
  out_of_range: boolean;
}

export interface TabData {
  instrument: string;
  label: string;
  tuning: string;
  string_names: string[];
  octave_offset: number;
  note_count: number;
  entries: TabEntry[];
  warnings: string[];
  /** systems -> lines (one per string) -> cells. */
  systems: TabCell[][][];
  text: string;
}

/**
 * Fetch the text-tab layout for a fretted instrument (guitar/bass/ukulele).
 * Built from the current saved notes, so it reflects note edits once the
 * auto-save has run.
 */
export function fetchTab(
  projectId: string,
  instrumentKey: string
): Promise<TabData> {
  return request<TabData>(
    `/api/projects/${projectId}/tab?instrument=${encodeURIComponent(instrumentKey)}`
  );
}

/** Direct URL for downloading the tab as a .txt file. */
export function tabDownloadUrl(
  projectId: string,
  instrumentKey: string
): string {
  return `${API_BASE_URL}/api/projects/${projectId}/download/tab?instrument=${encodeURIComponent(instrumentKey)}`;
}

/**
 * Fetch the PDF sheet music for a solo instrument as a Blob.
 *
 * Unlike the other downloads this goes through fetch rather than a plain
 * link: PDF generation can fail server-side, and a fetch lets the UI show
 * the backend's error message instead of a broken tab.
 */
export async function fetchPdf(
  projectId: string,
  instrumentKey: string,
  style: SheetStyle = "clean"
): Promise<Blob> {
  const url = `${API_BASE_URL}/api/projects/${projectId}/download/pdf?instrument=${encodeURIComponent(instrumentKey)}&style=${style}`;
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ApiError(
      "Could not reach the backend. Is the backend server running on port 8000?"
    );
  }
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      // non-JSON error body; fall through to the generic message
    }
    throw new ApiError(
      detail || `PDF download failed: ${response.status} ${response.statusText}`,
      response.status
    );
  }
  return response.blob();
}
