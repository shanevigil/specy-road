#!/usr/bin/env bash
# e2e: PM Gantt drag-reorder fix — proves a stale-token POST resolves to
# 200 + on-disk reorder when the server is run with
# SPECY_ROAD_GUI_PM_AUTO_RETRY_AUTOFF=1 and the client follows the
# transparent-retry contract (capture stale fp -> POST -> 412
# retryable:true -> GET fresh fp -> POST -> 200).
#
# Reads the dogfood fixture, builds a writable git working tree + bare
# remote with integration_branch=master, advances the remote, and
# exercises both /api/outline/reorder (same parent) and
# /api/outline/move (cross parent — the M9.2-shaped scenario).

set -euo pipefail
EVD=${EVD:-/opt/cursor/artifacts/evidence}
REPORT="$EVD/12_e2e_pm_can_move.txt"
mkdir -p "$EVD"
PORT=${PORT:-8765}
PYBIN=${PYBIN:-/workspace/.venv/bin/python}
SPECY_BIN=${SPECY_BIN:-/workspace/.venv/bin/specy-road}

WORK=/tmp/e2e_work
REMOTE=/tmp/e2e_remote.git
HELPER=/tmp/e2e_helper
rm -rf "$WORK" "$REMOTE" "$HELPER" /tmp/e2e_uvicorn.log

cp -r /workspace/tests/fixtures/specy_road_dogfood "$WORK"
git init --bare -q "$REMOTE"
git -C "$WORK" init -q -b master
git -C "$WORK" -c user.email=t@e -c user.name=t add -A
git -C "$WORK" -c user.email=t@e -c user.name=t commit -q -m initial
sed -i 's/integration_branch: main/integration_branch: master/' \
  "$WORK/roadmap/git-workflow.yaml"
git -C "$WORK" -c user.email=t@e -c user.name=t commit -q -am "use master integration branch"
git -C "$WORK" remote add origin "$REMOTE"
git -C "$WORK" push -q -u origin master
git clone -q "$REMOTE" "$HELPER"
git -C "$HELPER" -c user.email=t@e -c user.name=t commit -q --allow-empty -m "ahead-1"
git -C "$HELPER" -c user.email=t@e -c user.name=t commit -q --allow-empty -m "ahead-2"
git -C "$HELPER" push -q origin master

# Kill any prior uvicorn on the port
PIDS=$(pgrep -f "uvicorn .*specy_road.gui_app" || true)
if [ -n "$PIDS" ]; then for p in $PIDS; do kill "$p"; done; sleep 2; fi

cat > /tmp/e2e_start_gui.sh <<EOF
#!/usr/bin/env bash
exec env \\
  SPECY_ROAD_GUI_PM_AUTO_RETRY_AUTOFF=1 \\
  SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=1 \\
  SPECY_ROAD_GUI_AUTO_INTEGRATION_FF=1 \\
  "$SPECY_BIN" gui --repo-root "$WORK" --port $PORT
EOF
chmod +x /tmp/e2e_start_gui.sh
nohup /tmp/e2e_start_gui.sh > /tmp/e2e_uvicorn.log 2>&1 &
disown
sleep 5
curl -s -o /dev/null -w "uvicorn /api/health %{http_code}\n" "http://127.0.0.1:$PORT/api/health" \
  | tee "$REPORT"

{
  echo "===== e2e — PM can actually move the feature with the fix on ====="
  echo "branch fix/drag_and_drop @ $(git -C /workspace rev-parse HEAD)"
  echo "env: SPECY_ROAD_GUI_PM_AUTO_RETRY_AUTOFF=1, REMOTE_OVERLAY=1, AUTO_INTEGRATION_FF=1"
  echo
  echo "--- repo state ---"
  echo "WORK = $WORK   integration_branch=master"
  echo "REMOTE = $REMOTE   tip=$(cat $REMOTE/refs/heads/master)"
  echo "WORK HEAD before any GET = $(git -C $WORK rev-parse HEAD)"
} >> "$REPORT"

