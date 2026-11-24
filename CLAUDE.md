# specy-road (Claude Code)

@AGENTS.md

`AGENTS.md` (imported above) is the one agent entry for this repository: its load order, branch policy pointer, lean-change rules and the version-numbers rule apply to you. This file holds only Claude-specific notes.

- Claude Code skips `AGENTS.md` while this file exists, so the import above is what loads it; keep it.
- Claude Code does not load `sr/AGENTS.md` on its own: for `sr/` roadmap work, read it as the load order says.
- Other sessions may share this checkout: run tests with a capped worker count (`pytest -n 4`), and commit with `git commit --only <paths>`.
