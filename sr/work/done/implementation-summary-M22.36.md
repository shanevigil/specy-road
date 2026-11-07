# M22.36 — Each RC publishes its wheel URL and install line, and the package links to the guide

Touch zones: `.github/workflows/release-publish.yml`, `pyproject.toml`, `README.md`, `docs/install-release-candidates.md`, `CHANGELOG.md`. The fix round also edits `tests/test_release_harness.py`, the file the review named. `project.version` stays `0.3.1rc2`.

Merged `origin/WIP/improvements-0-3-1` before the fix. `CHANGELOG.md` kept this leaf's `[Unreleased]` entry and the integration entries.

## A1

`github-release` still extracts the changelog section, then appends three lines from the wheel just uploaded in `dist/`:

- **Wheel URL:** `https://files.pythonhosted.org/packages/<blake2b-256 2>/<2>/<rest>/<filename>` for PyPI, or the same path on `test-files.pythonhosted.org` for TestPyPI. That is the URL PyPI serves. Checked against the published `specy_road-0.2.3` wheel: the script's URL and sha256 match the index.
- **sha256:** sha256 of those wheel bytes.
- **One install line:** `pip install "specy-road @ <url>#sha256=<sha>"`. pip checks the fragment, and the requirement is a direct URL, so TestPyPI is not an index.

One rule decides both refusals: the target is `pypi` or `testpypi`, and `dist/` contains exactly one `*.whl`. An sdist beside that wheel is ignored. Anything else exits before a URL is written. The two earlier checks are that one rule.

## A2

`[project.urls]` lists Homepage, Documentation, Release candidates (the install guide), Repository, Changelog and Issues.

Every README link a package reader can follow is an absolute `https://github.com/shanevigil/specy-road/` URL. In-page anchors such as `#install` stay anchors. The install guide, the RC guide and the rest of the docs table are included.

`docs/install-release-candidates.md` says moving to a newer RC is a fresh install of the new URL, because `uv tool upgrade` stays on the URL pin. That is in the agent quickstart, next to the receipt explanation under Direct wheel URL, and under After installing with the `uv tool install --force "specy-road[gui] @ <new URL>"` form.

## A3

`project.version` is still `0.3.1rc2`. `CHANGELOG.md` `[Unreleased]` has the entry under `### Fixed`. The header note now says the workflow appends the wheel URL, sha256 and install line to the release body.

## Verification

- The notes script, extracted from the workflow, reproduced the live PyPI URL and sha256 for `specy_road-0.2.3-py3-none-any.whl`, and the TestPyPI host for the same bytes.
- `python -m pytest -n 4 -p no:cacheprovider -q tests/test_release_harness.py` — 26 passed.
- `python -m ruff check specy_road tests scripts` — passed.
- `specy-road file-limits` — OK. The warnings it prints are on files this leaf did not touch.

## Probes

- Both publish hosts: the notes step is the only place that picks `files.pythonhosted.org` or `test-files.pythonhosted.org`. README, pyproject, the changelog and the RC guide do not build a URL. Result: one test runs the step for `pypi` and `testpypi`.
- Exact wheel URL: that test compares the notes with a literal blake2 path for fixed wheel bytes, and a different sdist sits beside the wheel. Result: the URL names the wheel on the host for that target.
- Exact sha256: the same notes equal the literal sha256 of those bytes. Result: pass.
- Install line: the same notes end with one `pip install "specy-road @ <url>#sha256=<sha>"` line and no second command. Result: pass.
- Unsupported target: `dry-run` (the workflow's other target) and `local` (any other string) hit the same refusal. Result: non-zero, changelog unchanged, no URL.
- Wheel count: an empty dist, an sdist alone, two wheels and three wheels hit that same refusal. Result: non-zero, changelog unchanged, the message names the wheel filenames.

## Added

### Helpers

- `_notes_step_script` in `tests/test_release_harness.py` — reads the notes step's Python from the workflow, so the test runs that step and not a copy.
- `_run_notes_step` in `tests/test_release_harness.py` — runs that Python against a temp dist and notes file.

### Branches or guards

- `host is None or len(wheels) != 1` in the release-notes step — one refusal for an unknown target or any wheel count other than one. It replaces the two separate checks.

### Mocks

- none

### Tests

- `test_release_notes_name_the_wheel_for_both_publish_hosts` — both hosts, the exact URL, the exact sha256 and the one install line, with an sdist beside the wheel.
- `test_release_notes_reject_an_unsupported_publish_target` — `dry-run` and `local` write no URL.
- `test_release_notes_reject_a_dist_that_is_not_one_wheel` — zero wheels, an sdist alone, two wheels and three wheels write no URL.
