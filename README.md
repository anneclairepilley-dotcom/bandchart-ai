# BandChart AI

AI music arranging and rehearsal app that turns songs into editable lead sheets, solo sheets, band charts and custom arrangements.

## v0.1 — Transcription Prototype

This is the smallest possible working prototype: a local web app where you upload an audio
file and the backend runs **real audio-to-MIDI transcription** using Spotify's open-source
[Basic Pitch](https://github.com/spotify/basic-pitch) model. Everything runs on your own
computer — no accounts, no payments, no cloud services, no data leaves your machine.

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

---

## Quick Start (Mac) — no coding required

This folder includes three double-click scripts that do all the technical setup for you.
Use them in order, top to bottom.

**Step 0 — Get the app onto your Mac.** Download or clone this repository, then open the
`bandchart-ai` folder in Finder. You should see `check.command`, `setup.command`, and
`start.command` inside it.

**Step 1 — Check your computer is ready.** Double-click **`check.command`**.

A Terminal window opens and tells you whether Python, Node.js, npm, and ffmpeg are
installed, with a one-line command to install anything that's missing (via
[Homebrew](https://brew.sh) — the script tells you how to get that too, if you don't have it).
Fix anything marked `[MISSING]`, then run it again until everything says `[OK]`.

**Step 2 — Set everything up.** Double-click **`setup.command`**.

This installs everything the app needs, including TensorFlow (the machine-learning library
Basic Pitch runs on) — that download can take **several minutes** the first time. Let it run
until it says "Setup complete!". It's safe to run again later if anything seems broken.

**Step 3 — Start the app.** Double-click **`start.command`**.

This starts the app and opens it in your browser at http://localhost:3000. Keep the Terminal
window open while you use the app — closing it (or pressing Ctrl+C inside it) stops the app.

That's it. Create a project, upload a song, click "Run Transcription", and download the results.

> **macOS says a script "cannot be opened because it is from an unidentified developer":**
> right-click (Control-click) the file, choose **Open**, then click **Open** again in the
> dialog that appears. You only need to do this once per script.
>
> **Double-clicking does nothing / opens a text editor instead of Terminal:** open Terminal
> (Applications → Utilities → Terminal), type `cd `, drag the `bandchart-ai` folder into the
> window, press Return, then run `./check.command` (and later `./setup.command`,
> `./start.command`) the same way.

---

## Manual setup (Windows / Linux / advanced users)

The double-click scripts above are macOS-only. On any other platform, or if you'd rather run
things yourself, follow these steps.

Requires **Python 3.9–3.11** (TensorFlow, which Basic Pitch depends on, doesn't yet support
newer Python versions) and **Node.js 18+**. Install `ffmpeg` too if you want to transcribe
compressed formats like mp3/m4a (wav/flac/ogg work without it).

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

## Architecture

```
backend/    FastAPI service — local JSON-file project storage, Basic Pitch transcription
frontend/   Next.js app — upload UI, transcription preview, downloads
```

- Backend stores everything under `backend/storage/projects/<project_id>/`:
  `project.json`, the uploaded `audio/`, and the generated `output/transcription.mid` +
  `output/transcription.json`.
- Frontend talks to the backend over HTTP (`NEXT_PUBLIC_API_BASE_URL`, default
  `http://localhost:8000`).

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
