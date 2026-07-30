# BandChart AI — Project Notes

Living notes for contributors (human or AI). Last updated after v0.9.4 (2026-07).
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

### v0.7 — guitar / bass / ukulele tab (done)
- `backend/app/tablature.py`: the detected melody (the working notes, raw — same list as
  the note table and Play Along, so indexes line up) becomes text tab for three fretted
  instruments in standard tuning: guitar E2 A2 D3 G3 B3 E4, bass E1 A1 D2 G2, ukulele
  G4 C4 E4 A4 (high G, reentrant — range extremes must be found by pitch, not line order)
- Placement: each note goes on one string at the lowest playable fret (≤15). If the
  melody doesn't fit the instrument, a whole-octave shift is chosen automatically
  (most notes in range, then most frets ≤12, then smallest shift — bass usually lands
  −1 or −2 octaves) and reported as a warning; notes that still don't fit render as `x`
  on the nearest string and are listed in a warning. Never crashes on range problems
- Layout: one column per note in time order, `|` at each measure change (2s bars at the
  fixed 120 BPM), systems wrapped at ~56 chars. Built once in Python and returned BOTH as
  plain text (the .txt download) and as per-line cells tagged with note indexes so the
  web preview can highlight the playing column — don't duplicate the layout in TS
- Endpoints: `GET /projects/{id}/tab?instrument=<guitar|bass|ukulele>` (JSON for the
  preview) and `GET /projects/{id}/download/tab?instrument=…` (.txt). 400 for
  non-fretted instruments and for empty note lists (download only), 404 untranscribed
- guitar/bass/ukulele were ALSO added to the INSTRUMENTS table (musicxml.py +
  lib/instruments.ts, now 11 keys) with written_offset 0 (music21 treats them as
  non-transposing), so MusicXML/PDF keep working for them — as staff notation. The UI
  says a proper tab PDF is a later version
- Frontend: `components/TabView.tsx` (SheetMusic's depsKey fetch pattern; re-fetches on
  notesVersion bump so note deletes update it after auto-save). Fretted selection swaps
  the Sheet music panel for a Tab output panel; Download TAB button appears only for
  fretted keys. Play Along is untouched and highlights the tab column via
  currentNoteIndex (cells carry the note index; whole column highlights)
- Tab is generated from the detected melody line — it is NOT full guitar/bass extraction
  from a mixed song, and there are no chords (still monophonic)

### v0.8 — blue playhead, readable tab, note editing (done)
- **Blue sheet playhead** (SheetMusic.tsx): the orange note-box cursor is gone. OSMD now
  has cursor 0 = light BLUE measure wash (visible) and cursor 1 = an INVISIBLE (alpha 0)
  note-box cursor used ONLY at load time: it is walked once to record every entry's
  {time, x, top, height} (update() + fixCursorSize() per step, then hide()). The visible
  note follower is our own absolutely-positioned 3px blue div (data-testid
  sheet-playhead), placed by interpolating between the current and next entry's x within
  a system on every play tick — so it GLIDES rather than jumps. Pause freezes it (the
  transport stops ticking), stop parks it at entry 0, speed changes stay in sync because
  it's driven purely by transport position. It lives as a SIBLING of the OSMD container
  inside a position:relative wrapper (OSMD clears the container's innerHTML on reload —
  the playhead must not be inside it); entry offsets are relative to that wrapper.
  fixCursorSize() is still required (the Tailwind img-collapse gotcha from v0.5.6)
- **Tab readability** (tablature.py + TabView.tsx): note columns widened to a 3-dash
  prefix (both the .txt download and the preview — the layout still lives ONLY in
  Python); preview font text-sm→text-base, leading-7, p-4; string names dark+semibold,
  dashes/bars muted gray-400 so the lines read as strings, fret numbers font-bold
  near-black, out-of-range x bold red. Orange current-column highlight kept
- **Inline note editing** (page.tsx): the note table's pitch/start/duration cells are now
  UNCONTROLLED inputs committing on blur/Enter; row keys include the note values so rows
  re-mount (fresh defaultValue) whenever a note actually changes — that's how reset and
  external updates refresh the inputs. Pitch accepts note names (G4, F#3, Bb3 — parsed
  by parsePitchInput) or MIDI 0-127; start ≥ 0; duration > 0 (mirrors backend Note model
  bounds). Invalid input → clear red message (editError, data-testid edit-error), state
  untouched. "+ Add a note" appends after the last note (same pitch, 0.5s) — also
  offered in the all-notes-deleted empty state. Every commit re-SORTS the working copy
  by start_time — playback scheduling, noteIndexAt, and the tab's note_index mapping all
  assume sorted order; keep that invariant. Saving reuses the existing debounced PUT, so
  JSON/MIDI/MusicXML/PDF/tab all regenerate with no extra "regenerate" button needed
