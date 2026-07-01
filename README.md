# BandChart AI

AI music arranging and rehearsal app that turns songs into editable lead sheets, solo sheets, band charts and custom arrangements.

## v0.1 — Transcription Prototype

This is the smallest possible working prototype: a local web app where you upload an audio
file and the backend runs **real audio-to-MIDI transcription** using Spotify's open-source
[Basic Pitch](https://github.com/spotify/basic-pitch) model. No accounts, no payments, no
cloud services — everything runs locally and stores files on disk.

**What it does:**
- Create a project
- Upload an audio file (wav, mp3, flac, ogg, m4a, aiff)
- Run real ML-based transcription on the uploaded audio (Basic Pitch / TensorFlow, runs on CPU)
- Generate a MIDI file and a JSON file listing every detected note (pitch, start time, duration, confidence)
- Preview the transcription in the browser (simple piano-roll + note table)
- Download the MIDI and JSON files

**Explicitly out of scope for v0.1:** accounts, payments, full band charts, rehearsal packs,
PDF export, MusicXML export, YouTube support, complex editing, stem separation, drums, chord
detection. Just transcription.

### Architecture

```
backend/    FastAPI service — local JSON-file project storage, Basic Pitch transcription
frontend/   Next.js app — upload UI, transcription preview, downloads
```

- Backend stores everything under `backend/storage/projects/<project_id>/`:
  `project.json`, the uploaded `audio/`, and the generated `output/transcription.mid` +
  `output/transcription.json`.
- Frontend talks to the backend over HTTP (`NEXT_PUBLIC_API_BASE_URL`, default
  `http://localhost:8000`).

## Running it locally

Requires **Python 3.10–3.11** and **Node.js 18+**. `ffmpeg` should be installed on your
system so Basic Pitch/librosa can decode compressed formats like mp3/m4a (wav/flac/ogg work
without it).

### 1. Backend (FastAPI + Basic Pitch)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # pulls in TensorFlow, can take several minutes
uvicorn app.main:app --reload --port 8000
```

The backend now runs at http://localhost:8000 (interactive API docs at
http://localhost:8000/docs). It creates `backend/storage/` on first use.

### 2. Frontend (Next.js)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The app runs at http://localhost:3000. By default it talks to the backend at
`http://localhost:8000` — copy `frontend/.env.local.example` to `frontend/.env.local` if you
need to point it elsewhere.

### 3. Use it

1. Open http://localhost:3000
2. Create a project, giving it a name
3. Upload an audio file
4. Click "Run Transcription" and wait for it to finish (real model inference — a few seconds
   to a couple of minutes depending on file length and your machine)
5. View the note preview, and download the `.mid` and `.json` files

## API summary (backend)

All endpoints are under `/api`.

| Method | Path | Description |
| --- | --- | --- |
| POST | `/projects` | Create a project — `{"name": string}` |
| GET | `/projects` | List all projects |
| GET | `/projects/{id}` | Get one project |
| POST | `/projects/{id}/audio` | Upload audio (multipart field `file`) |
| POST | `/projects/{id}/transcribe` | Run transcription on the uploaded audio |
| GET | `/projects/{id}/notes` | Get the detected-notes JSON |
| GET | `/projects/{id}/audio` | Stream the original uploaded audio |
| GET | `/projects/{id}/download/midi` | Download the generated MIDI file |
| GET | `/projects/{id}/download/json` | Download the generated notes JSON file |

Each note in the JSON output has: `pitch` (MIDI number), `pitch_name` (e.g. `"C4"`),
`start_time` (seconds), `duration` (seconds), and `confidence` (0–1, derived from Basic
Pitch's note amplitude estimate).
