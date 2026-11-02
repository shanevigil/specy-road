# Implementation summary: M8.1 — harness facts fixture drives model-profiles and executor templates

## What changed

- **A1 — fixture and schema.** `specy_road/templates/project/model-profiles/harness-facts.yaml`
  holds one record per supported harness (`claude-code`, `codex`, `cursor`, `generic`: the
  `worker_state.HARNESSES` list a roster `harness` may name; `generic` added in round 4). Each record covers version, headless command, executor command template, session
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

## Round 3 (escalated; RCA-3, in-scope items only)

A2's acceptance text is unchanged pending the maintainer's decision on RCA-3's rewrite. This
pass does only the two items in scope under either reading. No YAML encodings were added.

- **R4 — the shipped layout only.**
  - **What is rewritten.** `render_profile` rewrites only the shipped layout: a block-style
    `access:` whose children are all one-line keys indented two spaces (`_shipped_layout`).
    It writes only when the result parses to the original front matter with just
    `access.cli` changed (`_renders_to`).
  - **What is left alone.** Any other layout stays byte-identical: a folded or literal `cli`,
    a flow mapping, four-space or other indentation. `--render` then names the profile
    (`cannot render …`) and exits 1.
  - **Unparseable front matter.** A profile whose front matter is missing or not YAML is
    reported as `drift: … front matter does not parse`. `--check` exits 1, and `--render`
    exits 1 and leaves the file alone.
  - **Reverses round 2.** The round-2 whole-value matcher (`_CLI_VALUE`) is gone, because it
    was an extra encoding.
  - **Changed test.** `test_render_replaces_a_folded_multi_line_cli_whole` is now
    `test_render_refuses_a_folded_cli_and_leaves_it_byte_identical`. It asserts exit 1 and
    unchanged bytes instead of a rewrite. That follows the instruction that every layout
    other than the shipped single-line shape stays byte-identical. It is a changed
    expectation, not a removed check.
  - **New tests.** `test_render_refuses_a_four_space_access_mapping_and_leaves_it_byte_identical`
    is Sol's R4 input: valid YAML, with `--check` and `--render` both exiting 1 and the bytes
    unchanged. `test_a_profile_whose_front_matter_does_not_parse_is_drift` covers the parse
    case. Both share the helper `_render_refuses`.
- **R5 — `--capture --accept --dry-run`.** It now prints `would accept as …` and writes
  nothing (`run_capture(dry_run=...)`). The capture CLI test asserts that the accepted files
  are byte-identical after a `--dry-run` accept.
- **Docs.** `docs/orchestration-models.md` states the shipped-layout rule and the dry-run
  behaviour.

## Round 4 (gpt-5.6-sol-high block at 23367a84, A1 and A2)

- **A1 — the `generic` harness.**
  - **The record.** The fixture now has a `generic` record. Its sourced facts are labelled
    `documented`: the headless command and executor template (it runs the roster
    `channels.cli` or the profile's own `access.cli`), the session facts (no resume, interrupt
    or hand-off), hooks (the session guard's generic contract) and quota (no usage reported).
    Each source is `docs/orchestration-workers.md`, `docs/orchestration-models.md`,
    `worker_adapters.py` or `tool_call_guard_adapters.py`. Everything else is `unverified`:
    version, permissions, instruction files, skill dirs, git actions and model families.
  - **What it renders.** `renders_cli_for: []`, so it renders no `access.cli`. It does
    render into the README block, re-rendered with `--render --repo-root
    specy_road/templates/project`. An empty list now reads "none listed".
  - **No `capture_commands`.** Generic has no binary of its own, so the key is now optional in
    the schema. `--capture generic` without `--from` refuses with a message. With `--from`,
    only `version.txt` (plus any accepted files) is required.
  - **Coverage test.** The coverage test now compares the fixture's ids with the public
    `specy_road.worker_state.HARNESSES` (the list `worker_adapters` asserts its adapters
    against) instead of a hard-coded tuple. The accepted-captures test derives its harness list
    from the records that have `capture_commands`.
- **A2 — damaged README markers.**
  - **What counts as a block.** `_block_span` accepts only exactly one start marker followed
    by exactly one end marker. A README with neither marker is still `behind`.
  - **Damaged markers are drift.** One marker missing, a repeated marker, or the end before
    the start is now `drift: … the harness block markers are missing one, repeated or out of
    order` (`_markers_malformed`). `--check` exits 1; `--render` leaves the file byte-identical
    and exits 1 (`cannot render …`). It never guesses where a block was.
  - **Message change.** The `cannot render` message is now generic. A profile that cannot be
    rewritten gets the shipped-layout explanation in its finding detail.
- **Tests (+4).**
  - `test_a_damaged_marker_pair_is_drift_and_render_leaves_it_byte_identical`, through the CLI
    and parametrized: start deleted, end deleted, swapped.
  - `test_the_generic_harness_has_no_binary_to_capture`.
  - `test_the_shipped_fixture_validates_and_covers_every_supported_harness` (renamed;
    `HARNESSES`).
- **Docs.** `docs/orchestration-models.md` names `generic`, its capture rule and the marker
  rule.

## Verification

- `.conda/bin/pytest tests/test_harness_facts.py -q -p no:cacheprovider`: 49 passed (after
  round 4).
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
- `harness_facts._ACCESS_BLOCK` / `_CLI_LINE` — the `access:` mapping and its one-line `cli` key.
  Round 2's `_CLI_VALUE` was removed in round 3.
- `harness_facts._shipped_layout` / `_renders_to` — rewrite only the shipped layout, and only
  when the result parses to the same front matter with just `access.cli` changed (round 3, R4).
- Unparseable-front-matter drift branch in `plan_render` (round 3).
- `--dry-run` branch in `refresh_profiles.run_capture` — `--accept --dry-run` writes nothing
  (round 3, R5).
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
- `specy_road/templates/project/model-profiles/harness-facts.yaml` — the fixture (A1), with a
  `generic` record added in round 4.
- `harness_facts._markers_malformed` and the stricter `_block_span` — damaged markers are
  drift, never re-rendered (round 4, A2).
- `generic` branch in `refresh_profiles.capture` (no `capture_commands` means `--from` is
  needed), and the `rec.get("capture_commands")` fallback in `classify_capture` (round 4, A1).
- `specy_road/templates/project/model-profiles/harness-captures/{claude-code,codex,cursor}/*.txt`
  — the accepted captures (A3).
- `specy_road/templates/project/schemas/harness-facts.schema.json` — the schema (A1).
- `specy_road/templates/project/model-profiles/README.md` — the rendered harness block (A2).
- `tests/test_harness_facts.py` — 49 tests. The tests added or changed in rounds 1–4 are listed
  under their rounds; round 3 also added the `_render_refuses` helper:
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
