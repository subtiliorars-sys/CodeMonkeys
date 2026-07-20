#!/usr/bin/env bash
# Build a deployable Linux desktop app for CodeMonkeys (PyInstaller onedir +
# AppImage). Mirrors scripts/build-windows.ps1. Requires Python 3.12+, pip,
# and a WebKitGTK backend for pywebview (see requirements-desktop.txt).
#
# Usage:
#   scripts/build-linux.sh [--skip-install] [--no-appimage]
#
# Debian/Ubuntu build-machine deps for pywebview's GTK backend:
#   sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
#     gir1.2-webkit2-4.1 libcairo2-dev
set -euo pipefail

SKIP_INSTALL=0
NO_APPIMAGE=0
for arg in "$@"; do
  case "$arg" in
    --skip-install) SKIP_INSTALL=1 ;;
    --no-appimage) NO_APPIMAGE=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> CodeMonkeys Linux build"
echo "    root: $ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

if [ "$SKIP_INSTALL" -eq 0 ]; then
  echo "==> Installing desktop requirements"
  "$PYTHON" -m pip install -r requirements-desktop.txt
fi

# static/forge/tailwind.css is gitignored (Docker/CI compile it via npx); the
# packaged binary ships static/ as-is via desktop/codemonkeys.spec, so without
# this the shipped app would render completely unstyled. Requires Node on the
# *build* machine only — end users never need it.
echo "==> Building vendored Tailwind CSS"
if ! command -v npx >/dev/null 2>&1; then
  echo "npx not found - install Node.js to build the vendored CSS before packaging" >&2
  exit 1
fi
npx --yes tailwindcss@3.4.17 -i static/forge/tailwind.input.css -o static/forge/tailwind.css --minify

DIST="$ROOT/dist/CodeMonkeys"
BUILD="$ROOT/build/codemonkeys-linux"
rm -rf "$DIST" "$BUILD"

SPEC="$ROOT/desktop/codemonkeys.spec"
echo "==> PyInstaller ($SPEC)"
"$PYTHON" -m PyInstaller --noconfirm --clean --distpath "$ROOT/dist" --workpath "$BUILD" "$SPEC"

BIN="$DIST/CodeMonkeys"
if [ ! -x "$BIN" ]; then
  echo "Build failed - missing $BIN" >&2
  exit 1
fi

README="$DIST/README.txt"
cat > "$README" <<EOF
CodeMonkeys - Linux desktop
============================

Run:  ./CodeMonkeys

Data and workspace:  \$XDG_CONFIG_HOME/codemonkeys/data (default ~/.config/codemonkeys/data)
Loopback server:   http://127.0.0.1:<port>/  (port chosen at launch)

First run: register the Owner account (PIN + TOTP), then add your API keys
under Settings -> Models and keys (bring-your-own-key). Owner can later invite
users and (optionally) grant Vertex/GCP credits.

Requires a WebKitGTK runtime for the native window (GTK3 + webkit2gtk on the
*end-user* machine too, not just the build machine):
  Debian/Ubuntu: sudo apt-get install gir1.2-webkit2-4.1
If WebKitGTK is unavailable, the server still starts — open the printed
http://127.0.0.1:<port>/ URL in a browser instead.

Dev / headless smoke:
  ./CodeMonkeys --no-window
  or:  python -m desktop --no-window
EOF

echo ""
echo "OK - packaged app:"
echo "  $BIN"
echo "Tarball for distribution:"
echo "  tar -C '$ROOT/dist' -czf '$ROOT/dist/CodeMonkeys-linux.tar.gz' CodeMonkeys"

if [ "$NO_APPIMAGE" -eq 1 ]; then
  exit 0
fi

echo ""
echo "==> Building AppImage"
APPIMAGETOOL="$ROOT/build/appimagetool.AppImage"
if [ ! -x "$APPIMAGETOOL" ]; then
  if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
  else
    echo "==> Downloading appimagetool"
    mkdir -p "$ROOT/build"
    curl -fsSL -o "$APPIMAGETOOL" \
      https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$APPIMAGETOOL"
  fi
fi

APPDIR="$ROOT/build/CodeMonkeys.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST/." "$APPDIR/usr/bin/"
cp "$ROOT/desktop/codemonkeys.desktop" "$APPDIR/CodeMonkeys.desktop"
cp "$ROOT/desktop/icon-256.png" "$APPDIR/codemonkeys.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/CodeMonkeys" "$@"
EOF
chmod +x "$APPDIR/AppRun"

INSTALLERS="$ROOT/dist/installers"
mkdir -p "$INSTALLERS"
VERSION="$(cat "$ROOT/desktop/VERSION" 2>/dev/null || echo "0.0.0")"

ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$INSTALLERS/CodeMonkeys-Desktop-${VERSION}-x86_64.AppImage"

echo ""
echo "OK - AppImage:"
echo "  $INSTALLERS/CodeMonkeys-Desktop-${VERSION}-x86_64.AppImage"
