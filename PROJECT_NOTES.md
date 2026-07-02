# BandChart AI — Project Notes

Living notes for contributors (human or AI). Last updated after v0.2 (2026-07).
If you are a new Claude Code session: read this file, then README.md, before changing code.

## Purpose

BandChart AI turns songs into editable lead sheets, solo sheets, band charts and custom
arrangements. Long-term: a rehearsal/arranging tool for musicians. Current state: an early
local-only prototype that does real audio-to-notes transcription and exports solo parts.

The owner is non-technical and runs the app in **GitHub Codespaces** (sometimes Mac).
Explanations, error messages, and README instructions must stay beginner-friendly.

## Version history

### v0.1 — Transcription prototype (done)
- Create project → upload audio (`.wav .mp3 .flac .ogg .m4a .aiff .aif`, ≤50MB)
- Real monophonic pitch transcription with **librosa pYIN** (`backend/app/transcription.py`):
  22050 Hz mono, C2–C7 range, frames grouped into notes, <0.09s notes dropped
- Outputs: `transcription.mid` (pretty_midi) + `transcription.json`
  (notes: `pitch`, `pitch_name`, `start_time`, `duration`, `confidence` 0–1)
- Frontend: piano-roll SVG preview + note table, MIDI/JSON downloads
- Reliability pass: friendly upload/transcription errors, "What works best" guidance box,
  upload/transcribe progress states (spinner + elapsed seconds), "Start again with a
  different file" flow, zero-notes empty state; re-upload clears stale outputs

### v0.2 — MusicXML + solo instrument selector (done)
- `backend/app/musicxml.py`: notes → MusicXML via **music21**; fixed 120 BPM, 4/4,
  sixteenth-note quantization, auto rests/clef; saved to project outputs folder
- 8 instruments: `concert`, `piano`, `flute`, `violin`, `alto_sax`, `tenor_sax`,
  `trumpet`, `clarinet` (keys shared between backend `INSTRUMENTS` dict and
  `frontend/lib/instruments.ts` — keep in sync)
- Transposition uses music21's built-in instrument transpositions:
  alto sax written +9 semitones above concert, tenor sax +14, trumpet/clarinet +2,
  others 0. Exported parts carry `<transpose>` so MuseScore plays at concert pitch
- Frontend: instrument dropdown on transcribed projects, note table shows
  **concert pitch + written pitch** columns, MusicXML download button follows selection

### v0.3 — planned next
**PDF sheet music export from MusicXML.** Not started. Notes for the implementer:
- MuseScore CLI (`mscore -o out.pdf in.musicxml`) is the usual high-quality route but is a
  heavy install for Codespaces; LilyPond (via `music21` → `lilypond`) or `verovio`
  (pip-installable, SVG→PDF) are lighter options — evaluate `verovio` first
- Keep the existing MusicXML pipeline as the source; PDF should be derived from it
- Same delivery pattern: endpoint `GET /api/projects/{id}/download/pdf?instrument=<key>`,
  file saved in outputs folder, download button follows the instrument selector

**Still out of scope (owner has said "not yet" repeatedly):** accounts, payments, full band
charts, rehearsal packs, YouTube, chord detection, stem separation, drums, complex editing,
redesigns. Do not add these without being asked.

## What has been tested and confirmed working
All verified end-to-end in-browser (Playwright/Chromium) and via API calls through the
Next.js proxy, plus confirmed by the owner in Codespaces:
- Full flow: create project → upload → real pYIN transcription → preview → downloads
- Synthetic 3-note test (C4/G4/C5 sine tones) detected correctly, 0.90–0.95 confidence
- 15MB upload arrives intact; 43-second transcription completes (proxy limits raised)
- All 8 MusicXML exports parse in music21 round-trip with correct written offsets
  (0 / +9 / +14 / +2) and `<transpose>` only on transposing instruments
