#!/usr/bin/env bash
# Installs the CodeMonkeys terminal CLI from a running CodeMonkeys server.
#
#   curl -fsSL https://codemonkeys.fly.dev/static/cli-dist/install.sh | bash
#
# Override the source server with CM_SERVER, e.g. for a self-hosted instance:
#   CM_SERVER=https://my-instance.example.com bash install.sh
set -euo pipefail

CM_SERVER="${CM_SERVER:-https://codemonkeys.fly.dev}"
WHEEL_URL="${CM_SERVER%/}/static/cli-dist/codemonkeys_cli-0.1.0-py3-none-any.whl"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found on PATH." >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "Fetching CLI wheel from $WHEEL_URL ..."
curl -fsSL "$WHEEL_URL" -o "$tmp/codemonkeys_cli.whl"

echo "Installing with pip (--user) ..."
python3 -m pip install --user --upgrade "$tmp/codemonkeys_cli.whl"

echo
echo "Installed. Run:"
echo "  codemonkeys --server $CM_SERVER"
echo "(first run prompts for username + MFA code, then caches the token in ~/.codemonkeys/cli.json)"
echo
echo "If 'codemonkeys' isn't found, make sure your Python user-scripts dir is on PATH"
echo "(python3 -m site --user-base, then add its bin/Scripts subfolder)."
