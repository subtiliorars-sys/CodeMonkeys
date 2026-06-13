#!/usr/bin/env bash
# Start all fleet UI audit servers (ports 8091–8100). Run from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

start() {
  local name="$1" dir="$2" cmd="$3"
  echo "▶ $name"
  (cd "$dir" && eval "$cmd") &
  echo $! > "/tmp/fleet-audit-${name}.pid"
}

start codemonkeys "$ROOT/projects/claude/CodeMonkeys" \
  'DATA_DIR=./data/audit USERS_FILE=./data/audit/users.json python3 -m uvicorn server:app --host 127.0.0.1 --port 8091'

start meniscus "$ROOT/projects/claude/MeniscusMaximus" \
  'USERS_FILE=./dev_users.json DEV_USER=ui-audit python3 -m uvicorn server:app --host 127.0.0.1 --port 8092'

start pixelsports "$ROOT/projects/claude/PixelSports" \
  'python3 -m http.server 8093 --bind 127.0.0.1'

start drivingmenuts "$ROOT/projects/claude/DrivingMeNuts" \
  'npm run dev -- --host 127.0.0.1 --port 8094'

start tradegame-site "$ROOT/projects/claude/TradeGame/site" \
  'python3 -m http.server 8095 --bind 127.0.0.1'

start tradegame-sim "$ROOT/projects/claude/TradeGame/sim/dist-ui" \
  'python3 -m http.server 8096 --bind 127.0.0.1'

start cairn "$ROOT/projects/shared/Cairn/site" \
  'python3 -m http.server 8097 --bind 127.0.0.1'

start ilerioluwa "$ROOT/projects/shared/Ilerioluwa-GoalKeeper-Training-Institute---Preview" \
  'python3 -m http.server 8098 --bind 127.0.0.1'

start omnitender "$ROOT/projects/gemini/omnitender-web" \
  'python3 -m http.server 8099 --bind 127.0.0.1'

start omni-herald "$ROOT/projects/gemini/omni-herald" \
  'OH_DATA_DIR=./data/audit SESSION_SECRET=ui-audit-session-secret-32chars-min OWNER_USERNAME=ui-audit OWNER_BOOTSTRAP_PASSWORD=audit-bootstrap-12 PORT=8100 HOST=127.0.0.1 python3 server.py'

echo "Waiting for servers…"
sleep 4
for p in 8091 8092 8093 8094 8095 8096 8097 8098 8099 8100; do
  curl -fsS -o /dev/null -m 2 "http://127.0.0.1:$p/" 2>/dev/null && echo "  ✓ $p" || echo "  ✗ $p"
done
echo "Done. Stop with: kill \$(cat /tmp/fleet-audit-*.pid)"