# Capture stale fingerprint
PAYLOAD=$(curl -s "http://127.0.0.1:$PORT/api/roadmap")
FP_STALE=$(echo "$PAYLOAD" | $PYBIN -c 'import sys,json;print(json.load(sys.stdin)["fingerprint"])')
M0_KIDS=$(echo "$PAYLOAD" | $PYBIN -c "
import sys, json
d = json.load(sys.stdin)
sibs = sorted([(n.get('sibling_order',0), n['id']) for n in d['nodes'] if n.get('parent_id')=='M0'])
print(json.dumps([k for _,k in sibs]))
")
M0_LAST_KEY=$(echo "$PAYLOAD" | $PYBIN -c "
import sys, json
d = json.load(sys.stdin)
sibs = sorted([(n.get('sibling_order',0), n['id'], n['node_key']) for n in d['nodes'] if n.get('parent_id')=='M0'])
print(sibs[-1][2])
")
{
  echo
  echo "--- captured stale fingerprint = $FP_STALE ---"
  echo "M0 children (display) = $M0_KIDS"
  echo "moving last child (node_key=$M0_LAST_KEY) ..."
} >> "$REPORT"

# Drift the remote two more commits and FF local HEAD to mimic auto-FF
git -C "$HELPER" fetch -q
git -C "$HELPER" -c user.email=t@e -c user.name=t reset --hard origin/master -q
git -C "$HELPER" -c user.email=t@e -c user.name=t commit -q --allow-empty -m "race-1"
git -C "$HELPER" -c user.email=t@e -c user.name=t commit -q --allow-empty -m "race-2"
git -C "$HELPER" push -q origin master
sleep 6   # past the 5s fetch throttle
# Kick the server-side auto-FF by hitting GET (advances HEAD via merge --ff-only)
curl -s -o /dev/null "http://127.0.0.1:$PORT/api/roadmap"
sleep 1
HEAD_AFTER=$(git -C "$WORK" rev-parse HEAD)
{
  echo
  echo "--- after auto-FF: WORK HEAD = $HEAD_AFTER ---"
} >> "$REPORT"

# Compute the rotated order (move last child to position 0)
ROTATED=$(echo "$M0_KIDS" | $PYBIN -c "
import sys, json
xs = json.load(sys.stdin)
print(json.dumps(xs[-1:] + xs[:-1]))
")
{
  echo "--- POST /api/outline/reorder with STALE fp -> expect 412 retryable:true ---"
} >> "$REPORT"
RESP1=$(curl -s -i -X POST "http://127.0.0.1:$PORT/api/outline/reorder" \
  -H 'Content-Type: application/json' \
  -H "X-PM-Gui-Fingerprint: $FP_STALE" \
  -d "{\"parent_id\":\"M0\",\"ordered_child_ids\":$ROTATED}")
echo "$RESP1" | head -10 >> "$REPORT"

# Client one-shot retry: refresh and re-POST with fresh fp
FP_FRESH=$(curl -s "http://127.0.0.1:$PORT/api/roadmap/fingerprint" \
  | $PYBIN -c 'import sys,json;print(json.load(sys.stdin)["fingerprint"])')
{
  echo
  echo "--- client one-shot retry: GET fresh fp = $FP_FRESH; re-POST ---"
} >> "$REPORT"
RESP2=$(curl -s -i -X POST "http://127.0.0.1:$PORT/api/outline/reorder" \
  -H 'Content-Type: application/json' \
  -H "X-PM-Gui-Fingerprint: $FP_FRESH" \
  -d "{\"parent_id\":\"M0\",\"ordered_child_ids\":$ROTATED}")
echo "$RESP2" | head -10 >> "$REPORT"

# Read on-disk node_key order under M0 to verify the move actually landed
$PYBIN - <<PY >> "$REPORT"
import json, pathlib
work = pathlib.Path("$WORK")
out = []
for chunk in (work / "roadmap" / "phases").glob("*.json"):
    doc = json.loads(chunk.read_text())
    for n in doc.get("nodes") or []:
        if n.get("parent_id") == "M0":
            out.append((int(n.get("sibling_order", 0)), n["id"], n["node_key"]))
out.sort()
print("\n--- on-disk M0 children after retry ---")
for so, did, key in out:
    print(f"  sibling_order={so}  display_id={did}  node_key={key}")
print(f"\n--- Last-child node_key was {'$M0_LAST_KEY'}; it must now be at sibling_order=0:")
top_key = out[0][2] if out else None
print(f"   top node_key = {top_key}  ->  match: {top_key == '$M0_LAST_KEY'}")
PY

echo >> "$REPORT"
echo "===== /api/outline/move (cross-parent: move M0's last child under M1) =====" >> "$REPORT"

# Re-capture state
PAYLOAD=$(curl -s "http://127.0.0.1:$PORT/api/roadmap")
FP_STALE=$(echo "$PAYLOAD" | $PYBIN -c 'import sys,json;print(json.load(sys.stdin)["fingerprint"])')
MOVE_KEY=$(echo "$PAYLOAD" | $PYBIN -c "
import sys,json
d = json.load(sys.stdin)
sibs = sorted([(n.get('sibling_order',0), n['id'], n['node_key']) for n in d['nodes'] if n.get('parent_id')=='M0'])
print(sibs[-1][2])
")
echo "captured stale fp=$FP_STALE; moving node_key=$MOVE_KEY under M1[0]" >> "$REPORT"

# Force another race: push more commits and let auto-FF advance
git -C "$HELPER" fetch -q
git -C "$HELPER" -c user.email=t@e -c user.name=t reset --hard origin/master -q
git -C "$HELPER" -c user.email=t@e -c user.name=t commit -q --allow-empty -m "race-3"
git -C "$HELPER" -c user.email=t@e -c user.name=t commit -q --allow-empty -m "race-4"
git -C "$HELPER" push -q origin master
sleep 6
curl -s -o /dev/null "http://127.0.0.1:$PORT/api/roadmap"
sleep 1

RESP3=$(curl -s -i -X POST "http://127.0.0.1:$PORT/api/outline/move" \
  -H 'Content-Type: application/json' \
  -H "X-PM-Gui-Fingerprint: $FP_STALE" \
  -d "{\"node_key\":\"$MOVE_KEY\",\"new_parent_id\":\"M1\",\"new_index\":0}")
echo "[stale move] $(echo "$RESP3" | head -1)" >> "$REPORT"

FP_FRESH=$(curl -s "http://127.0.0.1:$PORT/api/roadmap/fingerprint" \
  | $PYBIN -c 'import sys,json;print(json.load(sys.stdin)["fingerprint"])')
echo "client retry: fresh fp=$FP_FRESH" >> "$REPORT"
RESP4=$(curl -s -i -X POST "http://127.0.0.1:$PORT/api/outline/move" \
  -H 'Content-Type: application/json' \
  -H "X-PM-Gui-Fingerprint: $FP_FRESH" \
  -d "{\"node_key\":\"$MOVE_KEY\",\"new_parent_id\":\"M1\",\"new_index\":0}")
echo "[retry  move] $(echo "$RESP4" | head -1)" >> "$REPORT"

# Assert the move persisted on disk
$PYBIN - <<PY >> "$REPORT"
import json, pathlib
work = pathlib.Path("$WORK")
new_parent = None
for chunk in (work / "roadmap" / "phases").glob("*.json"):
    doc = json.loads(chunk.read_text())
    for n in doc.get("nodes") or []:
        if n.get("node_key") == "$MOVE_KEY":
            new_parent = n.get("parent_id")
print(f"on-disk parent_id of moved node_key = {new_parent}  ->  match (M1): {new_parent == 'M1'}")
PY

# Validate
"$SPECY_BIN" validate --repo-root "$WORK" 2>&1 | tail -2 >> "$REPORT"

# Cleanup uvicorn
PIDS=$(pgrep -f "uvicorn .*specy_road.gui_app" || true)
if [ -n "$PIDS" ]; then for p in $PIDS; do kill "$p"; done; fi

echo
echo "Wrote $REPORT"
