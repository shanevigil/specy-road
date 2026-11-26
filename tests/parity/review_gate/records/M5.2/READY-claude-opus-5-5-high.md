---
node_id: M5.2
agent: claude-opus-5-5-high
branch: feature/rm-stale-command-check
commit: "ca6199b30ae47655753eb27731bb64c3eb679a6a"
base: "cf1e222d58bdeb60bc0cb6c45a08b7649d07011e"
changed_paths:
  - specy_road/bundled_scripts/validate_roadmap.py
  - specy_road/bundled_scripts/validate_stale_commands.py
  - specy_road/cli.py
  - tests/test_validate_stale_commands.py
  - docs/install-and-usage.md
  - sr/work/implementation-summary-M5.2.md
  - AGENTS.md
verify:
  - {cmd: "python -m pytest -q tests/test_validate_stale_commands.py", exit: 0, tail: "8 passed in 0.63s"}
  - {cmd: "specy-road file-limits", exit: 0, tail: "OK: file limits satisfied."}
  - {cmd: "ruff check specy_road/bundled_scripts/validate_stale_commands.py tests/test_validate_stale_commands.py", exit: 0, tail: "All checks passed!"}
---
Review round 15 rework (grok-4.7-high blocked A1 at 70fac47).
_reports now classifies the original line, so a one-line code span still counts as the follower. Use the specy-road frob `M1.2`., `path/to/file`., `--flag`., and `command`. warn. the specy-road toolkit `is` and other specy-road formats that accept `--strict` stay quiet.
_MENTION fails when a word character continues after the token. specy-road frob_extra and Run specy-road do_next do not warn. Run __specy-road frob__ now., - __specy-road frob__, and specy-road frob_ still warn.
Out of scope, amended A1: run all the specy-road frob stays quiet because a run verb counts only immediately before the product name, or before one noun-phrase word. the specy-road toolkit **is** a library is unchanged: the emphasis exception is for markers attached to the product name, not the follower.
The full suite was not re-run after this round.
scripts/check_clones.py was not run: pylint is not installed in this environment.