- Error paths: bad extension/oversize/empty rejected client-side and server-side with
  friendly messages; stale outputs cleared on re-upload (notes/MIDI/MusicXML 404 after)
- `tsc --noEmit` and `npm run lint` clean; scripts syntax-checked and exercised

## Current limitations
- **Monophonic only**: pYIN follows one melody line; chords/full-band mixes won't work
- **Rhythm is rough**: fixed 120 BPM assumption, 4/4, sixteenth-grid quantization —
  MusicXML timing will not match the recording's real tempo
- `.mp3`/`.m4a` need ffmpeg on the server (Codespaces: `sudo apt-get install -y ffmpeg`);
  `.wav/.flac/.ogg` work without
- Synchronous transcription request (no job queue); Next proxy timeout raised to 10 min
- No delete-project endpoint; no auth; local JSON-file storage only
- pitch range C2–C7; notes shorter than 0.09s dropped

## Exact commands to run it

### GitHub Codespaces (owner's usual environment)
Terminal 1 — backend:
```bash
cd /workspaces/bandchart-ai/backend
python3 -m venv .venv            # first time only
source .venv/bin/activate
pip install -r requirements.txt  # first time and after every git pull
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Terminal 2 — frontend:
```bash
cd /workspaces/bandchart-ai/frontend
npm install                      # first time and after every git pull
npm run dev
```
Open via **Ports tab → port 3000 → globe icon**. Port 8000 never needs to be public —
the Next server proxies `/api/*` to the backend (see `frontend/next.config.ts`).

### Mac (double-click scripts at repo root)
`check.command` → `setup.command` → `start.command`. See README for details.

## Architecture / key files
```
backend/  FastAPI (Python 3.9+; owner's Codespace uses 3.12)
  app/main.py           all routes under /api; friendly error mapping
  app/transcription.py  pYIN engine — DO NOT swap without explicit request
  app/musicxml.py       music21 export + INSTRUMENTS table
  app/storage.py        storage/projects/<id>/{project.json,audio/,output/}
frontend/ Next.js 16 (app router, Tailwind, TypeScript)
  app/page.tsx                  project list/create
  app/projects/[id]/page.tsx    the whole project workflow UI
  lib/api.ts                    typed fetch helpers; API_BASE_URL defaults to "" (same-origin)
  lib/instruments.ts            instrument keys/labels/offsets (mirror of backend)
  next.config.ts                /api rewrite proxy, 60MB body, 10-min timeout,
                                allowedDevOrigins for *.app.github.dev
```
API endpoints: see the table in README.md. Project statuses:
`created → uploaded → transcribing → transcribed | failed`.

## Working conventions & gotchas
- **Delivery flow**: work on branch `claude/bandchart-transcription-v0.1-ion3pb`, restart it
  from `origin/main` after each merge (its PRs get merged into `main` right away, with the
  owner's standing approval, so their Codespace `git pull` just works). Never push to main.
- **Frontend note (Next.js 16)**: `frontend/AGENTS.md` warns APIs differ from training
  data — read `node_modules/next/dist/docs/` before nontrivial Next changes. Real examples:
  proxy body buffering (`experimental.proxyClientMaxBodySize`), proxy timeout
  (`experimental.proxyTimeout`), `allowedDevOrigins`.
- **Browser can't reach port 8000 in Codespaces** — that's why the proxy exists. Never
  reintroduce absolute `http://localhost:8000` URLs in browser-side code.
- music21 import is heavy (seconds); it's imported at module load in `musicxml.py`.
- Root `.gitignore` covers `.venv/`, `__pycache__/`, `node_modules/`, `.next/`,
  `backend/storage|uploads|outputs`. The owner once staged 874 venv files — if Source
  Control shows huge counts, it's environment junk, not source; `git reset`, don't commit.
- Verify changes for real before shipping: run both servers and drive the UI (Playwright
  with `executablePath: '/opt/pw-browsers/chromium'` in this environment), not just tsc/lint.
