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

command -v python3 >/dev/null 2>&1 || fail "Python 3 is not installed. Double-click check.command to see how to install it."
command -v node >/dev/null 2>&1 || fail "Node.js is not installed. Double-click check.command to see how to install it."
command -v npm  >/dev/null 2>&1 || fail "npm is not installed. Double-click check.command to see how to install it."
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo -e "${YELLOW}Warning:${NC} ffmpeg is not installed. wav/flac/ogg files will still work, but mp3/m4a files will fail to transcribe."
  echo "         You can install it later with: brew install ffmpeg"
fi
echo -e "${GREEN}Prerequisites OK.${NC}"
echo

echo "Setting up the backend (installs librosa and other Python packages — a minute or two on a first run)..."
cd backend || fail "Could not find the backend folder. Make sure this script is inside the bandchart-ai project folder."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv || fail "Could not create a Python virtual environment."
fi
./.venv/bin/pip install --upgrade pip >/dev/null 2>&1
./.venv/bin/pip install -r requirements.txt || fail "Installing backend dependencies failed. Check your internet connection and try running setup.command again."
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
