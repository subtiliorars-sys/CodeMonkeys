#!/usr/bin/env bash
# Build vendored Tailwind CSS for local dev (Docker/CI run the same command).
set -euo pipefail
cd "$(dirname "$0")/.."
npx --yes tailwindcss@3.4.17 \
  -i static/forge/tailwind.input.css \
  -o static/forge/tailwind.css --minify
echo "Built static/forge/tailwind.css ($(wc -c < static/forge/tailwind.css) bytes)"
