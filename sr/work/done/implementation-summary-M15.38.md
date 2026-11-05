# Implementation summary: M15.38

**Leaf:** add-node caps a title-derived codename at 64 characters so the planning file name fits (`derived-codename-capped-so-planning-names-fit`)

**Commit (implementation):** see latest fix commit on `feature/rm-derived-codename-capped-so-planning-names-fit` (round 2 removes unreachable branches after grok-4.7-low block)

**Base (from pickup):** `6d771bebeff0eec2d79092c1aee80a58a5092cfd`

## Fix round (grok-4.7-low)

Removed two unreachable guards: `cap_codename_slug` empty-`parts` return (all-hyphen slugs already exit on `strip("-")`), and `derive_codename_with_collision_suffix` empty-`slug` return after a non-empty `title_to_codename` result. Behaviour and tests unchanged.

## Fix round (gpt-6.1-sol-low)

Re-export `CODENAME_MAX_CHARS` from `roadmap_edit_fields` (imported from `roadmap_codename_cap`; single literal `64` remains only in the cap module). `derive_codename_with_collision_suffix` and M15.38 tests import the constant via `roadmap_edit_fields`.

## Probes

- `cap_codename_slug` with hyphen-only input (`"---"`, `"----"`) — returns `""` at the post-`strip("-")` guard; never reaches word split.
- `cap_codename_slug` with non-empty slug and `max_chars >= 1` — never returns `""` (single-token truncation keeps at least one character when input token is non-empty).
- `derive_codename_with_collision_suffix` after `if not uncapped` — capped slug is non-empty for every non-empty `title_to_codename` output (same invariant as probe above).
- `derived_codename_from_title` — only calls `cap_codename_slug` after `title_to_codename`; empty title still yields `""` via early cap on empty input, no separate empty-slug guard needed.
- `_with_suffix` collision path — `max_base` is at least 59 for 4-char suffixes; non-empty `uncapped` keeps `base` non-empty under the same cap invariant.
- `codename_was_derived` / `maybe_sync_codename_from_title` — use `cap_codename_slug` only on non-empty uncapped slugs or empty titles; no duplicate empty-capped checks added elsewhere.
- Reviewer’s targeted pytest list (77 tests) — all pass after removal.
- A1 public surface — `from specy_road.bundled_scripts.roadmap_edit_fields import CODENAME_MAX_CHARS` resolves to `64` (re-export from cap module).
- Literal `64` for codename cap — only `roadmap_codename_cap.CODENAME_MAX_CHARS`; error messages use the constant, not a second literal.
- `codename_length_error` / `cap_codename_slug` defaults — read `CODENAME_MAX_CHARS` from the cap module only; no duplicate definition.
- `roadmap_crud_ops` — imports length helper from cap module only; does not define or hardcode the cap.

## Acceptance

| ID | Status |
|----|--------|
| A1 | `CODENAME_MAX_CHARS = 64` defined in `roadmap_codename_cap.py` and re-exported from `roadmap_edit_fields`; `cap_codename_slug` / `derived_codename_from_title` used in `derive_codename_with_collision_suffix`, `_derive_codename` (via prepare), and `maybe_sync_codename_from_title`. `title_to_codename` unchanged. `codename_was_derived` accepts uncapped or capped slug. |
| A2 | `codename_length_error` + checks in `cmd_add` and `_set_codename`; one-line `error:` message, exit 1, no writes on refuse. |
| A3 | `planning_filename_for_node` raises `ValueError` naming the node when UTF-8 filename length exceeds 255. `docs/roadmap-authoring.md` codename row documents the 64-character cap. |
| A4 | Three tests in `tests/test_roadmap_crud_atomicity.py` (long title add, 65-char `--codename`, 65-char `edit-node --set codename=`). |

## Touch zones (confirmed)

PM-listed zones plus **`specy_road/bundled_scripts/roadmap_codename_cap.py`** (split out so `roadmap_edit_fields.py` stays under the 400-line cap). Suggest adding that path to the roadmap node touch zones on merge.

- `specy_road/bundled_scripts/roadmap_codename_cap.py` *(new)*
- `specy_road/bundled_scripts/roadmap_edit_fields.py`
- `specy_road/bundled_scripts/roadmap_crud_prepare.py`
- `specy_road/bundled_scripts/validate_self_heal.py`
- `specy_road/bundled_scripts/roadmap_crud_ops.py`
- `specy_road/bundled_scripts/planning_artifacts.py`
- `docs/roadmap-authoring.md`
- `tests/test_roadmap_crud_atomicity.py`

## Verification run

```text
specy-road file-limits
ruff check specy_road/bundled_scripts/roadmap_codename_cap.py specy_road/bundled_scripts/roadmap_edit_fields.py specy_road/bundled_scripts/roadmap_crud_prepare.py specy_road/bundled_scripts/validate_self_heal.py specy_road/bundled_scripts/roadmap_crud_ops.py specy_road/bundled_scripts/planning_artifacts.py tests/test_roadmap_crud_atomicity.py
python -m pytest -q -p no:cacheprovider tests/test_roadmap_crud_atomicity.py tests/test_validate_self_heal.py
```

## Added

- `specy_road/bundled_scripts/roadmap_codename_cap.py` — holds `CODENAME_MAX_CHARS`, cap/derive/length helpers so `roadmap_edit_fields.py` stays within file-limits.
- `CODENAME_MAX_CHARS` — A1 constant (64).
- `cap_codename_slug` — word-boundary cap; single long token truncated; no trailing `-`.
- `derived_codename_from_title` — capped derivation for sync/add/heal paths.
- `codename_length_error` — shared A2 message body for CLI and `--set codename`.
- Collision suffix branch in `derive_codename_with_collision_suffix` — shrinks base slug so `-<hex>` suffix fits in 64 chars.
- `_derive_codename` delegation to `derive_codename_with_collision_suffix` — one derivation implementation for heal and add.
- `codename_was_derived` uncapped-or-capped check — A1: legacy long derived codenames still track title edits.
- `planning_filename_for_node` byte-length guard — A3: `ValueError` instead of `OSError` on add-node.
- `cmd_add` length refusal before pattern check — A2 for `--codename`.
- `_set_codename` length refusal — A2 for `edit-node --set codename=`.
- `test_add_node_long_title_caps_derived_codename` — A4 long title success path.
- `test_add_node_refuses_explicit_codename_over_64_chars` — A4 refuse `--codename` with snapshot unchanged.
- `test_edit_node_refuses_codename_over_64_chars` — A2 edit-node refuse with snapshot unchanged.
