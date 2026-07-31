# BandChart AI — Project Notes

Living notes for contributors (human or AI). Last updated after v0.9.7.1 (2026-07).
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

### v0.9.7.1 — stem separation before transcription (done)
Request literally said "Build BandChart AI v0.9.7.1 only" and its suggested commit
message said the same, but the pass-mark section further down the same request said
"v0.9.8 passes if..." — v0.9.8 (instrument-focused Solo Arrangement) had already shipped
in full in the immediately preceding turn with unrelated content, so that's almost
certainly a copy-paste leftover from whatever template produced the request, not a real
instruction to overwrite it. Went with **v0.9.7.1**, the name stated twice and never used
before, and flagged the mismatch to the owner rather than guessing which one they
actually meant (same judgment-call pattern as the v0.9.7→v0.9.8 rename the turn before).

Goal: "Stop dense full-song transcription by adding proper stem separation before
transcription." Read this PROJECT_NOTES.md file first, as instructed — and found that
almost everything requested was **already built**: Demucs 4-stem separation
(`app/separation.py`, v1.0/v0.9.6), Piano Expert (`app/piano_expert.py`, v0.9.6), and
Solo Arrangement's per-instrument stem routing (`app/arrangement.py`, v0.9.6) already
match the request's exact routing table (Bass→bass stem, Piano/Guitar→accompaniment
stem, Voice/Violin/Alto Sax/Trumpet→vocal stem) and already run separation BEFORE
transcription, already degrading honestly to the full mix with the exact message
"Source separation failed. Using full mix instead." when Demucs isn't available — which
it still isn't, here (see below). So this version's real work was the genuine gaps, not
a rebuild:

**Re-investigated Demucs/Piano Expert from scratch, not from memory** (Feature 3's
explicit ask): direct `curl` against all four previously-blocking hosts
(`download.pytorch.org`, `zenodo.org`, `dl.fbaipublicfiles.com`, `huggingface.co`) in
this session's fresh container, before writing any code. All four still return 403 at
the TCP CONNECT level (re-confirmed, not assumed); `pypi.org` (control) returns 200.
Identical to every prior version's finding — this environment's network policy hasn't
changed. Didn't burn time/disk on a multi-GB `pip install` that would only reconfirm the
same checkpoint-host block at runtime; the direct curl is actually stronger evidence for
that specific claim than an install attempt would be.

**`backend/app/arrangement.py`** — `run_solo_arrangement()` gains `separation_status`
("demucs" | "unavailable" | "failed"), a genuine 3-state read computed by calling
`separation.is_available()` before `separate_full()`, instead of collapsing "Demucs isn't
installed" and "Demucs is installed but errored" into the same `separation_engine: None`.
`separation_engine` (`"demucs"` or `None`) is kept as-is for back-compat. Unit-tested all
three states via `unittest.mock.patch` (the "unavailable" state is also exercised live,
every real run in this sandbox hits it): "unavailable" confirmed live; "failed"
(`demucs_is_available` → True, `separate_full` → None) and "demucs" (both mocked to
succeed, with a fake `SeparationResult`) confirmed via monkeypatch, since real Demucs
can't run here.

