#!/bin/bash
# BandChart AI — checks that your Mac has everything needed to run the app.
# Double-click this file in Finder, or run it from Terminal with: ./check.command

cd "$(dirname "$0")" || exit 1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

all_ok=true

check() {
  local label="$1" cmd="$2" hint="$3"
  if command -v "$cmd" >/dev/null 2>&1; then
    local version
    version="$("$cmd" --version 2>&1 | head -n1)"
    echo -e "${GREEN}[OK]${NC} $label found — $version"
  else
    echo -e "${RED}[MISSING]${NC} $label not found."
    echo "         Install it with: $hint"
    all_ok=false
  fi
}

# Pick the same Python interpreter setup.command will use: Homebrew's
# Python 3.12 when available (Apple Silicon, then Intel Homebrew, then PATH),
# otherwise the system python3.
pick_python() {
  local candidate
  for candidate in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3.12 python3; do
    if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

py_version() {
  "$1" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null
}

py_minor() {
  "$1" -c 'import sys; print(sys.version_info[1])' 2>/dev/null
}

echo "BandChart AI — checking your computer"
echo "======================================"
echo

PYTHON_BIN="$(pick_python)"
if [ -n "$PYTHON_BIN" ]; then
  PY_VER="$(py_version "$PYTHON_BIN")"
  PY_MINOR="$(py_minor "$PYTHON_BIN")"
  if [ -n "$PY_MINOR" ] && [ "$PY_MINOR" -ge 10 ] 2>/dev/null; then
    echo -e "${GREEN}[OK]${NC} Python found — $PYTHON_BIN (Python $PY_VER)"
  else
    echo -e "${YELLOW}[OLD]${NC} Python $PY_VER found at $PYTHON_BIN — it still works, but tools like"
    echo "        yt-dlp are dropping support for Python below 3.10."
    echo "        Install a newer one with: brew install python@3.12"
    echo "        Then run setup.command again — it rebuilds the app environment automatically."
  fi
else
  echo -e "${RED}[MISSING]${NC} Python not found."
  echo "         Install it with: brew install python@3.12   (or download from https://www.python.org/downloads/)"
  all_ok=false
fi

# If the app environment already exists on an old Python and a newer one is
# available, setup.command will rebuild it — say so here.
if [ -x "backend/.venv/bin/python" ] && [ -n "$PYTHON_BIN" ]; then
  VENV_MINOR="$(py_minor backend/.venv/bin/python)"
  if [ -n "$VENV_MINOR" ] && [ "$VENV_MINOR" -lt 10 ] 2>/dev/null && [ -n "$PY_MINOR" ] && [ "$PY_MINOR" -ge 10 ] 2>/dev/null; then
    echo -e "${YELLOW}[NOTE]${NC} The app environment was built with old Python 3.$VENV_MINOR."
    echo "        Run setup.command — it will rebuild it with Python $PY_VER automatically."
  fi
fi

check "Node.js" node "brew install node   (or download from https://nodejs.org/)"
check "npm" npm "npm is installed together with Node.js — reinstall Node.js if this is missing"
check "ffmpeg" ffmpeg "brew install ffmpeg   (needed for YouTube import and for mp3/m4a uploads)"

# yt-dlp (YouTube import) lives inside the app's own Python environment,
# which setup.command creates — so check there, not on the system.
if [ -x "backend/.venv/bin/python" ]; then
  if backend/.venv/bin/python -c "import yt_dlp" >/dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} yt-dlp (YouTube import) is installed in the app environment"
  else
    echo -e "${RED}[MISSING]${NC} yt-dlp is not in the app environment yet."
    echo "         Double-click setup.command to install it."
    all_ok=false
  fi
else
  echo -e "${YELLOW}[LATER]${NC} yt-dlp (YouTube import) — installed automatically when you run setup.command."
fi

echo
if $all_ok; then
  echo -e "${GREEN}Everything looks good!${NC} Next, double-click setup.command."
else
  echo -e "${YELLOW}Something is missing.${NC} Install the item(s) above, then run this check again."
  echo
  echo "Don't have Homebrew? Install it first by pasting this into Terminal:"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
fi

echo
read -n 1 -s -r -p "Press any key to close this window..."
echo
