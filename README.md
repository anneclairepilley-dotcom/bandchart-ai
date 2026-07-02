# BandChart AI

AI music arranging and rehearsal app that turns songs into editable lead sheets, solo sheets, band charts and custom arrangements.

## v0.5.5 — Transcription + Solo Parts + Sheet Music + Play Along + Editing

This is the smallest possible working prototype: a local web app where you upload an audio
file and the backend runs **real audio-to-pitch transcription** using
[librosa](https://librosa.org/)'s pYIN algorithm. Everything runs on your own computer — no
accounts, no payments, no cloud services, no data leaves your machine.

pYIN is a genuine, well-established pitch-tracking algorithm — it follows one melodic line at
a time (monophonic: a single voice, vocal line, or solo instrument, not full chords). It was
chosen over deep-learning models like Basic Pitch/TensorFlow because it's pure Python/numpy —
no TensorFlow — so it installs reliably everywhere, including GitHub Codespaces and other
environments with newer Python versions.

**What it does:**
- Create a project
- Upload an audio file (wav, mp3, flac, ogg, m4a, aiff)
- Run real pitch-tracking transcription on the uploaded audio (librosa pYIN, runs on CPU, no GPU/TensorFlow needed)
- Generate a MIDI file and a JSON file listing every detected note (pitch, start time, duration, confidence)
- Preview the transcription in the browser (simple piano-roll + note table)
- Pick a solo instrument (concert pitch, piano, flute, violin, alto sax, tenor sax, trumpet,
  clarinet) — the note table shows both the detected concert pitch and the written pitch,
  transposed for E♭/B♭ instruments
- Download MIDI, JSON, MusicXML (sheet music that opens in
  [MuseScore](https://musescore.org) and similar apps), and **PDF sheet music** — all
  written for the chosen instrument
- Choose between two sheet-music styles: **Cleaned sheet music** (default — smooths pitch
  wobbles, merges repeated fragments, drops noise blips, snaps rhythm to an eighth-note
  grid, and adds an estimated key signature so most notes engrave without accidentals) or
  **Raw transcription** (every detected note, literally, on a sixteenth grid)
- **Play Along mode**: hear the transcribed notes in the browser with Play/Pause/Stop, a
  moving playhead and current-note highlighting, playback speeds of 50/75/100/125%, an
  optional 4-click count-in, and a running time display (playback uses the generated
  transcription, not the original audio)
- **Three playback sounds** — Piano-ish (default), Soft synth, Pluck — softer little
  synthesizer voices instead of harsh beeps
- **Sheet music in the browser**: the generated notation renders right on the project page
  (via OpenSheetMusicDisplay), for the selected instrument and style — and it's the main
  play-along surface: an orange box highlights the current notes, a lighter wash marks the
  current bar, the cursor sits visibly at the start before you play, returns there on
  Stop, and the sheet auto-scrolls to keep the current bar in view
- **Auto-scroll** (on by default, toggleable): the sheet music, piano roll and note table
  keep the current note in view while playing
- **Delete wrong notes**: a ✕ button on each row of the note table removes a misdetected
  note — the preview, playback, sheet music and every download update automatically, and
  "Reset to original transcription" undoes all edits

**Explicitly out of scope so far:** accounts, payments, full band charts, rehearsal packs,
PDF export, YouTube support, complex editing, stem separation, drums, chord detection.

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

This installs everything the app needs (librosa and the other Python/Node packages) — the
first run can take a minute or two. Let it run until it says "Setup complete!". It's safe to
run again later if anything seems broken.

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

## Quick Start (GitHub Codespaces) — no coding required

Codespaces gives you a Linux terminal in your browser — paste these commands into it one
block at a time and press Enter after each.

**1. Get the latest code** (skip this if you just opened a brand-new Codespace):
```bash
git pull
```

**2. Set up and start the backend:**
```bash
cd backend
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Leave this running. Codespaces will pop up a notification offering to open port 8000 — you
can ignore/dismiss it. The app talks to the backend through the frontend's own server, so
port 8000 never needs to be opened or made public.

**3. Open a second terminal** (click the `+` in the terminal panel, or menu **Terminal → New
Terminal**) and start the frontend:
```bash
cd frontend
npm install
npm run dev
```

**4. Open the app.** Click the **Ports** tab (next to the Terminal tab), find port **3000**,
and click the globe/open-in-browser icon next to it — or Codespaces may pop up a "your
application running on port 3000" notification with an **Open in Browser** button.

That's it. Create a project, upload a song, click "Run Transcription", and download the results.

> **Getting `ffmpeg: command not found`, or mp3/m4a files fail to transcribe:** run
> `sudo apt-get update && sudo apt-get install -y ffmpeg` in the terminal, then try again.
> (wav/flac/ogg files work without ffmpeg.)

---

## Manual setup (Windows / Linux / advanced users)

The double-click scripts above are macOS-only, and the Codespaces steps assume a browser
terminal. On any other platform, or if you'd rather run things yourself, follow these steps.

Requires **Python 3.9+** and **Node.js 18+**. Install `ffmpeg` too if you want to transcribe
compressed formats like mp3/m4a (wav/flac/ogg work without it).

### 1. Backend (FastAPI + librosa)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
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

The app runs at http://localhost:3000. The frontend's own server proxies all `/api` requests
to the backend at `http://localhost:8000`, so no extra configuration is needed — copy
`frontend/.env.local.example` to `frontend/.env.local` only if your backend runs somewhere
else.

### 3. Use it

1. Open http://localhost:3000
2. Create a project, giving it a name
3. Upload an audio file
4. Click "Run Transcription" and wait for it to finish (real pitch-tracking analysis — a few
   seconds to a minute or so depending on file length and your machine)
5. View the note preview, pick a solo instrument, and download the `.mid`, `.json`,
   `.musicxml` and `.pdf` files

> **Updating from an older version?** After `git pull`, run
> `pip install -r requirements.txt` in the backend once more (with the virtual environment
> active) — newer versions add libraries (music21 for MusicXML, verovio/cairosvg/pypdf for
> PDF export).

### Trying the PDF export and cleanup (beginner steps)

1. Open a project that has finished transcribing (status "transcribed")
2. Pick an instrument from the **Solo instrument** dropdown — e.g. *Alto Sax (E♭)*
3. Leave **Sheet music style** on *Cleaned sheet music* (the default)
4. Click **Download PDF (Alto Sax (E♭))**. The button shows "Preparing PDF…" for a few
   seconds while the sheet music is engraved, then the file lands in your Downloads folder
5. Open it with any PDF viewer (double-click it — no special software needed). You should
   see a titled page of real notation, transposed for the instrument you picked
6. **To see what the cleanup does:** switch the style to *Raw transcription*, download the
   PDF again (it gets `-raw` in its filename), and compare the two side by side — the raw
   one typically has many more short notes, ties and accidentals
7. If something goes wrong, a red message appears under the buttons telling you what to do —
   the MusicXML download keeps working either way

**What the cleanup can and can't do:** it makes real recordings much more readable, but it
assumes a steady tempo near 120 BPM and works note-by-note — it won't fix a rushed
performance, detect the real tempo or time signature, or turn a rough take into a polished
chart. The rhythm you see is still an approximation. The MIDI and JSON downloads always
contain the untouched detection regardless of the style toggle.

### Trying Play Along (beginner steps)

1. Open a transcribed project and find the **Play Along** panel (below the download buttons)
2. Click **Play** — after the optional 4-click count-in you'll hear the detected notes,
   and the **sheet music follows along**: the orange box moves note to note, the light
   wash tracks the current bar, and the score scrolls itself. (The note table highlights
   too, and a piano-roll view lives under "Advanced note timeline" if you want it.)
3. **Pause** freezes playback where it is; pressing **Play** again continues from there;
   **Stop** resets to the beginning
4. Try the speed buttons — **50%** and **75%** are handy for practising along slowly;
   pitch stays the same, only the pace changes
5. Remember: playback is the *transcription*, not your recording — if a note sounds wrong
   here, it will also be wrong in the sheet music, which makes this a quick way to check a
   transcription by ear

### Fixing wrong notes (beginner steps)

1. In the **Note detail** table, find the wrongly detected note (playing along and watching
   the highlight is the easiest way to spot it)
2. Click the red **✕** at the end of its row — the note disappears from the preview, the
   sheet music, playback, and all downloads (a "Edits saved" note confirms it)
3. Deleted too much? Click **Reset to original transcription** to get everything back
4. The sheet music panel and the downloads always match what's left in the table

| API | Method | Path |
| --- | --- | --- |
| Save edited notes | PUT | `/api/projects/{id}/notes` |
| Undo all edits | POST | `/api/projects/{id}/notes/reset` |

## Troubleshooting

**PDF download fails with a message about "cairo".** The PDF engine uses a system library
called cairo that is preinstalled in GitHub Codespaces and on most computers. If it's
missing, run `sudo apt-get update && sudo apt-get install -y libcairo2` in the terminal,
restart the backend, and try again. The MusicXML download works regardless.

**"Could not reach the backend" error in the app.** Two usual causes: (1) the backend isn't
running — check the terminal where you started `uvicorn`; it should say
`Uvicorn running on http://0.0.0.0:8000` with no errors above it. (2) You're on old code —
run `git pull` in the project folder, then stop the frontend (Ctrl+C in its terminal) and
start it again with `npm run dev`. Older versions made the browser call the backend's port
directly, which fails in Codespaces; the current version routes everything through the
frontend server.

**`ModuleNotFoundError: No module named 'distutils'` during `pip install`.** This happened
with the earlier version of this project, which used Basic Pitch/TensorFlow — TensorFlow
doesn't support the newer Python versions that ship by default in environments like GitHub
Codespaces, and installing it could fall back to a build process that needed the `distutils`
module Python removed in 3.12+. The app no longer uses Basic Pitch/TensorFlow at all (see
above), so this shouldn't happen anymore. If you still hit it: make sure you have the latest
code (`git pull`), delete any old virtual environment (`rm -rf backend/.venv`), and reinstall
following the steps above.

## Architecture

```
backend/    FastAPI service — local JSON-file project storage, librosa pYIN transcription
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
| GET | `/projects/{id}/download/musicxml?instrument=<key>&style=<clean\|raw>` | Download MusicXML for a solo instrument — instrument keys: `concert`, `piano`, `flute`, `violin`, `alto_sax`, `tenor_sax`, `trumpet`, `clarinet`; style defaults to `clean` |
| GET | `/projects/{id}/download/pdf?instrument=<key>&style=<clean\|raw>` | Download PDF sheet music (same parameters) |

Each note in the JSON output has: `pitch` (MIDI number), `pitch_name` (e.g. `"C4"`),
`start_time` (seconds), `duration` (seconds), and `confidence` (0–1, pYIN's voiced-pitch
probability for that note, averaged over its frames).
