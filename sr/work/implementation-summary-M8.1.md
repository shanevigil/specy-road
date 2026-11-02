# Implementation summary: M8.1 — harness facts fixture drives model-profiles and executor templates

## What changed

- **A1 — fixture and schema.** `specy_road/templates/project/model-profiles/harness-facts.yaml`
  holds one record per rostered harness (`claude-code`, `codex`, `cursor`; the roster names no
  other). Each record covers version, headless command, executor command template, session
  flags, permission example, instruction files plus size guidance, skill dirs, hooks,
  autonomous git actions with their switches, model families, quota behaviour,
  `capture_commands` and `relationships`. Every fact is labelled `documented`, `runtime` or
  `unverified`. The schema requires a `source` unless the label is `unverified`. Facts come
  only from sources the repository already cites: the triage note, `docs/install-and-usage.md`,
  `docs/optional-ai-tooling-patterns.md`, `worker_adapters.py`, the profiles and
  `claude_code_limits.py`. Anything without a cited source is `unverified` (Codex skill dirs
  and quota, Cursor quota, Claude's attribution switch). The schema is
  `specy_road/templates/project/schemas/harness-facts.schema.json`, and
  `specy_road/harness_facts.py:load_facts` validates against it and refuses duplicate ids.
- **A2 — rendering and drift.** Two regions are rendered from the fixture:
  - each profile's `access.cli`, from the `executor_template` whose `renders_cli_for` names
    the profile's `family`;
  - a new README harness block between markers (inserted before `## Role rankings`).

  `refresh-profiles --check` reports a hand edit to either as `drift` (exit 1). A README with
  no block is `behind` (exit 0), because it predates rendering rather than being a hand edit.
  `--render` rewrites the regions (`--dry-run` lists them). A plain `refresh-profiles` still
  copies only missing files, and now also prints drift without failing. The shipped templates
  were rendered with `--render --repo-root specy_road/templates/project`. Only the README
  changed: every shipped profile's `access.cli` already equals its template, so `prompt
  --channel cli` behaviour is unchanged.
- **A3 — version-bump diff.**
  - **Where captures live.** `model-profiles/harness-captures/<harness>/` stores the accepted
    `--version` and `--help` output. These were captured on 2026-11-02 from the installed
    `claude` 2.1.312, `codex` 0.165.0 (plus `codex exec --help`) and `agent`
    2026.10.22-27dcf5f.
  - **How to run it.** `refresh-profiles --capture <harness>` runs the record's
    `capture_commands`; `--from DIR` reads a capture from a directory instead. Either way the
    new capture is classified against the accepted one: each new identifier is assigned (its
    relationship), unassigned (contains a workflow word, which fails with exit 1) or other.
    Removed identifiers and the version change are listed too.
  - **Accepting.** `--accept` stores a passing capture as the new accepted one.
  - **What counts as an identifier.** `--flags`, the rows under `Commands:`, and the first
    word of each line of an `inventory*.txt` file.
  - **Relationships so far.** Every workflow identifier in the three accepted captures is
    assigned. That makes 36 workflow identifiers, plus the flags the adapters use, for example
    `--worktree`/`--bg`/`--cloud`/`ultrareview`/`fork`/`--plan` → `avoid`, `review` (codex) →
    `duplicate`, and `--resume`/`--session-id` → `use`.
- **Docs.** `docs/orchestration-models.md` gains a "Harness facts" section covering the
  fixture, labels, rendered regions, `--check`/`--render`/`--capture`/`--accept`.

## Decisions a reviewer should check

- **Literal substring match.** The workflow-word match is a plain substring of the lower-cased
  identifier, as the acceptance text says ("containing"). So `pr` also matches `--print` and
  `--permission-prompts`. Those are assigned `neutral`/`use`/`complement` in the fixture. A
  false alarm costs one fixture line, and a token match would have narrowed the acceptance.
- **Fixture and captures are read from the toolkit's copy.** `refresh-profiles` always reads
  them from `specy_road/templates/project/model-profiles/`, even in an adopter repo, and
  `--accept` writes the accepted capture there. That makes it a maintainer action in a source
  checkout.
- **Behind vs drift.** A README without the block is reported as `behind` and does not fail
  `--check`. That is why `refresh-profiles --check` on this repository (it resolves `sr/`)
  exits 0: `sr/model-profiles/README.md` predates the block, and every `sr/` profile's `cli`
  matches. `sr/` is outside the touch zones, so I did not re-render it.
- **`runtime` labels.** Versions and help-derived facts are labelled `runtime` because they
  come from the committed captures. Hook facts are labelled `runtime` because
  `docs/optional-ai-tooling-patterns.md` records the 2026-10-28 sandbox runs. Nothing
  behavioural was newly verified here; that is still M8.7's job.

## Touch zones (final)

The brief's list is accurate. Used: `specy_road/templates/project/model-profiles/`,
`specy_road/bundled_scripts/refresh_profiles.py`, `specy_road/harness_facts.py`,
`specy_road/templates/project/schemas/`, `docs/orchestration-models.md`, `tests/`. Unused:
root `schemas/`, which does not exist in this repository (the schema lives under the project
templates).

Follow-ups outside the zones (not done):

- `specy_road/cli_usage.py` and `docs/install-and-usage.md` still describe `refresh-profiles`
  as copy-only; their one-liners could name `--check`/`--render`/`--capture`.
- `init project` copies the whole template tree, so new scaffolds also receive
  `harness-facts.yaml` and `harness-captures/`. `refresh-profiles` copies only `*.md`, as
  before.
- `sr/model-profiles/README.md` can take the block with `refresh-profiles --render`.

## Review round 1 (gpt-6.1-sol block, R1 and R2)

- **R1 — `--render` and a removed `access.cli`.**
  - `render_profile` now puts a removed `access.cli` back as the first line under a
    block-style `access:` mapping.
  - `--render` reports `rendered` only for files it actually updated (`_report_render`).
  - A drifted profile with no block-style `access:` to write into (flow style
    `access: { … }`) is reported as `cannot render …` and exits 1.
  - Regressions through `main`:
    `test_render_restores_a_removed_cli_and_check_then_passes` (remove the line, `--render`,
    `--check` exits 0) and `test_render_fails_on_a_region_it_cannot_write`.
- **R2 — incomplete captures.**
  - `classify_capture` refuses a capture that lacks any file the record's `capture_commands`
    names or any file the accepted capture has (inventory files included). The error is
    `incomplete <harness> capture: no …`, raised before classification, so `--accept` writes
    nothing.
  - `write_capture` no longer deletes files. With that guard in front of it, a
    capture can never drop an accepted input.
  - Regression through `main`:
    `test_an_incomplete_capture_is_refused_and_the_accepted_one_is_kept`. A version-only
    capture and a capture missing an accepted `inventory-features.txt` both exit 1, and the
    accepted directory is byte-identical afterwards.
  - The `_capture` test helper now includes `help-exec.txt`, because codex's
    `capture_commands` names it. No assertion was loosened.
- **Docs.** `docs/orchestration-models.md` states both rules.

## Review round 2 (gpt-6.1-sol block, R3)

- **R3 — multi-line `access.cli`.** `render_profile` now replaces the whole `access.cli`
  value, not only its first line.
  - **Scope.** The search runs inside the block-style `access:` mapping (`_ACCESS_BLOCK`), so
    it cannot touch a `cli:` key under another mapping.
  - **What counts as the value.** The key line plus every continuation line indented deeper
    than the key, with blank lines between them (`_CLI_VALUE`). That covers folded and literal
    block scalars and quoted scalars broken across lines.
  - **Untouched.** Everything outside that span stays byte-identical. The `access:` line must
    end at its line end or a comment, so a flow mapping (`access: { … }`) is still refused, as
    in round 1.
- **Regression through `main`:** `test_render_replaces_a_folded_multi_line_cli_whole`. It uses
  a `>-` folded scalar with a blank line inside. `--check` exits 1, `--render` exits 0,
  `--check` then exits 0, and the file is byte-identical to the shipped profile.

## Verification

- `python -m pytest tests/test_harness_facts.py -q -p no:cacheprovider`: 43 passed (after
  round 2).
- `python -m pytest -q -x -p no:cacheprovider`: 3018 passed, 2 skipped (18 min, before
  round 1; round 1 reran only the touched test file, as instructed).
- `python -m specy_road.bundled_scripts.refresh_profiles --check`: exit 0 (this repository
  resolves `sr/`; README `behind`, no drift).
- `--check --repo-root specy_road/templates/project`: exit 0, no drift.
- `--capture claude-code|codex|cursor` against the installed binaries: exit 0 each, with no
  new identifiers.
- `specy-road file-limits`: OK.

## Added

- `specy_road/harness_facts.py` — new module. It loads and validates the fixture
  (`load_facts`, `schema_errors`, `harness`), renders it (`rendered_cli`, `render_block`,
  `render_readme`, `render_profile`, `plan_render`, plus `Finding`/`RenderPlan`), and runs the
  capture diff (`identifiers`, `workflow_word`, `read_capture`, `classify_capture`,
  `write_capture`, `CaptureDiff`). Needed for A1–A3.
- `harness_facts._ACCESS_LINE` and the insert branch in `render_profile` — restore a removed
  `access.cli` (review R1).
- `harness_facts._ACCESS_BLOCK` / `_CLI_VALUE` (replacing `_CLI_LINE` / `_ACCESS_LINE`) — the
  whole `access.cli` value, scoped to the `access:` mapping (review R3).
- Completeness guard in `classify_capture` — a capture missing a commanded or accepted file is
  refused (review R2).
- `refresh_profiles._report_render` — `--render` reports only applied updates and exits 1 on
  a region it cannot write (review R1).
- `harness_facts._cli_line` — quotes a rendered `cli` only when YAML would misread it bare. The
  shipped values stay byte-identical.
- `harness_facts._prose` / `_evidence` / `_fact` — format the README block and escape `<id>`
  so Markdown does not swallow it as a tag.
- `harness_facts._block_span` — finds the README block, so edits outside it are never drift.
- Duplicate-id guard in `load_facts` — JSON Schema cannot express unique ids across records.
- `refresh_profiles.render_profiles`, `_report`, `capture`, `_print_diff`, `run_capture` —
  implement `--check`/`--render` and `--capture`/`--accept`.
- `refresh_profiles._parser` and `_copy_missing` — `main` would otherwise pass the
  80-line function cap. `_copy_missing` keeps the old behaviour unchanged.
- Guard in `main`: `--from`/`--accept` without `--capture` is a usage error.
- `specy_road/templates/project/model-profiles/harness-facts.yaml` — the fixture (A1).
- `specy_road/templates/project/model-profiles/harness-captures/{claude-code,codex,cursor}/*.txt`
  — the accepted captures (A3).
- `specy_road/templates/project/schemas/harness-facts.schema.json` — the schema (A1).
- `specy_road/templates/project/model-profiles/README.md` — the rendered harness block (A2).
- `tests/test_harness_facts.py` — 43 tests (the 3 added in round 1 and the 1 added in round 2
  are listed under their review rounds):
  - the fixture validates and covers the roster; each schema rule rejects a broken record;
  - an unverified fact needs no source, and a duplicate id is refused;
  - the shipped files are render-identical;
  - CLI drift, render-back and edits outside the block; README behind; default-run drift
    warning; YAML quoting;
  - identifier extraction; every workflow word fails until assigned; subcommand and inventory
    classification; neutral additions and removals;
  - the accepted captures pass against an empty baseline; the capture CLI's fail and accept
    paths; running `capture_commands`; missing version file or unknown harness.
- Mocks: `monkeypatch` of `hf.bundled_captures_dir`, so `--accept` writes to `tmp_path`, never
  the package; `monkeypatch` of `hf.load_facts`, so `capture_commands` run `sys.executable`
  instead of a real harness.
