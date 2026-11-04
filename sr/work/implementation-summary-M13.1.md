# Implementation summary — M13.1

## What changed

- **A1** — `specy_road/version_skew.py` gains `launchers_on_path()` (walks `PATH` in order, every `specy-road` / `specyrd` executable like `which -a`, symlinks resolved, `running` set when the path or its target lies under `sys.prefix` (raw or resolved) or the target is the resolved `sys.argv[0]`) and `print_install_report()` (the "Install" section plus a stderr warning when the first `specy-road` on PATH is not the running install, naming both paths, `which -a specy-road`, reinstall or reorder PATH). `specy-road doctor` calls `print_install_report()` first: one import name and one call line in `doctor.py` (now 399 lines). Launcher rows start with `- `, not two spaces, because doctor's own findings rows (and `tests/test_doctor.py`) use the two-space indent.
- **A2** — `warn_if_blocks_written_by_other_version(project)` reads `Written by specy-road X` from the managed block of `<project>/AGENTS.md` and `<git root>/CLAUDE.md` (where `apply_agent_guide_block` writes it) via `managed_block._split`, and warns per file when X differs from the running `__version__`: "`<file>` block written by specy-road X, running Y; run `specy-road upgrade`". It is called from the top of `warn_if_running_version_older()`, so the per-command check `cli.py` already runs (validate included) and doctor emit it with no edit to `cli.py` or `validate_roadmap.py`. Non-fatal (stderr only).
- **A3** — the older-than-recorded message, its condition and `warn_if_pin_differs` are unchanged; nothing installs or removes launchers; upgrade output untouched (M13.2).

## Touch zones (final)

`specy_road/version_skew.py`, `specy_road/bundled_scripts/doctor.py`, `tests/` — accurate; no change outside them. `cli.py` (listed as an outside call site) stays unchanged because the new check rides on `warn_if_running_version_older()`.

## Verification

- `python -m pytest -q -n 4` — 3963 passed.
- `python -m pytest -q tests/test_version_skew_install.py tests/test_doctor.py tests/test_cli_version.py tests/test_running_toolkit_version.py` — pass.
- `specy-road file-limits` — OK.

## Added

- `Launcher` dataclass (version_skew.py) — plain record (name, path, resolved, running) shared by doctor now and upgrade (M13.2) later.
- `_is_running_install()` — the sys.prefix / argv[0] membership test for one launcher.
- `launchers_on_path(path_env=None)` — A1 helper; `path_env` lets tests pass a fake PATH; skips missing/non-executable entries and repeated PATH dirs.
- `print_install_report(path_env=None)` — A1 rendering and shadow warning kept out of doctor.py (near the 400-line cap).
- Guard: no warning when no `specy-road` is on PATH at all (nothing shadows the running install).
- `warn_if_blocks_written_by_other_version(project)` — A2 per-block check; called at the start of `warn_if_running_version_older()`.
- doctor.py: `print_install_report()` call at the start of `cmd_doctor`.
- `tests/test_version_skew_install.py::test_launchers_in_path_order_and_shadow_warning` — fake PATH with a plain launcher then a symlink into a monkeypatched `sys.prefix`: order, resolution, running flag, warning.
- `::test_no_shadow_warning_when_running_install_is_first` — the warning's negative case.
- `::test_validate_warns_on_block_from_other_version_with_matching_manifest` — A2: manifest at the running version, AGENTS.md block from 0.0.1, via `cli.main(["validate", ...])`; also asserts the older-than-recorded message stays silent.
- `::test_claude_md_block_from_other_version_warns` — CLAUDE.md block covered too.
- Mocks: `monkeypatch` of `sys.prefix` and `sys.argv` in the two launcher tests, so the running install is a temp directory.
