# Implementation summary: M15.1

Touch zones (final, unchanged): `docs/install-and-usage.md`, `docs/install-release-candidates.md`, `docs/upgrading.md`, `docs/release-runbook.md`, `tests/`, `README.md`, `docs/supply-chain-security.md`. No change was needed outside them.

## Acceptance

- **A1:** The RC section moved to the new `docs/install-release-candidates.md`. `docs/install-and-usage.md` keeps the `### Install a release candidate (TestPyPI)` heading (same anchor) with a one-line pointer, and is now 373 lines (it was 395). The old anchor `install-and-usage.md#install-a-release-candidate-testpypi` is gone from every doc: `docs/upgrading.md`, `docs/release-runbook.md` (three places, plus the CHANGELOG-template line), `README.md` and `docs/supply-chain-security.md` now link `install-release-candidates.md`.
- **A2:** The new doc covers pip and uv pip (`"rc/<wheel>[gui]"` after the `--no-deps` sha256-checked download), pipx and uv tool from the checked wheel, and the direct-URL form `"specy-road[gui] @ https://test-files.pythonhosted.org/.../specy_road-<ver>-py3-none-any.whl"` for pipx and uv tool. How the sha256 is checked: pipx (and pip) honour a `#sha256=` fragment; uv tool ignores it, so the doc says to `curl -fsSL "$URL" | sha256sum` first. It notes that uv tool keeps the URL in its receipt, while a local wheel path breaks once `rc/` is deleted.
  Verified in scratch environments under `/tmp` against the published `0.3.1rc3` wheel: `pip install "<wheel>[gui]"` and `uv pip install "<wheel>[gui]"` (fastapi imported); `uv tool install` and `pipx install` (pipx 1.18.13 via `uvx`) of `"<wheel>[gui]"`; pipx with `URL#sha256=<good>` installed, and with a wrong hash failed with a hash mismatch; uv tool 0.13.7 with a wrong fragment, and with a wrong-hash constraints file, **installed anyway**. The uv receipt recorded `url = …` for the URL form and `path = …` for the local wheel. (Side note, not in scope: the rc3 wheel reports `__version__` `0.3.1rc2`.)
- **A3:** The "Never an index" section says TestPyPI is never an index for extras or dependencies via `--index-url`, `--extra-index-url`, uv `--index`/`--extra-index-url`, or any index strategy (`unsafe-best-match`, `first-index`), because a squatted name can outrank PyPI's and pip runs its `setup.py`. It names no third-party package or uploader.
- **A4:** The extras list in `docs/install-and-usage.md` (Install block and quickstart) now names `[gui]`, `[gui-next]`, `[review]`. The new `tests/test_docs_install_extras.py` reads `[project.optional-dependencies]` from `pyproject.toml`, drops `dev`, and fails when an extra is not named in either install doc. Red at base: with HEAD's `install-and-usage.md` and an empty new doc it fails (`[gui]` missing); green now.
- **A5:** Runbook A.3 step 5 is reworded: the human publishing the release posts the announcement, which carries the filled-in pip, pipx and uv tool commands with `[gui]`, the wheel's direct `test-files.pythonhosted.org` URL and its sha256. `docs/release-runbook.md` stays at 898 lines (no net lines added).

## Checks

- `python -m pytest -q -n 4` (full suite): 4024 passed.
- `specy-road file-limits`: OK.
- `tests/test_docs_rc_install_recipe.py` still passes: the new doc never puts TestPyPI and two index flags on one line.

## Added

- `docs/install-release-candidates.md`: the moved RC section, plus the extras, direct-URL and never-an-index content (A1–A3).
- `tests/test_docs_install_extras.py::test_install_docs_name_every_extra`: the pyproject-driven extras check (A4).
- Helpers, branches or guards: none.
- Mocks: none.

## Fix round 1

- **F1 (Sol, P3)**, class: a claim about how an installer chooses between indexes, stated without the index order it depends on. `docs/install-release-candidates.md` "Never an index" now says how each form goes wrong: `--index-url` makes TestPyPI the only index; pip `--extra-index-url` and uv `unsafe-best-match` take the highest version from either index; uv `first-index` takes each name from the first index that has it, and `--index`/`--extra-index-url` are searched before PyPI, so TestPyPI wins every name it has. The PyPI-has-no-RC clause is limited to the case where PyPI is listed first. The "squatted sdist runs build code" wording replaces "pip runs its `setup.py`", because uv builds sdists too. The never-an-index warning is unchanged.

## Probes

- uv 0.13.7, `--index-url <final> --index <rc>` (local HTTP Simple indexes), `probe-y==1.0.0rc1`: installed 1.0.0rc1 from `--index`, so an explicit index is searched before the default.
- uv 0.13.7, `--index <final> --index <rc>`, `probe-y==1.0.0rc1`: failed, "found on <final> but not at the requested version". The qualified PyPI-first clause holds.
- uv tool 0.13.7, `"probe-x[gui] @ http://127.0.0.1/<wheel>#sha256=<wrong>"`: the wheel was installed (it failed afterwards only because it has no entry points). The doc's "uv tool ignores the fragment" holds.
- pip, same URL with the wrong fragment: refused with "Expected sha256 … Got …". The "pip and pipx check the fragment" claim holds.
- "An exact pin needs no `--pre`" (pip and uv both accept a prerelease when `==` names it exactly) and "`uv venv` installs no pip" (it does unless `--seed` is given): these match the tools' documented behaviour; no change.
- `docs/supply-chain-security.md` "Release candidates from TestPyPI" (`--index-url` + `--extra-index-url` and `unsafe-best-match` let any package come from either index): accurate; no change.
- Runbook A.3 step 5, README and upgrading.md only link to the doc or describe the announcement and make no claims about how indexes are chosen; no change.
- `pytest tests/test_docs_install_extras.py tests/test_docs_rc_install_recipe.py tests/test_doc_links.py`: 8 passed. `specy-road file-limits`: OK.
