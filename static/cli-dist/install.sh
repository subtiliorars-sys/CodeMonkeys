#!/usr/bin/env bash
# Installs the CodeMonkeys terminal CLI from a running CodeMonkeys server.
#
#   curl -fsSL https://codemonkeys.fly.dev/static/cli-dist/install.sh | bash
#
# Override the source server with CM_SERVER, e.g. for a self-hosted instance:
#   CM_SERVER=https://my-instance.example.com bash install.sh
set -euo pipefail

CM_SERVER="${CM_SERVER:-https://codemonkeys.fly.dev}"
WHEEL_URL="${CM_SERVER%/}/static/cli-dist/codemonkeys_cli-0.1.2-py3-none-any.whl"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# Keep the real wheel filename (version + tags) - 'uv tool install' rejects a
# generic renamed filename ("Must have a version"), unlike pip which is lenient.
wheel_name="$(basename "$WHEEL_URL")"
wheel_path="$tmp/$wheel_name"
echo "Fetching CLI wheel from $WHEEL_URL ..."
curl -fsSL "$WHEEL_URL" -o "$wheel_path"

# Prefer 'uv tool install' when available: an isolated install that never
# touches the system/managed Python, so it works even when pip refuses with
# "externally-managed-environment" (e.g. a uv-managed or distro-managed
# Python - PEP 668). Falls back to pip --user otherwise.
installed=""
if command -v uv >/dev/null 2>&1; then
  echo "Installing with 'uv tool install' (isolated) ..."
  if uv tool install "$wheel_path" --force; then
    installed="uv"
  else
    echo "uv install failed; falling back to pip ..."
  fi
fi

if [ -z "$installed" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Neither 'uv' nor 'python3' was found on PATH. Install uv (https://astral.sh/uv) - recommended, no system-Python conflicts - or install python3." >&2
    exit 1
  fi
  echo "Installing with pip (--user) ..."
  if ! python3 -m pip install --user --upgrade "$wheel_path"; then
    echo "pip install failed. If the error says 'externally-managed-environment', this Python is managed by your OS/uv and blocks --user installs by design (PEP 668) - install uv (https://astral.sh/uv) and re-run this script instead." >&2
    exit 1
  fi
  installed="pip"
fi

echo
echo "Installed. Run:"
echo "  monkey --server $CM_SERVER"
echo "('cm' and 'codemonkeys' also work, same command)"
echo "(first run prompts for username + MFA code, then caches the token in ~/.codemonkeys/cli.json)"
echo
if [ "$installed" = "uv" ]; then
  echo "If 'monkey' isn't found, run 'uv tool update-shell' then restart your shell."
else
  echo "If 'codemonkeys' isn't found, make sure your Python user-scripts dir is on PATH"
  echo "(python3 -m site --user-base, then add its bin/Scripts subfolder)."
fi
