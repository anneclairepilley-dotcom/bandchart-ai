# BandChart AI

AI music arranging and rehearsal app that turns songs into editable lead sheets, solo sheets, band charts and custom arrangements.

## v0.9.3 — Better note detection and real polyphony

This is the smallest possible working prototype: a local web app where you upload an audio
file and the backend runs **real audio-to-pitch transcription**. Everything runs on your own
computer — no accounts, no payments, no cloud services, no data leaves your machine.

Two detection engines are on board (v0.9.3):

- **Melody (default)**: [librosa](https://librosa.org/)'s pYIN — a genuine, well-established
  pitch-tracking algorithm that follows one melodic line at a time (monophonic: a single
  voice, vocal line, or solo instrument, not full chords). It's pure Python/numpy — no
  TensorFlow — so it installs reliably everywhere, including GitHub Codespaces. v0.9.3
  makes it noticeably better: repeated notes of the same pitch are no longer glued into
  one long note (a loudness re-attack check finds the re-strikes), and clearly
  low-confidence detections are dropped (with a message, and never to the point of
  emptying a quiet recording).
- **Simple polyphonic / chords (experimental)**: Spotify's open-source
  [Basic Pitch](https://github.com/spotify/basic-pitch) model (ICASSP 2022) — a real
  learned transcription model that hears several notes at once. It runs on CPU through its
  bundled ONNX network (no TensorFlow, no GPU, no accounts, nothing paid — the model ships
  inside the pip package). Detected notes carry a velocity (loudness) and simultaneous
  notes share a chord group id like `"chord_1"` in the JSON. If the model isn't installed
  or fails, the app quietly falls back to the built-in v0.9.2 CQT detector, and if THAT
  finds nothing usable it falls back to melody-only — always with an honest message, never
  a crash.

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
- Pick a solo instrument (concert pitch, piano, flute, violin, voice/vocals, alto sax,
  tenor sax, trumpet, clarinet, guitar, bass guitar, ukulele) — the note table shows both
  the detected concert pitch and the written pitch, transposed for E♭/B♭ instruments
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
- **Simple polyphonic / chords detection** (v0.9.2, upgraded in v0.9.3): the "Note
  detection" advanced setting — Melody only (default) or **Simple polyphonic / chords**
  (experimental; picked automatically for Piano + Direct transcription). v0.9.3 replaces
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
  note saying so). This is NOT full band or complex-piano transcription
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
- **Delete projects**: a Delete button beside each project on the dashboard removes the
  project with its uploaded audio and generated files, after a confirmation prompt

**Explicitly out of scope so far:** accounts, payments, full band charts, rehearsal packs,
complex editing, stem separation, drums, automatic chord detection from recordings (the
parked chord tools are manual markers plus rough melody-based suggestions; Ultimate
Guitar-style chord sheets are a much later feature, probably v5.0), accurate transcription
of complex piano pieces or full-band mixes (polyphonic detection is experimental and for
clear, simple material — the best results still come from clear recordings of one
instrument), strummed guitar chord shapes/diagrams, full guitar/bass extraction from mixed
songs (tab stays melody-first).

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
pip install --no-deps basic-pitch
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
pip install --no-deps basic-pitch   # optional: the polyphonic-mode model (see note above)
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
> `pip install -r requirements.txt` and `pip install --no-deps basic-pitch` in the backend
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
| POST | `/projects/{id}/settings` | Save the setup choices — `{"instrument", "mode", "time_signature", "key_signature", "rhythm_detail"}` |
| POST | `/projects/{id}/transcribe` | Run transcription on the uploaded audio |
| GET | `/projects/{id}/notes` | Get the detected-notes JSON |
| GET | `/projects/{id}/audio` | Stream the original uploaded audio |
| GET | `/projects/{id}/download/midi` | Download the generated MIDI file |
| GET | `/projects/{id}/download/json` | Download the generated notes JSON file |
| GET | `/projects/{id}/download/musicxml?instrument=<key>&style=<clean\|raw>` | Download MusicXML for a solo instrument — instrument keys: `concert`, `piano`, `flute`, `violin`, `alto_sax`, `tenor_sax`, `trumpet`, `clarinet`, `guitar`, `bass`, `ukulele`; style defaults to `clean` (staff notation for all keys, including the fretted ones) |
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
probability for that note, averaged over its frames).
