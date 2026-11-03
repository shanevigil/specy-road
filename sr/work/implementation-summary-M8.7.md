# Implementation summary — M8.7

Runtime verification of harness facts against installed binaries on the coordinator
machine (Claude Code 2.1.312, Codex CLI 0.165.0, Cursor agent 2026.10.22-27dcf5f).

## Acceptance

- **A1:** Ran the harness-capabilities runtime checklist in scratch repo
  `/tmp/m87-scratch-MvkgPX` (with sibling worktrees and `specy-road init project`).
  Results with dates are in
  `docs/design-notes/M8.7-runtime-verification-harness-facts.md`.
- **A2:** Replaced every `unverified` label in
  `specy_road/templates/project/model-profiles/harness-facts.yaml` with `runtime`
  or `documented` rows citing that design note (including explicit still-unknown
  rows for Cursor quota, Claude usage-limit wording, and generic per-binary facts).

## Touch zones (confirmed)

- `docs/` — design note
- `specy_road/templates/project/model-profiles/` — harness-facts fixture and rendered README harness block
- `research/` — read only (`sr/research/prompts/harness-capabilities.md`); no edit required

## Verification

- `pytest tests/test_harness_facts.py` — exit 0
- `specy-road refresh-profiles --check --repo-root specy_road/templates/project` — exit 0
- `specy-road file-limits` — exit 0

## Added

none
