# BandChart AI

AI music arranging and rehearsal app that turns songs into editable lead sheets, solo sheets, band charts and custom arrangements.

## v0.9.7.1 — stem separation before transcription

This is the smallest possible working prototype: a local web app where you upload an audio
file and the backend runs **real audio-to-pitch transcription**. Everything runs on your own
computer — no accounts, no payments, no cloud services, no data leaves your machine.

**v0.9.7.1 makes Solo Arrangement's existing stem-separation step more honest and visible,
and gives Direct transcription a nudge toward Solo Arrangement when a full mix comes back
dense.** Most of what this version asked for — Demucs 4-stem separation, Piano Expert,
and per-instrument stem routing (Bass → bass stem, Piano/Guitar → accompaniment stem,
Voice/Violin/Alto Sax/Trumpet → vocal stem) — turned out to already exist (v1.0/v0.9.6);
the real gaps closed this version: the results page now shows a genuine 3-value
**"Source separation: Demucs / unavailable / failed"** line instead of a single Yes/No
read, alongside a relabelled **"Stem used: vocals / bass / other / full mix"**; Direct
transcription on a dense recording now suggests *"Use Solo Arrangement for a cleaner
playable version"*; and Engine Lab gained `demucs_bass`/`demucs_other` adapters
(alongside the existing `demucs_vocals`) so all three separated-stem options can be
compared against full-mix Basic Pitch and Piano Expert directly. Demucs and Piano Expert
were re-investigated from scratch (not from memory) and remain document-only in every
environment this app has been tested in — see **Transcription engine stack** below for
exactly why.

