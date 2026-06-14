#!/usr/bin/env bash
# Copy fleet-automation into MeniscusMaximus + CodeMonkeys (no node_modules/dist).
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
MM="$(cd "$SRC/../MeniscusMaximus" && pwd)"
CM="$(cd "$SRC/../CodeMonkeys" && pwd)"

for DEST in "$MM/tools/fleet-automation" "$CM/tools/fleet-automation"; do
  mkdir -p "$(dirname "$DEST")"
  rsync -a --delete \
    --exclude node_modules \
    --exclude dist \
    --exclude user-data \
    --exclude .env \
    "$SRC/" "$DEST/"
  echo "Synced → $DEST"
done
