#!/bin/bash
# BandChart AI — starts the app and opens it in your browser.
# Double-click this file in Finder, or run it from Terminal with: ./start.command
#
# Leave this window open while you use the app.
# Close the window (or press Ctrl+C) to stop the app.

cd "$(dirname "$0")" || exit 1

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail() {
  echo
  echo -e "${RED}$1${NC}"
  echo
  read -n 1 -s -r -p "Press any key to close this window..."
  echo
  exit 1
}

[ -d "backend/.venv" ]        || fail "The backend isn't set up yet. Double-click setup.command first."
[ -d "frontend/node_modules" ] || fail "The frontend isn't set up yet. Double-click setup.command first."

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  echo "Stopping BandChart AI..."
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  >/dev/null 2>&1
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" >/dev/null 2>&1
  wait >/dev/null 2>&1
  echo "Stopped."
}
trap cleanup EXIT
trap 'exit 0' INT TERM

echo "BandChart AI — Starting"
echo "========================"
echo

echo "Starting backend on http://localhost:8000 ..."
(cd backend && ./.venv/bin/uvicorn app.main:app --port 8000) &
BACKEND_PID=$!

backend_up=false
for _ in $(seq 1 60); do
  if curl -s -o /dev/null "http://localhost:8000/api/projects"; then
    backend_up=true
    break
  fi
  sleep 1
done
$backend_up || fail "The backend didn't start. Scroll up to see the error, or try double-clicking setup.command again."
echo -e "${GREEN}Backend is running.${NC}"
echo

echo "Starting frontend on http://localhost:3000 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

frontend_up=false
for _ in $(seq 1 60); do
  if curl -s -o /dev/null "http://localhost:3000"; then
    frontend_up=true
    break
  fi
  sleep 1
done
$frontend_up || fail "The frontend didn't start. Scroll up to see the error, or try double-clicking setup.command again."
echo -e "${GREEN}Frontend is running.${NC}"
echo

echo "Opening BandChart AI in your browser..."
open "http://localhost:3000" >/dev/null 2>&1

echo
echo "BandChart AI is running at http://localhost:3000"
echo "Keep this window open while you use the app."
echo "Press Ctrl+C, or close this window, to stop it."
echo

wait
