# Implementation summary: `M4.5` — repository files as evidence; null results; quotes on research-born ideas

Branch `feature/rm-brainstorm-repo-evidence`, base `2280d77`.

## What changed

- **A1 — repo sources.** `add-evidence IDEA --source-type repo --path FILE[:LINE] --quote …` (with `--path`,
  `--source-type` can be left out) records `source_type: repo`, `path` (as given, relative to the git root) and `commit` (the full
  `HEAD` SHA). It refuses a path that the `HEAD` commit does not hold, such as an untracked or uncommitted
  file, because verify could never check it. It also refuses a path that is a directory (a tree object, not a blob). `verify` checks repo sources locally with no prompt and no network:
  `git cat-file blob <commit>:<path>` run at the enclosing git root; `matched` when the quote (whitespace collapsed, case kept) appears on
  a span that covers the cited line (anywhere in the file when no line was given), `not-found` when not or
  when that commit holds no file at the path (a directory is not one), `blocked` when the commit is no longer
  in the repository or the file there cannot be read as UTF-8 text. When
  the user declines the web fetch, repo sources are still checked; the exit code stays 1 as before.
- **A2 — null results.** `add-evidence IDEA --query TEXT --no-result [--stance against …]` records `query`,
  `result: none` and no quote. `pending()` never selects such a source, so `verify` neither fetches nor asks
  about it.
- **A3 — quotes on `add-idea`.** `add-idea --evidence URL --quote TEXT` (repeatable; quote N backs
  `--evidence` N) records a structured source (`url`, `quote`, `retrieved_at` today, `unverified`) that
  `verify` checks like any `add-evidence` source. A URL with no quote stays a plain `evidence` link. It works
  in `--from-file` records too (`quote: [...]`). More quotes than URLs, an empty quote or one over 300
  characters is refused.
- **Shape on disk.** Every source still carries a `url` so that every existing reader keeps working: the
  evidence prompt, the converge prompt, promote's `## References`, verify's report and its merge key. A repo
  source's `url` is `repo:<path>@<12-char sha>` and a null result's is `no-result:<query>`. Neither is
  mirrored into the idea's plain `evidence` URL list, which stays pages only. On read, a `repo` source
  without `path`/`commit`, or a `result: none` source without `query`, is rejected.
- **`add-evidence --url`** is no longer argparse-required. Exactly one of `--url`, `--path` or `--query`
  is required, with a `BrainstormError` (exit 1) otherwise. Every existing `--url` behaviour is unchanged,
  including the quote and 300-character rules and their messages.
- `docs/brainstorming.md`: the "must know" bullet, the rounds paragraph (`--quote` with `--evidence`), and
  section 3 (repo sources, null results, the locators and local verify).

## Review round 1 (gpt-6.1-sol, block on A1)

