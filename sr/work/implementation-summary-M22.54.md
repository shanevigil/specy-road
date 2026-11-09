# Implementation summary: M22.54 `public-hygiene-gate`

## What changed

- `scripts/check_machine_paths.py` is renamed to `scripts/check_public_hygiene.py` (git rename). The old machine-path pattern is kept as-is and three bounded categories are added:
  - **Personal data:** email addresses that `scripts/public_hygiene_allow.txt` does not list (per address, never per line), and local-list name tokens and username as whole words. That one rule also covers `owner:` values and `<username>-s<digits>` presence names. A `github.com/<handle>` URL is masked before the name scan.
  - **Machine setup:** a home path into a local-list account directory, home-prefixed conda and venv paths, `CLAUDE_CONFIG_DIR` set to a path starting with `/` or `~`, a literal number on the apparmor sysctl, and local-list machine and profile names.
  - **Process content:** the text denylist and local-list phrases. In commit messages only, `sr/work`, `sr/planning`, `sr/roadmap` and `sr/tools` mentions. Under `--promotion` only, the path denylist on tracked paths and `--archive` member names (zip or tar), with `specy_road/templates/` and `tests/parity/` exempt.
- Modes: default (tracked files, `sr/` skipped), `--range A..B` (adds the commit messages in the range; a missing endpoint exits 1 and names it), `--promotion` (adds the path denylist and, over the range, the identity check), and `--commit-msg FILE`. The last checks one message, blanks git's `#` comment lines and ignores everything below the `commit -v` scissors line.
- Identity check: under `--promotion`, an author or committer address in the range must match the allow file's `public:` entry or a `bot:` entry. While `public:` reads `PUBLIC_IDENTITY_UNSET`, the check prints `advisory (public identity unset): …` lines and does not fail the run.
- Local list: `<kind>: <value>` lines (kinds `name`, `handle`, `home`, `machine`, `phrase`). It is read from `<git common dir>/info/public-hygiene-local.txt`, which is untracked by construction and shared by linked worktrees, and from the `PUBLIC_HYGIENE_LOCAL` env var (the CI secret). A malformed line stops the run, naming the source and line number but never the line itself.
- `scripts/public_hygiene_allow.txt` holds exactly the A2 entries, with `bot:` and `public:` prefixes. The dependabot entry is `49699333+dependabot[bot]@users.noreply.github.com`.
- `.pre-commit-config.yaml`: a `public-hygiene` file hook and a `public-hygiene-commit-msg` hook at `stages: [commit-msg]`. `default_stages: [pre-commit]` keeps the other hooks from running again at the commit-msg stage; it needs pre-commit 3.2 or later (not installed on this machine, so only the YAML parse was checked).
- `.github/workflows/validate.yml`: checkout uses `fetch-depth: 0`. The hygiene step passes `--range` for a pull request (base sha to head sha) or a branch push (`before` to `sha`), and adds `--promotion` when the pull request targets `main` or the push is to `main`. A `workflow_call` run comes from a tag push or a dispatch in `release-publish.yml`, so it checks files only. Event values go through `env:`, not inline `${{ }}` in the script.
- Docs: `AGENTS.md` (a Public hygiene bullet with both install commands), `docs/contributor-guide.md` (both install commands and a Public-hygiene gate section), and `specy_road/agent_rule_provenance.md` (the enforcement pointer now names the new script).
- `docs/orchestration-workers.md` line 198 is reworded by coordinator decision, with the path added to the zones. It states Ubuntu 24.04's stock default without writing a literal sysctl assignment, and the meaning is unchanged.

## Decisions (coordinator-accepted)

- `handle:` entries only exempt `github.com/<handle>` URLs from name hits; the handle itself is not a name token. Counting it as one flagged 11 product references to the public repo slug, for example `CANONICAL_OWNER_REPO`.
- The apparmor rule was not narrowed; the doc line was reworded instead.
- Email shape: the TLD must be at least two letters, so `a@b.c` and `lockfile-lint@4.14.0` are not addresses. A domain ending in a file extension (`.md`, `.py`, …) or starting with `pytest.mark` is no address (accepted limit).

## Final touch zones

The brief's nine, plus `docs/orchestration-workers.md` (coordinator). `scripts/line_width_baseline.json` still names `scripts/check_machine_paths.py`. It is a report that never fails and already carries removed paths (`scripts/census/*`), so it stays untouched.

## Verification

- `python scripts/check_public_hygiene.py` exits 0 on this tree. With the maintainer's username, name tokens and handle supplied only through the env var, it also exits 0.
- `python scripts/check_public_hygiene.py --range 16f20e4c..HEAD` exits 0.
- `pytest -n 4 tests/test_lean_gates.py`: 91 passed, including the kept machine-path rows, which now also run as commit messages. The full suite with `-n 4` gave 7027 passed and 15 skipped.
- `ruff check specy_road tests scripts` and `validate_file_limits.py` pass.

