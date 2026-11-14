# M17.9 sandbox: the orchestration view in a real browser

`CHECKLIST.md` lists what is checked and the expected values. `sandbox_setup.py` installs the wheel,
seeds a fixture repo with the orchestration state and serves it with `specy-road gui --read-only`
(standard library and specy-road only). `browser_check.py` drives headless Chromium through every item
with Playwright for Python. The approval and its limits are in the M17.10 planning sheet.

## 1. On the host: build

The VM has Python 3.12 and Playwright but no node, so the GUI and the wheel are built on the host, from
`HEAD` in a clean copy (the checkout is not touched):

```bash
tests/sandbox/pm_gui_orchestration/build_on_host.sh dist-m17.9      # PYTHON=... to pick the interpreter
```

It runs `npm ci && npm run build` in `gui/pm-gantt`, builds the wheel, downloads its `[gui]`
dependencies as CPython 3.12 x86_64 Linux wheels into `wheelhouse/` (the VM installs offline), writes
`COMMIT` (the commit built) and `sandbox-files.tar` (this directory and the dogfood fixture from `HEAD`).
Commit the checklist and scripts first: the tar is taken from `HEAD`.

## 2. Copy to the VM

Everything in the output directory: `specy_road-*.whl`, `COMMIT`, `wheelhouse/`, `sandbox-files.tar`.
On the VM, `tar -xf sandbox-files.tar` recreates `tests/sandbox/pm_gui_orchestration/` and
`tests/fixtures/specy_road_dogfood/` side by side, as the scripts expect. The VM also needs `git` and `ps`.

## 3. Run

From the directory holding the copied files, with the interpreter that has Playwright:

```bash
python3 tests/sandbox/pm_gui_orchestration/browser_check.py \
  --wheel specy_road-*.whl --wheelhouse wheelhouse
```

It installs the wheel with `pip install --target` (no virtualenv; the browser keeps the system
Playwright), seeds, starts the read-only server, waits for HTTP 200, confirms `pid_alive` is true for the
running worker in `GET /api/orchestration`, then walks the items. Items 19 and 20 start a second, writable
server on the same repo; its PM decision code is read from its output and kept in memory. Every child
(servers, the inert worker process) is stopped on exit, pass or fail, and on SIGTERM. Exit status 0 means
every item passed. The pass takes a few minutes; keep the tool's timeout at 1800 s or less.

`sandbox_setup.py` alone (same `--wheel`/`--wheelhouse`) seeds, serves and confirms, prints the URL and
seeded ids, and exits; `--serve` keeps it up until interrupted, for looking around by hand.

## 4. Outputs

Under `./work/m17.9-<UTC time>/` (or `--work DIR`, which must not exist):

- `results.json`: the wheel's file name, sha256 and `COMMIT`, the `specy_road` module path and version,
  then per item `n`, `title`, `passed`, `observed` or `error`, and `screenshot`. `RESULTS.md` is written
  from it after the run.
- `screens/NN-<title>.png`: one screenshot per item.
- `server-read-only.log`, `server-writable.log`: the servers' output (the decision code masked).
- `repo/`, `origin.git`, `wt-leaf/`, `wt-scratch/`: the seeded fixture; `<work>-site/`: the installed wheel.

`work/` is gitignored at the repository root; nothing from a run is committed.
