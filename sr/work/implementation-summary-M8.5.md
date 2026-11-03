# Implementation summary: M8.5 — Guard hooks per harness and avoid lists in every model profile

Branch `feature/rm-guard-hooks-per-harness-and-avoid-lists-in-every-model-profile`, base `c376e2bed268d1bbcaeac2c77e7e086518b0ed15`.

## Touch zones (final)

PM listed `specy_road/templates/specyrd/hooks/`, `specy_road/specyrd_init.py`, `specy_road/templates/project/model-profiles/`, `docs/orchestration-models.md`, `tests/`.

Added with `specy-road edit-node M8.5 --add touch_zones=…` (kept because acceptance needs them):

- `docs/orchestration-workers.md` — A3 requires the pre-push recipe here.
- `specy_road/bundled_scripts/orchestration_guard_cli.py` — A1/A4 hook bodies call `specy-road orchestration guard`.
- `specy_road/cli.py` — forwards `orchestration` to that CLI.
- `specy_road/orchestration_guard_adapters.py` — per-harness hook JSON (Claude exit 2 + `onFailure: block`, Codex trust notes, Cursor `failClosed`).
- `specy_road/orchestration_role_guard.py` — reviewer vs executor denials the hooks invoke.
- `specy_road/specyrd_cli.py` — `--install-orchestration-hooks` and `--install-pre-push-hook` (A1, A3).
- `specy_road/specyrd_hooks.py` — merges hook snippets and installs the optional pre-push script.

`edit-node` also wrote `roadmap/phases/M8.json` and `roadmap/registry.yaml` (committed as it named). Those are the zone/claim update, not acceptance files; they are not added as zones (they overlap every other M8 / registry claim).

Reverted (acceptance does not need this leaf to edit the worker runner/adapters; other leaves own those files):

- `specy_road/worker_adapter_base.py`, `specy_road/worker_adapter_codex.py` — Codex `--disable` lives on the launch template (`harness-facts.yaml` / profile `access.cli`); A5 pins that argv, not the adapter default.
- `specy_road/worker_runner.py`, `specy_road/worker_runner_queue.py`, `specy_road/worker_ops_message.py` — Claude env switches are named in profiles; wiring them into `worker_runner.run` is left to the runner leaf.
- `specy_road/specyrd_init_helpers.py` — folded back into in-zone `specyrd_init.py`.

## Acceptance

- **A1:** Checked-in hook templates under `specy_road/templates/specyrd/hooks/`; `specyrd init --install-orchestration-hooks` merges snippets for Claude Code (PreToolUse, exit 2, `onFailure: block`), Codex (`.codex/hooks.json` + trust notes), and Cursor (`beforeShellExecution`, `failClosed`). Hooks call `specy-road orchestration guard --format …` with `SPECY_ROAD_ORCHESTRATION_ROLE`.
- **A2:** Every shipped profile has `## Orchestration: harness features to avoid` with switches; OpenAI GPT profiles and `harness-facts.yaml` Codex template include `--disable memories|multi_agent|goals`.
- **A3:** Shipped `pre-push` script; `specyrd init --install-pre-push-hook`; recipe in `docs/orchestration-workers.md`; test refuses push under `work/.worktrees/`.
- **A4:** Claude config uses exit 2 and `onFailure: block`; Codex README documents trust / `--dangerously-bypass-hook-trust`; subprocess tests exercise hook adapters.
- **A5:** Avoid lists name Claude env switches, Codex `--disable` flags, and Cursor persist/`/goal`/cloud (no switch). `test_codex_launch_template_pins_disable_flags` pins the Codex argv on the launch template and every OpenAI GPT `access.cli`.

## Verification

- `specy-road file-limits` → exit 0
- `pytest tests/test_orchestration_guard_hooks.py` → exit 0
- `pytest tests/test_worker_adapters.py::test_default_commands_follow_the_documented_cli_flags` → exit 0

## Added

- `orchestration_role_guard.py` — role-based command classification for hook denials.
- `orchestration_guard_adapters.py` — per-harness hook JSON for executor and reviewer roles.
- `bundled_scripts/orchestration_guard_cli.py` — `specy-road orchestration guard` CLI entry.
- `cli.py` — in-process dispatch for `specy-road orchestration guard`.
- `specyrd_hooks.py` — merge hook JSON and install optional `pre-push`.
- `specyrd_init.py` / `specyrd_cli.py` — `--install-orchestration-hooks`, `--install-pre-push-hook`.
- `templates/specyrd/hooks/` — `README.md`, `pre-push`.
- `tests/test_orchestration_guard_hooks.py` — role rules, adapters, profiles lint, pre-push, specyrd init hook merge, Codex launch-template argv pin.
- Profile body sections and `harness-facts.yaml` Codex executor template — avoid lists and rendered `access.cli` alignment (A2, A5).

### Helpers

- `_maybe_install_specyrd_hooks` in `specyrd_init.py` — calls the hook installer when the init flags are set.

### Branches / guards

- `decide_role` / `classify_for_role` — deny commit (reviewer), push, `gh pr`, executor worktree/cloud commands.
- Claude hook `onFailure: "block"` and exit 2; Cursor `failClosed: true`.
- Optional git `pre-push` refuses a toplevel under `work/.worktrees/`.

### Mocks

- none

### Tests

- `test_orchestration_role_rules` — blocked vs allowed commands per role.
- `test_orchestration_hook_adapters_block_like_their_harness` — each adapter's deny exit/JSON.
- `test_claude_print_config_has_on_failure_block` — A4 `onFailure: block`.
- `test_codex_launch_template_pins_disable_flags` — A5 Codex `--disable` on template and GPT `access.cli`.
- `test_every_shipped_profile_lists_orchestration_avoid` — A2 heading present.
- `test_specyrd_init_installs_claude_orchestration_hooks` — A1 init merge.
- `test_pre_push_refuses_worktree_allows_main` — A3.
- `test_orchestration_and_session_adapters_share_harness_keys` — harness key parity with session guard.
