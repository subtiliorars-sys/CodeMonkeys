#!/usr/bin/env bash
# Bundle JimmyTheHat marketing + handoff docs and sync to Google Drive.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HANDOFF="$ROOT/JimmyTheHat-Handoff"
DRIVE_SCRIPTS="$ROOT/scripts/drive"

# shellcheck source=drive/drive-lib.sh
source "$DRIVE_SCRIPTS/drive-lib.sh"
drive_load_defaults

PS="$ROOT/PixelSports"
YM="$ROOT/yes-man"
TG="$ROOT/TradeGame"

mkdir -p "$HANDOFF"/{itch-io,builds,store-assets,steam,fleet,tradegame}
mkdir -p "$HANDOFF/store-assets"/{pixelsports-volleyball,pixelsports-hub,yes-man,no,tradegame,driving-me-nuts}

cp -f "$PS/docs/ITCH_UPLOAD_NOW.md" "$HANDOFF/itch-io/CHECKLIST.md"
cp -f "$PS/docs/ITCH_PASTE_READY.md" "$HANDOFF/itch-io/PixelSports-hub-paste.md"
cp -f "$YM/docs/ITCH_PASTE_READY.md" "$HANDOFF/itch-io/Yes-Man-paste.md"
cp -f "$YM/docs/ITCH_PASTE_READY_NO.md" "$HANDOFF/itch-io/No-paste.md"

cp -f "$PS/docs/STEAM_PASTE_READY.md" "$HANDOFF/steam/PixelSports-steam-paste.md"
cp -f "$PS/docs/STORE_LAUNCH.md" "$HANDOFF/steam/STORE_LAUNCH.md"

cp -f "$PS/docs/FLEET_BROWSER_INDEX.md" "$HANDOFF/fleet/FLEET_BROWSER_INDEX.md"

cp -f "$TG/docs/assets/ITCH_IO_PAGE.md" "$HANDOFF/tradegame/ITCH_IO_PAGE.md" 2>/dev/null || true
cp -f "$TG/docs/LAUNCH_DISCORD_POST.md" "$HANDOFF/tradegame/LAUNCH_DISCORD_POST.md" 2>/dev/null || true
cp -f "$TG/docs/assets/OWNER_QUICKSTART.md" "$HANDOFF/tradegame/OWNER_QUICKSTART.md" 2>/dev/null || true
cp -f "$TG/docs/PAYMENT_CONFIG.md" "$HANDOFF/tradegame/PAYMENT_CONFIG.md" 2>/dev/null || true

cp -f "$PS/release/pixelsports-browser-v0.1.0.zip" "$HANDOFF/builds/" 2>/dev/null || true
cp -f "$PS/release/broadside-browser-v0.1.0.zip" "$HANDOFF/builds/" 2>/dev/null || true
cp -f "$PS/release/sortie-browser-v0.1.0.zip" "$HANDOFF/builds/" 2>/dev/null || true
cp -f "$YM/release/yes-man-browser-v0.5.0.zip" "$HANDOFF/builds/" 2>/dev/null || true
cp -f "$YM/release/no-sentence-browser-v0.5.0.zip" "$HANDOFF/builds/" 2>/dev/null || true
cp -f "$TG/release/tradegame-v0.1.0-web.zip" "$HANDOFF/builds/" 2>/dev/null || true
cp -f "$PS/release/store-assets/cover-630x500.png" "$HANDOFF/store-assets/pixelsports-volleyball/" 2>/dev/null || true
cp -f "$PS/release/store-assets/screenshot-0"*.png "$HANDOFF/store-assets/pixelsports-volleyball/" 2>/dev/null || true
cp -f "$PS/release/store-assets/steam-header-460x215.png" "$HANDOFF/store-assets/pixelsports-volleyball/" 2>/dev/null || true
cp -f "$PS/release/store-assets/cover-hub-630x500.png" "$HANDOFF/store-assets/pixelsports-hub/" 2>/dev/null || true
cp -f "$PS/release/store-assets/screenshot-01-hub.png" "$HANDOFF/store-assets/pixelsports-hub/" 2>/dev/null || true
cp -f "$PS/release/store-assets/steam-header-hub-460x215.png" "$HANDOFF/store-assets/pixelsports-hub/" 2>/dev/null || true
cp -rf "$YM/release/store-assets/." "$HANDOFF/store-assets/yes-man/" 2>/dev/null || true
cp -rf "$YM/release/store-assets-no/." "$HANDOFF/store-assets/no/" 2>/dev/null || true
cp -rf "$TG/release/store-assets/." "$HANDOFF/store-assets/tradegame/" 2>/dev/null || true
DMN="$ROOT/DrivingMeNuts"
cp -rf "$DMN/release/store-assets/." "$HANDOFF/store-assets/driving-me-nuts/" 2>/dev/null || true
cp -f "$DMN/docs/ITCH_PASTE_READY.md" "$HANDOFF/itch-io/Driving-Me-Nuts-paste.md" 2>/dev/null || true
cp -f "$ROOT/scripts/store-assets/STORE_BRAND.md" "$HANDOFF/store-assets/README.md" 2>/dev/null || true

if [[ -n "${GDRIVE_REMOTE:-}" ]]; then
  REMOTE="$GDRIVE_REMOTE"
else
  TARGET_REMOTE="${HANDOFF_REMOTE:-gdrive-personal}"
  if ! drive_remote_exists "$TARGET_REMOTE"; then
    echo "Remote '$TARGET_REMOTE' is not set up yet." >&2
    echo "" >&2
    echo "Your old 'gdrive' remote was OmniTender — handoff went to the wrong account." >&2
    echo "Add personal Drive:" >&2
    echo "  bash $DRIVE_SCRIPTS/drive-add.sh gdrive-personal \"Personal Google Drive\"" >&2
    echo "" >&2
    echo "Then re-run this script. Or one-shot to OmniTender:" >&2
    echo "  GDRIVE_REMOTE='gdrive-omnitender:JimmyTheHat — Handoff' $0" >&2
    exit 1
  fi
  REMOTE="$(drive_resolve_target jimmythehat-handoff 2>/dev/null || echo "${TARGET_REMOTE}:JimmyTheHat — Handoff")"
fi

echo "=== Local bundle ==="
find "$HANDOFF" -type f | sort
echo ""
echo "=== Syncing to $REMOTE ==="
echo "(only this folder on this account — not your whole Drive)"
rclone sync "$HANDOFF" "$REMOTE" --progress --exclude ".DS_Store"

echo ""
echo "Done. Open Google Drive → JimmyTheHat — Handoff → START_HERE.md"
rclone lsf "$REMOTE" 2>/dev/null | head -20