**v0.9.8 narrowed the app around the 7 real instruments it's actually built for — Guitar,
Bass, Piano, Violin, Alto Sax, Trumpet, Voice — and makes Solo Arrangement genuinely
instrument-aware instead of one-size-fits-all.** The instrument picker (and the "Solo
instrument" selector on the results page) now show only those 7; Concert pitch and the
other backend-supported keys (Flute, Clarinet, Tenor Sax, Ukulele) are hidden from the
main workflow, not deleted — old projects and direct backend/API use still work with
them. A new central instrument profile table (`backend/app/instrument_profiles.py`) gives
each of the 7 a real playable range (in concert/sounding MIDI), how many simultaneous
notes it can take, and its Solo Arrangement treatment. A new **"Fit to instrument range"**
step octave-shifts notes that fall outside that range — by whole phrases, never
individual random jumps, so the tune keeps its shape and key — with an honest warning
whenever it happens. **Guitar** Solo Arrangement now genuinely attempts playable
multi-note **TAB** for detected chords (a real fret/string search, not just the top note),
with a warning when a chord can't be placed and gets simplified. **Arrangement difficulty**
(Easy/Medium) is replaced with a 3-tier **Arrangement density** (Simple/Balanced/Detailed),
and the old "Piano-style arrangement" focus option is dropped (Piano/Guitar support notes
are controlled by density instead). See **Instrument profiles & range fitting** and
**Solo Arrangement** below for the full details. Explicitly not part of this version:
no drums, no new instruments, no accounts/payments, no v2.0 redesign — Ultimate
Guitar-style chord sheets remain a much later feature (probably v5.0).

**v0.9.7 was a small, targeted quality patch driven by a real test result**, not a
synthetic benchmark: the owner ran Mrs Magic locally on their Mac (Basic Pitch, Piano
Expert not installed there) and reported it "got the main idea and the multiple notes
but wasn't perfect" — wrong notes, missing notes, timing off, and too dense to read.
Two of those were fixed with real evidence behind the change: Basic Pitch's harmonic-
ghost filter was dropping **real octave doublings** (a bass note played with its own
octave — extremely common, intentional piano writing) because it was reusing a rule
tuned for a completely different, much cruder fallback engine; and repeated chord
events from sustain-pedal resonance are now merged instead of cluttering the sheet.
Timing/rhythm accuracy is flagged as a separate, bigger gap (real tempo detection
doesn't exist yet) rather than patched blind — see **Current limitations** below.

v0.9.6 was entirely about transcription **quality**. Basic Pitch (v0.9.3) was a real
improvement over the original pYIN-only engine, but it still isn't accurate enough on
dense piano recordings or full songs — the "Mrs Magic" hard benchmark below is the
honest reality check. This version adds two more specialist engines to the stack —
**Piano Expert** (a piano-specific model, tried first for Piano when available) and
**Demucs 4-stem source separation** (vocals/drums/bass/other, so Solo Arrangement can
give each instrument its own most-relevant stem) — investigated properly and wired in as
real, working, entirely optional adapters. Both are honestly **document-only** in every
hosted environment (GitHub Codespaces-style sandboxes) this app has actually been tested
in: they need dependencies and model downloads that are network-blocked there. See
**Transcription engine stack** below for exactly what that means and why v1.0 (in the
"this is genuinely solved" sense) isn't being declared yet.

v0.9.5 uses what the Engine Lab found (v0.9.4) to make BandChart choose transcription
settings automatically instead of leaving it all to guesswork: which engine to try, how many
simultaneous notes to allow, and what to tell you when it falls back or the audio is dense.
The **Engine Lab** (`/engine-lab`, linked quietly at the bottom of the home page) also
gained a "Use this output" button — run a couple of engines against a real project's audio,
compare them, and adopt whichever one actually did better. See **Smart transcription
routing** and **Engine Lab** below for full details.

Two detection engines are selectable in the main app (v0.9.3):

- **Melody (default)**: [librosa](https://librosa.org/)'s pYIN — a genuine, well-established
  pitch-tracking algorithm that follows one melodic line at a time (monophonic: a single
  voice, vocal line, or solo instrument, not full chords). It's pure Python/numpy — no
  TensorFlow — so it installs reliably everywhere, including GitHub Codespaces. v0.9.3
  makes it noticeably better: repeated notes of the same pitch are no longer glued into
  one long note (a loudness re-attack check finds the re-strikes), and clearly
  low-confidence detections are dropped (with a message, and never to the point of
  emptying a quiet recording).
- **Basic Pitch / multiple notes**: Spotify's open-source
  [Basic Pitch](https://github.com/spotify/basic-pitch) model (ICASSP 2022) — a real
  learned transcription model that hears several notes at once. It runs on CPU through its
  bundled ONNX network (no TensorFlow, no GPU, no accounts, nothing paid — the model ships
  inside the pip package). Detected notes carry a velocity (loudness), a `"source":
  "basic_pitch"` tag and simultaneous notes share a chord group id like `"chord_1"` in
  the JSON. If the model isn't installed or fails, the app quietly falls back to the
  built-in v0.9.2 CQT detector, and if THAT finds nothing usable it falls back to
  melody-only — always with an honest message, never a crash.
- **Piano Expert** (v0.9.6, Piano only, optional): a piano-specialist transcription
  model, tried BEFORE Basic Pitch for Piano when it's actually installed and working.
  Document-only in the environments this app has been tested in so far (see
  **Transcription engine stack** below) — when unavailable, Piano transcription runs
  exactly like before, no behaviour change.

**What it does:**
- **Clean home screen** (v0.9.1): "Turn sound into sheet music" — upload an audio file
  (wav, mp3, flac, ogg, m4a, aiff) or paste a **YouTube URL** (with the same rights
  confirmation as before) straight from the home page; a project is created for you
  (YouTube projects are even named after the video). Videos over 10 minutes and live
  streams are rejected; short clips work best
- **Setup step before transcribing** (v0.9.1): pick your instrument from a grid
  (including the new **Voice / Vocals**), choose **Direct transcription** ("transcribe
  one clear instrument or voice") or **Solo arrangement** ("turn the main melody into a
  playable solo piece for your chosen instrument" — labelled as melody-first, because
  BandChart is melody-first and full band separation is coming later), and optionally
  open **Advanced settings**: time signature (Let us predict — currently assumes 4/4 —
  or 4/4, 3/4, 6/8), key signature (Let us predict or C/G/D/A/F/Bb/Eb/Am/Em/Dm) and
  **Rhythm detail** (Readable, the default, or Precise)
- Run real pitch-tracking transcription on the uploaded audio (librosa pYIN, runs on CPU, no GPU/TensorFlow needed)
- Generate a MIDI file and a JSON file listing every detected note (pitch, start time, duration, confidence)
- Preview the transcription in the browser (simple piano-roll + note table)
- Pick a solo instrument — **Guitar, Bass, Piano, Violin, Alto Sax, Trumpet or Voice**
  (v0.9.8: the picker is narrowed to these 7 real instruments; Concert pitch, Flute,
  Clarinet, Tenor Sax and Ukulele are hidden from the main workflow but still work via
  the backend/API and on older projects) — the note table shows both the detected
  concert pitch and the written pitch, transposed for E♭/B♭ instruments
- **Tablature for guitar, bass and ukulele** (v0.7): picking one of the fretted
  instruments swaps the sheet-music view for a plain text-style **tab preview** —
  string lines with fret numbers in standard tuning, built from the same detected
  melody. A **Download TAB** button saves it as a `.txt` file. Frets 0–12 are
  preferred; if the melody sits outside the instrument's range it is shifted by whole
  octaves to fit (with a clear note saying so), and any note that still can't be
  played is marked `x` and listed in a warning instead of crashing. During Play
  Along the current tab column is highlighted, and deleting notes updates the tab
  like every other output
- Download MIDI, JSON, MusicXML (sheet music that opens in
  [MuseScore](https://musescore.org) and similar apps), and **PDF sheet music** — all
  written for the chosen instrument
- Choose between two sheet-music styles: **Cleaned sheet music** (default — smooths pitch
  wobbles, merges repeated fragments, drops noise blips, snaps rhythm to an eighth-note
  grid, and adds a key signature — your chosen one, or an estimated one) or
  **Raw transcription** (every detected note, literally, on a sixteenth grid)
- **Readable rhythm** (v0.9.1, default): the cleaned sheet gets a second smoothing pass —
  starts snap to the beat grid, durations become simple values (quavers, crotchets,
  dotted crotchets, minims, dotted minims, semibreves — long held notes stay long and
  tie naturally), and tiny awkward rests are absorbed. On real melodies this typically
  removes ALL stray sixteenths and ties. Pick **Precise** in Advanced settings to stay
  closer to the detected timings, or Raw for the literal record
- **Piano grand staff** (v0.9.1): choosing Piano engraves a proper two-staff system —
  treble and bass clef joined by a brace, split around middle C, with rests filling
  whichever side has no melody — in the browser, the MusicXML and the PDF
- **Play Along mode**: hear the transcribed notes in the browser with Play/Pause/Stop, a
  moving playhead and current-note highlighting, playback speeds of 50/75/100/125%, an
  optional 4-click count-in, and a running time display (playback uses the generated
  transcription, not the original audio)
- **Per-instrument playback sounds** (v0.9.1): the Sound selector defaults to **Auto
  (match instrument)** — piano gets the soft piano-ish tone, guitar a warm pluck, bass a
  deep dark pluck, ukulele a light quick pluck, and flute/violin/sax/trumpet/clarinet/
  voice a breathy sustained tone. Piano-ish/Soft synth/Pluck remain as manual choices —
  all gentle little Web Audio patches, never harsh beeps
- **Sheet music in the browser**: the generated notation renders right on the project page
  (via OpenSheetMusicDisplay), for the selected instrument and style — and it's the main
  play-along surface: a thin **blue playhead** glides continuously through the notes as
  they play (v0.8), a light blue wash marks the current bar, the playhead sits visibly at
  the start before you play, freezes on Pause, returns to the start on Stop, and the
  sheet auto-scrolls to keep the current bar in view. Bar numbers sit cleanly at the
  start of each system (v0.9.2)
- **Click to seek** (v0.9.2): click anywhere on the sheet and the blue playhead jumps to
  the nearest note — playback continues from there if playing, stays put if paused, and
  a click while stopped sets where the next Play begins. The note timeline (piano roll),
  the tab columns and the note-table rows are clickable too
- **Multiple-note detection** (v0.9.2, upgraded in v0.9.3): the "Note
  detection" advanced setting — Melody only (default) or **Basic Pitch / multiple notes**
  (picked automatically for Piano + Direct transcription). v0.9.3 replaces
  the primary engine with Spotify's **Basic Pitch** model (ONNX, CPU) — real learned
  polyphonic transcription with up to 4 simultaneous notes kept per moment. Simultaneous
  notes are grouped into chord events (`"group": "chord_1"` in the JSON, with a
  per-note velocity), appear as stacked chords on the piano grand staff, play together
  in Play Along (at their detected loudness), and land together in
  MIDI/JSON/MusicXML/PDF. A chord-aware rhythm cleanup keeps chords intact while
  snapping starts and durations to readable values. It is honest about its limits: it
  works best with clear piano or simple chords, reports when weak notes were removed or
  a moment was simplified, falls back with a clear message when the model is missing or
  finds nothing usable, and the tab stays melody-first (top note of each chord, with a
  note saying so). This is NOT full band or complex-piano transcription. **v0.9.7**:
  octave doublings (a bass note played with its own octave) no longer get mistaken for
  harmonic ghosts and dropped, and repeated chord events from sustain-pedal resonance
  are merged instead of cluttering the sheet — both fixed from real feedback testing
  against a hard real-world recording, not just synthetic test clips
- **Smart transcription routing** (v0.9.5, instrument caps centralised in v0.9.8): Piano
  defaults to multiple-note detection in BOTH Direct transcription and Solo arrangement
  (grand staff either way); Guitar now also defaults to it in Solo arrangement (v0.9.8 —
  Solo Arrangement attempts real playable multi-note TAB), and can be turned on manually
  for Direct transcription too; Violin can use multiple-note detection capped at 2
  simultaneous notes (double-stops); Bass and the melody-first instruments (Alto Sax,
  Trumpet, Voice) stay melody only. Every transcribed project shows an honest status
  block under the audio player — **Instrument**, **Mode** (Direct transcription / Solo
  arrangement), **Engine used**, **Detection mode**, and for Solo Arrangement also
  **Arrangement density** and **Range fitting**, plus **Fallback** (e.g. "Basic Pitch
  failed, used melody-only fallback." when it genuinely degrades) and **Warnings** (a
  rough density read plus any instrument-specific caution) — never hidden, so you always
  know what actually ran
- **A stronger engine stack** (v0.9.6): Piano now tries the **Piano Expert** specialist
  model first (when installed), before Basic Pitch — same fallback chain, same honest
  status block, just one more (optional) engine ahead of it. Solo Arrangement's optional
  source separation is now **4-stem** (vocals/drums/bass/other, not just vocals), so Bass
  can follow its own isolated bass stem instead of the same pass everyone else gets.
  See **Transcription engine stack** below for what's actually active vs. document-only
- **Auto-scroll** (on by default, toggleable): the sheet music, piano roll and note table
  keep the current note in view while playing
- **Fix wrong notes** (v0.8, chord-aware since v0.9.3): the note table is editable —
  type a new pitch (a note name like G4 or F#3, or a MIDI number), start time or
  duration into any row and press Enter; **+ Add a note** appends a note you can then
  adjust; on polyphonic transcriptions the little **+** on each row adds a note
  starting at the SAME time (so you can build or extend a chord — melody projects
  keep one note per moment on the engraved sheet, so the row **+** only appears in
  polyphonic mode); ✕ deletes a single note — including one note out of a chord,
  leaving the rest. A Chord column shows which notes were detected together.
  The preview, playback, sheet music, tab and every download update automatically, and
  "Reset to original transcription" undoes all edits. Invalid values get a clear error
  message instead of breaking anything
- **Chord markers (parked under Experimental tools since v0.9.3)**: the v0.9 manual
  chord-name tools (add/edit/delete/reset, rough suggestions, chord chart download)
  still exist, but they were a weak side feature, so they now live collapsed under
  **Experimental tools** at the bottom of the project page instead of cluttering the
  main flow. Proper Ultimate Guitar-style chord sheets are a much later feature,
  probably v5.0
- **Solo Arrangement for real songs** (v1.0, stem routing upgraded in v0.9.6,
  instrument-aware since v0.9.8): choosing **Solo arrangement** runs its own pipeline
  instead of the plain single-line detector — it tries to separate the song into stems
  and picks the one that matches your instrument (vocals for Voice/Violin/Alto
  Sax/Trumpet, its own bass stem for Bass, the accompaniment stem for Piano/Guitar),
  falling back to the full mix, honestly, when it can't separate at all. Piano/Guitar can
  also add a small number of simple supporting notes, and **Guitar now attempts real
  playable multi-note TAB** for detected chords (v0.9.8). New **Arrangement focus** (Main
  melody / Melody + simple support) and **Arrangement density** (Simple / Balanced /
  Detailed, v0.9.8 — replaces the old Easy/Medium difficulty) controls appear in Advanced
  settings when Solo arrangement is selected. A final **"Fit to instrument range"** step
  (v0.9.8) octave-shifts any notes outside the chosen instrument's playable range, by
  whole phrases so the tune keeps its shape. See **Instrument profiles & range fitting**,
  **Solo Arrangement** and **Transcription engine stack** below
- **Delete projects**: a Delete button beside each project on the dashboard removes the
  project with its uploaded audio and generated files, after a confirmation prompt

**Explicitly out of scope so far:** accounts, payments, full band charts, rehearsal packs,
complex editing, drums, additional instruments beyond the 7 main ones (v0.9.8 —
Flute/Clarinet/Tenor Sax/Ukulele/Concert pitch still work via the backend/API and old
projects, just hidden from the main picker), automatic chord detection from recordings
(the parked chord tools are manual markers plus rough melody-based suggestions; Ultimate
Guitar-style chord sheets are a much later feature, probably v5.0), accurate transcription
of complex piano pieces or full-band mixes (polyphonic detection is experimental and for
clear, simple material), strummed guitar chord shapes/diagrams, full guitar/bass
extraction from mixed songs (tab stays melody-first — v0.9.8's multi-note guitar TAB
attempts real chords when it detects them, but isn't full chord-shape recognition).
**Source separation (Demucs, now 4-stem) and Piano Expert** both exist in the code as
real, working optional adapters but are not installed by default and are not active in
the hosted environments this app has been tested in — see **Transcription engine stack**
below; neither promises perfect vocal isolation or perfect full-band/dense-piano
transcription.

---

## Transcription engine stack (v0.9.6)

Basic Pitch (v0.9.3) is a real improvement over a plain pitch tracker, but it's still
not accurate enough on dense piano recordings or full songs — that's the honest reason
v0.9.6 exists. This version adds two more specialist engines and wires them in as real,
working, entirely optional adapters — the main app keeps working exactly as before
whenever they're unavailable.

**The full engine chain, in try-order:**

| Instrument | Direct transcription | Solo arrangement |
| --- | --- | --- |
| **Piano** | Piano Expert (if installed) → Basic Pitch → CQT → pYIN | Same chain, run on the accompaniment ("other") stem if Demucs separated it, the full mix otherwise |
| Everything else | Basic Pitch → CQT → pYIN (unchanged from v0.9.5) | Same chain, run on the instrument's chosen stem (see the stem table below) |

**Piano Expert** — a piano-specialist transcription model (ByteDance/Qiuqiang Kong's
`piano_transcription_inference`), tried before Basic Pitch for Piano whenever it's
actually installed and its model checkpoint can load. It is **not** in
`requirements.txt` and is never installed automatically — install it yourself with
`pip install piano_transcription_inference` in the backend's virtual environment if you
want to try it (it also needs PyTorch, which pip will pull in for you). If it's missing,
fails to load, or errors during transcription, Piano falls back to Basic Pitch
automatically, and the status block says so plainly (`Fallback: Piano Expert failed
(...), used Basic Pitch instead.`).

**Demucs 4-stem separation** — upgraded from v1.0's vocals-only split to Demucs'
default 4-stem output: **vocals, drums, bass, other**. Solo Arrangement now picks the
stem that actually matches your instrument instead of a one-size-fits-all vocal/
accompaniment split:

| Instrument | Stem used (when separation works) |
| --- | --- |
| Voice, Violin, Alto Sax, Trumpet | vocals |
| Bass | bass |
| Piano, Guitar | other (accompaniment) |

Like Piano Expert, Demucs is **not** in `requirements.txt`. Install it yourself
(`pip install demucs`) if you want to try it — it also needs PyTorch. If separation
isn't available or fails for any reason, you'll see exactly this message: **"Source
separation failed. Using full mix instead."** — and every instrument falls back to
running its detection engine on the full mix, same as before v0.9.6. Nothing crashes
either way.

**Why both are document-only in the environments this app has actually been tested in**
(GitHub Codespaces-style sandboxes): both depend on PyTorch, and only the default
GPU-oriented PyPI wheel is reachable there (the lighter CPU-only wheel host,
`download.pytorch.org`, is network-blocked) — installing it pulls in several gigabytes
of unused CUDA packages. On top of that, their model checkpoints download from hosts
that are ALSO network-blocked in those environments (`zenodo.org` for Piano Expert,
`dl.fbaipublicfiles.com`/`huggingface.co` for Demucs) — so even a successful install
can't fetch a working model there. **Neither of these is a fixable bug in BandChart AI**
— they're environment network policy, confirmed by directly testing the actual hosts
(re-confirmed again in v0.9.7.1 with a fresh `curl` against all four hosts before writing
any code that version — still 403 at the TCP CONNECT level, identical to every previous
check). If you're on a Mac with a normal, unrestricted internet connection, both are worth
trying — see the installation commands above, and check `/engine-lab` afterwards to
confirm they show as available.

**Honest bottom line**: this app is not calling its transcription quality "solved" —
v1.0 (in the sense of "genuinely good enough") is being held back deliberately until
someone can confirm Piano Expert and/or Demucs actually work and actually help on real
hardware, against the Mrs Magic benchmark below. Until then, Basic Pitch (optionally
alongside 4-stem separation once installed) remains the best available option, same as
v0.9.5.

---

## Solo Arrangement (v1.0, stem routing upgraded in v0.9.6, instrument-aware in v0.9.8, honest separation status in v0.9.7.1)

Solo Arrangement is for turning a **full song** into a playable solo part — different
from Direct transcription, which is for a clean recording of one instrument or voice.
Instead of running the same single-line pYIN/Basic Pitch pass on the whole mixed song,
Solo Arrangement:

1. Cleans up the audio (normalises volume, trims silence) into a scratch copy — your
   original upload is never touched
2. Tries to separate the song into stems (optional — Demucs, see **Transcription engine
   stack** above). Each instrument follows its own most-relevant stem — see the stem
   table above — falling back to the full mix, honestly, when separation isn't available
3. Extracts the main melody with the same pYIN/Basic Pitch/Piano Expert engines the rest
   of the app uses, cleaned up the same way (tiny ghost notes removed, pitch jitter
   smoothed, rhythm quantized for readability)
4. For **Piano and Guitar only**, when you ask for it (Arrangement focus below), adds a
   number of simple low-register supporting notes from the accompaniment stem — how many,
   controlled by **Arrangement density** — never a full reduction of everything detected
5. **Fits the result to the chosen instrument's playable range** (v0.9.8) — see
   **Instrument profiles & range fitting** below
6. Feeds the result into the same sheet music / TAB / MIDI / JSON / MusicXML / PDF / Play
   Along / note editor as everything else — **Guitar** attempts real playable multi-note
   TAB for any chords that survive (v0.9.8), not just the top note

**Arrangement controls** (Advanced settings, only shown for Solo arrangement):
- **Arrangement focus**: *Main melody* (default) — melody only, no extra notes; *Melody +
  simple support* — adds the support notes described above (Piano/Guitar only)
- **Arrangement density** (v0.9.8, replaces the old Easy/Medium *Arrangement difficulty*):
  *Simple* (default) — fewest support notes, cleanest to read; *Balanced* — a moderate
  amount of extra detail; *Detailed* — closer to everything actually detected, still
  limited by what the instrument can play

**Honest status, every time** — a status block under the audio player, shown for every
transcribed project:
```
Instrument: Guitar
Mode: Solo arrangement
Engine used: Basic Pitch
Detection mode: Multiple notes
Source separation: unavailable
Stem used: other
Arrangement focus: Melody + support
Arrangement density: Balanced
Range fitting: Octave-shifted to fit range
Warnings: Dense audio may need editing
```
**"Source separation"** (v0.9.7.1) is a genuine 3-value read, never a simple yes/no:
*Demucs* (it ran and produced stems for this project), *unavailable* (Demucs isn't
installed — the normal case in the hosted environments this app has been tested in), or
*failed* (Demucs is installed but errored on this particular audio). **"Stem used"**
(renamed from "Source" in v0.9.7.1) is *vocals* / *bass* / *other* / *full mix* — which
one it actually ran detection on. (Direct transcription projects show the same
Instrument/Mode/Engine used/Detection mode lines, without the Solo-Arrangement-only
ones — and, v0.9.7.1, may show a dense-full-mix suggestion instead; see below.) You'll
also see one of these exact messages depending on what happened: *"Solo Arrangement finds
the strongest melody and creates a playable part. Dense songs may need editing."*
(always), *"Using vocal stem for main melody."* (isolation worked, and this instrument
uses the vocal stem), *"Source separation failed. Using full mix instead."* (separation
isn't available or failed — see **Transcription engine stack** above), *"Added simple
support notes. Please check and edit."* (when support notes were added), *"Some notes
were octave-shifted to fit &lt;Instrument&gt;."* (v0.9.8 range fitting moved something),
and *"Some guitar notes were simplified because the detected chord was not playable."*
(v0.9.8 — Guitar TAB couldn't fit every note of a detected chord onto the fretboard and
dropped the least useful one).

**Direct transcription on a dense full mix** (v0.9.7.1): Direct transcription stays
different from Solo Arrangement — no stem separation, it just runs detection on whatever
you uploaded. But if the result comes back reading as genuinely dense (the same density
read the status line already shows), you'll now also see: *"Direct transcription on a
full mix may be dense. Use Solo Arrangement for a cleaner playable version."* — a
suggestion, not a block; Direct transcription still runs and still works, this just
points at the better tool for a full song.

**What this is not**: BandChart AI does not claim to perfectly separate every instrument,
and Solo Arrangement does not claim to perfectly transcribe a full band. It finds the
strongest melody it can and builds a playable, editable starting point — dense songs will
need checking and cleanup, honestly flagged every time.

---

## Instrument profiles & range fitting (v0.9.8)

Every instrument's playable range, transposition and note-taking ability now lives in one
place — `backend/app/instrument_profiles.py` — instead of being scattered across the
routing, arrangement and tab code as separate special cases. All ranges are **concert
(sounding) MIDI** — the pitch a listener actually hears, not what a transposing player
reads off the page; written-pitch transposition for Alto Sax/Trumpet is applied only at
MusicXML/PDF export time, same as before.

| Instrument | Playable range | Max simultaneous notes | Notes |
| --- | --- | --- | --- |
| Piano | A0–C8 (MIDI 21–108) | 6 | Grand staff, chords preserved |
| Guitar | E2–E6 (MIDI 40–88) | 4 | Standard tuning; attempts playable multi-note TAB |
| Bass | E1–G4 (MIDI 28–67) | 1 | Bassline/melody-first, standard tuning |
| Violin | G3–A7 (MIDI 55–105) | 2 | Melody plus simple double-stops only |
| Alto Sax | Db3–A5 sounding (MIDI 49–81) | 1 | Melody only; written a major 6th above concert (E♭) |
| Trumpet | E3–C6 sounding (MIDI 52–84) | 1 | Melody only; written a major 2nd above concert (B♭) |
| Voice | C3–C5 (MIDI 48–72) | 1 | Melody only, a comfortable singable range |

**"Fit to instrument range"** is the last Solo Arrangement step: notes that fall outside
the table above are octave-shifted into range. Whole **phrases** move together (grouped by
gaps of silence ≥1 second, shifted by whichever whole-octave amount most of the phrase's
out-of-range notes need) rather than shifting note-by-note, so a melody keeps its shape
instead of jumping around awkwardly; only a genuine straggler still out of range after its
phrase's shift gets clamped individually. It's always a whole-octave shift (±12
semitones), never an arbitrary semitone transposition — that keeps the melody in the same
key. Whenever anything moved, you'll see *"Some notes were octave-shifted to fit
&lt;Instrument&gt;."* under the audio player. Direct transcription is unaffected — range
fitting is a Solo Arrangement step, since it needs a single target instrument to fit
against.

---

## Smart transcription routing (v0.9.5)

Instead of one fixed engine for everything, BandChart now decides how to transcribe based
on the instrument, the mode (Direct transcription vs Solo arrangement), and your Note
detection setting — and always tells you exactly what it decided.

**Which engine/mode is used for each instrument:**

| Instrument | Direct transcription | Solo arrangement |
| --- | --- | --- |
| **Piano** | Basic Pitch, multiple notes (auto-selected), up to 6 at once, grand staff | Basic Pitch, multiple notes (auto-selected), up to 6 at once, grand staff |
| **Guitar** | Melody only (pYIN) by default; multiple notes if you choose it, up to 4 at once | Multiple notes (auto-selected, v0.9.8), up to 4 at once — attempts real playable multi-note TAB, with "Guitar TAB attempts a playable multi-note chord where it can. Some notes may be simplified if the detected chord isn't playable." |
| **Bass** | Melody only (pYIN) by default; no chordal mode | Same — melody-first, bass TAB unaffected |
| **Violin** | Melody only (pYIN) by default; multiple notes if you choose it | Melody only by default; multiple notes if you choose it, capped at **2 simultaneous notes (double-stops)** — shows "Violin output is limited to melody and simple double-stops for now." |
| Alto Sax, Trumpet, Voice | Melody only (pYIN) | Melody only (pYIN) — melody-first by instrument design, per v0.9.8's instrument profiles |
| Everything else (Flute, Tenor Sax, Clarinet, Ukulele, Concert pitch — hidden from the main picker since v0.9.8, still backend-supported) | Melody only (pYIN) | Melody only (pYIN) |

Every instrument keeps the manual "Note detection" Advanced setting — the table above is
just the pre-selected default; you can always switch it.

**How the fallback chain works** (unchanged engines, smarter reporting): when Multiple
notes is requested, BandChart tries Basic Pitch first, then the built-in CQT detector if
Basic Pitch isn't installed or fails, and finally plain melody-only pYIN if everything
else fails or finds nothing. Nothing about this chain is new — v0.9.5 just makes it
visible via a status block under the audio player on every transcribed project:

```
Engine used: Basic Pitch
Mode: Multiple notes
Fallback: none
Warnings: none
```

If Basic Pitch weren't available, "Engine used" would read "Built-in simple detector" and
"Fallback" would explain why. If everything failed and it landed on melody-only, "Fallback"
reads exactly **"Basic Pitch failed, used melody-only fallback."** — this is never hidden,
so you always know what actually ran, not just what you asked for.

**Audio difficulty warning**: the same status block's Warnings line also reports a rough
density read — "Simple melody", "Some overlapping notes", or "Dense piano/audio — may need
editing" when the polyphonic detector had to trim notes or the recording came back
consistently low-confidence. It's deliberately rough (a handful of blunt signals, not a
model) — treat it as a hint to check the note editor, not a verdict.

**C major chord gate** (the pass/fail basic test — see Testing below): uploading a clean
C major chord (C4+E4+G4) with Piano + Direct transcription, or Piano + Solo arrangement,
must detect all three notes together as one chord group, with JSON showing overlapping
notes and MIDI/Play Along sounding them together. This is verified automatically before
every release.

---

## Engine Lab (v0.9.4, "Use this output" added in v0.9.5, per-stem adapters completed in v0.9.7.1)

BandChart's note detection is genuinely hard to get right, especially on real piano
recordings — see "Mrs Magic" below. Rather than keep swapping the main engine and hoping,
v0.9.4 adds a small, separate **Engine Lab** for comparing engines honestly on the same
audio, side by side, with real numbers.

**Open it:** click the quiet "Engine Lab" link at the bottom of the home page, or go to
`/engine-lab` directly. It is a developer tool, not part of the normal workflow. Running
engines here is read-only and never touches a real project — the one exception is the
explicit "Use this output" button (v0.9.5, step 5 below), the only way a lab result
becomes a project's active transcription.

**What it does:**
1. Choose audio: one of six **built-in synthetic test clips** (A4 tone, C major chord,
   C major scale, simple block chords, left-hand bass + right-hand melody, and — new in
   v0.9.7 — octave-doubled bass + melody, a permanent regression test for the real-world
   fix below), an **existing project's audio**, or a **direct upload** just for the lab
2. Pick one engine and click **Run engine** — the result (processing time, note count,
   overlapping notes, chord groups, pitch range, any warnings, MIDI/JSON download links,
   and a small piano-roll debug view) is added to a comparison table, so you can run
   several engines on the same clip and see them side by side
3. For the six built-in test clips, every note's correct pitch and timing is known in
   advance, so the lab also shows a **rough accuracy score**: correct/missed/extra notes,
   whether simultaneous notes were preserved together, and mean timing error. This is
   deliberately simple (exact pitch match, generous timing tolerance) — good enough to
   rank engines on clean audio, not a rigorous benchmark
4. If an engine isn't installed or available, it's shown grayed out with a clear
   **"Engine unavailable: [reason]"** message instead of being hidden or crashing
5. **(v0.9.5) "Use this output"**: run a couple of engines against an existing project's
   audio, compare them, then click **Use this output** on whichever result actually did
   better — it becomes that project's active transcription (JSON/MIDI rewritten, "Reset
   to original transcription" now resets back to this applied result, manual chord
   markers clear the way a fresh transcribe would). Only works for a run made from that
   exact project's own audio — a fixture or a direct-upload run can't be applied, on
   purpose, so a lab experiment can never accidentally overwrite the wrong project

**Engines available in the lab today:**

| Engine | Status | Notes |
| --- | --- | --- |
| pYIN (melody baseline) | ✅ Available | The original monophonic engine. Scores 0% on any chord test by design — it can only follow one line, which is exactly the limitation the other engines exist to fix |
| Basic Pitch (Spotify) | ✅ Available | The app's current main polyphonic engine. Detects chords exactly on clean synthetic audio |
| Built-in simple detector (CQT) | ✅ Available | The v0.9.2 fallback (no external model). Comparable to Basic Pitch on clean audio, faster, no model download |
| Piano Expert (ByteDance) | ⚙️ Available if installed (v0.9.6) | Real adapter — active automatically once `piano_transcription_inference` is installed and its checkpoint loads. Not installed by default; see **Transcription engine stack** above |
| Demucs + Basic Pitch, vocal separation (v0.9.6) | ⚙️ Available if installed | Separates with Demucs, then runs Basic Pitch on the isolated vocal stem — what Voice/Violin/Alto Sax/Trumpet Solo Arrangement actually uses when Demucs works |
| Demucs + Basic Pitch, bass separation (v0.9.7.1) | ⚙️ Available if installed | Same separation, isolated bass stem — what Bass Solo Arrangement actually uses when Demucs works |
| Demucs + Basic Pitch, accompaniment separation (v0.9.7.1) | ⚙️ Available if installed | Same separation, isolated "other" stem — what Piano/Guitar Solo Arrangement actually use when Demucs works |
| Omnizart | ⛔ Investigated, not active | See below |
| MT3 (Magenta) | ⛔ Investigated, not active | See below |

**Sample results** (synthetic fixtures, this environment, CPU):

| Fixture | pYIN | CQT | Basic Pitch |
| --- | --- | --- | --- |
| A4 tone | 100% (1 note) | 100% | 100% |
| C major chord | 0% (1 note, no chord) | 100% (3 notes, 1 group) | 100% (3 notes, 1 group) |
| C major scale | 100% (8 notes) | 99% (1 extra) | 100% (8 notes) |
| Block chords (C/F/G) | 0% (1 note) | 100% (9 notes, 3 groups) | 100% (9 notes, 3 groups) |
| Bass + melody | 56% (misses the bass) | 96% (5 extra) | 96% (6 extra) |

Takeaways: pYIN is honest about being melody-only — it fails hard on anything with two
notes at once, which is exactly why Basic Pitch exists. CQT and Basic Pitch are neck-and-
neck on clean, simple material; Basic Pitch is the one kept as the app's default because
it's a real learned model rather than a hand-tuned spectral heuristic, which tends to
generalize better to real (non-synthetic) recordings. Both pick up a few extra notes on
the bass+melody test (low notes have strong harmonics that can be mistaken for extra
pitches) — a real, honest limitation, not hidden here.

**Piano Expert and Demucs (v0.9.6) — wired in as real, active-when-installed adapters,
not just investigated.** See **Transcription engine stack** above for the full writeup;
short version: both need PyTorch (pulls in unused CUDA packages from the default PyPI
wheel in environments where the CPU-only wheel host is blocked) and a model checkpoint
from a host that's also network-blocked in every environment this app has actually been
tested in (Zenodo for Piano Expert, fbaipublicfiles/huggingface for Demucs) — re-checked
directly against those hosts in v0.9.6, not just re-read from old notes. Neither is in
`requirements.txt`; both activate automatically the moment they're actually installed
and working, here and in the main app.

**Other engines investigated but not wired into the app (v0.9.4):**
- **Omnizart** — a general transcription toolkit (piano/vocal/chord/drum/beat).
  Genuinely works: installed and ran real transcription on CPU, no GPU needed. But it
  only runs on **Python 3.10** (this app uses 3.12), needs the system `portaudio`
  library, and pulls in TensorFlow plus ~700MB of checkpoints (~3.5GB total footprint).
  That doesn't fit safely inside the main backend environment — it would need its own
  separate virtual environment and a way to call out to it (a subprocess bridge), which
  is future work, not done here
- **MT3 (Magenta)** — investigated via research only (not installed). No PyPI package;
  installing it means cloning a repo and pulling JAX/T5X/TensorFlow from source, plus
  fetching checkpoints from Google Cloud Storage via `gsutil`. The project itself is in
  caretaker mode (occasional trivial commits, no real feature work since ~2022). Not
  practical for a CPU-only, no-fuss local setup — skipped
- **"MuScriptor"** — investigated via research only. This turned out to be a real,
  actively developed model (Kyutai + MireloAI), pip-installable, with a genuinely small
  CPU-capable variant. **However, its model weights are licensed CC BY-NC 4.0
  (non-commercial only)** — the code is MIT but the weights are not free to use if
  BandChart AI is or becomes a paid product. Flagging this for a future decision rather
  than integrating it under an uncertain license
- **librosa spectral-peak fallback** — this already exists in the app as the "Built-in
  simple detector (CQT)" engine (v0.9.2); no new work needed here

**Mrs Magic hard piano benchmark:** a genuinely hard real piano recording
(`https://youtu.be/yO_OD7Yx2j8`), used as the honest reality check that synthetic test
clips can't provide. Import it as a normal project and try, in order: **Piano Direct
transcription with Piano Expert** (if you've installed it — the strongest candidate),
**Piano Direct transcription with Basic Pitch** (the default), and **Piano Solo
arrangement with Demucs + Piano Expert/Basic Pitch** (if you've installed Demucs too) —
then pick the same audio under "An existing project's audio" in the lab to compare all
of them side by side and optionally apply the best one. **This still could not be run
from this cloud environment** — YouTube blocks import attempts from cloud servers (same
limitation as the rest of the app; see "Run locally on Mac for YouTube import" below), on
top of Piano Expert/Demucs being document-only there anyway. Run it on a real Mac with
Piano Expert and/or Demucs installed; no engine is expected to solve it perfectly, and
v0.9.7 does NOT claim it's solved — the honest goal is an editable, non-collapsed-to-
one-line result you can clean up, not a perfect transcription. **If you do get a chance
to test this, the results would genuinely help decide whether Piano Expert becomes the
piano default in a future version.**

**Real result so far (v0.9.7):** the owner did run this on their Mac with Basic Pitch
(Piano Expert wasn't installed there) — "got the main idea and the multiple notes but
wasn't perfect": wrong notes, missing notes, timing/rhythm off, and too dense to read.
v0.9.7 fixed two of those with real evidence behind the change (octave doublings no
longer dropped as false harmonics; repeated chord events merged instead of cluttering
the sheet) — see the Multiple-note detection bullet above. Timing/rhythm is still an
open gap: the app assumes a fixed 120 BPM everywhere, and Mrs Magic almost certainly
isn't at exactly that tempo — real tempo detection would be needed to fix it properly,
and doesn't exist yet.

---

## Run locally on Mac for YouTube import

YouTube often blocks downloads coming from cloud servers like Codespaces, but is usually
happy with home internet connections — so if YouTube import keeps getting blocked, running
the app on your own Mac is the best fix. It's the same app with the same features; only
the computer changes. (Your Codespaces projects don't transfer over — each place keeps its
own local storage — and Codespaces keeps working as before.)

It takes three double-clicks, described step by step in the next section:

1. **`check.command`** — confirms Python, Node/npm, ffmpeg and yt-dlp are ready, with an
   install command for anything missing (ffmpeg matters: **YouTube import needs it**).
   The app prefers Homebrew's **Python 3.12** when installed and warns if your Python is
   older than 3.10 (old versions still run, but tools like yt-dlp are dropping them —
   `brew install python@3.12` is the fix, and setup rebuilds everything automatically)
2. **`setup.command`** — installs everything the app needs, including yt-dlp for YouTube
   import (safe to run again any time). If the optional PDF engine (verovio) can't be
   built on your Mac, setup completes anyway with a fallback: everything works except the
   PDF button, which will explain the alternative (MusicXML + free MuseScore app)
3. **`start.command`** — starts the app and opens http://localhost:3000 in your browser

## Quick Start (Mac) — no coding required

This folder includes three double-click scripts that do all the technical setup for you.
Use them in order, top to bottom.

**Step 0 — Get the app onto your Mac.** Download or clone this repository, then open the
`bandchart-ai` folder in Finder. You should see `check.command`, `setup.command`, and
`start.command` inside it.

**Step 1 — Check your computer is ready.** Double-click **`check.command`**.

A Terminal window opens and tells you whether Python, Node.js, npm, ffmpeg, and yt-dlp
(for YouTube import) are ready, with a one-line command to install anything that's missing
(via [Homebrew](https://brew.sh) — the script tells you how to get that too, if you don't
have it). Fix anything marked `[MISSING]`, then run it again until everything says `[OK]`.
(`yt-dlp` showing `[LATER]` is normal before first setup — setup.command installs it.)

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
pip install --no-deps basic-pitch==0.4.0
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
(The `--no-deps` line installs the Basic Pitch note-detection model used by polyphonic
mode. `--no-deps` is deliberate: the package declares an old TensorFlow it doesn't
actually need here — the model runs through onnxruntime, which is already in
requirements.txt. If you skip this line the app still works; polyphonic mode just uses
the built-in simpler detector.)
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

Requires **Python 3.10+** (3.9 still runs, but dependencies like yt-dlp are deprecating it
— the Mac scripts prefer Homebrew's Python 3.12 automatically) and **Node.js 18+**.
Install `ffmpeg` too for YouTube import and compressed formats like mp3/m4a (wav/flac/ogg
uploads work without it).

### 1. Backend (FastAPI + librosa)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install --no-deps basic-pitch==0.4.0   # optional: the polyphonic-mode model (see note above)
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
> `pip install -r requirements.txt` and `pip install --no-deps basic-pitch==0.4.0` in the backend
> once more (with the virtual environment active) — newer versions add libraries (music21
> for MusicXML, verovio/cairosvg/pypdf for PDF export, onnxruntime + Basic Pitch for
> v0.9.3's polyphonic detection).

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
   and the **sheet music follows along**: a thin blue playhead glides through the
   notes, the light blue wash tracks the current bar, and the score scrolls itself. (The note table highlights
   too, and a piano-roll view lives under "Advanced note timeline" if you want it.)
3. **Pause** freezes playback where it is; pressing **Play** again continues from there;
   **Stop** resets to the beginning
4. Try the speed buttons — **50%** and **75%** are handy for practising along slowly;
   pitch stays the same, only the pace changes
5. Remember: playback is the *transcription*, not your recording — if a note sounds wrong
   here, it will also be wrong in the sheet music, which makes this a quick way to check a
   transcription by ear

### Guitar, bass and ukulele tab (beginner steps)

v0.7 adds simple text-style tablature for the three fretted instruments. It's built from
the **same single detected melody line** as everything else — this is still monophonic
melody transcription, **not** full guitar chord transcription and not band/bass-line
extraction from a mixed song. One note at a time, shown as fret numbers instead of staff
notation.

**How it works:**
- Pick **Guitar**, **Bass** or **Ukulele** in the Solo instrument dropdown. The
  sheet-music panel is replaced by a **Tab output** panel: six lines for guitar
  (standard tuning E2 A2 D3 G3 B3 E4), four for bass (E1 A1 D2 G2) and four for ukulele
  (G4 C4 E4 A4, high G). Each column is one detected note, in playing order, with a bar
  line at each new measure (at the app's fixed 120 BPM grid)
- Each note is placed on one string, preferring low frets (0–12) for easy playing
- If the melody doesn't fit the instrument's range (very common for bass, which is a low
  instrument), the whole melody is shifted up or down by whole octaves to fit — a yellow
  note above the tab tells you when this happened. Any note that *still* can't be played
  is shown as `x` in the tab and listed in the warning — nothing crashes
- **Download TAB** (only visible for the three fretted instruments) saves the tab as a
  plain `.txt` file you can open, print or paste anywhere
- Play Along works exactly as before, and the current tab column lights up orange as it
  plays. Deleting a note updates the tab preview and the TAB download too
- The MusicXML and PDF downloads still work for these instruments, but they use **staff
  notation** for now — a proper engraved tab PDF is planned for later

**How to test it:** transcribe any short melody, select **Guitar** — the tab preview and
the **Download TAB** button appear. Switch to **Bass** — expect the yellow octave-shift
note on most melodies. Switch to **Ukulele**, then back to **Piano** — the sheet music
view returns. Delete a note in the note table and watch the tab column disappear.

### Chord markers — parked under Experimental tools (beginner steps)

The v0.9 chord layer was a weak side feature, so since v0.9.3 it lives collapsed under
**Experimental tools (chord markers)** at the bottom of the project page. Proper
Ultimate Guitar-style chord sheets are a much later feature, probably v5.0. You place
the chord names yourself (or start from rough suggestions) — the app does **not**
detect chords from the recording.

1. Open a transcribed project, scroll to the bottom, and click
   **Experimental tools (chord markers)** to unfold the section
2. Click **+ Add chord** — a chord row appears with a name box and a start time in
   seconds (the matching bar number is shown next to it)
3. Type any normal chord name — C, Am, F#m7, Bb, G7, Cmaj7, G/B — and press Enter.
   Typos like "H9" get a clear red message and change nothing
4. Chord names still appear engraved above the staff in the MusicXML and PDF downloads
   (transposed for E♭/B♭ instruments), and the JSON download includes the markers
5. **Download Chord Chart** saves a plain text file with the bar grid and every chord
   with its time and bar number
6. **Suggest chords from melody (rough)** fills the list with simple in-key guesses from
   the detected melody. They are a rough starting point — please check and edit them
7. Chords stay put when you edit, add or delete melody notes; **Reset chords** clears
   the list. A chord placed after the end of the melody gets a friendly warning
8. Limitations: one chord layer, no strummed guitar shapes/diagrams, no chord detection
   from full-band recordings, and the chord names no longer show on the in-browser
   sheet strip — chord sheets return properly in a much later version (probably v5.0)

### Fixing wrong notes (beginner steps)

Since v0.8 you can **edit** notes, not just delete them.

1. In the **Note detail** table, find the wrongly detected note (playing along and watching
   the highlight is the easiest way to spot it)
2. **Fix the pitch**: click the pitch box, type the right note — a name like `G4`, `F#3`
   or `Bb3`, or a MIDI number — and press Enter (or click away)
3. **Fix the timing**: the start time and duration boxes work the same way (seconds)
4. **Add a missing note**: click **+ Add a note** under the table — a new note appears
   after the last one; then type in the pitch and timing you want. On polyphonic
   transcriptions you can also **stack a chord** (v0.9.3): click the little blue **+**
   on a row — it adds a note starting at the SAME time as that row (a third above),
   ready to adjust
5. Still wrong? Click the red **✕** at the end of a row to delete that note entirely —
   including a single note out of a detected chord (the Chord column shows which notes
   belong together); the other chord notes stay
6. Every change auto-saves (an "Edits saved" note confirms it) and updates the preview,
   the sheet music, the tab, playback and all downloads — there is nothing extra to
   regenerate
7. If you type something invalid (like `H9` or a negative time) you get a clear red
   message and nothing changes
8. Changed your mind? Click **Reset to original transcription** to get the untouched
   detection back

| API | Method | Path |
| --- | --- | --- |
| Save edited notes | PUT | `/api/projects/{id}/notes` |
| Undo all edits | POST | `/api/projects/{id}/notes/reset` |
| Delete a project | DELETE | `/api/projects/{id}` |

### Importing from YouTube (beginner steps)

1. Create or open a project, and in the "Add audio" box click **Import from YouTube**
2. Paste a normal YouTube video link (like `https://www.youtube.com/watch?v=…` or
   `https://youtu.be/…`)
3. Tick the confirmation box — *"I confirm I own this content or have permission to
   process it for private transcription/arrangement use."* The import button stays
   disabled until you do. BandChart AI does not publish, share or create a public library
   from your transcription; everything stays in your own project storage
4. Click **Import YouTube audio**. The app checks the link, extracts the audio, converts
   it to WAV, and starts the transcription automatically — importing can take a minute
5. From there everything works exactly like an uploaded file: preview, sheet music,
   Play Along, note editing, and all four downloads

Notes and limits:
- YouTube import uses the same monophonic transcription engine. It works best on clear
  single melody lines, not full band mixes
- Videos longer than **10 minutes**, live streams, and playlist links are rejected
- If a video is private, age-restricted, removed, or YouTube can't be reached, you'll get
  a plain-English message saying so — your project's existing audio and results are never
  touched by a failed import

### YouTube import limitations in Codespaces

YouTube sometimes blocks downloads coming from cloud servers (Codespaces machines run in
data centres, and YouTube treats heavy data-centre traffic as suspicious). If that
happens you'll see: *"YouTube blocked this cloud server from downloading the audio…"*.

- **This is not necessarily an app bug** — the app asked correctly and YouTube refused
- **The fallback always works**: download or record the audio yourself and use the normal
  **Upload audio file** option — everything after the import step is identical
- **Running the app on your own computer** often works better, since YouTube is less
  suspicious of home internet connections than of data centres
- Trying again later, or a different video, sometimes gets through

**YouTube import troubleshooting:**
- *"yt-dlp library is missing"* — in the backend terminal (venv active) run
  `pip install -r requirements.txt`, then restart the backend
- *"ffmpeg is required"* — run `sudo apt-get update && sudo apt-get install -y ffmpeg`,
  then restart the backend (Codespaces usually needs this once; see the ffmpeg note above)
- *"Couldn't reach YouTube"* — the server's network may block YouTube, or the connection
  dropped; try again, or download the audio yourself and use normal file upload

### Deleting a project (beginner steps)

1. Go back to the project list (the "← Back to projects" link, or open http://localhost:3000)
2. Every project row has a red **Delete** button on the right
3. Click it — a confirmation appears: *"Delete this transcription? This will remove its
   uploaded audio and generated files."* Cancel keeps everything; OK deletes the project,
   its uploaded audio, and all its generated files (JSON, MIDI, MusicXML, PDF)
4. Deletion is permanent — there's no undo — but it only ever touches that one project's
   own storage folder, never the app itself or your other projects

## Troubleshooting

**Piano Expert / Demucs show "Engine unavailable" in `/engine-lab`, or Piano/Solo
Arrangement never seem to use them.** This is expected unless you've deliberately
installed them (they're optional, not in `requirements.txt`, and never install
automatically). To try them: `pip install piano_transcription_inference` and/or
`pip install demucs` in the backend's virtual environment (both also pull in PyTorch).
Then restart the backend and check `/engine-lab` — if they still show unavailable, the
reason text tells you why: usually a blocked checkpoint download (Zenodo for Piano
Expert, fbaipublicfiles.com/huggingface.co for Demucs — some networks, including GitHub
Codespaces-style cloud sandboxes, block these outright). A Mac with a normal home
internet connection is the most likely place these actually work. If they're genuinely
unreachable on your network, the app keeps working exactly as before — Basic Pitch
stays the active engine, and Solo Arrangement falls back to the full mix.

**`No module named 'pkg_resources'` when running Basic Pitch.** Fresh Python 3.12
environments no longer include setuptools (which provides `pkg_resources`) by default.
It's now in `requirements.txt`, so run `pip install -r requirements.txt` again (or
`pip install setuptools`) inside the backend venv.

**`module 'scipy.signal' has no attribute 'gaussian'` from Basic Pitch.** This happens
when pip installed an OLD basic-pitch (it backtracks through ancient versions while
trying to satisfy basic-pitch's declared TensorFlow dependency). Old versions call a
scipy function that modern scipy removed. Fix: install the pinned version without its
declared dependencies — `pip install --no-deps basic-pitch==0.4.0` — which uses the
current scipy API and runs on onnxruntime. No scipy downgrade needed.

**Mac setup said the optional PDF engine (verovio) couldn't be installed.** Setup still
completes and everything else works — transcription, YouTube import, the in-browser sheet
music (which doesn't use verovio), and MIDI/JSON/MusicXML downloads. The PDF button will
show a message pointing you to the alternative: download the MusicXML and open it in the
free [MuseScore](https://musescore.org) app. To enable PDFs on the Mac, install Xcode
Command Line Tools (`xcode-select --install` in Terminal — a few minutes), then run
`setup.command` again.

**PDF download fails with a message about "cairo".** The PDF engine uses a system library
called cairo. In Codespaces it's usually preinstalled — if missing, run
`sudo apt-get update && sudo apt-get install -y libcairo2`. On a Mac run
`brew install cairo`. Then restart the backend and try again. The MusicXML download
works regardless.

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
| POST | `/projects/{id}/youtube` | Import audio from a YouTube URL — `{"url": string, "rights_confirmed": true}` |
| POST | `/projects/{id}/settings` | Save the setup choices — `{"instrument", "mode", "time_signature", "key_signature", "rhythm_detail", "note_detection", "arrangement_focus", "arrangement_density"}` (the last two are v1.0/v0.9.8, ignored by Direct transcription; `arrangement_density` renamed from `arrangement_difficulty` in v0.9.8) |
| POST | `/projects/{id}/transcribe` | Run transcription on the uploaded audio |
| GET | `/projects/{id}/notes` | Get the detected-notes JSON |
| GET | `/projects/{id}/audio` | Stream the original uploaded audio |
| GET | `/projects/{id}/download/midi` | Download the generated MIDI file |
| GET | `/projects/{id}/download/json` | Download the generated notes JSON file |
| GET | `/projects/{id}/download/musicxml?instrument=<key>&style=<clean\|raw>` | Download MusicXML for a solo instrument — instrument keys: `concert`, `piano`, `flute`, `violin`, `alto_sax`, `tenor_sax`, `trumpet`, `clarinet`, `guitar`, `bass`, `ukulele` (v0.9.8: the app's main picker only shows `guitar`, `bass`, `piano`, `violin`, `alto_sax`, `trumpet`, `voice` — the rest still work here); style defaults to `clean` (staff notation for all keys, including the fretted ones) |
| GET | `/projects/{id}/download/pdf?instrument=<key>&style=<clean\|raw>` | Download PDF sheet music (same parameters) |
| GET | `/projects/{id}/tab?instrument=<guitar\|bass\|ukulele>` | Tab layout as JSON (entries, warnings, preview grid) for the in-app tab preview |
| GET | `/projects/{id}/download/tab?instrument=<guitar\|bass\|ukulele>` | Download the tab as a plain `.txt` file |
| GET | `/projects/{id}/chords` | Get the chord markers |
| PUT | `/projects/{id}/chords` | Save the chord marker list — `{"chords": [{"name": "Am", "start_time": 2.0}]}` |
| POST | `/projects/{id}/chords/suggest` | Rough diatonic chord suggestions from the melody (replaces the list) |
| GET | `/projects/{id}/download/chords` | Download the plain-text chord chart |
| PUT | `/projects/{id}/notes` | Save an edited note list (rewrites JSON + MIDI; chords are preserved) |
| POST | `/projects/{id}/notes/reset` | Restore the original transcription |
| DELETE | `/projects/{id}` | Delete a project and all its files |

Each note in the JSON output has: `pitch` (MIDI number), `pitch_name` (e.g. `"C4"`),
`start_time` (seconds), `duration` (seconds), and `confidence` (0–1, pYIN's voiced-pitch
probability for that note, averaged over its frames). Polyphonic notes may also carry
`velocity` (0–1), `group` (a shared chord id like `"chord_1"`), `reattack` (a repeated
melody note the detector split at a genuine re-strike) and `source` (which detector
produced it: `"basic_pitch"`, `"cqt"`, `"pyin"` or `"piano_expert"` (v0.9.6, Piano only,
when installed); support notes added for Piano/Guitar carry `"accompaniment"`).

The top-level `/projects/{id}/notes` response also carries v0.9.5's routing status,
always present: `engine_used` (`"basic_pitch"` | `"cqt"` | `"pyin"` | `"piano_expert"`),
`routing_mode` (`"melody_only"` | `"multiple_notes"` | `"double_stops"`),
`fallback_reason` (a string when a Multiple-notes request degraded to a different
engine, else `null`), `warnings` (a list of strings — engine messages plus any
instrument-specific caution), and `difficulty` (a rough density read, one of `"Simple
melody"`, `"Some overlapping notes"`, `"Dense piano/audio — may need editing"`, `"No
notes detected"`).

For Solo Arrangement projects (v1.0, stems upgraded in v0.9.6, density/range fitting in
v0.9.8, honest separation status in v0.9.7.1), it additionally carries: `arrangement_source`
(`"vocal_stem"` | `"bass_stem"` | `"accompaniment"` | `"full_mix"`), `separation_engine`
(`"demucs"` or `null`, kept for back-compat), `separation_status` (`"demucs"` | `"unavailable"`
| `"failed"`, v0.9.7.1 — the 3-state read the "Source separation" status line uses),
`arrangement_focus` (`"main_melody"` | `"melody_support"` — `"piano_style"` was dropped in
v0.9.8), `arrangement_density` (`"simple"` | `"balanced"` | `"detailed"` — renamed from
`arrangement_difficulty`'s `"easy"`/`"medium"` in v0.9.8), and `range_fitting` (`"none"` |
`"octave_shifted"` | `"simplified"`, v0.9.8) — `null`/absent for Direct transcription
projects. Direct transcription's `warnings` may additionally include a dense-full-mix
suggestion (v0.9.7.1, see **Solo Arrangement** above).

### Engine Lab endpoints (v0.9.4, separate from the main pipeline)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/engine-lab/engines` | List engines with availability (`{"available": bool, "unavailable_reason": string\|null}`) |
| GET | `/engine-lab/fixtures` | List the six built-in synthetic test clips |
| GET | `/engine-lab/fixtures/{key}/audio` | Stream a fixture's generated audio |
| GET | `/engine-lab/sources` | List projects with audio + fixtures, for the source picker |
| POST | `/engine-lab/audio` | Upload audio directly into the lab (multipart field `file`) — returns `{"audio_id"}` |
| POST | `/engine-lab/runs` | Run one engine — `{"engine": "pyin"\|"basic_pitch"\|"cqt"\|"piano_expert"\|"demucs_vocals"\|"omnizart"\|"mt3", "source": {"kind": "project"\|"fixture"\|"upload", ...}}` (unavailable engines return 400 "Engine unavailable: {reason}") |
| GET | `/engine-lab/runs` / `/engine-lab/runs/{id}` | List recent runs / get one run's full result |
| GET | `/engine-lab/runs/{id}/download/midi` \| `/download/json` | Download a run's output |
| POST | `/engine-lab/runs/{id}/apply/{project_id}` | v0.9.5: make this run's notes the project's active transcription. 400 if the run's source wasn't that exact project's own audio, or if the run failed |