**`backend/app/transcription.py`** — Feature 5's new warning: when `mode ==
"direct_transcription"` and the existing `describe_difficulty()` read comes back "Dense
piano/audio — may need editing", `run_transcription()` now also appends "Direct
transcription on a full mix may be dense. Use Solo Arrangement for a cleaner playable
version." to `warnings`. Deliberately reuses the existing density signal instead of
guessing from audio duration (a clean, minutes-long instrument recording shouldn't
trigger a "this might be a full mix" warning just for being long) — one signal, already
trusted elsewhere in the app, not a new heuristic invented for this. Verified it does NOT
fire on a simple clean chord (no false positive) and DOES fire on a synthetic
Mrs-Magic-style dense piano passage.

**`backend/app/engine_lab/adapters.py`** — Feature 6's gap: only `demucs_vocals` existed
(v0.9.6); added `demucs_bass` and `demucs_other`, both sharing a new `_run_demucs_stem()`
helper (separate with Demucs, run Basic Pitch on the named stem) so the lab can compare
all three separated-stem+Basic-Pitch combinations against full-mix Basic Pitch and Piano
Expert on the same source audio — exactly what Bass and Piano/Guitar Solo Arrangement
actually use when Demucs is available. **No frontend changes needed** for this — same as
v0.9.6's finding, `app/engine-lab/page.tsx` already renders the engine list, note count,
overlapping-note count, warnings, MIDI/JSON downloads and "Use this output" generically
from `GET /engine-lab/engines` / `POST /engine-lab/runs`; the two new adapters just show
up. Verified: both list with the same honest "Demucs isn't installed" reason as
`demucs_vocals`, and running either one returns a friendly 400, never a crash.

**Frontend** (`app/projects/[id]/page.tsx`, `lib/api.ts`) — `NotesResponse` gains
`separation_status`. The Solo Arrangement status block gains a **"Source separation:"**
line (Demucs / unavailable / failed) and the existing "Source:" line is relabelled
**"Stem used:"** with its value wording changed to match the request's exact vocabulary
("vocals" / "bass" / "other" / "full mix" instead of "vocal stem" / "accompaniment") —
`ARRANGEMENT_SOURCE_LABELS` updated, its one call site unaffected. Direct transcription's
new dense-full-mix warning needed no new UI at all — it's just another string in the
`warnings` array the existing status block already renders.

**Testing**: 26 checks against a live server (C major gate re-verified with Piano Expert
correctly unavailable so Basic Pitch is engine_used; A4 tone on Voice; a synthetic dense
piano piece triggering the new Direct-mode warning and NOT a simple clean chord; Solo
Arrangement honestly reporting `separation_status: "unavailable"` and falling back to
`full_mix` for Piano/Voice/Bass; Engine Lab listing and gracefully 400-ing the two new
adapters) — all passed. 3 monkeypatched unit tests covering the "failed" and "demucs"
`separation_status` states that can't occur live here. Re-ran the full 22-check v0.9.8
baseline suite (Piano chord grouping, Guitar multi-note TAB, Bass/Sax/Trumpet/Voice range
fitting, Violin double-stop cap, density scaling) — all still passed, confirming this
version didn't regress the previous one. 7 Playwright checks against a production build
(the new status lines render with the right wording; Engine Lab shows the two new engines
and their unavailable reasons) — all passed.

**Honest Mrs Magic report (Test 3, as required)**: could NOT be verified whether Demucs +
Piano Expert/Basic Pitch beats full-mix Basic Pitch on real Mrs Magic audio — Demucs and
Piano Expert remain fully document-only in every environment this app has been tested in,
re-confirmed this version via direct network checks, not assumption. What WAS verified:
the pipeline runs coherently end-to-end when separation is unavailable (honest status,
clean fallback, no crash), and Direct transcription on a dense piece now surfaces a
concrete suggestion to try Solo Arrangement instead. The owner would need to test on a
Mac (where Piano Expert was previously confirmed to actually install and run, per
v0.9.6's investigation) to get a real before/after on the underlying quality question.

### v0.9.8 — instrument-focused Solo Arrangement (done)
Request said "Build BandChart AI v0.9.7 only," but v0.9.7 (Basic Pitch tuning from real
Mrs Magic feedback) had already shipped in the immediately preceding turn — built this as
**v0.9.8** instead of reusing the number, flagged to the owner rather than silently
overwriting or blocking on a question (same judgment-call pattern as v0.9.6 following
v1.0). Goal: narrow the app around the 7 real instruments it's actually built for
(Guitar, Bass, Piano, Violin, Alto Sax, Trumpet, Voice) and make Solo Arrangement
instrument-aware instead of one-size-fits-all. Explicit prohibitions honored: no drums,
no new instruments, no accounts/payments, no v2.0 redesign, the weak chord feature stayed
parked, nothing else (upload/YouTube/Basic Pitch/pYIN/Engine Lab/exports/Play
Along/note editing/TAB/grand staff) broke.

**`backend/app/instrument_profiles.py`** (new) — single source-of-truth
`InstrumentProfile` dataclass table for the 7 main instruments: display name, concert
(sounding) MIDI range, comfortable range, written offset, clef, `max_simultaneous_notes`,
tab support, a short solo-focus description. `MAIN_INSTRUMENTS` lists the 7 keys in
picker order. Deliberately does NOT touch `musicxml.py`'s existing `INSTRUMENTS`/
`TUNINGS` dicts (concert/flute/tenor_sax/clarinet/ukulele still fully work there) —
this table is additive, everything else falls back to its old behaviour via
`.get(instrument, <old default>)`.

**`backend/app/range_fit.py`** (new) — "Fit to instrument range," the last Solo
Arrangement step. Notes are grouped into phrases (silence gap ≥1.0s starts a new
phrase); each phrase shifts by ONE whole-octave amount, chosen by **majority vote**
among the phrase's out-of-range notes (must be ≥half the phrase, not just any vote) —
an isolated outlier in an otherwise in-range phrase doesn't drag the whole phrase with
it. Only genuine stragglers still out of range after their phrase's shift get clamped
individually. Whole octaves only, never an arbitrary semitone transpose (keeps the key).
**Bug caught by my own unit tests before shipping**: the first version applied a
phrase-wide shift whenever ANY note was out of range, regardless of vote size — fixed by
requiring a real majority (`votes[winner] >= len(phrase) / 2`); re-verified with an
adversarial "one outlier among several in-range notes" case.

**`backend/app/routing.py`** — `INSTRUMENT_MAX_POLYPHONY` now derived directly from
`instrument_profiles.PROFILES` (piano=6 [was 4], guitar=4, violin=2, bass/alto_sax/
trumpet/voice=1) instead of hardcoded per-instrument entries; melody-only instruments
capped at 1 naturally degrade a manually-forced "poly" request to monophonic output via
the existing `_assign_groups(max_polyphony=1)` mechanism — no special-case rejection
code needed. `SOLO_AUTO_POLY_INSTRUMENTS` gains `"guitar"` (Solo Arrangement now attempts
real multi-note TAB, so defaulting to poly detection is worth it there, same as Piano).

**`backend/app/arrangement.py`** — `arrangement_difficulty` (easy/medium) renamed
`arrangement_density` (simple/balanced/detailed) with new support-note budgets
(`SUPPORT_NOTE_BUDGET = {simple: 6, balanced: 20, detailed: 40}`) and minimum gaps; the
"piano_style" arrangement focus is dropped entirely (support notes now purely
density-controlled). New final pipeline step calls `range_fit.fit_notes_to_range()`
against the chosen instrument's profile (concert pitch — Alto Sax/Trumpet's written
transposition still only applies at MusicXML/PDF export time, unchanged); result gains
`"range_fitting"` (`"none"`/`"octave_shifted"`/`"simplified"`) alongside the renamed
`"arrangement_density"`.

**`backend/app/tablature.py`** — Guitar TAB now genuinely attempts a playable multi-note
chord instead of always collapsing to the top note. New `_try_chord_assignment()`:
brute-force `itertools.permutations` search over which string each simultaneous pitch
goes on, filtered by fret validity (0–15) and hand span (≤4 frets among non-open frets),
scored by (frets-over-12 count, span, fret sum). Returns an index-parallel
`list[tuple[string, fret]]`, deliberately NOT a pitch-keyed dict — caught in design
review, before writing the caller, that two notes in a cluster could land on the same
pitch after range-fitting and silently collide in a dict keyed by pitch value.
`build_tab()` branches on `instrument_key == "guitar"`: progressively drops the
lowest-confidence note and retries when no complete assignment exists, down to a single
note if needed (`simplified_chords` counter → the exact warning "Some guitar notes were
simplified because the detected chord was not playable."); bass/ukulele keep their
original top-note-only logic completely unchanged. `_layout_systems()` rewritten to
group same-time-window entries into one shared column (multiple strings, one time slot)
instead of always one column per entry — verified byte-identical to the old layout for
the single-note-per-cluster case (i.e. every pre-v0.9.8 use of tab).

**`backend/app/models.py` / `backend/app/main.py`** — `Project`/`ProjectSettings`
`arrangement_difficulty` → `arrangement_density` throughout (validation set, error
messages, the `set_project_settings`/`transcribe`/`_save_working_notes` preserved-fields
dict, which also gains a new preserved `"range_fitting": None` entry); `piano_style`
dropped from `VALID_ARRANGEMENT_FOCUSES`.

**Frontend** (`frontend/lib/instruments.ts`, `lib/api.ts`,
`app/projects/[id]/page.tsx`) — new `MAIN_INSTRUMENTS`/`MAIN_INSTRUMENT_KEYS` exports
(guitar/bass/piano/violin/alto_sax/trumpet/voice, mirrors the backend's
`instrument_profiles.MAIN_INSTRUMENTS`); the full `INSTRUMENTS` list is untouched and
still used for label lookups on old/hidden-instrument projects, just no longer the
source for either picker (the setup grid and the post-transcription "Solo instrument"
dropdown both switched to `MAIN_INSTRUMENTS`). `defaultNoteDetection()` now takes mode
too, so Guitar + Solo arrangement also pre-selects poly detection (mirrors
`SOLO_AUTO_POLY_INSTRUMENTS`). Arrangement focus radio drops "Piano-style arrangement";
"Arrangement difficulty" (Easy/Medium) replaced with "Arrangement density"
(Simple/Balanced/Detailed). Status block rebuilt: `engine-status` (Direct transcription)
now shows Instrument/Mode/Engine used/Detection mode/Fallback/Warnings and is gated to
`project.mode !== "solo_arrangement"` (previously it had no such gate and rendered
redundantly alongside `arrangement-status` for every Solo project — fixed as a side
effect, not separately requested); `arrangement-status` (Solo arrangement) gains
Instrument/Detection mode/Arrangement density/Range fitting lines alongside its existing
Source/Engine/Arrangement focus/Warnings. Default `instrumentKey` changed from
`"concert"` to `"piano"` (Concert pitch is no longer a user-facing choice, per the
request "it can remain internally if needed for calculations, but users should not see
it as an instrument").

**Testing**: unit-tested each new/changed module directly (instrument profiles, range
fitting's phrase/majority-vote logic including the outlier-vote bug fix, guitar chord
placement, arrangement density budgets) before any server involvement, matching this
project's established methodology. Then a real end-to-end pass against the running
FastAPI server (22 checks: Piano C-major chord preserved in both Direct and Solo, Guitar
Solo multi-note TAB across multiple strings in one column, Bass/Alto Sax/Trumpet/Voice
range-fitting into their profile ranges with correct MusicXML export, Violin capped at 2
simultaneous notes, Piano density Simple vs. Detailed producing more support notes) — all
passed. A Playwright suite against the built app (35 checks: picker shows exactly the 7
main instruments and never Concert pitch/Flute/Clarinet/Tenor Sax/Ukulele, density UI
hidden for Direct transcription and showing all 3 options for Solo, no Piano-style
option, the new status block's Instrument/Mode/Detection mode lines, blue playhead, note
editing, MIDI/JSON/MusicXML/PDF/TAB downloads, Play Along controls, chord feature still
collapsed under Experimental tools, Engine Lab loads, project delete) — all passed.
**Environment note, not a regression**: this sandbox's `next dev` (Turbopack) has a
broken HMR WebSocket that, here, left client-side `useEffect` calls (and therefore all
`fetch()`-based data loading) never firing at all — confirmed via a `window.fetch`
intercept that never triggered, despite `useState`-driven interactivity (e.g. checkbox
clicks) working fine. This reproduces on `app/page.tsx`, code untouched by this version,
so it's a dev-server-only quirk in this container, not caused by or fixed in this
version's changes. Building with `next build && next start` (production mode, no HMR)
sidesteps it completely — that's what the Playwright suite above actually ran against.
Worth knowing for future sessions in this same environment: don't trust a stuck "Loading
projects…" on `next dev` here as a real bug without first trying a production build.

### v0.9.7 — Basic Pitch tuning from real Mrs Magic feedback (done)
First version driven by an actual real-world test result rather than synthetic fixtures
or a formal spec: the owner ran Mrs Magic on their Mac (v0.9.6 shipped explicitly asking
for this) and reported back — Basic Pitch ran (confirmed; Piano Expert isn't installed
on their machine), "got the main idea and the multiple notes but wasn't perfect": wrong
notes, missing notes, timing/rhythm off, and too dense to read. Scoped this round to what
could be fixed with real evidence and verified in this sandbox (Basic Pitch itself runs
here, even though Mrs Magic's actual audio can't be fetched — YouTube's still blocked);
timing/rhythm is flagged as a separate, bigger follow-up rather than hacked at blind.

**`backend/app/polyphonic.py`** — two targeted, both Basic-Pitch-only (the CQT fallback
is untouched):
1. **Octave doublings were being dropped as false harmonics.** `_suppress_harmonics()`
   (added v0.9.3) was written for and tuned against the CQT fallback — a hand-tuned
   spectral heuristic with no real sense of "is this a played note," which genuinely
   needs a broad harmonic-interval list (octave, 12th, double-octave, etc.) to avoid
   ghosts. That same list was also being applied to Basic Pitch's output, a trained ML
   model with much better inherent discrimination — and octave doublings (a bass note
   played with its own octave, a melody doubled an octave up) are extremely common,
   *intentional* piano writing, not a spectral ghost. New `BP_HARMONIC_INTERVALS = (19,
   24, 28)` — same as before minus the octave (`12`) — passed to `_suppress_harmonics()`
   only for the Basic Pitch path; `_detect_with_cqt` keeps the original full
   `HARMONIC_INTERVALS`, unchanged. **Verified this was a real, not just theoretical,
   gap**: a balanced-amplitude synthetic test didn't reproduce it (both notes' Basic
   Pitch confidence came back too close together to trip the 0.8 ratio either way — real
   playing is rarely that evenly voiced), so the Engine Lab's new `octave_doubling`
   fixture deliberately voices the octave note quieter (confirmed via raw Basic Pitch
   output: 0.47 vs 0.66 confidence, a 0.71 ratio — below the 0.8 threshold) to actually
   exercise the check; with the OLD interval set the quiet octave note is dropped, with
   the NEW one it survives — a real before/after difference, not a no-op fix
2. **Repeated chord events add clutter.** New `_merge_repeated_chords()`: consecutive
   chord/note events sharing the EXACT same pitch set, separated by ≤
   `CHORD_REPEAT_GAP_S` (0.25s), merge into one longer event — the model can re-trigger
   the same held chord multiple times on a real piano's sustain-pedal resonance, and
   each repeat was previously its own separate engraved event. Runs after
   `_assign_groups` inside `_detect_with_basic_pitch`; message "Repeated chord events
   were merged to reduce clutter." when it actually changes anything. Unit-tested
   directly on crafted note dicts (repeat within gap → merges; different pitch set →
   doesn't; repeat but gap too large → doesn't; single ungrouped note → doesn't crash)
   since real Basic Pitch re-triggering behavior on a held pedal chord can't be reliably
   forced from synthetic audio in this sandbox

**`backend/app/engine_lab/fixtures.py`** — new `octave_doubling` fixture (6th fixture,
appended after the original 5; not part of the owner's original benchmark order),
permanently regression-tests the real-world failure mode above instead of relying on
one-off manual verification.

**What this does NOT fix**: wrong notes beyond harmonic-interval scope (Basic Pitch's
own model limits on real, non-synthetic, possibly-noisy/reverberant audio are what they
are — no post-filter can add accuracy the model doesn't have) and — the honest big one —
**timing/rhythm**. The app quantizes everything to a fixed 120 BPM assumption
(`transcription.py`/`musicxml.py`/`notation_cleanup.py`, unchanged since v0.1); Mrs Magic
is a real recording almost certainly not at exactly 120 BPM, so ALL rhythm quantization
(readable-mode snapping especially) will drift from the actual performance regardless of
how good note detection gets. Fixing this needs real tempo estimation, which doesn't
exist anywhere in the app — flagged as a candidate next feature, not attempted here
(deliberately: guessing at a quick tempo-detection hack without evidence risks a worse,
less predictable result than the current honest "fixed 120 BPM, Precise mode is the
escape hatch" limitation).

**Testing**: unit-tested directly against real Basic Pitch inference (installed in this
sandbox) on the new fixture — confirmed via raw model output inspection, not just the
final result, that the fix changes behavior (old interval set drops the quiet octave
note, new one keeps it); `_merge_repeated_chords` unit-tested on crafted note dicts (real
audio can't reliably reproduce pedal re-triggering); C major chord gate re-verified
unchanged; full re-run of all existing Playwright suites (v0.9.3/Engine Lab/v0.9.5/v1.0/
v0.9.6, ~160 checks) — all green, including the Engine Lab suite which now exercises 6
fixtures instead of 5.

**Mrs Magic**: still not independently verified by this session (YouTube blocked here,
same as ever) — these are principled, evidence-backed improvements to a real reported
failure mode, not a claim that Mrs Magic now transcribes perfectly. The owner would need
to re-test on their Mac to confirm the actual before/after difference on the real
recording.

### v0.9.6 — serious transcription engine stack (done)
Built chronologically AFTER v1.0, deliberately numbered lower: the owner's explicit
instruction this version was "v1.0 should not happen until transcription is good
enough" — v1.0's Solo Arrangement pipeline was real progress on ARRANGEMENT, but the
underlying note-detection QUALITY was still the actual complaint (Basic Pitch helps but
isn't enough for dense piano/full songs, Mrs Magic still not solved). v0.9.6 is entirely
about that: a stronger engine stack, evaluated honestly, wired in only where it
genuinely works in this environment.

**Investigated fresh (not just re-read from old notes) — network policy re-confirmed via
curl before touching any code:**
- `download.pytorch.org`, `dl.fbaipublicfiles.com`, `huggingface.co`, `zenodo.org` — all
  still 403 at the TCP CONNECT level, identical to every prior investigation (v0.9.4,
  v1.0). `github.com`/`objects.githubusercontent.com`/`raw.githubusercontent.com` ARE
  reachable, which prompted a genuine re-investigation of Piano Expert specifically (see
  below) in case a GitHub-hosted checkpoint mirror existed as a workaround — Demucs was
  NOT re-investigated from scratch (its blockers — fbaipublicfiles/huggingface — were
  just reconfirmed blocked by the same curl check, and nothing about the CUDA-bloat
  problem changes between sessions)

**Piano Expert (ByteDance/Qiuqiang Kong `piano_transcription_inference`)** — same two
blockers as the v0.9.4 finding, both independently re-confirmed by curl directly against
the actual hosts before any code was written this version (not just re-read from old
notes): `download.pytorch.org` (the CPU-only PyTorch wheel host) and `zenodo.org` (the
package's checkpoint host) both still return 403 at the TCP CONNECT level. The one new
thing checked this version — since `github.com`/`objects.githubusercontent.com` ARE
reachable here — was whether the checkpoint might also be mirrored as a GitHub Release
asset (which would download from the reachable `objects.githubusercontent.com`) rather
than only on Zenodo; a deeper background investigation was launched to check this and
attempt a real install + inference end-to-end, but its result wasn't back in time for
this version's commit. `backend/app/piano_expert.py` is written as a real, working
adapter regardless of the outcome — defensive by design (see below), so it's safe to
ship now and simply activates automatically if that investigation (or the owner,
manually) turns up a working install path later. Treat "GitHub-hosted checkpoint mirror"
as an open question for the next version, not a confirmed workaround.

**`backend/app/piano_expert.py`** (new) — real, working adapter (not a permanently-
unavailable stub like v0.9.4's Engine Lab placeholder): `is_available()` lazily imports
`piano_transcription_inference`; `transcribe_piano()` loads the model as a lazy
singleton (loading is slow), runs inference at 16kHz mono (the package's expected rate),
and converts `est_note_events` (onset/offset/midi_note/velocity) into BandChart's note
schema. Post-filtering mirrors Basic Pitch's pattern: a same-pitch rejoin pass merges
events split mid-sustain (`REJOIN_GAP_S=0.05`), quiet/short events are dropped
(`MIN_VELOCITY_FRACTION=0.15` of this recording's loudest note, `MIN_NOTE_DURATION=0.05s`),
and `_assign_groups` (imported from `polyphonic.py`, same cross-module-private-import
precedent as before) groups chords with a generous cap of 8 — deliberately higher than
Basic Pitch's 4, since a real piano-specialist model can legitimately detect fuller
chords and shouldn't be artificially trimmed the same way. Never added to
requirements.txt; never installed automatically.

**Routing** (`backend/app/routing.py::specialist_engine_for()`, new): a tiny lookup,
`{"piano": "piano_expert"}` today, nothing else qualifies. Wired into BOTH
`transcription.py::run_transcription()` (Direct transcription) and
`arrangement.py::_detect_melody()` (Solo Arrangement) as an attempt made BEFORE the
existing Basic Pitch/CQT/pYIN chain, guarded so it only even checks availability for
piano and only when poly detection was requested. When Piano Expert isn't installed
(this environment, always) the block does nothing at all and the pre-existing chain runs
completely unchanged — verified by re-running the C major chord gate: still exactly
`C4/E4/G4`, `engine_used: "basic_pitch"`, identical to before this version. When
monkeypatched available-and-working, it's used and reported as `engine_used:
"piano_expert"`; when monkeypatched available-but-failing, it falls back to Basic Pitch
with `fallback_reason: "Piano Expert failed (...), used Basic Pitch instead."` — all
three paths unit-tested directly (not just inferred).

**`backend/app/separation.py`** — upgraded from v1.0's 2-stem (`--two-stems vocals`) to
htdemucs' default **4-stem separation** (vocals/drums/bass/other) in one call:
`separate_full()` returns a `SeparationResult` with all four stem paths;
`separate_vocals()` is now a thin back-compat alias. `SeparationResult.accompaniment_path`
is a property returning `other_path` (the closest single stem to "the rest of the band"
for callers that only want vocals-vs-everything-else). Still document-only for the exact
same two reasons as v1.0 (re-confirmed, see above) — never in requirements.txt.

**Solo Arrangement stem routing** (`backend/app/arrangement.py`) — v1.0 only had a
2-stem split (bass got "accompaniment" = everything non-vocal; everyone else got
vocals). v0.9.6 routes per the request's exact table, now that 4 real stems exist:
- **Bass** → its own isolated `bass_path` stem (`arrangement_source: "bass_stem"`,
  new value) — a real bassline instead of the old "same full-mix pass as everyone else"
  gap documented in v1.0's known limitations
- **Piano, Guitar** → the `other_path` (accompaniment) stem — moved OUT of the
  vocal-stem-default group they were incorrectly lumped into in v1.0 (a piano/guitar
  part doesn't live in the vocal stem)
- **Voice, Violin, Alto Sax, Trumpet** (and anything else) → unchanged, vocal stem when
  available — these usually carry the main melody line
All three routing branches are unit-tested with a monkeypatched `separate_full` (since
real Demucs can't run in this sandbox) confirming each instrument actually receives the
stem the table says it should.

**Exact wording change**: the "no separation available" message changed from v1.0's
"Using full mix because no clear vocal stem was isolated." to the v0.9.6 request's exact
required wording, **"Source separation failed. Using full mix instead."** — this is a
deliberate wording change per this version's explicit spec, not a regression; the old
v1.0 Playwright test asserting the old string was updated to match.

**Engine Lab expansion** (`backend/app/engine_lab/adapters.py`) — `piano_expert`'s
adapter entry now calls the REAL `is_available()`/`transcribe_piano()` (previously a
permanent `False`/`NotImplementedError` stub). Two new adapters: `demucs_vocals`
("Demucs + Basic Pitch (vocal separation)") — separates with `separate_full` into a
throwaway temp dir, then runs Basic Pitch on the isolated vocal stem, so the lab can
directly compare "separation + detection" against running detection on the full mix on
the exact same source audio; and `mt3` — a documented-unavailable stub (research-only,
no PyPI package, JAX/T5X/TensorFlow from source, GCS checkpoints, caretaker-mode
upstream — same investigation as v0.9.4, just now actually listed in the lab per this
version's explicit request instead of only being written up in README prose). **No
frontend changes needed** — `app/engine-lab/page.tsx` already renders the engine list
generically from `GET /engine-lab/engines`, so all three new/upgraded adapters (and
their honest unavailable reasons) appear automatically. Verified: listing them doesn't
crash, and attempting to RUN an unavailable one (`POST /engine-lab/runs`) returns a
friendly 400 "Engine unavailable: {reason}", never a 500 — for both `piano_expert` and
`demucs_vocals`.

**Frontend** (`app/projects/[id]/page.tsx`): `ENGINE_LABELS` gains `piano_expert: "Piano
Expert"`; `ARRANGEMENT_SOURCE_LABELS` gains `bass_stem: "bass stem"`. That's the entire
frontend diff for this version, per the explicit "do not add UI fluff" instruction — the
existing engine-status and arrangement-status blocks already display whatever engine/
source key comes back, so a new engine or stem type just needs a display label, not new
UI structure.

