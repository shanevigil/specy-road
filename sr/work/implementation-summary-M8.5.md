# Implementation summary: M8.5 — Guard hooks per harness and avoid lists in every model profile

Branch `feature/rm-guard-hooks-per-harness-and-avoid-lists-in-every-model-profile`, base `c376e2bed268d1bbcaeac2c77e7e086518b0ed15`.

## Touch zones (final)

PM listed `specy_road/templates/specyrd/hooks/`, `specy_road/specyrd_init.py`, `specy_road/templates/project/model-profiles/`, `docs/orchestration-models.md`, `tests/`.

Also edited (file-limit and wiring, named in ## Added): `specy_road/cli.py`, `specy_road/specyrd_cli.py`, `specy_road/orchestration_role_guard.py`, `specy_road/orchestration_guard_adapters.py`, `specy_road/bundled_scripts/orchestration_guard_cli.py`, `specy_road/specyrd_hooks.py`, `specy_road/specyrd_init_helpers.py`, `specy_road/worker_adapter_base.py`, `specy_road/worker_adapter_codex.py`, `specy_road/worker_runner.py`, `specy_road/worker_runner_queue.py`, `specy_road/worker_ops_message.py`, `docs/orchestration-workers.md`.

## Acceptance

- **A1:** Checked-in hook templates under `specy_road/templates/specyrd/hooks/`; `specyrd init --install-orchestration-hooks` merges snippets for Claude Code (PreToolUse, exit 2, `onFailure: block`), Codex (`.codex/hooks.json` + trust notes), and Cursor (`beforeShellExecution`, `failClosed`). Hooks call `specy-road orchestration guard --format …` with `SPECY_ROAD_ORCHESTRATION_ROLE`.
- **A2:** Every shipped profile has `## Orchestration: harness features to avoid` with switches; OpenAI GPT profiles and `harness-facts.yaml` Codex template include `--disable memories|multi_agent|goals`.
- **A3:** Shipped `pre-push` script; `specyrd init --install-pre-push-hook`; recipe in `docs/orchestration-workers.md`; test refuses push under `work/.worktrees/`.
- **A4:** Claude config uses exit 2 and `onFailure: block`; Codex README documents trust / `--dangerously-bypass-hook-trust`; subprocess tests exercise hook adapters.
- **A5:** Worker launch sets Claude env disables and Codex `--disable` flags; `test_codex_worker_launch_pins_disable_flags` pins argv.

## Verification

- `specy-road file-limits` → exit 0
- `pytest tests/test_orchestration_guard_hooks.py` → exit 0
- `pytest tests/test_worker_adapters.py::test_default_commands_follow_the_documented_cli_flags` → exit 0
- `pytest tests/test_worker_queue_message.py` → exit 0 (queue helpers moved, behaviour unchanged)

## Added

- `orchestration_role_guard.py` — role-based command classification and `executor_harness_env` for worker launches.
- `orchestration_guard_adapters.py` — per-harness hook JSON for executor and reviewer roles.
- `bundled_scripts/orchestration_guard_cli.py` — `specy-road orchestration guard` CLI entry.
- `cli.py` — dispatch `orchestration guard` subcommand.
- `specyrd_hooks.py` — merge hook JSON and install optional `pre-push`.
- `specyrd_init_helpers.py` — init context and hook install (file limit split from `specyrd_init.py`).
- `specyrd_init.py` / `specyrd_cli.py` — `--install-orchestration-hooks`, `--install-pre-push-hook`.
- `templates/specyrd/hooks/` — `README.md`, `pre-push`.
- `worker_adapter_base.CODEX_EXECUTOR_DISABLE` — shared `--disable` tuple for Codex workers.
- `worker_adapter_codex.py` — applies disables on launch/resume.
- `worker_runner_queue.py` — queue delivery split from `worker_runner.py` (file limit); re-export unchanged API.
- `worker_ops_message.py` — import queue helper from new module.
- `tests/test_orchestration_guard_hooks.py` — role rules, adapters, profiles lint, pre-push, specyrd init hook merge, Codex argv pin.
- Profile body sections and `harness-facts.yaml` Codex executor template — avoid lists and rendered `access.cli` alignment (A2, A5).
