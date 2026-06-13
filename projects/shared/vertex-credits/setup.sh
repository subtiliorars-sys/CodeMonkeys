#!/usr/bin/env bash
# One-time Vertex setup — Linux / macOS / WSL
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/codemonkeys"
CURSOR_RULES="${HOME}/.cursor/rules"

echo "== Vertex GCP credits setup (codemonkeys-498819) =="
mkdir -p "$CFG"
if [[ ! -f "$CFG/vertex.env" ]]; then
  cp "$ROOT/vertex.env.example" "$CFG/vertex.env"
  echo "Wrote $CFG/vertex.env"
else
  echo "Keeping existing $CFG/vertex.env"
fi

mkdir -p "$CURSOR_RULES"
cp "$ROOT/cursor-rule-vertex-gcp-credits.mdc" "$CURSOR_RULES/vertex-gcp-credits.mdc"
echo "Installed Cursor rule → $CURSOR_RULES/vertex-gcp-credits.mdc"

if [[ -f "$CFG/vertex-sa.json" ]]; then
  echo "Service account already at $CFG/vertex-sa.json"
elif [[ -n "${VERTEX_SA_SRC:-}" && -f "$VERTEX_SA_SRC" ]]; then
  cp "$VERTEX_SA_SRC" "$CFG/vertex-sa.json"
  chmod 600 "$CFG/vertex-sa.json"
  echo "GOOGLE_APPLICATION_CREDENTIALS=$CFG/vertex-sa.json" >> "$CFG/vertex.env"
  echo "Installed SA from VERTEX_SA_SRC"
elif command -v gcloud >/dev/null 2>&1; then
  echo "Running: gcloud auth application-default login (browser)"
  gcloud auth application-default login --project=codemonkeys-498819
else
  echo ""
  echo "No gcloud CLI. Either:"
  echo "  1) Install Google Cloud SDK, re-run this script, OR"
  echo "  2) Download SA JSON from GCP Console → save as:"
  echo "     $CFG/vertex-sa.json"
  echo "     then add: GOOGLE_APPLICATION_CREDENTIALS=$CFG/vertex-sa.json"
fi

echo ""
echo "Verify:"
PY="python3"
for candidate in \
  "$HOME/projects/claude/CodeMonkeys/.venv/bin/python" \
  "$(dirname "$0")/../../claude/CodeMonkeys/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then PY="$candidate"; break; fi
done
"$PY" -m pip install -q google-auth 2>/dev/null || true
"$PY" "$ROOT/verify_vertex.py" || {
  echo "Install deps: pip install google-auth"
  exit 1
}
echo ""
echo "Done. Same repos on Windows → run setup.ps1 there once."