**Chord feature**: still parked under "Experimental tools" (v0.9.3), untouched — the
request explicitly said not to bring it back. Ultimate Guitar-style chord sheets remain
deferred to a much later version (probably v5.0), unchanged.

**Testing**: unit-tested (venv heredocs, with `unittest.mock.patch` monkeypatching for
the pieces that can't actually run here — Piano Expert available+working,
available+failing, and confirmed it's never even checked for non-piano instruments;
Demucs 4-stem routing for bass/piano/voice with a fake `separate_full`) — all before any
server involvement, matching the established methodology. Then a new Playwright suite
(20 checks: Engine Lab lists + graceful-400 checks, the C major gate through the real
server, bass's new stem routing end-to-end, chord/YouTube regressions) plus a full
re-run of the existing v0.9.3/Engine Lab/v0.9.5/v1.0 suites (~140 checks) — all green.

**v1.0 status**: still not declared "done" in the sense the owner means it — Piano
Expert and Demucs remain document-only in every environment this app has actually been
tested in (Codespaces-style sandboxes). The code is real and will activate automatically
wherever those hosts are reachable (most likely a home Mac with a fast, unrestricted
connection); until the owner can confirm that on real hardware against Mrs Magic, don't
claim the underlying quality problem is solved.

### v1.0 — Solo Arrangement rebuild (done)
Goal: make Solo Arrangement actually useful on real pop/rock songs — find the main
melody (vocal first) and turn it into a playable solo part — instead of running the
same single-line detector used for Direct transcription on the whole mixed song.
Direct transcription (`app/transcription.py`) is completely untouched; Solo Arrangement
gets its own pipeline that reuses the same engines.

**`backend/app/separation.py`** (new) — optional Demucs vocal/accompaniment adapter.
Investigated Meta's Demucs (PyPI `demucs`, htdemucs model) for real vocal isolation via
a background agent, mirroring the v0.9.4 engine-investigation pattern. Findings:
- Installs (2m43s, torch 2.13.0) but reproduces the exact CUDA-bloat problem found with
  `piano_transcription_inference` in v0.9.4: `download.pytorch.org` (the CPU-only wheel
  host) is policy-blocked here (403 on CONNECT), so pip falls back to the default PyPI
  wheel, which drags in ~2.7GB of unused CUDA packages (cublas, cudnn, cufft, cusolver,
  nccl, triton) even with no GPU present. Total venv: 4.7GB. One improvement over the
  ByteDance case: demucs does NOT need torchaudio for inference, only under its `[train]`
  extra (uses a Rust `sphn` library for I/O instead)
- **Harder blocker**: the htdemucs checkpoint downloads from `dl.fbaipublicfiles.com`;
  `huggingface.co` (an alternate repo) is separately blocked too. Both are TCP-CONNECT-
  level blocked here, not just slow — so no htdemucs variant, however small, can even be
  fetched in this environment, regardless of the CUDA question
- CPU inference itself is NOT the problem: the investigation instantiated the real
  (untrained) HTDemucs architecture and ran a forward pass on a synthetic clip — 9.3s for
  an 8s clip on 4 CPU cores, roughly 1x realtime. 26.9M params (~108MB fp32), matching a
  real htdemucs checkpoint's rough size; `htdemucs_ft` bags 4 such models (~4x cost),
  `mdx_extra_q` is a smaller quantized bag but its actual size couldn't be verified here
  (host unreachable)
- **Decision: document-only, not wired as a live dependency.** `demucs` is NOT in
  `requirements.txt` and is never installed automatically — per the spec ("if Demucs is
  too heavy, add it as optional or document it" / "do not break the app if Demucs is not
  installed"). `separation.py` is a real, working adapter (`is_available()` lazily
  imports `demucs.separate`; `separate_vocals()` shells out to
  `demucs.separate.main(["-n","htdemucs","--two-stems","vocals",...])` and reads
  `htdemucs/<stem>/vocals.wav` + `no_vocals.wav`) — if a user manually
  `pip install demucs` in an environment where those two hosts are reachable, it will
  actually run. By default, and on ANY failure (not installed, `SystemExit` from
  `demucs.separate.main`, missing output files, any exception), `separate_vocals()`
  returns `None` and never raises — the arrangement pipeline always falls back to the
  full mix and shows "Using full mix because no clear vocal stem was isolated."

**`backend/app/arrangement.py`** (new) — `run_solo_arrangement()`, the Solo Arrangement
pipeline, parallel to (and independent of) `transcription.run_transcription()`:
1. `_prepare_audio()`: librosa peak-normalise (to 0.95) + `librosa.effects.trim(top_db=40)`
   into a `tempfile.TemporaryDirectory`-scoped scratch WAV — the user's original upload
   is never touched, matching the existing convention that Play Along/download always
   read the untouched original audio file
2. `separate_vocals()` (above) — None in this environment, so `arrangement_source` is
   always `"full_mix"` here; the code path for `"vocal_stem"`/`"accompaniment"` exists and
   is exercised by the unit tests below, ready for an environment where Demucs works
3. Melody source routing: everyone gets the vocal stem when one exists, EXCEPT bass
   (`BASS_PREFERS_ACCOMPANIMENT`), which always follows the accompaniment/full mix — a
   bass part follows the low end of the song, not the singer
4. `_detect_melody()` re-implements the SAME engine dispatch as
   `run_transcription()`/`app/routing.py` (Basic Pitch → CQT fallback → pYIN, honest
   `fallback_reason` strings) but on the caller-chosen source instead of always the
   original upload — duplicated rather than extracted into transcription.py, to keep
   Direct transcription's code path completely unchanged (lower regression risk than a
   shared-helper refactor)
