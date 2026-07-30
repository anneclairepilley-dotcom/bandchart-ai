#!/bin/bash
# BandChart AI — one-time setup. Installs everything the app needs.
# Double-click this file in Finder, or run it from Terminal with: ./setup.command
#
# Safe to run more than once (it won't reinstall things that are already there).

cd "$(dirname "$0")" || exit 1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail() {
  echo
  echo -e "${RED}Setup stopped:${NC} $1"
  echo
  read -n 1 -s -r -p "Press any key to close this window..."
  echo
  exit 1
}

echo "BandChart AI — Setup"
echo "====================="
echo

echo "Checking prerequisites..."

# Prefer Homebrew's Python 3.12 (Apple Silicon path first, then Intel
# Homebrew, then anything on PATH), falling back to the system python3.
PYTHON_BIN=""
for candidate in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3.12 python3; do
  if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
[ -n "$PYTHON_BIN" ] || fail "Python 3 is not installed. Double-click check.command to see how to install it."
PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null)"
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[1])' 2>/dev/null)"
echo "Using $PYTHON_BIN (Python $PY_VER)"
if [ -n "$PY_MINOR" ] && [ "$PY_MINOR" -lt 10 ] 2>/dev/null; then
  echo -e "${YELLOW}Warning:${NC} Python $PY_VER is getting old — tools like yt-dlp are dropping support"
  echo "         for versions below 3.10. For best results install a newer one with:"
  echo "         brew install python@3.12   — then run setup.command again."
fi

command -v node >/dev/null 2>&1 || fail "Node.js is not installed. Double-click check.command to see how to install it."
command -v npm  >/dev/null 2>&1 || fail "npm is not installed. Double-click check.command to see how to install it."
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo -e "${YELLOW}Important:${NC} ffmpeg is not installed. YouTube import will NOT work without it,"
  echo "         and mp3/m4a uploads won't transcribe (wav/flac/ogg uploads still work)."
  echo "         Install it with: brew install ffmpeg   — then run setup.command again."
fi
echo -e "${GREEN}Prerequisites OK.${NC}"
echo

echo "Setting up the backend (installs librosa, yt-dlp and other Python packages — a minute or two on a first run)..."
cd backend || fail "Could not find the backend folder. Make sure this script is inside the bandchart-ai project folder."

# If the app environment was built with an old Python and a newer interpreter
# is available now, rebuild it — packages are simply reinstalled.
if [ -x ".venv/bin/python" ]; then
  VENV_MINOR="$(./.venv/bin/python -c 'import sys; print(sys.version_info[1])' 2>/dev/null)"
  if [ -n "$VENV_MINOR" ] && [ "$VENV_MINOR" -lt 10 ] 2>/dev/null && [ -n "$PY_MINOR" ] && [ "$PY_MINOR" -ge 10 ] 2>/dev/null; then
    echo -e "${YELLOW}Rebuilding the app environment:${NC} it was using old Python 3.$VENV_MINOR — recreating it with Python $PY_VER…"
    rm -rf .venv
  fi
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv || fail "Could not create a Python virtual environment."
fi
./.venv/bin/pip install --upgrade pip >/dev/null 2>&1
if ! ./.venv/bin/pip install -r requirements.txt; then
  # The usual culprit on Macs is verovio (the optional PDF engraving engine),
  # which sometimes has to compile from source and fails without Xcode tools.
  # Everything except PDF export works without it, so retry without verovio
  # rather than failing the whole setup.
  echo
  echo -e "${YELLOW}The full install failed — retrying without the optional PDF engine (verovio)…${NC}"
  CORE_REQS="$(mktemp)"
  grep -viE '^[[:space:]]*verovio' requirements.txt > "$CORE_REQS"
  ./.venv/bin/pip install -r "$CORE_REQS" || { rm -f "$CORE_REQS"; fail "Installing backend dependencies failed. Check your internet connection and try running setup.command again."; }
  rm -f "$CORE_REQS"
  echo
  echo -e "${YELLOW}Note:${NC} the optional PDF engine (verovio) couldn't be installed on this Mac."
  echo "      Everything else works — transcription, YouTube import, sheet music in the"
  echo "      browser, and MIDI/JSON/MusicXML downloads. For printable sheet music,"
  echo "      download the MusicXML and open it in the free MuseScore app."
  echo "      To enable PDFs here later: install Xcode Command Line Tools with"
  echo "      'xcode-select --install', then run setup.command again."
fi
if ./.venv/bin/python -c "import yt_dlp" >/dev/null 2>&1; then
  echo -e "${GREEN}yt-dlp (YouTube import) installed.${NC}"
else
  echo -e "${YELLOW}Warning:${NC} yt-dlp didn't install — YouTube import won't work until you run setup.command again."
fi

# v0.9.3: the Basic Pitch note-detection model. Installed WITHOUT its declared
# dependencies on purpose — they pin an old TensorFlow that doesn't install on
# Python 3.12, and the bundled ONNX model doesn't need TensorFlow at all
# (onnxruntime from requirements.txt runs it). If this step fails the app
# still works: polyphonic mode falls back to the built-in simple detector.
echo "Installing the Basic Pitch note-detection model (used by polyphonic mode)…"
if ./.venv/bin/pip install --no-deps basic-pitch >/dev/null 2>&1 \
   && ./.venv/bin/python -c "import basic_pitch.inference" >/dev/null 2>&1; then
  echo -e "${GREEN}Basic Pitch model installed.${NC}"
else
  echo -e "${YELLOW}Note:${NC} the Basic Pitch model couldn't be installed on this Mac."
  echo "      Everything still works — polyphonic (chords) mode just uses the built-in"
  echo "      simpler detector instead. Run setup.command again later to retry."
fi
cd ..
echo -e "${GREEN}Backend ready.${NC}"
echo

echo "Setting up the frontend..."
cd frontend || fail "Could not find the frontend folder. Make sure this script is inside the bandchart-ai project folder."
npm install || fail "Installing frontend dependencies failed. Check your internet connection and try running setup.command again."
if [ ! -f ".env.local" ] && [ -f ".env.local.example" ]; then
  cp .env.local.example .env.local
fi
cd ..
echo -e "${GREEN}Frontend ready.${NC}"
echo

echo -e "${GREEN}Setup complete!${NC} Double-click start.command to launch BandChart AI."
echo
read -n 1 -s -r -p "Press any key to close this window..."
echo
