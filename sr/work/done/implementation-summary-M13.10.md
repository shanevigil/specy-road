# Implementation summary: M13.10

Docs-only leaf; no code changes.

- **A1** `docs/upgrading.md` (new), "Migrating to the split rules files": a table of three kinds of `AGENTS.md` text with a destination and one example each (repo-specific specy-road policy → `.specyrd/AGENTS.team.md`; project rules → stay in root `AGENTS.md`; generic mechanics now in `.specyrd/AGENTS.md` → delete), plus "keep it when unsure" and "never edit inside the markers".
- **A2** "Preview a version you have not installed": scratch venv in `/tmp/sr-preview`, M13.6's download / sha256 / `--no-deps` install then dependencies from PyPI, the venv's `specy-road upgrade --dry-run --repo-root <repo>`, `rm -rf` the venv. "Which install is this": `pip show specy-road` (works on 0.1.x without `--version`), `pipx list`, `uv tool list`; links M13.6's "Which install is running" (`which -a`) instead of repeating it.
- **A3** `docs/install-and-usage.md`: the existing first line of "Keeping a consumer repo current after an upgrade" now links `upgrading.md`; the file stays at 395 lines (cap 400). `CHANGELOG.md` `## [Unreleased]` → `### Changed` gains one bullet: file-limits counts functions in `.tsx` files (added on the 0.3.1 line, first tagged in v0.3.1-rc2), so counts differ from 0.2.x and from CI on an older pin. No version heading.
- **A4** In "Which install is this": `uv tool install <wheel>` records the wheel path in uv's receipt, so `uv tool upgrade` needs that file; keep it or reinstall from the index.

Touch zones confirmed: `docs/upgrading.md`, `docs/install-and-usage.md`, `CHANGELOG.md` used; `tests/` unchanged (existing doc tests cover the new file: `test_docs_rc_install_recipe.py` scans every `docs/*.md`, so the preview recipe is checked against the two-index form).

Verification: `specy-road file-limits` (OK), `pytest -q tests/test_doc_links.py tests/test_docs_rc_install_recipe.py` (7 passed).

## Added

- `docs/upgrading.md` — the new upgrade guide (A1, A2, A4).
- Helpers: none
- Branches or guards: none
- Mocks: none
- Tests: none — existing `tests/test_docs_rc_install_recipe.py` already gates every doc, including this one, against the unsafe TestPyPI recipe.