5. `_extract_support_notes()` (piano + guitar only, `SUPPORT_CAPABLE_INSTRUMENTS`, and
   only when `arrangement_focus` is `melody_support` or `piano_style`): runs
   `polyphonic.detect_notes_poly` on the accompaniment/full-mix source, keeps only notes
   below middle C (`SUPPORT_MAX_PITCH=60`, so they never collide with the melody
   register), then thins to a small fixed budget (24 notes / 0.6s min gap for Easy, 48 /
   0.3s for Medium — `piano_style` always uses the Medium budget for a fuller left hand
   regardless of the difficulty control) — deliberately NOT "detect everything and dump
   it in"; tagged `"source": "accompaniment"` on each note
6. Merge: melody + support notes combined; if any support notes were added, `detection`
   flips to `"poly"` (even when the melody itself came from monophonic pYIN) so the
   export pipeline treats it as polyphonic — `_assign_groups` (imported from
   `polyphonic.py`, generous cap of 8) re-clusters the combined list purely for chord-id/
   density-display purposes. **No changes needed in `musicxml.py`/`tablature.py`**: the
   existing grand-staff split-at-middle-C logic and melody-first tab collapsing already
   handle merged melody+support notes correctly, since they're driven by pitch register
   and quantized timing, not by any new field
7. Result dict is the same shape `run_transcription()` writes, plus `arrangement_source`
   ("vocal_stem"|"accompaniment"|"full_mix"), `separation_engine` ("demucs" or null),
   `arrangement_focus`, `arrangement_difficulty` — always present, never hidden