## Accepted limits

- History before the checked range is not scanned (M22.58 rehearses the rewrite).
- Name tokens are skipped when the local list and the CI secret are both unset; the other rules still run.
- On the WIP line, default mode skips the tracked `sr/` tree and applies no path denylist.
- The identity check is advisory until the operator sets the `public:` entry.
- `scripts/lean_metrics.py` is not on the path denylist.
- An email-shaped token whose domain is a file name or a pytest decorator is not an address.
- **Dev-push message range:** CI checks every commit message in a push range. A push to `dev` that merges WIP commits whose messages mention `sr/work`, `sr/planning`, `sr/roadmap` or `sr/tools` fails until those messages leave history (M22.58). The same holds for a pull request to `dev` or `main` that carries such commits.
- `--commit-msg` blanks only `#` comment lines; a custom `core.commentChar` is not read.
- A `workflow_call` run gets the local-list secret only if the caller passes secrets; without it the name rules are skipped there.
- No CHANGELOG `[Unreleased]` line: `CHANGELOG.md` is outside the touch zones.

## Added

### Helpers
- `Rules` (NamedTuple): compiled allow patterns, bots, public identity, text rules and the handle-URL mask, built once per run. It is a NamedTuple because the test loader does not register the module, which `dataclass` needs.
- `load_local`: reads the local list from the untracked file and the CI secret.
- `load_rules`: parses the allow file and assembles the text rules.
- `_any`: builds a case-insensitive whole-word alternation from local-list values.
- `_entries`: non-comment lines of the allow file.
- `line_hits` and `text_hits`: per-line categories and formatted hits; the `sr/` mention applies to messages only.
- `clean_message`: what git keeps of a commit-msg file.
- `tracked` and `file_hits`: the file scan (from the old `find_machine_paths`).
- `archive_members`, `denied_paths` and `promotion_path_hits`: the path denylist over tracked paths and wheel or sdist members.
- `missing_endpoints`, `range_hits`, `identity_hits` and `identity_report`: the range checks; `identity_report` makes the check advisory while the placeholder is set.
- `_report`: prints hits and returns the exit code. `_git`: decoded git output.

### Branches and guards
- Malformed local-list line raises `SystemExit`, because a typo in a kind would silently disable a rule (test: `test_public_hygiene_refuses_a_malformed_local_line_without_echoing_it`).
- Missing range endpoint exits 1 and names it, as A3 requires (test: `test_public_hygiene_range_checks_every_message_and_names_a_missing_endpoint`).
- Zip-or-tar branch in `archive_members`: wheels are zip and sdists are tar (test: `test_public_hygiene_promotion_passes_shipped_paths_and_checks_archive_members[zip|gztar]`).
- Comment lines and the scissors cut in `clean_message`: `git commit` with an editor writes status comments that name `sr/` paths, and `-v` adds a diff (content row with `SCISSORS`).
- `UnicodeDecodeError` skip for binary files: kept from the old script.

### Mocks
- none. `monkeypatch.setenv`/`delenv` of `PUBLIC_HYGIENE_LOCAL` is the CI-secret input, not a mock.

### Tests (all in `tests/test_lean_gates.py`)
- `test_public_hygiene_passes_on_this_repo`: renamed from `test_machine_paths_pass_on_this_repo`; it is the "self" row.
- `test_public_hygiene_content_rows`: extends `test_machine_paths_flag_personal_paths_only`. Its rows stay and now run in a tracked file and as `--commit-msg` text, and the sheet's content rows (email, mixed, owner, presence, name, home, config dir, local names, text, sr mention) are added, plus conda/venv, apparmor and machine-name rows for A1(b).
- `test_public_hygiene_reads_names_from_the_local_file_or_the_ci_secret`: the two sources, and the skip when both are unset.
- `test_public_hygiene_refuses_a_malformed_local_line_without_echoing_it`: the guard above.
- `test_public_hygiene_path_denylist_runs_under_promotion_only`: the "paths" row.
- `test_public_hygiene_promotion_passes_shipped_paths_and_checks_archive_members`: the "shipped paths" row, plus archive member names.
- `test_public_hygiene_identity_check_reports_until_the_public_identity_is_set`: the "identity" row, run for author and committer separately; it also checks that a bot committer passes and that default mode runs no identity check.
- `test_public_hygiene_range_checks_every_message_and_names_a_missing_endpoint`: the "range" row.
- Fixture `no_hygiene_secret` (autouse): keeps a developer's or CI's `PUBLIC_HYGIENE_LOCAL` out of the synthetic rows.
