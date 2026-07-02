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

### v0.3 — PDF sheet music export (done)
- `backend/app/pdf.py`: MusicXML → verovio (SVG pages) → cairosvg (per-page PDF) → pypdf
  merge. All pip-installable; cairosvg needs the libcairo2 system library (present in
  Codespaces/most Linux; README has a troubleshooting entry). Imports are lazy so a missing
  library fails only the PDF request, never backend startup
- Endpoint: `GET /api/projects/{id}/download/pdf?instrument=<key>` (same keys as MusicXML);
  saves `output/transcription-<instrument>.pdf`; derived from the MusicXML pipeline
- **Gotcha (hard-won)**: verovio toolkits must NOT be created per request — font loading
  breaks after a few instantiations across FastAPI's worker threads. `pdf.py` keeps one
  lazy singleton toolkit behind a `threading.Lock`; keep it that way
- Metronome `<direction>` elements are stripped before engraving (their note glyph needs a
  music text font cairosvg can't load → renders as a box); the .musicxml keeps the tempo
- v0.2 improvement ride-along: MusicXML/PDF now carry a real title
  ("<project name> — <instrument>") instead of music21's "Music21 Fragment" default
- Frontend: "Download PDF (<instrument>)" button follows the selector; uses fetch + blob
  (not a plain link) so PDF failures show the backend's friendly message in a red box

### v0.4 — notation cleanup (done)
- `backend/app/notation_cleanup.py`: pure-Python pass between transcription and
  MusicXML/PDF export (stored transcription.json is never modified). Pipeline:
  pitch-wobble smoothing (short jump-and-return notes absorbed into neighbours) →
  same-pitch merge (gaps ≤0.12s) → fragment removal (<0.15s) → eighth-note quantization
  (starts and durations, at the fixed 120 BPM)
- `notes_to_musicxml(style="clean"|"raw")`: clean (default) runs cleanup + estimates a key
  via music21 `analyze('key')`, inserts a KeySignature (transposes correctly through
  toWrittenPitch), and respells accidentals to match the key (flats in flat keys, no
  E#/Cb/double accidentals). raw = literal v0.3 behaviour (sixteenth grid, no key sig),
  title gets a "(raw transcription)" suffix, filenames a "-raw" suffix
- **Gotcha (hard-won)**: music21 pitches created from MIDI numbers carry explicit
  natural Accidental objects; makeAccidentals then displays spurious naturals. The respell
  step strips alter==0 accidentals — keep that, or naturals reappear
- Endpoints take `style=clean|raw` (default clean, 400 on anything else); frontend has a
  "Sheet music style" radio toggle (Cleaned recommended/default vs Raw)
- MIDI/JSON downloads intentionally stay raw — they're the faithful record

### v0.6 — planned next
Not decided; the owner has hinted YouTube import is next on their wish list, but it is NOT
approved yet — ask before building it. (Long-term list also: full band charts, rehearsal
packs, tabs; see out-of-scope below.)

### v0.5.6 — sheet music as the main play-along surface (done)
- OSMD now draws TWO simultaneous cursors (`cursorsOptions` in the constructor):
  type 3 "current measure" wash (orange, alpha 0.12) + type 0 "current notes" box
  (orange, alpha 0.45). Both are stepped together in the follow effect
- Cursors are parked VISIBLY at the first entry when the sheet loads and whenever
  playback stops (position null → step 0, no more hide()); pause freezes them in place
- **Gotcha (hard-won)**: OSMD sizes cursor overlays via width/height ATTRIBUTES on
  1px-tall <img> elements; Tailwind preflight's `img { height: auto }` collapses them to
  invisible hairlines (this was why the v0.5.5 cursor felt like it "didn't follow").
  CSS `height: revert` does NOT fix it (presentational hints are skipped by revert);
  the fix is `fixCursorSize()` in SheetMusic.tsx re-applying inline style.height/width
  after every cursor show/update — keep calling it after each move
- Sheet box grew to max-h 600px; the piano roll moved into a collapsed
  `<details>` "Advanced note timeline" so the score is the primary surface
- Follow-along granularity is note-entry level on the quantized sheet (stated in the UI);
  true beat-accurate sync to the literal recording timing would need per-note mapping
  between raw times and engraved positions — a possible future refinement

### v0.5.5 — Play Along fixes (done)
- **Softer playback voices** (`PlayAlong.tsx` `scheduleNoteSound`): Piano-ish default
  (triangle + octave sine, percussive decay, lowpass), Soft synth (detuned sines, slow
  attack), Pluck (fast exponential decay) — plain Web Audio, still no Tone.js
- **In-browser sheet music** (`frontend/components/SheetMusic.tsx`): OpenSheetMusicDisplay
  2.0 (npm dep) renders the generated MusicXML (selected instrument + style; re-fetches
  when notesVersion bumps). Playback cursor: entry timestamps are collected once by
  walking OSMD's cursor (RealValue whole-notes × 2 = seconds at the fixed 120 BPM), then
  the cursor jumps deterministically to the last entry ≤ transport position. The cursor
  follows the quantized beat grid, not literal recording timing — stated in the UI.
  drawTitle/Subtitle/Composer/Credits all false (OSMD otherwise prints a "Music21" credit)
- **Auto-scroll** (default on, toggle in the panel, state owned by the page): sheet
  scrollbox, piano-roll horizontal scroll, and note-table vertical scroll each keep the
  current position in view; all scroll ONLY their own container, never the page
- **Note deletion**: ✕ per table row edits a client working copy instantly; a debounced
  (600ms) auto-save PUTs to `/api/projects/{id}/notes`, which rewrites transcription.json
  AND regenerates the MIDI — so JSON/MIDI/MusicXML/PDF all reflect edits (MusicXML/PDF
  generate on demand from transcription.json). `POST /notes/reset` restores
  `transcription-original.json`, snapshotted at transcribe time. Editing notes stops
  playback (PlayAlong's cleanup effect keys on `notes`)
- **More aggressive cleanup** (clean style): min fragment 0.15→0.2s, merge gap
  0.12→0.2s, wobble window 0.15→0.22s, plus a second smooth+merge pass to catch
  cascading wobbles exposed by the first merge
- **Lint gotcha (recurring)**: react-hooks rules forbid synchronous setState in effect
  bodies — set state in async callbacks/event handlers, or key derived state on a deps
  string (see SheetMusic's `depsKey`/`result` pattern)

### v0.5 — Play Along mode (done)
- Frontend-only; no backend changes, no new dependencies (plain Web Audio API, no Tone.js)
- `frontend/components/PlayAlong.tsx`: oscillator-per-note playback of the RAW
  transcription notes (matching the piano roll; the style toggle affects downloads only)
  - Look-ahead scheduler: a requestAnimationFrame loop schedules triangle-wave
    oscillators (attack/release-enveloped) up to 0.25s ahead on the AudioContext clock;
    transport position = anchorPos + (ctx.currentTime - anchorCtx) * rate
  - Play/Pause/Stop, speeds 0.5/0.75/1/1.25 (re-anchors live; pitch unchanged),
    optional 4-click square-wave count-in (only on fresh starts, beat = 0.5s/rate),
    auto-stop at the end, resume mid-note re-schedules the remainder
  - **Lint gotcha**: the new react-hooks rules reject self-referencing useCallbacks and
    render-phase ref writes — the rAF body lives in a ref assigned inside a useEffect,
    scheduled via a stable `tick` wrapper; keep that structure
- Highlighting: PlayAlong reports (position, noteIndex) via onTick each frame; page passes
  playheadTime/currentNoteIndex to NotePreview (orange playhead line + orange current
  rect) and currentIndex to a memoized NoteTable (orange row, `data-playing` attr) so
  60fps position updates don't re-render the table
- AudioContext is created on the first Play click (browser autoplay policy) and closed on
  unmount

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
- PDF export: valid `%PDF-` files for all 8 instruments; visually inspected (real engraved
  notation, correct title/part name, no missing-glyph boxes); 12 sequential + 6 concurrent
  requests all succeed (singleton-toolkit fix); browser download event fires; simulated
  500 shows the friendly error in the UI
- v0.4 cleanup: unit-tested (wobble absorption, same-pitch merge, fragment drop, grid
  snap, melody preservation); on a synthetic vibrato melody with re-articulations the
  cleaned engraving went from 9 notes / 2 ties / 4 accidentals / 3 sixteenths (raw) to
  7 notes / 0 ties / 0 accidentals / 0 sixteenths with a correct F major signature
  (transposing to D major for alto sax); PDFs visually compared; style toggle + filenames
  verified in-browser; clean is the default when no style param is sent
- v0.5 Play Along, all in-browser (headless Chromium): play advances time and flips the
  button to Pause; current-note row highlighted and playhead rendered; pause freezes and
  resume continues; stop resets and clears highlights; 2s of wall clock advances the
  transport ~2s at 100% vs ~1s at 50%; count-in holds transport at 0 for the first ~2s;
  auto-stop fires at the end; all six download endpoints still 200 afterwards
- v0.5.6: both cursors render as real boxes (40px tall) at the start before playback,
  move across systems during playback, the sheet auto-scrolls when the cursor leaves a
  shortened viewport, pause freezes and stop returns the cursors to the start (visible);
  PUT/reset note edits and all download endpoints re-verified after the layout change
- v0.5.5: OSMD sheet renders (svg) with cursor visible and moving during playback;
  deleting a note updates table rows, preview rects, JSON note_count, MIDI note count
  (pretty_midi round-trip), MusicXML and project.note_count; reset restores; auto-scroll
  moves the piano roll during playback and stays put when toggled off; voice selector
  defaults to Piano-ish; aggressive-cleanup unit cases (0.18s fragment dropped, 0.18s gap
  merged, 0.2s wobble absorbed, cascading wobble caught); `npm run build` passes with OSMD
- Error paths: bad extension/oversize/empty rejected client-side and server-side with
  friendly messages; stale outputs cleared on re-upload (notes/MIDI/MusicXML 404 after)
- `tsc --noEmit` and `npm run lint` clean; scripts syntax-checked and exercised

## Current limitations
- **Monophonic only**: pYIN follows one melody line; chords/full-band mixes won't work
- **Rhythm is approximate**: fixed 120 BPM assumption, 4/4; cleaned style quantizes to an
  eighth grid (raw: sixteenth) — no real tempo/meter detection, so timing won't match a
  performance that isn't near 120 BPM
- **Cleanup trade-offs**: repeated same-pitch notes with small gaps merge into one longer
  note; genuinely fast ornaments shorter than ~0.15s are treated as noise and dropped;
  key estimation can pick a wrong key on short/chromatic material (raw style is the
  escape hatch)
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
  app/musicxml.py       music21 export + INSTRUMENTS table (style=clean|raw)
  app/notation_cleanup.py  wobble/merge/fragment/quantize pipeline for clean style
  app/pdf.py            verovio/cairosvg/pypdf PDF engraving (singleton toolkit + lock)
  app/storage.py        storage/projects/<id>/{project.json,audio/,output/}
frontend/ Next.js 16 (app router, Tailwind, TypeScript)
  app/page.tsx                  project list/create
  app/projects/[id]/page.tsx    the whole project workflow UI (memoized NoteTable inside,
                                note-edit working copy + debounced auto-save)
  components/PlayAlong.tsx      Web Audio play-along engine + panel (3 synth voices)
  components/SheetMusic.tsx     OSMD sheet render + playback cursor sync
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
