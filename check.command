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

# Basic Pitch's transcription engine (TensorFlow) only supports Python 3.9-3.11 —
# newer Macs often ship/install a newer default python3, so check the version too.
check_python() {
  local candidate ver major minor found_compatible="" found_any=""
  for candidate in python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      ver="$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null)"
      [ -z "$ver" ] && continue
      major="${ver%%.*}"; minor="${ver#*.}"
      [ -z "$found_any" ] && found_any="$candidate ($ver)"
      if [ "$major" = "3" ] && [ "$minor" -ge 9 ] 2>/dev/null && [ "$minor" -le 11 ] 2>/dev/null; then
        found_compatible="$candidate ($ver)"
        break
      fi
    fi
  done

  if [ -n "$found_compatible" ]; then
    echo -e "${GREEN}[OK]${NC} Python found — $found_compatible"
  elif [ -n "$found_any" ]; then
    echo -e "${RED}[MISSING]${NC} Only $found_any was found, but this app needs Python 3.9–3.11 (the TensorFlow library it depends on doesn't support newer Python versions yet)."
    echo "         Install it with: brew install python@3.11"
    all_ok=false
  else
    echo -e "${RED}[MISSING]${NC} Python not found."
    echo "         Install it with: brew install python@3.11   (or download from https://www.python.org/downloads/)"
    all_ok=false
  fi
}

echo "BandChart AI — checking your computer"
echo "======================================"
echo

check_python
check "Node.js" node "brew install node   (or download from https://nodejs.org/)"
check "npm" npm "npm is installed together with Node.js — reinstall Node.js if this is missing"
check "ffmpeg" ffmpeg "brew install ffmpeg   (only needed for mp3/m4a files — wav/flac/ogg work without it)"

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