8. Honest messages wired exactly to spec wording: "Solo Arrangement finds the strongest
   melody and creates a playable part. Dense songs may need editing." (always, first
   warning); "Using vocal stem for main melody." (separation succeeded, non-bass);
   "Using full mix because no clear vocal stem was isolated." (separation unavailable/
   failed, all instruments); "Added simple support notes. Please check and edit." (support
   notes were actually added)

**Bass without separation — a known, documented limitation**: unit-testing on a
synthetic "vocal pop song" fixture (see below) with Demucs unavailable showed bass falls
back to the SAME full-mix pYIN pass as every other instrument, which tracks the vocal
melody (the strongest, most voice-like line in the mix) rather than a real bassline — bass
doesn't get a genuinely different result from voice/violin/etc. without real source
separation. This is honestly a real gap, not swept under the rug: the code path and
`arrangement_source` labeling are correct (bass never claims to use a vocal stem), the
pipeline never crashes, and output is always playable/editable — but on a real song
without Demucs, expect the bass arrangement to often need heavy editing or replacement.
Fixing this properly needs either working source separation or a bass-specific frequency
bias in the detector (considered, not implemented this version — would mean touching
`transcription.py`'s shared FMIN/FMAX constants, adding regression risk to Direct
transcription for a benefit that's moot without separation anyway)

**Frontend** (`app/projects/[id]/page.tsx`, `lib/api.ts`):
- New "Arrangement focus" (Main melody / Melody + simple support / Piano-style
  arrangement) and "Arrangement difficulty" (Easy / Medium) radio groups inside the
  existing "Advanced settings" details, shown ONLY when Solo arrangement mode is
  selected (Direct transcription never sees them) — defaults Main melody / Easy per spec,
  Readable rhythm already defaulted on since v0.9.1
- New status block `data-testid="arrangement-status"` (separate element from the existing
  v0.9.5 `engine-status` block, so its "Mode:"/"Warnings:" lines never collide with that
  block's differently-scoped "Mode: Multiple notes"-style routing label) shown only when
  `notes.arrangement_source` is present: `Mode: Solo arrangement` / `Source: <label>` /
  `Engine: [Demucs + ]<engine label>` / `Arrangement focus: <label>` / `Warnings: <same
  difficulty+warnings composition as engine-status>`
- `_save_working_notes` (main.py) preserves the 4 new fields exactly like the v0.9.5
  routing fields — a note edit or reset never changes which source/engine produced the
  original arrangement

**Testing**: unit-tested `run_solo_arrangement()` directly (venv heredocs) across
voice/piano/guitar/bass/violin × main_melody/melody_support/piano_style before any
server involvement, then a new Playwright suite (`test_v10.js`, 29 checks) plus a full
re-run of the existing v0.9.3/Engine Lab/v0.9.5 suites (91 checks) — all green. Built a
synthetic **vocal pop song fixture** (16s, numpy+soundfile: a vocal-range sung-style
melody with light harmonics/vibrato over a quiet root-note bassline, mixed vocal-forward
like a typical pop mix) since no real pop song audio exists in this sandbox and YouTube
import (Mrs Magic, `youtu.be/yO_OD7Yx2j8`) is still blocked from this cloud environment
(confirmed again this version — 502 "Couldn't reach YouTube from the server", same as
every prior version; the owner needs to run Test 3 locally). On that fixture, pYIN's
full-mix fallback (no Demucs) correctly tracked the vocal melody, not the bassline —
validating that a vocal-forward mix (typical real production) already works reasonably
well even without separation; an earlier, more bass-forward version of the same fixture
showed pYIN latching onto the bass line instead, which is exactly the failure mode real
source separation is meant to fix. Direct transcription sanity gate (C major chord,
Piano) re-verified unchanged.

**Chord feature**: still parked under "Experimental tools" (v0.9.3), untouched — per
spec, not brought back as a main feature; roadmap note in the UI is unchanged ("Ultimate
Guitar-style chord sheets are a much later feature, probably v5.0").

### v0.9.5 — smart transcription routing (done)
Uses the v0.9.4 Engine Lab findings to make BandChart choose engine/polyphony settings
per instrument automatically, and report exactly what it did — no rebuild, purely
additive on top of the existing pYIN/Basic Pitch/CQT pipeline.

**`backend/app/routing.py`** (new, pure decision logic — never runs detection itself):
- `INSTRUMENT_MAX_POLYPHONY = {"violin": 2}` — everything else keeps
  `polyphonic.MAX_POLYPHONY` (4). Threaded through `detect_notes_poly()` ->
  `_detect_with_basic_pitch()`/`_detect_with_cqt()` -> `_assign_groups(max_polyphony=)`
  — **gotcha (hard-won)**: `_assign_groups`'s own overflow message used to hardcode
  "strongest 4 were kept" regardless of the actual cap; now interpolates
  `max_polyphony` — a violin run would have said "4" while only keeping 2 otherwise
- `DIRECT_AUTO_POLY_INSTRUMENTS = SOLO_AUTO_POLY_INSTRUMENTS = {"piano"}` — piano now
  defaults to polyphonic detection in BOTH modes (previously only Direct, via the
  frontend's `detectionTouchedRef` heuristic); `default_note_detection(instrument, mode)`
  is the single source of truth, mirrored in the frontend as
  `defaultNoteDetection(instrument)` (mode dropped there since both instrument sets are
  currently identical — kept per-mode in the backend for future flexibility)
- `INSTRUMENT_POLY_NOTES` — exact-wording caution strings for guitar
  ("Guitar chord/tab output is experimental. TAB may show the main playable line
  first.") and violin ("Violin output is limited to melody and simple double-stops for
  now."), appended to `warnings` only when the engine actually ran in poly mode
  (never shown after a fallback to pyin, where they'd be misleading)
- `describe_difficulty(notes, messages, engine_used)` — rough density label from the
  ACTUAL result, not audio pre-analysis. **Gotcha (hard-won, caught before shipping)**:
  the first version used `overlap_ratio > 0.5` as a dense-signal, which false-positives
  on any clean fully-grouped chord (a single 3-note chord is 100% grouped) — a genuine
  C major triad was reading "Dense piano/audio — may need editing", which is dishonest.
  Fixed to key off `avg_group_size >= 3.5` (chords consistently near the polyphony cap)
  and the engine's own overflow messages ("too dense" / "only the strongest N were
  kept") — the single most reliable density signal there is, since it means the
  detector itself had to trim something
- `run_transcription()` (transcription.py) gains `instrument`/`mode` params, calls
  `resolve_routing()`, and the result dict gains `engine_used` (derived from
  `notes[0]["source"]` — reliable since one detection pass never mixes engines),
  `routing_mode` (flips to "melody_only" in the OUTPUT if a poly request truly fell
  back to pyin, even though the plan requested "multiple_notes" — Mode and Engine used
  must never look contradictory), `fallback_reason` (exact strings: "Basic Pitch
  unavailable — used the built-in simple detector instead." for CQT fallback, "Basic
  Pitch failed, used melody-only fallback." for total fallback to pyin — both null on
  a clean run or a melody-requested run), `warnings`, `difficulty`
- `_save_working_notes` (main.py) preserves the 5 new fields exactly like
  chords/detection/detection_note — a note edit or reset never changes which engine
  produced the ORIGINAL detection, only which notes are stored
- Verified: C major chord gate automated for Piano+Direct AND Piano+Solo (both detect
  C4/E4/G4 together, one chord group, MIDI simultaneous, JSON overlapping); CQT-fallback
  and total-fallback status fields unit-tested by monkeypatching; violin caps to ≤2 on
  BOTH the Basic Pitch and CQT paths; guitar/violin instrument notes appear only when
  poly actually ran

**Engine Lab "Use this output"** (`engine_lab/routes.py`,
`POST /runs/{run_id}/apply/{project_id}`): the one deliberate exception to "the lab
never touches a project" — an explicit button, not automatic. Safety: 400 unless
`run.source.kind == "project"` AND `run.source.project_id == project_id` (a
fixture/upload run can never become a project's transcription, so a lab experiment
can't accidentally overwrite the wrong thing); 400 if the run itself errored. Applying
treats it like a fresh transcribe (chords reset to `[]`, `original_transcription.json`
re-snapshotted so "Reset to original" resets back to the applied result, not whatever
ran before), sets `project.note_detection` to match what was actually applied so future
settings stay consistent. `describe_difficulty` reused directly (imported from
`app.routing`) so lab-applied projects get the same honest status block as a normal
transcribe.

**Frontend**: `app/projects/[id]/page.tsx` gains an "Engine status" block under the
audio player (`data-testid="engine-status"`) showing all 4 lines every time, never
conditionally hidden — `ENGINE_LABELS`/`ROUTING_MODE_LABELS` maps for display text;
Warnings line folds `difficulty` in as the first item (when not "Simple melody"/"No
notes detected") ahead of the raw engine warnings, matching the single "Warnings:" line
the request asked for while keeping the two concepts separate in the data model.
`app/engine-lab/page.tsx` gained a "Use output" table column — a button when
`run.source.kind === "project"`, "✓ Applied" after success, "—" otherwise; apply errors
surface in a banner above the table.

**Instrument scope note**: the request named 7 instruments explicitly (Guitar, Bass,
Piano, Violin, Alto Sax, Trumpet, Voice) as "existing working features to keep" — read
as which instruments this version's routing rules cover, NOT an instruction to remove
Concert pitch/Flute/Tenor Sax/Clarinet/Ukulele from the picker (no REMOVE section
mentioned them, and "Do not rebuild the app" argues against a destructive UI narrowing
on an ambiguous read). All 12 instruments remain selectable; the 5 unlisted ones fall
into the same melody-first default bucket as Alto Sax/Trumpet/Voice — flagged in the
final report in case the owner actually wanted the narrower picker.

**Mrs Magic**: still could not be run from this cloud environment (YouTube blocks
cloud-server import, same as v0.9.3/v0.9.4) — routing now sends it through the
strongest available route (Piano + Direct, Basic Pitch, up to 4 notes) but this is
UNVERIFIED on the actual hard benchmark; the owner needs to run it locally. Not claimed
solved.

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

### Next — planned
Not decided. Ask the owner. Long-term: v2.0 is still planned as the big black/silver
premium redesign (not yet — the owner will ask for it explicitly). As of v1.0, Solo
Arrangement has its own melody-finding pipeline (see above) but real source separation
(Demucs) is document-only in this environment — a bass-forward or dense full mix without
an isolated vocal stem can still mistrack the melody; auto chords are still rough
suggestions only; accurate complex-piano / full-band transcription remains future work.
Other long-term items (full band charts, rehearsal packs) remain unapproved; see
out-of-scope below.

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
  simultaneous notes (2 for violin, v0.9.5); full-band mixes and dense piano still won't
  transcribe accurately. The best results still come from clear recordings of one
  instrument. v0.9.5's routing chooses good defaults per instrument, but does not make
  the underlying detectors more accurate — Mrs Magic (the hard piano benchmark) remains
  unsolved and unverified beyond this cloud environment's YouTube block
- **No real source separation or Piano Expert in this environment**: v0.9.6's
  `app/separation.py` (4-stem Demucs) and `app/piano_expert.py` (ByteDance piano
  specialist) are both real, working adapters, but both are document-only here — Demucs
  drags in ~4.7GB of unused CUDA packages AND its checkpoint host is network-blocked;
  Piano Expert needs the same PyTorch plus a Zenodo-hosted checkpoint, also blocked (see
  the v0.9.6 notes above; re-confirmed via curl, not just re-read from old notes). Piano
  Direct/Solo transcription always falls back to Basic Pitch; Solo Arrangement always
  falls back to the full mix. On a vocal-forward mix (typical pop production) pYIN still
  finds the melody reasonably well without separation, but a bass-forward or dense mix
  can mistrack it. Both will activate automatically wherever those hosts ARE reachable
  (most likely a home Mac with a fast, unrestricted connection) — nothing else needs to
  change
- **Rhythm is approximate**: fixed 120 BPM assumption default 4/4 (3/4 and 6/8 selectable);
  cleaned style quantizes to an eighth grid (raw: sixteenth) — no real tempo/meter
  detection, so timing won't match a performance that isn't near 120 BPM. **v0.9.7:
  confirmed as the likely biggest remaining gap on real recordings** (owner feedback on
  Mrs Magic specifically called out timing/rhythm as off, alongside note accuracy that
  v0.9.7 did address) — real tempo estimation is a candidate next feature, not attempted
  yet
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
                        CQT+onset fallback; chord grouping, max_polyphony param (v0.9.5:
                        instrument-specific caps, e.g. violin=2); v0.9.7: octave-scoped
                        harmonic suppression for Basic Pitch + repeated-chord merge
  app/routing.py         v0.9.5 smart routing: per-instrument polyphony cap + default
                        note_detection + caution notes + describe_difficulty()
  app/separation.py     optional Demucs 4-stem adapter (v0.9.6: vocals/drums/bass/other;
                        v1.0 was 2-stem) — document-only in this environment (never
                        installed automatically); never raises
  app/piano_expert.py   v0.9.6 optional ByteDance Piano Expert adapter — real, working,
                        document-only in this environment (checkpoint host blocked);
                        tried before Basic Pitch for piano when actually available
  app/arrangement.py    run_solo_arrangement(): the Solo Arrangement pipeline (audio
                        prep, optional 4-stem separation with per-instrument stem
                        routing, specialist-engine-first melody detection, sparse
                        support notes) — parallel to run_transcription(), unchanged
  app/chords.py         chord-name validation, chart text, rough suggestions, keys
  (settings: Project.instrument/mode/time_signature/key_signature/rhythm_detail/
  note_detection/arrangement_focus/arrangement_difficulty)
  app/notation_cleanup.py  wobble/merge/fragment/quantize pipeline for clean style
  app/pdf.py            verovio/cairosvg/pypdf PDF engraving (singleton toolkit + lock)
  app/storage.py        storage/projects/<id>/{project.json,audio/,output/}
  app/engine_lab/        v0.9.4 Engine Lab — isolated from the main pipeline, imports
                        FROM app/transcription.py + app/polyphonic.py, never vice versa
    base.py               EngineAdapter/EngineRunOutput types
    adapters.py            ADAPTERS registry: pyin/basic_pitch/cqt always available;
                          piano_expert (real adapter, active if installed) and
                          demucs_vocals (separate + Basic Pitch) reported live;
                          omnizart/mt3 registered but permanently unavailable (v0.9.6)
    fixtures.py            5 synthetic test clips + known expected notes
    scoring.py             rough accuracy scoring against expected notes
    stats.py               engine-agnostic note_count/overlap/chord-group/pitch-range
    storage.py              storage/engine_lab/{fixtures,audio,runs}/ — separate tree
    routes.py               APIRouter at /api/engine-lab, included in main.py; v0.9.5
                          adds POST /runs/{id}/apply/{project_id} — the one endpoint
                          here that DOES write to a project (explicit, guarded)
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
