# Implementation summary: M21.23 (rc4-docs-corrections)

Docs-only change; no code.

- **A1:** `docs/install-and-usage.md` refresh-profiles paragraph and `docs/orchestration-models.md` (older-scaffold sentence, plain refresh-profiles sentence) now say the default copies the missing profiles a roster entry in `roadmap/orchestration.yaml` names, `--profiles all` copies every missing shipped profile, `--only` adds one. `init project`'s `all` default text was not touched.
- **A2:** `docs/orchestration-workers.md` Cursor sandbox note: the sentence naming `composer-2.5`, `grok-4.7-exec` and decision D8 is replaced by a generic `cursor_force: true` sentence. `suggested_prompts/bootstrap-agents-md.md` gives the exact markers; checked against the rendered `managed_block.HTML_COMMENT.start`/`.end` (python import, both substrings present). `docs/orchestration-review.md` delegate step 2 says a `claude-code` reviewer without `channels.cli` runs bare or explicit as `orchestration-reviewer-output.md` describes.
- **A3:** CHANGELOG `[Unreleased]` Changed: file cap 400 → 1000, 750-line hard alert (warning; `--strict-hard-alerts` fails), overrides that existed only to sit above 400 dropped, `set_gate_status_fixture` and the 1100-line proposal override kept. First `[Unreleased]` Fixed list gets one doc-corrections bullet. `docs/whats-new.md` and the rc4 section untouched.
- **A4:** docs +11/-6 roughly, CHANGELOG +15.

Touch zones confirmed accurate; no change outside them.

Verification: `specy-road file-limits` OK; doc-text tests (`tests/test_shared_checkout_guidance.py`, `test_docs_install_extras.py`, `test_review_round6_docs.py`, `test_review_round6_policy.py`, `test_docs_rc_install_recipe.py`, `test_worker_resume_permissions.py`, `test_lean_rules.py`) pass; marker equality check passes.

## Added

- helpers: none
- branches/guards: none
- mocks: none
- tests: none (docs-only; marker equality checked with a one-off python command passed to `ready`)
