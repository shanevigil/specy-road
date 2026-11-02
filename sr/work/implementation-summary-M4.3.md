# Implementation summary: M4.3 — Batch ideas and verdicts from a file, merge, and gap ideas (`brainstorm-batch-io`)

Base `b13b1c0`. Branch `feature/rm-brainstorm-batch-io`.

## Design

A `--from-file` record is parsed by the single command's own argparse subparser. `record_parser`
builds a fresh `add-idea` or `revise` subparser with abbreviations off and `error` raising
`BrainstormError`. Each record `{flag: value}` is turned into the argv the single command would take
(`--flag=value`, bare `--flag` for `true`, one `--flag=v` per list item, `id` as revise's positional).
That gives file records exactly the flag names, choices and append semantics of the command line,
with no second table of keys to keep in sync. Every record is parsed and applied to the in-memory
session first. The session file is written once, under the existing `session_lock`, only if all of
them succeed.

`merged`, the merge links, the gap marker and cluster objects are new optional session data. They
are parsed and serialised in `brainstorm_session.py`, because `brainstorm_fields.py` is outside the
touch zones. Like the v2 fields, they are left out of the YAML when empty.

## Acceptance

- **A1:** `add-idea --from-file PATH` reads a YAML list, a mapping with an `ideas:` list, or JSONL
  (every non-blank line starts with `{`). `-` reads stdin. Keys are the add-idea flag names, with
  `-` or `_` accepted. Repeatable flags (`evidence`, `assumption`) take a list. A bad record (unknown
  or abbreviated key, bad `kind`, a list for a single-value flag, `slug`/`repo-root`/`from-file`/
  `help`/`id`, missing title) fails as `PATH record N: … — nothing was written`, prints nothing on
  stdout and leaves the file byte-identical. `--from-file` combined with content flags is refused.
  Without `--from-file`, `--title` is still required. This is now checked in the handler (exit 1)
  instead of by argparse (exit 2).
- **A2:** `revise --from-file PATH` takes a list or a `verdicts:` mapping, with `id` naming the
  idea. Every id is resolved before any change. Each record then goes through the existing
  `_apply_revise`, so a record behaves exactly like `revise ID …`, and the session is written once.
  A bad id, choice, overlap relation or missing `id` writes nothing. `revise` without an id or a file
  is refused, and so is an id given together with a file. Single `revise ID …` still calls the
  unchanged `cmd_revise`.
- **A3:** `brainstorm merge ID --into ID…` (space- or comma-separated) sets `status: merged` and
  `merged_into` on the duplicate. Each target gets the duplicate in `merged_from` (the reverse link).
  It also records `decision {status: merged, decided_at, into}`. It refuses self-merge, merging into
  a merged idea, re-merging, and merging a promoted idea. `set_status` now refuses to re-triage a
  merged idea. Promote already skips non-accepted ideas, and a test covers it (`promote --dry-run`
  lists the target, not the merged idea). `recommend --check` no longer asks a merged idea for a
  cluster or verdict.
- **A4:** `add-idea --from-gap` (also `from-gap: true` in a file record) stores
  `raised_in: converge`. `recommend` prints `gap idea Bn (raised in the converge pass) needs a
  verdict: …` for each gap idea without a recommendation. `recommend --check` and `list` tag these
  ideas `[gap]`.
- **A5:** `brainstorm cluster CID [--name …] [--best ID] [--critic 'role: text']…` records
  `session.clusters[CID] = {name, best, critic}`. `--best` must already carry that cluster id, and
  `''` clears a name or best. A repeated role replaces that role's critic. `list --by cluster` shows
  `CID  name  (n)  best: ID` as the group header. The cluster's critics appear only with
  `--show-verdicts`, matching the per-idea critics. Recorded clusters with no members show as `(0)`
  when no `--status` filter is set. `list --json` includes `clusters`.

## Behaviour notes

- `revise` is now registered from `HANDLERS_V2` as `cmd_revise_any`, which dispatches to
  `cmd_revise` or to the file path. `brainstorm_cli_revise` is imported lazily there because it
  imports `brainstorm_cli_v2`.
- `docs/brainstorming.md` was already at 406 lines (over the 400 cap) on the base, so
  `file-limits` failed before this change. I reflowed four hard-wrapped paragraphs without changing
  their wording, and the file is now 395 lines including the new text.

## Touch zones (final)

Used: `brainstorm_cli.py`, `brainstorm_cli_args.py`, `brainstorm_cli_args_v2.py`,
`brainstorm_cli_v2.py`, `brainstorm_session.py`, `docs/brainstorming.md`,
`tests/test_brainstorm_batch_io.py` (new). `brainstorm_promote.py` was not changed, because promote
already skips merged ideas through `pending_ideas`. No path outside the zones was changed.

Follow-ups outside the zones (not done; none is needed for the acceptance items):
- `brainstorm_prompt.py`: the recommend prompt still says to mention new ideas in prose and "leave
  the session alone"; it could name `add-idea --from-gap`, `cluster` and `merge`.
- `suggested_prompts/brainstorm-roadmap.md` and the agent allow-list (frame, add-idea,
  add-evidence, revise) do not mention `cluster`/`merge`.
- The GUI: `gui/pm-gantt/src/types.ts` does not list the `merged` status, and the PATCH route
  could set `merged` without links through `set_status`.

## Verification

- `pytest -q` (whole suite, from this worktree): 2758 passed, 2 skipped (16m55s), exit 0.
- `pytest -q tests/test_brainstorm_batch_io.py`: 24 passed.
- `specy-road file-limits`: OK (it failed on the base because `docs/brainstorming.md` was at 406).
- `ruff check specy_road tests scripts` (ruff 0.17.3, the CI pin): all checks passed.
- `scripts/check_clones.py --pylint <venv pylint 4.1.3>`: 0 new clone pairs.
- `scripts/check_test_private_imports.py`: 0 new private references (the new tests use only public names).
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.

## Added

- `brainstorm_session.IDEA_STATUSES` += `merged`: the new idea status for A3.
- `Idea.merged_into` / `merged_from` / `raised_in`, `LINK_KEYS`, `_links()`: merge links and the gap marker, parsed (list of ids validated) and omitted from the file when empty.
- `BrainstormSession.clusters`, `_clusters_from()`: cluster objects (A5), validated on read, omitted when empty.
- Guard in `set_status`: refuses to re-triage a merged idea, which would leave stale links and let promote pick it up.
- `brainstorm_cli_args.add_from_file` (in `_args_v2`), `--from-gap`, optional `IDEA_ID` on revise, `--title` no longer argparse-required: the CLI surface for A1, A2 and A4.
- `brainstorm_cli_args.record_parser`, `_RECORD_BUILDERS`: the single command's own parser for a file record (exact flag names, errors raised).
- `brainstorm_cli_args._read_records`, `_record_argv`, `file_namespaces`, `_NOT_RECORD_KEYS`, `_FILE_LIST_KEY`: read YAML/JSONL/stdin and turn each record into a namespace; refuse keys that belong to the command line; refuse a list for a single-value flag (argparse would silently keep the last value).
- `brainstorm_cli_v2.idea_fields`: the add-idea namespace to `add_idea` kwargs, shared by the single and file paths.
- `brainstorm_cli_v2._refuse_flags_with_file`: guard against mixing `--from-file` with content flags or an id.
- `brainstorm_cli_v2.cmd_add_ideas_from_file`, `cmd_revise_any`: the all-or-none handlers (A1, A2).
- `brainstorm_cli_v2.cmd_merge`, `cmd_cluster` and the `merge` / `cluster` subparsers: A3 and A5.
- `brainstorm_cli._print_cluster`, and the `=> targets` / `[gap]` row marks: `list --by cluster` shows the cluster object; rows show merges and gaps.
- `brainstorm_cli.cmd_add_idea` title guard: keeps `--title` required when there is no file.
- `brainstorm_cli.cmd_recommend` gap lines, and the `_check_converge` merged skip and `[gap]` tag: A4, and a merged idea is not asked for a verdict.
- Mocks: `sys.stdin` monkeypatched with a `StringIO` for the JSONL-on-stdin test; no others.
- Tests (`tests/test_brainstorm_batch_io.py`, 24 cases): from-file add-idea with every key kind; 8 bad-record cases writing nothing; JSONL on stdin (including a value starting with `-`); flag/file mixing; revise from file success and 4 bad-record cases; revise id/file rules; merge links, the re-triage refusal and promote skip; merge refusals; from-gap through recommend, `--check` and list; `--check` skipping merged; cluster object in list/show-verdicts/json; `--best` membership and clearing; session round trip and a bad `merged_into` rejected on read.
