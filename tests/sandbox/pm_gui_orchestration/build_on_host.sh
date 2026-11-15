#!/usr/bin/env bash
# M17.9 host step (the VM has no node): build the GUI and the wheel from HEAD in a clean copy, collect
# the dependency wheels for the VM (CPython 3.12, x86_64 Linux), and pack the files the VM needs.
# Usage: tests/sandbox/pm_gui_orchestration/build_on_host.sh OUT_DIR   (PYTHON overrides python3)
set -euo pipefail
out="${1:?usage: build_on_host.sh OUT_DIR}"
py="${PYTHON:-python3}"
root="$(git rev-parse --show-toplevel)"
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
mkdir -p "$out"
out="$(cd "$out" && pwd)"
git -C "$root" archive HEAD | tar -x -C "$src"
(cd "$src/gui/pm-gantt" && npm ci && npm run build)
"$py" -m pip wheel -q --no-deps -w "$out" "$src"
wheel="$(ls "$out"/specy_road-*.whl)"
"$py" -m pip download -q -d "$out/wheelhouse" --only-binary=:all: --python-version 3.12 \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 "${wheel}[gui]"
git -C "$root" rev-parse HEAD > "$out/COMMIT"
git -C "$root" archive -o "$out/sandbox-files.tar" HEAD \
  tests/sandbox/pm_gui_orchestration tests/fixtures/specy_road_dogfood
echo "built $(basename "$wheel") at $(cat "$out/COMMIT") into $out"