- **R1:** a directory citation passed `cat-file -e`, and its git tree listing could match the quote. Now
  `repo_commit` requires `cat-file -t` to be `blob` and refuses anything else ("a tree in the HEAD commit,
  not a file"). `check_repo_source` returns `not-found` for any non-blob before reading, so a directory
  citation already in a session never matches.
- **R2:** a committed file that would not decode (for example Latin-1) was reported `not-found`. Now, once
  the blob is known to exist, a failed read returns `blocked`. Reading moved from `git show` to
  `git cat-file blob`.
- Both cases are covered through the public CLI (`add-evidence`, then `verify`). The docs' verify paragraph
  states both rules.

## Review round 2 (gpt-6.1-sol, block on A1)

- **R1:** in a nested layout (a project under `sr/`) a repo path resolved against the project root, because
  git reads a `<commit>:./<path>` name against its working directory. Code outside the project could not be
  cited, and a same-named file under the project could be read instead. Now `_blob` runs git at
  `runtime_paths.git_root(root)` (falling back to `root`) with the name `<commit>:<path>`, with any leading `./`
  dropped. Recording (`repo_commit`) and verify (`check_repo_source`) both use it. The "not in the HEAD commit"
  message says the path is relative to the git root, and so do the docs.
- Public CLI regression: a nested `sr/` project cites `src/pay.py` committed at the git root, with a decoy
  `sr/src/pay.py`; `verify` matches against the recorded commit after HEAD moves on.

## Touch zones (confirmed)

Changed: `specy_road/bundled_scripts/brainstorm_cli_args.py`, `brainstorm_cli_args_v2.py`, `brainstorm_cli_v2.py`,
`brainstorm_fields.py`, `brainstorm_verify.py`, `docs/brainstorming.md`, `tests/test_brainstorm_repo_evidence.py`.
`brainstorm_cli.py` needed no change (`cmd_add_idea` goes through `idea_fields`). No path outside the zones
was needed.

Not changed (outside the zones; possible follow-ups, not required by A1–A3):
`specy_road/bundled_scripts/brainstorm_prompt_evidence.py` (the evidence prompt still shows only the `--url`
form; it could mention `--path` and `--query … --no-result`), and `suggested_prompts/brainstorm-roadmap.md`
and `specy_road/templates/specyrd/commands/specyrd-brainstorm.md`, whose `--url` examples remain accurate.

## Verification

- `pytest` (full suite, 23 min): `1 failed, 2871 passed, 2 skipped`. The one failure was
  `test_validate_file_limits.py::test_file_limits_passes_on_repo`: my section-3 additions took
  `docs/brainstorming.md` to 429 lines (cap 400). Fixed by unwrapping the section-3 and rounds paragraphs onto
  one line each, as other paragraphs in that doc already are (no text removed, limit untouched); now 391 lines.
  Rerun after the fix: `pytest tests/test_validate_file_limits.py tests/test_brainstorm_*.py
  tests/test_review_round6_brainstorm.py tests/test_gui_app_brainstorm.py tests/test_doc_links.py` → `341 passed`.
  The rest of the suite was not rerun: the fix changed only line wrapping in that doc.
- Review round 1 fix: `pytest tests/test_brainstorm_repo_evidence.py tests/test_brainstorm_verify.py
  tests/test_validate_file_limits.py tests/test_doc_links.py` → `33 passed`. `file-limits`, `ruff` and the
  private-imports gate pass. Per the coordinator, only the touched test files were run.
- Review round 2 fix: the same four test files → `34 passed`. `file-limits`, `ruff` and the private-imports
  gate pass. Only the touched test files were run.
- `ruff check specy_road/bundled_scripts/`: clean (C901 ≤ 10).
- `specy-road file-limits`: OK (`brainstorm_cli_v2.py` 389 lines, `docs/brainstorming.md` 391; `add_v2_subcommands` split to stay ≤ 80).
- Dogfood `validate`/`export --check` not run: no fixture data changed, and manual runs write `.specyrd/cache` into the fixture.
- `python scripts/check_test_private_imports.py`: 0 new private references. It also reports one stale
  baseline entry (`tests/test_review_round6_evidence.py: …review_packet._changed`) that predates this
  leaf and that I left alone.

## Added

### Helpers
- `brainstorm_fields.REPO`, `NO_RESULT`: the two new source shapes are named in one place.
- `brainstorm_fields.repo_locator`, `no_result_locator`: the `url` locator these sources carry, so existing `url` readers keep naming them.
- `brainstorm_fields.is_no_result`: shared by read validation and `pending`.
- `brainstorm_fields._source`: per-source read validation moved out of `parse_extra` (which already had a C901 noqa), plus the repo/no-result checks.
- `brainstorm_fields.source_record(**located)`: carries `path`/`commit`/`query`/`result` without a parameter each.
- `brainstorm_verify._blob`: (review round 2) the git root to run in and the root-relative object name for a repo path; shared by recording and verify.
- `brainstorm_verify.split_path`: `file:line` → `(file, line)`.
- `brainstorm_verify.repo_commit`: the `HEAD` SHA at record time; refuses a path that commit does not hold.
- `brainstorm_verify.quote_in_file`: whitespace-collapsed quote match that must cover the cited line.
- `brainstorm_verify.check_repo_source`: the local verify states (matched / not-found / blocked); after review, a non-blob is not-found and an unreadable blob is blocked.
- `brainstorm_verify.is_local`: separates repo sources (read, not fetched, no prompt) from web ones.
- `brainstorm_cli_args_v2._evidence_quote`, `evidence_record`: build `add-evidence`'s record from its flags; moved out of `brainstorm_cli_v2.py`, which is at the 400-line cap.
- `brainstorm_cli_args_v2.quoted_sources`: `add-idea --quote` pairing and checks.
- `brainstorm_cli_args_v2._add_evidence_parser`: keeps `add_v2_subcommands` under the 80-line function cap.

### Branches and guards
- `add-evidence`: exactly one of `--url`/`--path`/`--query`; `--query` only with `--no-result`; no `--quote` with `--no-result`; empty `--query` refused; `--source-type repo` only with `--path` and vice versa.
- `repo_commit`: refuses an absent path and, after review, any object that is not a blob (R1).
- `check_repo_source`: non-blob → not-found (R1); blob present but unreadable → blocked (R2).
- `check_source`: dispatches repo sources to the local check before the https guard.
- `pending`: skips no-result sources, which have nothing to verify.
- `verify_session(root=, web=)`: checks only repo sources when the fetch was declined.
- `cmd_verify`: confirms only web URLs; returns 1 early only when there is nothing local to check, otherwise checks the local sources and returns 1.
- `cmd_add_evidence`: mirrors into `idea.evidence` only for `--url` sources.
- `_refuse_flags_with_file`: `--quote` beside `--from-file` is refused like the other flags.

### Mocks
- `default_fetch` replaced with one that raises: proves a repo source is never fetched.
- `default_fetch` stub and `socket.getaddrinfo` stub resolving to a public address: let the A3 test verify offline without referencing a private name.
- `sys.stdin` set to an empty `StringIO`: no terminal and no `--yes`, as in the existing verify tests.

### Tests (`tests/test_brainstorm_repo_evidence.py`)
- `test_repo_source_records_the_commit_and_verify_checks_it_locally`: A1 end to end; checked against the recorded commit after HEAD moves; wrong line → not-found.
- `test_verify_checks_repo_sources_even_when_the_fetch_is_declined`: repo and web sources mixed; only the web URL is asked about.
- `test_add_evidence_refuses_a_path_the_commit_does_not_hold`: untracked file, repo/url mismatch, wrong source type, missing quote.
- `test_a_nested_project_cites_code_outside_it_relative_to_the_git_root`: review round 2; a nested `sr/` project with source outside it and a decoy inside; record, then verify against the recorded commit.
- `test_a_directory_is_not_a_file_to_cite`: R1 through the CLI; refused at record time, and a hand-edited directory citation verifies not-found.
- `test_a_committed_file_that_does_not_read_is_blocked_not_not_found`: R2 through the CLI, using a committed Latin-1 file.
- `test_repo_source_states_and_quote_spans`: `split_path` and `quote_in_file` edge cases; no root → blocked.
- `test_a_commit_that_is_gone_is_blocked_and_a_missing_file_not_found`: local verify states.
- `test_a_repo_source_without_its_commit_is_rejected_on_read`: read-side validation.
- `test_no_result_records_a_disconfirming_search_and_verify_skips_it`: A2.
- `test_no_result_flag_combinations_are_refused` (6 cases): flag combinations.
- `test_add_idea_quote_records_a_verifiable_source`: A3, verified through `verify --yes`.
- `test_add_idea_quote_checks`: orphan quote, quote over 300 characters.
- `test_add_idea_from_file_takes_quotes`: `--from-file` records with `quote`, and the flag refused beside `--from-file`.