- No backend changes beyond the tab spacing — PUT /notes validation already covered edits
- **Testing gotcha (hard-won)**: reading /api/.../notes IMMEDIATELY after a save from
  test code can return a stale body (parallel in-flight GETs resolve out of order under
  Playwright's waitForFunction polling). The app itself is fine — its PUTs were traced
  and are single, ordered and correct. In tests, wait on a CONTENT-specific predicate
  (e.g. "the added note is present"), not just note_count, and assert on that same
  response body

### v0.9 — chord / lead sheet basics (done)
- **Manual chord markers first**: stored INSIDE transcription.json under "chords"
  ([{name, start_time}], kept sorted). `_save_working_notes` reads and re-writes the
  existing chords, so note edits/deletes/reset NEVER touch them; a fresh
  transcription/upload starts them at []. Old transcription.json files without the key
  parse fine (`.get("chords", [])` everywhere, frontend `data.chords ?? []`)
- `backend/app/chords.py`: name validation (regex — starts A–G, optional #/b, tail of
  chord letters/digits, optional /bass, ≤12 chars), `m21_chord_figure` (music21 wants
  '-' for flats: "Bbm7"→"B-m7", only root+bass letters converted), chord chart text
  (bar grid `| C | G | Am F |` + per-chord timing list; 2s bars at the fixed 120 BPM),
  and `suggest_chords`: music21 key estimate → per-bar best diatonic triad
  (duration-weighted pitch-class overlap + root bonus, repeats merged) — deliberately
  rough, always labelled as a starting point, NOT chord detection from audio
- Endpoints: GET/PUT `/projects/{id}/chords` (400 friendly message on a bad name),
  POST `/chords/suggest` (replaces the list, returns the "rough starting point"
  message; 400 when there are no notes), GET `/download/chords` (chord-chart .txt;
  400 when the chord list is empty)
- **Chord symbols on sheet/PDF/MusicXML**: notes_to_musicxml takes chords and inserts
  music21 harmony.ChordSymbol objects. **Gotchas**: (1) inserted AFTER key analysis,
  respell and bestClef so chords never change how the melody engraves — which means
  toWrittenPitch has already run, so transposing instruments get the symbols
  transposed BY HAND via `symbol.transpose(m21_inst.transposition.reverse())` (alto
  sax: C→A, Am→F#m — verified); (2) `_respell_for_key` must iterate
  getElementsByClass(note.Note), NOT `.notes` — ChordSymbol is a NotRest and has no
  `.pitch` (would crash). OSMD renders the <harmony> elements in the browser sheet and
  verovio renders them in the PDF — no frontend engraving work needed
- Frontend: `components/ChordsPanel.tsx` (rows of uncontrolled name/start inputs with
  the note-table commit pattern, add/suggest/reset/Download Chord Chart buttons,
  invalid-name/-time errors, non-blocking yellow warning for chords past the melody
  end) + exported `ChordStrip` (bar-grid line) shown above BOTH the sheet and the tab.
  Page owns chords state with its own debounced PUT (600ms) that bumps notesVersion so
  the sheet/tab refetch and show updated symbols; suggest saves server-side (set
  pendingChordSaveRef=false BEFORE setChords or it double-saves). Sheet heading flips
  to "Lead sheet (melody + chords)" with an info line (instrument, 120 bpm, 4/4) when
  chords exist
- Chords for fretted instruments stay names-only (strip above the tab) — no strummed
  chord shapes/diagrams yet, stated in the UI

### v0.9.1 — real sheet-music workflow (done)
- **Home hero** (app/page.tsx): "Turn sound into sheet music", central upload + YouTube
  (rights checkbox kept) — auto-creates a project (named from the filename, or renamed
  to the video title when the auto-name "YouTube import" is still in place) and routes
  to the project page. Failed hero uploads/imports delete the half-made project. No
  record button (recording isn't supported — don't pretend)
- **Setup step** (project page, status "uploaded"): instrument grid (INSTRUMENTS now
  12 keys — added `voice` / Voice / Vocals, m21 Vocalist, offset 0; NO drums — the
  engine can't do them), mode cards (`direct_transcription` | `solo_arrangement`) with
  the required "BandChart is melody-first. Full band separation is coming later." note,
  Advanced settings (time signature predict/4-4/3-4/6-8 — predict currently means 4/4
  and the option label says so; key predict/C/G/D/A/F/Bb/Eb/Am/Em/Dm; rhythm detail
  readable|precise, readable default). Start transcription = POST /settings (validated
  400s) then POST /transcribe; button guarded by a startBusy state (double-click safe).
  YouTube import from the project page NO LONGER auto-transcribes — it lands on this
  setup step. Settings live on the Project model (all Optional, old projects fine)
- **Readable rhythm** (notation_cleanup.make_readable, runs after clean_notes when
  rhythm_detail != "precise"): eighth-grid start snapping, durations snapped to
  (0.5, 1, 1.5, 2, 3, 4) ql — but durations LONGER than 4 ql keep their grid-rounded
  length so held notes tie instead of truncating; quaver-or-smaller gaps absorbed when
  the stretch stays simple; same-slot collisions keep the EARLIER note. On the test
  melodies: 0 ties / 0 sixteenths vs raw's 16 / 9. Playback/tab/JSON stay raw
- **Piano grand staff** (musicxml.py): two stream.PartStaff joined by layout.StaffGroup
  (brace), split at middle C (>= 60 treble), explicit clefs, chords on the treble
  staff. **Gotcha (hard-won, adversarial review):** BOTH staves must be padded with
  trailing rests to the same ceil-to-bar length — if one staff ends earlier,
  makeNotation emits different measure counts per staff, silently drops/misplaces
  harmony symbols and draws a final barline mid-piece
- **Settings plumbing**: time signature drives meter + bar length EVERYWHERE (4/4=2s,
  3/4 & 6/8=1.5s: chord chart, suggest windows, tab bar lines via seconds_per_bar
  params, frontend ChordStrip/ChordsPanel via secondsPerBar prop); chosen key drives
  the engraved KeySignature (KEY_SHARPS) and chord suggestions; solo_arrangement adds
  "(solo arrangement)" to the engraved title + a badge in the UI
- **Chord suggest upgrades** (chords.py): key_name forcing, major-key V→V7 when the
  bar clearly holds the seventh, uncertainty flag (correlationCoefficient < 0.5 —
  calibrated: clean tonal melodies ~0.65-0.9, noise ~0; and 0.0 is a REAL score, only
  None means unknown) → falls back to C major and the endpoint message says so
- **Per-instrument playback** (PlayAlong.tsx): Sound selector gained "Auto (match
  instrument)" default; patches piano/wind/guitar/bass/uke resolved from
  lib/instruments.ts patchForInstrument via a patchRef effect. Old explicit voices kept
- Built under a 3-lens adversarial review workflow: it caught the grand-staff unequal
  padding, readable-mode long-note truncation, a Start double-click race, the
  0.0-certainty mask, same-slot keep-later inconsistency, stale YouTube copy, stale
  setupError, and the frontend's hardcoded 2s bars — all fixed and re-verified

### v0.9.4 — Engine Lab: comparing transcription engines honestly (done)
Owner's core complaint: Mrs Magic (a hard real piano recording) still doesn't transcribe
well enough, and we'd been swapping engines on hope rather than evidence. v0.9.4 does NOT
touch the main transcription pipeline at all — it adds a completely separate side area for
running engines against the same audio and comparing them with real numbers.

**`backend/app/engine_lab/`** (new package, isolated from `app/transcription.py` and
`app/polyphonic.py` — imports FROM them, never the other way):
- `base.py` — `EngineAdapter` dataclass (key/label/description/availability_check/run_fn)
  and `EngineRunOutput` (notes, messages). `is_available()` wraps the check in try/except
  so a broken import can never crash the `/engines` listing
- `adapters.py` — `ADAPTERS` registry, 5 entries:
  - `pyin` → wraps `transcription._detect_notes` directly (bypasses `run_transcription`'s
    fallback chain — the lab wants to see EACH engine's own raw output, not the app's
    auto-fallback behavior)
  - `basic_pitch` → wraps `polyphonic._detect_with_basic_pitch` directly
  - `cqt` → wraps `polyphonic._detect_with_cqt` directly
  - `piano_expert` (ByteDance) and `omnizart` — both `is_available()` return
    `(False, <specific honest reason>)`; `run_fn` raises `NotImplementedError` (never
    called, since routes.py checks availability before calling run() — see below)
- `fixtures.py` — 5 synthetic test clips generated deterministically with numpy+soundfile
  (same percussive-tone technique as prior scratch fixtures: fundamental + quiet octave,
  exponential decay): `a4_tone`, `c_major_chord` (C4E4G4), `c_major_scale` (8 sequential
  notes), `block_chords` (C/F/G major triads in sequence), `bass_and_melody` (held C2+G2
  bass dyad under a 7-note RH melody, genuinely overlapping — a good register-spanning
  polyphony test). Each carries `expected_notes` (pitch/start/duration) for scoring.
  Cached to `backend/storage/engine_lab/fixtures/<key>.wav` on first request
- `scoring.py` — greedy pitch-exact + 0.2s-tolerance matching against expected notes;
  reports correct/missed/extra, a simultaneity check (did an expected chord cluster's
  matched detections ALSO cluster together, not just each individually match), mean
  timing error, and a simple 0-100 rough_score_percent. Deliberately simple per the
  owner's "don't overcomplicate this"
- `stats.py` — engine-agnostic comparable stats (note_count, overlapping_notes,
  chord_groups, pitch_range) computed by RE-clustering start times from scratch (40ms
  window, same constant as polyphonic.py's GROUP_WINDOW_S) — never trusts a "group" field
  the engine may or may not have set, so pyin (no groups) and basic_pitch (has groups)
  are measured identically
- `storage.py` — `backend/storage/engine_lab/{fixtures,audio,runs}/` — completely
  separate tree from `backend/storage/projects/`, so a lab run can never touch a real
  project's transcription.json
- `routes.py` — `APIRouter(prefix="/api/engine-lab")`, included via
  `app.include_router()` in main.py. `POST /runs` resolves the source (project audio via
  `storage.find_existing_audio`, fixture via `fixtures.ensure_fixture_audio`, or a
  lab-only upload), calls `adapter.run()` inside try/except (a crashing engine becomes a
  run record with `error` set, never a 500), writes MIDI via the EXISTING
  `transcription.write_midi_from_notes` (reused, not reimplemented), computes stats +
  scoring (if the source was a fixture), and persists the full run. `is_available()` is
  checked BEFORE calling run() so an unavailable engine returns 400 "Engine unavailable:
  {reason}" instead of ever reaching `_run_piano_expert`'s `NotImplementedError`

**Frontend**: `frontend/app/engine-lab/page.tsx` (new route `/engine-lab`, linked quietly
at the bottom of `app/page.tsx` — "a developer tool... not part of the normal workflow"),
`lib/engineLab.ts` (typed fetch helpers, deliberately separate from `lib/api.ts`),
`components/EngineLabPianoRoll.tsx` (small read-only SVG piano roll, colored by chord
group, opacity by confidence — NOT a reuse of NotePreview.tsx, which is playhead/seek-
coupled to Play Along and would've been more work to decouple than to write fresh).
Runs accumulate client-side (prepended, newest first) into a comparison table; a fresh
run auto-expands its detail row (piano roll + scoring + messages); clicking a row toggles
expand/collapse. Source picker: fixture (with audio preview `<audio>` tag) / existing
project / direct upload, matching "choose an audio file already uploaded/imported" from
the request plus a lab-only upload path for convenience.

**Investigation findings** (background agents, see README's Engine Lab section for the
owner-facing summary):
- **ByteDance `piano_transcription_inference`**: package installs cleanly (no conflicts
  with this venv's numpy 2.x/librosa/scipy — confirmed in a throwaway venv), but needs
  PyTorch (a real Linux/no-CDN-cache install here pulled the FULL CUDA 13 stack,
  ~5.2GB, since only the default PyPI wheel was reachable — a CPU wheel would be much
  smaller but `download.pytorch.org` was blocked by this sandbox's egress policy) AND
  auto-downloads a ~165MB checkpoint from Zenodo on first use (`zenodo.org` also
  blocked here, so the checkpoint fetch failed — `wget` silently wrote a 0-byte file,
  `PianoTranscription(device='cpu')` then crashed with `EOFError` unpickling it).
  Upstream repo (`bytedance/piano_transcription`) is archived as of Dec 2025 — no more
  fixes coming. Could NOT verify actual transcription quality end-to-end here.
  Registered in `adapters.py` as `piano_expert`, permanently `is_available()=False`
  with this exact reasoning as the UI's unavailable_reason — NOT wired to run, per
  "don't make it default until it passes tests here"
- **Omnizart**: genuinely works — installed cleanly on Python 3.10 (NOT this app's
  3.12; the container has no 3.8/3.9), needed one system package
  (`apt-get install portaudio19-dev` for the `pyaudio` build) and hit a
  `collections.MutableSequence` removal (Python 3.10+) inside `madmom==0.16.1`, which
  omnizart's own `__init__.py` already monkeypatches around — a real upstream fix, not
  something BandChart needs to work around itself. Downloaded ~700MB of checkpoints,
  ran actual piano/chord/drum/vocal transcription via CLI on a synthetic WAV, all
  succeeded on CPU (20-95s per short clip). Total footprint ~3.5GB. Registered as
  `omnizart` adapter, permanently unavailable — needs a genuinely separate venv +
  subprocess bridge to integrate safely, which is future work, not this version
- **MT3 (Magenta)**: research-only (not installed) — no PyPI package, requires cloning
  a repo and installing JAX/T5X/TensorFlow largely from source, checkpoints via
  `gsutil` from GCS. Caretaker-mode maintenance (trivial commits only since ~2022).
  Skipped, not worth the setup burden for a hobbyist Mac user
- **"MuScriptor"**: research-only. Surprising find — this is real (Kyutai + MireloAI,
  mid-2026), pip-installable, CPU-capable small variant, actively maintained. BUT its
  model weights are **CC BY-NC 4.0 (non-commercial only)** — code is MIT, weights are
  not free for a product that could become paid. Flagged for the owner, not integrated
  pending a licensing decision

**Sample cross-engine comparison** (this environment, CPU, run via the lab's own API):
A4 tone: all three available engines 100%. C major chord: pYIN 0% (1 note, no chord —
exactly its known limitation), CQT and Basic Pitch both 100% (3 notes, 1 chord group).
C major scale: pYIN and Basic Pitch 100%, CQT 99% (1 harmonic-driven extra note). Block
chords (C/F/G): pYIN 0%, CQT and Basic Pitch both 100% (9 notes, 3 groups). Bass+melody
(the hardest synthetic test — overlapping registers): pYIN 56% (can't hold the bass under
the melody, monophonic), CQT 96% (5 extra, harmonic-driven), Basic Pitch 96% (6 extra).
Timing: CQT is fastest (~0.04s), Basic Pitch next (~0.13-0.15s), pYIN slowest (~1-1.6s
per run — the Viterbi decoder itself, not JIT: numba warmup is a ONE-TIME ~20s cost on
the very first pyin call in a fresh process, separate from this steady-state number).

**Mrs Magic**: named as the hard real-world benchmark (`youtu.be/yO_OD7Yx2j8`). Could NOT
be run from this cloud environment — YouTube blocks import attempts from cloud servers,
same limitation as the rest of the app (see the existing "Run locally on Mac" section).
Owner needs to import it locally and compare engines in the lab there; do not claim it's
solved without that real test.

**Chord feature**: still parked under Experimental tools (v0.9.3), untouched this
version — v0.9.4 was entirely about note detection per the request ("Do not add more
chord features").

### v0.9.3 — better note detection and real polyphony (done)
The whole version went into note detection; weak side features were parked.

**Engine audit (as of v0.9.2, what v0.9.3 changed):**
- Pitch detection was `librosa.pyin` in `backend/app/transcription.py::_detect_notes` —
  a frame-by-frame MONOPHONIC pitch tracker (one melody line); notes were created right
  there by grouping consecutive same-pitch frames. Weaknesses: repeated same-pitch notes
  glued into one long note, no amplitude/velocity, low-confidence blips kept
- Rhythm cleanup lives in `backend/app/notation_cleanup.py` (`clean_notes` +
  `make_readable`), applied ONLY at export time inside `musicxml.py` — the stored
  transcription.json is never modified
- Exports: MIDI written at transcribe/edit time by `transcription.write_midi_from_notes`;
  MusicXML/PDF/TAB/chord chart generated on demand from transcription.json by
  `musicxml.py`/`pdf.py`/`tablature.py`/`chords.py` via `main.py`
- For simultaneous notes the missing pieces were: a real multi-pitch detector, a note
  format that marks chord membership, chord-aware cleanup, and editor support — all
  added in v0.9.2/v0.9.3 as below

**What v0.9.3 did:**
- **Basic Pitch is the primary polyphonic engine** (`backend/app/polyphonic.py::
  _detect_with_basic_pitch`): Spotify's open-source ICASSP-2022 model, run on CPU via
  the ONNX network bundled in the pip package. NO TensorFlow: `pip install --no-deps
  basic-pitch` + onnxruntime/resampy/mir_eval in requirements.txt. **Gotcha
  (hard-won)**: basic-pitch's declared deps pin tensorflow<2.15.1 which has no wheels
  for Linux Python 3.12 — a plain `pip install basic-pitch` backtracks into source
  builds and fails; `--no-deps` is REQUIRED, and `basic_pitch.inference.predict()`
  auto-selects the bundled ONNX model when TF/coreml/tflite are absent. Import kept
  lazy (~1.2s). ~1s inference for a 5s clip. Post-filters: pitch 24–100, amplitude
  ≥0.32, short+weak ghost removal (<0.18s & <0.42), then `_assign_groups` clusters
  onsets within 40ms into `"group": "chord_N"` ids, caps groups at 4 (strongest
  kept, honest message). Detected C/F/G sine triads EXACTLY (9 notes, 3 groups)
- Fallback chain: Basic Pitch missing → v0.9.2 CQT detector (now also group-tagged)
  with a "see the README to enable the model" message; CQT empty/failed → pYIN
  melody-only ("Fell back to melody-only transcription."); every step keeps the old
  behaviour working with a clear detection_note, never a crash
- **Melody engine improved** (`transcription.py`): repeated same-pitch notes that pYIN
  glues together are split at RE-ATTACK onsets — onset_detect candidates gated by an
  RMS dip-and-rise check (after ≥1.35× before), because raw onsets fire on vibrato
  (the wobbly fixture over-split 8→11 without the gate; with it: exactly 8, and the
  previously-merged repeated F4s separate). Low-confidence notes (<0.35 mean pYIN
  voicing prob) dropped with "Low-confidence notes were removed." — but never if that
  would empty the transcription
- **Note format**: optional `velocity` (0–1) + `group` ("chord_N") on Note
  (models.py, lib/api.ts); Basic Pitch fills both; PUT /notes round-trips them
  (model_dump(exclude_none=True) keeps older notes tidy); MIDI velocity prefers
  the detector's loudness; sortNotes on the page sorts (start_time, pitch) to match
  the backend
- **Chord-aware cleanup** (`notation_cleanup.clean_notes_poly`): eighth-grid starts,
  same-slot pitches dedupe (longest ring wins), ≤4 per event, readable duration
  snapping (>semibreve kept for ties; Precise keeps the literal grid), clipped to the
  next event, group ids reassigned. Used by musicxml.py for poly instead of skipping
  cleanup entirely (v0.9.2 behaviour)
- **Play Along**: per-note velocity scales loudness (floored at 0.35 so quiet chord
  members stay audible); resume/seek now re-schedules the remainder of EVERY
  mid-ring note, not just the first (chords resume whole)
- **Editor**: Chord column shows group ids; on POLY projects a per-row blue **+**
  adds a note at the SAME start time (a third above, source group/velocity copied)
  for building chords; ✕ still deletes a single note out of a chord. The row + is
  hidden on melody projects on purpose: the mono engraving path keeps one note per
  grid slot, so a stacked note would silently vanish from MusicXML/PDF (found by
  the adversarial review)
- **Review-round fixes** (adversarial workflow + E2E on synthetic chord fixtures):
  Basic Pitch events same-pitch REJOINED when the model splits one decaying note in
  two (gap ≤0.15s and no RMS re-attack at the junction); weak harmonic ghosts
  (+12/+19/+24/+28 above a stronger cluster member, <0.8× its confidence)
  suppressed like the CQT path; melody re-strike pieces carry an optional
  "reattack": true flag that merge_same_pitch/quantize respect, so the split
  repeated notes survive into the ENGRAVED clean sheet (they used to be re-merged);
  tab chord clustering uses a 40ms window (BP members aren't sample-identical);
  musicxml.py/pdf.py write via unique temp file + os.replace (concurrent sheet
  fetch + download no longer reads a half-written file)
- **Chord tools parked**: ChordsPanel moved into a collapsed "Experimental tools
  (chord markers)" details at the bottom of the project page; ChordStrip above
  sheet/tab and the "Lead sheet" heading flip removed. Roadmap note shown in the UI:
  Ultimate Guitar-style chord sheets are a much later feature, probably v5.0. All
  backend chord endpoints/exports unchanged
- Messages wired end-to-end: "Polyphonic detection is experimental…" (poly notice),
  "Fell back to melody-only transcription.", "Too many simultaneous notes… strongest
  4 were kept (simplified output).", "Low-confidence notes were removed.", "This
  audio is too dense for the current model." (when ≥half the chord moments overflow)
- setup.command installs basic-pitch (--no-deps) with a friendly fallback note;
  README documents the extra pip line for Codespaces/manual setups
- **Follow-up round (owner's Mac findings + label change)**: basic-pitch PINNED
  to ==0.4.0 everywhere (setup.command, README) — the owner's Terminal errors
  ("No module named pkg_resources", "scipy.signal has no attribute 'gaussian'")
  come from pip backtracking to ANCIENT basic-pitch versions while resolving
  its TensorFlow dep; 0.4.0 uses scipy.signal.windows.gaussian (current API) so
  NO scipy pin is needed — verified working with scipy 1.18. setuptools added
  to requirements.txt (provides pkg_resources; missing from fresh 3.12 venvs).
  UI label renamed to "Basic Pitch / multiple notes"; notice wording is now
  "Multiple-note detection works best with clear piano or simple chords. Dense
  songs may still need editing." Every note carries "source":
  "basic_pitch"|"cqt"|"pyin" (optional Note field, survives PUT round-trips)

### v0.9.2 — readability, click-to-seek, experimental polyphony (done)
- **Contrast sweep**: dim grays lifted one step app-wide (text-gray-400/500 → 600,
  button/input borders 300 → 400, card borders 200 → 300, darker StatusBadge text,
  darker piano-roll SVG labels). Still the light theme — v2.0 stays the big redesign
- **Click-to-seek**: PlayAlong exposes seek() via a registerSeek callback prop (page
  keeps it in a ref). Rules: playing → silenceAll + restart transport at the position
  (no count-in); paused → move the frozen position; stopped → set startPosRef, which a
  fresh Play (still with count-in) starts from; Stop resets it to 0. Click surfaces:
  the sheet (nearest entry — entry tops vary a few px WITHIN a system, so cluster with
  a ±100px band, never exact-match tops), the piano-roll timeline (linear x = 40px +
  60px/s), tab columns (note index → start time) and note-table rows (guard: ignore
  clicks on inputs/buttons). onTick fires immediately on seek so playhead/wash follow
  even while stopped
- **Experimental multiple-note detection** (backend/app/polyphonic.py): CQT (C2..B6,
  1 bin/semitone) + onset segmentation; per segment up to 4 locally-peaked bins above
  relative (25% of top) + absolute floors, harmonics suppressed (+12/+19/+24/+28 above
  an accepted note unless ≥80% of its energy); per-bin sustain trims durations.
  Wired as note_detection = "melody"|"poly" on Project/settings; run_transcription
  falls back to pYIN with a clear detection_note on failure/empty; transcription.json
  gains "detection" + "detection_note" (preserved by _save_working_notes like chords).
  Verified: sine triads C/F/G detected exactly, silence falls back with message
- Poly downstream: musicxml groups same-grid-slot notes into m21 chord.Chord objects
  (per staff on the piano grand staff; mono cleanup/readable passes are SKIPPED for
  poly — they'd merge or drop chord members); grand-staff padding counts NotRest (not
  just Note) so chords count toward staff length; MIDI/JSON overlap naturally;
  Play Along schedules overlapping notes together already; note editor shows/edits
  same-start rows; TAB stays melody-first (top note of each same-start group, original
  indexes kept for highlight, warning shown). Frontend defaults poly ONLY for
  piano + direct transcription (until the user touches the Note detection control)
- **Bar numbers**: OSMD options drawMeasureNumbers + drawMeasureNumbersOnlyAtSystemStart
  → numbers sit at system starts above the top staff, no mid-score floaters
- **Testing gotcha**: Playwright mouse.click uses viewport coordinates and does NOT
  auto-scroll — scrollIntoViewIfNeeded() the sheet first or every click silently
  misses and reads as "seek doesn't work" (it did; the clicks never landed)

### v1.0 — planned next
Not decided. Ask the owner. Long-term: v2.0 is still planned as the big black/silver
premium redesign (not yet — the owner will ask for it explicitly). The app is still
melody-first and strongest on clear single melody lines; multiple-note detection is
experimental (clear piano / simple chords only); auto chords are rough suggestions
only; accurate complex-piano / full-band transcription and stem separation remain
future work. Other long-term items (full band charts, rehearsal packs) remain
unapproved; see out-of-scope below.

### v0.6.2 — verovio made optional for Mac setup (done)
- verovio sometimes has no wheel for a Mac's Python/OS combo and fails to compile
  (clang++ error, usually missing Xcode CLT). It is ONLY used for server-side PDF
  engraving — the browser sheet preview is OSMD (npm), unaffected
- setup.command: if the full pip install fails, it retries with verovio filtered out and
  finishes with a clear note (PDF disabled, MusicXML+MuseScore alternative, and the
  xcode-select --install path to enable PDFs). requirements.txt still lists verovio so
  Codespaces' single pip install keeps PDF working
- pdf.py: `import verovio` failure now raises a friendly runtime message (surfaced by the
  existing PDF-button error box); the cairo message is Codespaces/Mac aware

### v0.6.1 — YouTube blocked fallback (done)
- YouTube frequently bot-blocks cloud/data-centre IPs (Codespaces included) — this is a
  YouTube-side refusal, not an app bug. The error mapper now detects bot checks and
  HTTP 403/429 responses (checked BEFORE the generic network branch, since these arrive
  wrapped in "Unable to download API page: HTTP Error 403" text) and shows: "YouTube
  blocked this cloud server from downloading the audio. This can happen in Codespaces.
  Try another video, upload an audio file instead, or run the app locally."
- UI: permanent note under the YouTube panel ("If YouTube blocks import, download or
  record the audio yourself and use Upload audio file instead.") and a
  "Switch to Upload audio file" button inside the error box for one-click fallback
- README gained a "YouTube import limitations in Codespaces" section

### v0.6 — YouTube URL import (done)
- `backend/app/youtube.py`: yt-dlp (pip dep) probes then downloads bestaudio and converts
  to WAV via the ffmpeg postprocessor. URL validation requires a real video reference
  (watch?v=…, youtu.be/…, shorts/…; playlist-only watch?list= links rejected). Probe-stage
  guards: live streams and unknown-duration videos rejected; >600s rejected. Downloads use
  the RESOLVED entry URL + playlist_items="1" so a playlist can never expand
- `POST /api/projects/{id}/youtube` {url, rights_confirmed}: 400s for empty/invalid URL or
  unticked rights; friendly mapped errors for private/age-restricted/unavailable videos,
  bot checks, network/blocked YouTube (502), and missing yt-dlp/ffmpeg (500 with install
  commands). **Failed imports never touch existing work**: download goes to
  project_dir/import-tmp and the old audio/outputs are cleared only after success
  (temp → clear → move). A delete-during-import race is guarded: project existence is
  rechecked before the final save so deleted projects can't resurrect
- Project metadata: source_type ("upload"/"youtube"), source_url, rights_confirmed,
  imported_at (optional fields; old projects parse fine). Upload sets source_type="upload"
- Frontend: "Add audio" box has Upload/YouTube mode toggle; YouTube panel has URL input,
  the exact rights checkbox wording, privacy + monophonic notes, button disabled until
  URL+rights, import progress text, and auto-runs transcription on success. "Imported
  from YouTube: <url>" shows in uploaded and transcribed views
- **Test-only escape hatch**: BANDCHART_ALLOW_ANY_URL=1 lets automated tests feed the
  endpoint a direct media URL (yt-dlp generic extractor) where youtube.com is blocked —
  it also skips the unknown-duration rejection. NEVER set it in normal use; unset =
  strict YouTube-only validation
- Built under adversarial review (3-lens workflow): it caught the clear-before-download
  data-loss bug, the live-stream duration bypass, the playlist expansion, the
  delete-during-import resurrection, and a stale saveError in the frontend — all fixed
  and re-verified. YouTube itself is unreachable from the dev sandbox, so the live-fetch
  step was verified via the generic extractor; the owner has since confirmed real
  YouTube import working on a local Mac (Codespaces may still be bot-blocked)

### v0.5.7 — safe project deletion (done)
- `DELETE /api/projects/{id}` removes the project's whole storage folder
  (`storage/projects/<id>/` — audio, outputs, metadata) via `storage.delete_project`,
  which refuses any path that doesn't resolve to a direct child of storage/projects/
  (defense-in-depth against traversal); 404 for unknown ids, friendly 500 detail on failure
- Dashboard: red Delete button per row (outside the row's Link so clicks don't navigate),
  native `window.confirm` with the agreed wording, optimistic list removal on success,
  error banner on failure, per-row "Deleting…" disabled state
- No note-count/other side effects — deletion is whole-project only; note-level deletes
  remain the v0.5.5 ✕/reset feature

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
- v0.6 YouTube import: full pipeline via the test hatch (real yt-dlp download + ffmpeg
  WAV conversion + transcription + all downloads); rights checkbox gates the button;
  URL/rights/live/duration/playlist validation unit-tested; error-mapper unit-tested
  against real yt-dlp error strings; failed import verified to leave an existing
  transcription fully intact (notes/midi/audio/reset all 200 after a 502 import);
  upload + note-edit + delete regressions re-run green in-browser
- **OWNER-CONFIRMED (2026-07): YouTube import works for real on a local Mac** — the
  import feeds the existing transcription pipeline exactly as designed, and normal audio
  upload still works alongside it. PDF export needed one extra step locally
  (`brew install cairo`), after which the whole app works. Codespaces may still get
  bot-blocked by YouTube (expected; local Mac is the reliable path for YouTube import)
- v0.9: chords unit-tested (name accept/reject lists, Bb→B- figure mapping, chart
  format, suggestions valid + diatonic for the F-major fixture); API-tested via the
  proxy (CRUD, invalid-name 400, chart download, chords inside the JSON download,
  chords surviving a note edit AND notes/reset, suggest save+message, MusicXML with 3
  <harmony> elements, alto-sax harmony roots transposed +9); PDF visually shows F/Gm/F
  above the right bars; in-browser (Playwright, 33 checks green): full owner test
  order — add C, add+rename G, C→Am, delete G, add F, bar numbers, invalid
  name/start errors, past-end warning appears and clears, lead-sheet heading +
  info line + strip, chord symbols visible in the OSMD svg, chart download content,
  suggest flow with rough-note message, note-edit + reset keep chords, tab + strip +
  Download TAB coexist; upload/transcribe/YouTube-gate/delete regressions green;
  npm run build + tsc + lint clean
- v0.8: in-browser (Playwright, 33 checks green): playhead parked visible at start,
  moves smoothly during playback, freezes on pause, keeps moving after a speed change,
  returns to start on stop; tab renders bold/dark fret numbers at text-base for all
  three instruments and the .txt download carries the wider spacing; pitch/duration/
  start edits land in the saved JSON and the tab preview, invalid pitch/duration/start
  each show their message and change nothing, delete + add note verified end to end
  (added note appended after the last, Play Along total updates), MIDI verified by
  pretty_midi round-trip after a pitch edit and after reset, MusicXML contains the
  edited pitch; upload→transcribe, YouTube validation errors, project delete and all
  download endpoints re-checked green; npm run build + tsc + lint clean
- v0.7 tab: fret mapping unit-tested (guitar melody on the top string, bass auto-shift
  −2 octaves with warning, ukulele open strings, mixed-extreme melody gets `x` + both
  warnings, empty list, TabError on piano); all three .txt downloads verified via the
  proxy; in-browser (Playwright): tab preview appears for all three instruments with
  correct string lines, Download TAB fires a real download with the right filename and
  content, Play Along runs with a tab instrument and highlights the current column
  (checked mid-playback at the correct note), deleting a note removes its column from
  preview AND download after auto-save, reset restores it, piano still shows OSMD sheet
  with no tab UI, staff MusicXML/PDF 200 for the fretted keys in both styles, all
  pre-v0.7 endpoints re-checked 200, `npm run build` + tsc + lint clean
- v0.5.7 delete: confirmation shows the exact agreed wording; cancel keeps the project;
  confirm removes it from the list immediately and survives a page refresh; the storage
  folder is gone from disk; other projects (sheet, downloads) unaffected; deleting an
  unknown id returns 404
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
- **Melody-first**: the default engine (pYIN) follows one melody line. Polyphonic mode
  (v0.9.3, Basic Pitch) is experimental — clear piano / simple chords only, max 4
  simultaneous notes; full-band mixes and dense piano still won't transcribe accurately.
  The best results still come from clear recordings of one instrument
- **Rhythm is approximate**: fixed 120 BPM assumption default 4/4 (3/4 and 6/8 selectable);
  cleaned style quantizes to an eighth grid (raw: sixteenth) — no real tempo/meter
  detection, so timing won't match a performance that isn't near 120 BPM
- **Cleanup trade-offs**: repeated same-pitch notes with small gaps can still merge when
  there's no clear re-attack (v0.9.3 splits them when the loudness dips and rises);
  genuinely fast ornaments shorter than ~0.15s are treated as noise and dropped;
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
pip install --no-deps basic-pitch  # v0.9.3 polyphonic model (--no-deps is REQUIRED)
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

Local Mac requirements (owner's working configuration): Homebrew; Python 3.12
(`brew install python@3.12` — the scripts prefer it and rebuild the venv from older
Pythons automatically); Node/npm; ffmpeg (`brew install ffmpeg` — required for YouTube
import and mp3/m4a); yt-dlp (installed automatically by setup.command into
backend/.venv); and Cairo (`brew install cairo`) for PDF export.

## Architecture / key files
```
backend/  FastAPI (Python 3.9+; owner's Codespace uses 3.12)
  app/main.py           all routes under /api; friendly error mapping
  app/transcription.py  pYIN melody engine (+ re-attack splitting, confidence floor)
                        — DO NOT swap without explicit request
  app/youtube.py        yt-dlp/ffmpeg YouTube audio import (validation + guards)
  app/musicxml.py       music21 export + INSTRUMENTS table (style=clean|raw)
  app/tablature.py      text tab for guitar/bass/ukulele (tunings, octave fit, layout)
  app/polyphonic.py     polyphonic detection: Basic Pitch (ONNX, lazy import) primary,
                        CQT+onset fallback; chord grouping, max 4 at once
  app/chords.py         chord-name validation, chart text, rough suggestions, keys
  (settings: Project.instrument/mode/time_signature/key_signature/rhythm_detail)
  app/notation_cleanup.py  wobble/merge/fragment/quantize pipeline for clean style
  app/pdf.py            verovio/cairosvg/pypdf PDF engraving (singleton toolkit + lock)
  app/storage.py        storage/projects/<id>/{project.json,audio/,output/}
  app/engine_lab/        v0.9.4 Engine Lab — isolated from the main pipeline, imports
                        FROM app/transcription.py + app/polyphonic.py, never vice versa
    base.py               EngineAdapter/EngineRunOutput types
    adapters.py            ADAPTERS registry (pyin, basic_pitch, cqt available;
                          piano_expert/omnizart registered but permanently unavailable)
    fixtures.py            5 synthetic test clips + known expected notes
    scoring.py             rough accuracy scoring against expected notes
    stats.py               engine-agnostic note_count/overlap/chord-group/pitch-range
    storage.py              storage/engine_lab/{fixtures,audio,runs}/ — separate tree
    routes.py               APIRouter at /api/engine-lab, included in main.py
frontend/ Next.js 16 (app router, Tailwind, TypeScript)
  app/page.tsx                  project list/create (+ quiet Engine Lab link)
  app/projects/[id]/page.tsx    the whole project workflow UI (memoized NoteTable inside,
                                note-edit working copy + debounced auto-save)
  app/engine-lab/page.tsx       v0.9.4 Engine Lab UI — source picker, engine picker,
                                comparison table, piano-roll debug view
  components/PlayAlong.tsx      Web Audio play-along engine + panel (3 synth voices)
  components/SheetMusic.tsx     OSMD sheet render + blue playhead + bar-wash sync
  components/TabView.tsx        text-tab preview for fretted instruments + highlight
  components/ChordsPanel.tsx    manual chord editor + ChordStrip bar-grid line
  components/EngineLabPianoRoll.tsx  read-only SVG piano roll for lab run results
  lib/api.ts                    typed fetch helpers; API_BASE_URL defaults to "" (same-origin)
  lib/engineLab.ts              typed fetch helpers for the Engine Lab (kept separate)
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
