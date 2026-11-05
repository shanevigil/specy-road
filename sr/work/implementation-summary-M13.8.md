# Implementation summary: M13.8

## What changed

- **A1** — `specy_road/behaviour_changes.py`: `BehaviourChange` (`since`, `command`, `flags`, `now`, optional `contradicts`, optional `current`, `command_anchor`) and `CATALOGUE` with five entries (four cited cases plus pickup `--base` for A4).
- **A2** — `specy_road/agent_text_report.py`: `warn_contradicted_instructions` reports contradicting agent text outside managed blocks; report only.
- **A3** — Pin helpers in `specy_road/version_pin.py`, re-exported from `validate_roadmap.py`; one call from `validate_at`.
- **A4** — Pickup `--base` entry; `docs/roadmap-authoring.md` steps 3–4 reordered (400 lines).

## Touch zones

Unchanged from the brief: `specy_road/behaviour_changes.py`, `specy_road/agent_text_report.py`, `specy_road/version_pin.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`, `docs/roadmap-authoring.md`.

## Fix round 3 (grok-4.7-low on cb9c72c)

**Class (A2 minimum): stale patterns required extra words beyond the cited flag pairing.** `mark-implementation-reviewed` needed approve/tests-pass/your-own in addition to `--yes`; `finish-this-task` needed always/every-time/must-pass in addition to `--on-complete merge|auto`. Grok's reproductions (`Pass --yes to … mark-implementation-reviewed after the checks` and `` `finish-this-task --on-complete auto` lands the work ``) printed no notice.

**Class (A4 commandless init-era copy): `contradicted_by` always required a command token.** Sentences such as "The first commit on the feature branch registers the work in registry.yaml." returned False.

**Design (same classes everywhere):**

1. **A2 minimum `contradicts`.** `--yes` alone (with command anchor) and `--on-complete merge|auto` alone (with command anchor).
2. **`current` silencers expanded** so toolkit docs that document correct use of those flags still pass `test_the_toolkit_s_own_current_guidance_gets_zero_notices` (never/only when/independent/recorded; `handoff status` / `review-packet` in hook scripts; `merge|pr` mode lists; bare `specy-road finish-this-task --on-complete merge` example lines).
3. **`command_anchor=False` on the `--base` entry only** so init-era first-commit-on-feature-branch prose matches without naming `do-next-available-task`; `current` still silences integration-branch-first wording (Sol R1).
4. **Code fences are one paragraph** (not one line each) so multi-line shell examples such as orchestration's pre-finish hook are read with their `handoff status` / `review-packet` context on earlier lines in the same fence.

Sol R1/R2 regressions from fix round 2 are unchanged: command anchor on entries 1–4, near-miss corpus (19 cases), integration-branch-first sentence silent.

| Entry | Anchor | Stale (`contradicts`) | Current (`current`) | New positives |
|---|---|---|---|---|
| `--yes` | command | `--yes` | never, only when, independent, recorded, handoff status, review-packet, … | Grok after-the-checks line; CITED[0] still hits (approve + when tests pass) |
| `--on-complete` | command | `--on-complete merge\|auto` | override, recorded, refuse, merge\|pr, bare merge example line, … | Grok auto lands line; CITED[1] still hits (always + merge) |
| `--base` | optional | first commit + register + claim term | integration branch, `--base` | Commandless feature-branch sentence (Grok A4) |

## Probes

- Grok A2 reproduction strings: both print one notice via `warn_contradicted_instructions` — pass.
- Grok A4 commandless feature-branch sentence: prints one notice — pass.
- Sol R1 integration-branch-first sentence: no notice — pass.
- Sol R2 pickup-truck + claim insurance sentence: no notice — pass.
- `test_the_toolkit_s_own_current_guidance_gets_zero_notices` over `docs/*.md`, templates, `AGENTS.md`: no hits after fence join and expanded `current` — pass.
- `test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work`: no hits — pass.
- Entries 1–4 with command anchor: unrelated lines without `specy-road <cmd>` or backtick command still never match — checked via near-miss corpus.
- `--local` / `--delete-branch` entries: unchanged contradicts; still require command anchor — checked via CITED and near-miss tests.
- Multi-entry line (finish on-complete + never deletes branch): one notice with both behaviours — pass.

## Verification

- `python -m pytest -n 4 -q tests/test_behaviour_changes.py tests/test_validate_roadmap.py tests/test_validate_stale_commands.py`
- `specy-road file-limits`

## Added

### Helpers
- `BehaviourChange.command_anchor`: when false, `--base` entry matches commandless init-era prose (fix round 3).

### Branches and guards
- `behaviour_changes`: A2-minimum `contradicts` for `--yes` and `--on-complete merge|auto`; expanded `current` for toolkit zero-notice corpus (fix round 3).
- `agent_text_report._paragraphs`: accumulate lines inside a code fence into one paragraph (fix round 3).

### Mocks
- none

### Tests
- `test_a2_a4_minimum_stale_pairings_print_a_notice` (3 parametrized Grok reproductions): pins A2/A4 minimum reporting (fix round 3).
- `test_a_code_fence_is_one_paragraph`: renamed from fence-per-line test; still asserts a bare merge example in a one-line fence is not reported (fix round 3).
