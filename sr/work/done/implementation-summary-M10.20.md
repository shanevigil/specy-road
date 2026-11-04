# M10.20 implementation summary

## Summary

GPT-6.1 Terra was piloted as an executor on three already-landed Agentic-led leaves, each replayed from its claim commit with `codex exec -m gpt-6.1-terra` at medium effort. The two reviewable results were reviewed by `cursor-grok-4.6-high` and `claude-opus-5-5-review`. The findings note recommends rostering Terra as an executor for small Agentic-led leaves, with three conditions, and a field profile was added.

## Acceptance

- **A1:** Terra is in the Codex 0.165.0 catalog as `gpt-6.1-terra`. Cursor's inventory (`2026.10.22-27dcf5f`) has only `gpt-5.6-terra-*`. The capture (Terra's catalog fields and the full slug list) is in the note.
- **A2:** M11.65, M11.73 and M11.77 were replayed. For each, the note records usage tokens, wall time, verifier outcomes and both reviewers' verdicts, compared with the landed version.
  - M11.65: approve / approve. Terra could not commit under Codex's workspace-write sandbox; the pilot committed its unchanged work.
  - M11.73: Terra stopped, since the needed edit was outside the touch zones; nothing to review.
  - M11.77: approve / approve.
  - Nothing was merged or pushed. Local branches `pilot/terra-M11.65`, `pilot/terra-M11.73` and `pilot/terra-M11.77` and their worktrees under this session's scratchpad are left in place for inspection. Remove them with `git worktree remove` and `git branch -D`.
- **A3:** The note is at `sr/docs/terra-executor-pilot.md`. The recommendation is yes, so the profile `specy_road/templates/project/model-profiles/openai-gpt/gpt-6.1-terra.md` was added.
- **A4:** The note records codex-cli 0.165.0. Terra is present in that inventory, so no recheck on 0.166.0 was needed.

## Notes for the reviewers and maintainer

- **Run count:** 7 model runs (3 executor, 4 reviewer) against a cap of about 6. M11.77 was added because M11.73 produced nothing to review.
- **Pilot reviewer prompts:** these were not `specy-road prompt` output, because `review-packet` and `review record` would have overwritten the real `sr/work/reviews/<ID>/` records. They asked for the gate's six headings and a verdict first, and only then showed the landed diff for a comparison section.
- **M11.65 replay:** the work was committed by the pilot as `1ce36bc2`, because the model's own `git commit` was denied by the sandbox. The content is the model's, unchanged.
- **Roster:** `sr/roadmap/orchestration.yaml` is unchanged. Approach says not to change roster defaults in this leaf, so the note gives the entry for the maintainer to add.
- **`docs/orchestration-models.md`:** unchanged.
- **Final touch zones used:** `sr/research/` and `specy_road/templates/project/model-profiles/openai-gpt/`.
- **Profile `access.cli`:** it is the harness-facts rendered template (any other value is drift). That template uses `sandbox_mode=workspace-write`, which cannot commit in a linked worktree. Fixing that belongs to `harness-facts.yaml` and `worker_adapter_base.CODEX_POLICY`, which are outside this leaf. The note flags it as condition 1.
- **README index:** `model-profiles/README.md` (outside the zones) does not list the new profile in its index table. No test requires it; a follow-up can add the row.

## Verification

- `python -m pytest -q -p no:cacheprovider -n 4 tests/test_models_and_prompt.py tests/test_lean_rules.py tests/test_orchestration_guard_hooks.py tests/test_harness_facts.py tests/test_model_profile_aliases.py tests/test_init_profiles_subset.py tests/test_verify_wheel_contents.py tests/test_upgrade.py tests/test_orchestrate_plan.py tests/test_cursor_usage_cost.py`: 167 passed, exit 0
- `specy-road file-limits`: exit 0
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road validate`: exit 0
- `specy-road models show gpt-6.1-terra --repo-root specy_road/templates/project`: loads; executor score 4

## Added

### Helpers
- none (the pilot's runner scripts live in the session scratchpad, not the repo)

### Branches or guards
- none

### Mocks
- none

### Tests
- none

### Files
- `sr/docs/terra-executor-pilot.md`: the A3 findings note, holding the A1/A4 capture and the A2 replay results
- `specy_road/templates/project/model-profiles/openai-gpt/gpt-6.1-terra.md`: the profile A3 asks for when the recommendation is yes
