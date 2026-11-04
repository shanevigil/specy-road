# Sourced by the sr/tools wrappers (`. "$(dirname "$0")/env.sh"`): resolves every path at run time,
# so no wrapper names a machine-specific directory.
#   ROOT     the main checkout: the parent of the shared git dir, so the same from a linked worktree
#            (workers and reviewers run with the leaf worktree, or its sr/, as cwd).
#   PY       ${SPECY_ROAD_PYTHON}, else the checkout's .conda, else its .venv, else python3.
#   REVIEWS  $ROOT/sr/work/reviews, the hand-off directory reviewers write to.
# PATH gets sr/tools (the specy-road shim) and the interpreter's bin directory first.
gcd=$(git rev-parse --git-common-dir) || { echo "sr/tools: not inside a git checkout" >&2; exit 2; }
ROOT=$(cd "$gcd/.." && pwd) || exit 2
if [ -n "${SPECY_ROAD_PYTHON:-}" ]; then PY=$SPECY_ROAD_PYTHON
elif [ -x "$ROOT/.conda/bin/python" ]; then PY=$ROOT/.conda/bin/python
elif [ -x "$ROOT/.venv/bin/python" ]; then PY=$ROOT/.venv/bin/python
else PY=python3
fi
REVIEWS=$ROOT/sr/work/reviews
case "$PY" in */*) PATH="$ROOT/sr/tools:$(dirname "$PY"):$PATH" ;; *) PATH="$ROOT/sr/tools:$PATH" ;; esac
export PATH
