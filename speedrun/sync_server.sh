#!/usr/bin/env bash
# Speedrun sync server: Anki's built-in self-hosted sync server (rslib/sync),
# serving one account for desktop <-> phone sync.
#
#     bash speedrun/sync_server.sh          # user: speedrun  pass: speedrun
#
# Configure the clients:
#   Desktop:   Tools -> Preferences -> Syncing -> Self-hosted sync server:
#                http://127.0.0.1:8080/
#   AnkiDroid: Settings -> Sync -> Custom sync server:
#                http://10.0.2.2:8080/   (emulator; use your Mac's LAN IP on a
#                real phone, e.g. http://192.168.1.20:8080/)
#   Then sign in on both with the user/pass below and press Sync.
#
# Data lives in speedrun/out/syncserver (gitignored).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$REPO/out/rust/debug/anki-sync-server"

if [ ! -f "$BIN" ]; then
  echo "Building sync server..."
  (cd "$REPO" && CARGO_TARGET_DIR="$REPO/out/rust" cargo build -p anki-sync-server)
fi

export SYNC_USER1="${SYNC_USER1:-speedrun:speedrun}"
export SYNC_BASE="${SYNC_BASE:-$REPO/speedrun/out/syncserver}"
export SYNC_HOST="${SYNC_HOST:-0.0.0.0}"
export SYNC_PORT="${SYNC_PORT:-8080}"

echo "Sync server on http://localhost:$SYNC_PORT/  (user: ${SYNC_USER1%%:*})"
echo "Desktop URL:   http://127.0.0.1:$SYNC_PORT/"
echo "Emulator URL:  http://10.0.2.2:$SYNC_PORT/"
exec "$BIN"
