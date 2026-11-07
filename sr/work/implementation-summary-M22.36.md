# M22.36 — Each RC publishes its wheel URL and install line, and the package links to the guide

Touch zones (final, unchanged): `.github/workflows/release-publish.yml`, `pyproject.toml`, `README.md`, `docs/install-release-candidates.md`, `CHANGELOG.md`. No other file needed a change. The notes step is shell in the workflow; the package page is `pyproject.toml` plus `README.md`; the upgrade pin is one guide. `project.version` stays `0.3.1rc2`.

## A1

`github-release` still extracts the changelog section, then appends three lines from the wheel just uploaded in `dist/`:

- **Wheel URL:** `https://files.pythonhosted.org/packages/<blake2b-256 2>/<2>/<rest>/<filename>` for PyPI, or the same path on `test-files.pythonhosted.org` for TestPyPI. That is the URL PyPI serves. Checked against the published `specy_road-0.2.3` wheel: the script's URL and sha256 match the index.
- **sha256:** sha256 of those wheel bytes.
- **One install line:** `pip install "specy-road @ <url>#sha256=<sha>"`. pip checks the fragment, and the requirement is a direct URL, so TestPyPI is not an index.

A target other than `pypi` or `testpypi`, or any count of wheels other than one, fails the step before the GitHub Release is created.

## A2

`[project.urls]` lists Homepage, Documentation, Release candidates (the install guide), Repository, Changelog and Issues.

Every README link a package reader can follow is an absolute `https://github.com/shanevigil/specy-road/` URL. In-page anchors such as `#install` stay anchors. The install guide, the RC guide and the rest of the docs table are included.

`docs/install-release-candidates.md` says moving to a newer RC is a fresh install of the new URL, because `uv tool upgrade` stays on the URL pin. That is in the agent quickstart, next to the receipt explanation under Direct wheel URL, and under After installing with the `uv tool install --force "specy-road[gui] @ <new URL>"` form.

## A3

`project.version` is still `0.3.1rc2`. `CHANGELOG.md` `[Unreleased]` has the entry under `### Fixed`. The header note now says the workflow appends the wheel URL, sha256 and install line to the release body.

## Verification

- The notes script, extracted from the workflow, reproduced the live PyPI URL and sha256 for `specy_road-0.2.3-py3-none-any.whl`, and the TestPyPI host for the same bytes.
- `python -m pytest -n 4 -p no:cacheprovider -q tests/test_release_harness.py tests/test_post_release_readme_cleanup.py tests/test_docs_rc_install_recipe.py tests/test_docs_install_extras.py` — 25 passed.
- `specy-road file-limits` — OK. The warnings it prints are on files this leaf did not touch.

## Added

### Helpers

- none

### Branches or guards

- `target not in hosts` in the release-notes step — an unknown publish target must not invent a wheel host.
- `len(wheels) != 1` in the release-notes step — the notes name one wheel, so zero or several fails the step.

### Mocks

- none

### Tests

- none. The notes step is workflow shell, and a new test file is outside the touch zones. The four existing test modules above still pass.
