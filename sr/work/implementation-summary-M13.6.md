# Implementation summary: M13.6

Docs-only leaf plus one docs test. Commit `338e1446`.

## Touch zones (final)

Confirmed as listed: `docs/install-and-usage.md`, `docs/release-runbook.md`, `docs/supply-chain-security.md`, `README.md`, `tests/` (new file `tests/test_docs_rc_install_recipe.py`). No change was needed outside them. `CHANGELOG.md` still has old two-index smoke-install lines inside past release entries. Those entries are historical and outside the zones, and the A4 test scans only `README.md` and `docs/**/*.md`, so they stay unchanged.

## Acceptance

- **A1:** In `docs/install-and-usage.md`, "Install a release candidate (TestPyPI)" now has these steps: `pip download --no-deps --only-binary :all:` of the exact pin from TestPyPI, `sha256sum` compared with the announced value, `pip install --no-deps <wheel>`, then `pip install <wheel>` with PyPI as the only index (this adds only the dependencies). The section says why: with both indexes any dependency can resolve from TestPyPI, where a name can be squatted. It links `supply-chain-security.md#release-candidates-from-testpypi`. The uv equivalent is `uvx pip download …`, then `sha256sum`, then `uv pip install <wheel>`. The `--index-strategy unsafe-best-match` advice and the ensurepip bootstrap were removed; the uv path needs no pip in the venv.
- **A2:** In `docs/release-runbook.md`, A.3 has a new step 5, "Announce the RC". It publishes the recipe and the wheel's sha256 from step 4. Step 4 now downloads the wheel, prints its `sha256sum` and checks it against `dist/` and the TestPyPI file listing. The other two-index commands in the runbook were moved to the download-then-install pattern: the A intro, the A.1 pre-flight and the CHANGELOG template inside A.2.
- **A3:**
  - The Install section shows `pip`, `pipx` and `uv tool` installs. Final-release upgrades are covered with `pip install -U`, `pipx upgrade` and `uv tool upgrade`, both in Install and in "Keeping a consumer repo current".
  - For RCs, the section covers `pipx install --force <wheel>` and `uv tool install --force <wheel>`, and how to go back to a final release.
  - A new subsection, "Which install is running", has `which -a specy-road specyrd`, `specy-road --version` and `readlink -f "$(command -v specyrd)"`. It explains the stale-`specyrd`-launcher failure and how to fix it. It also points to `specy-road doctor`, worded as "once your version ships that check" because M13.1 has not landed.
  - The README install block stays short: it links to that subsection and lists the three upgrade commands.
- **A4:** `tests/test_docs_rc_install_recipe.py` scans the code fences in `README.md` and `docs/**/*.md`. Fences may be indented, and backslash continuations are joined. The test fails on any command that pairs a `test.pypi.org` `--index-url`/`-i` with `--extra-index-url`.

## File limits

`docs/install-and-usage.md` went from 399 to 395 lines (cap 400). `docs/release-runbook.md` went from 899 to 898 lines (cap 900). `specy-road file-limits` reports OK.

## Verification

- `pytest -q tests/test_docs_rc_install_recipe.py`: 2 passed.
- `specy-road file-limits`: OK.
- Red-green: the detector run against the base (`cc8b1ba0`) `install-and-usage.md` and `release-runbook.md` exits 1, so the old recipe is caught.
- Full suite `pytest -n 4`: 3960 passed and 1 failed. The failure is `tests/test_cli.py::test_specy_road_init_build_gui_only_dry_run`. It was not caused by this change: the test asserts `"pip" not in stdout`, and stdout echoes the worktree path, which contains `…-pipx-and-uv-tool-…` from this leaf's codename. The test reads no docs. It would pass in a checkout whose path has no `pip`. I did not change it. The ready run deselects that one test, and this note explains why.

## Added

- `tests/test_docs_rc_install_recipe.py::_fenced_commands`: extracts the logical command lines inside code fences, joining continuations, so a multi-line two-index install is seen as one command.
- `tests/test_docs_rc_install_recipe.py::_two_index_testpypi`: the A4 predicate. It matches a TestPyPI `--index-url`/`-i` combined with `--extra-index-url`.
- `tests/test_docs_rc_install_recipe.py::test_the_detector_flags_the_two_index_form_and_passes_the_recipe`: a positive and negative control. It flags the old long and short (`-i`, indented fence) forms and passes the new recipe and prose mentions, so a broken detector cannot pass by matching nothing.
- `tests/test_docs_rc_install_recipe.py::test_no_doc_installs_from_testpypi_with_an_extra_index`: the A4 gate over `README.md` and `docs/**/*.md`.
- `docs/supply-chain-security.md` section "Release candidates from TestPyPI": the reason the recipe links to. It explains the two-index risk and uv's `unsafe-best-match`, and names the test.
- `docs/install-and-usage.md` subsection "Which install is running": required by A3.
- `docs/release-runbook.md` A.3 step 5 "Announce the RC": required by A2.
- Mocks: none. Branches or guards in code: none (docs-only leaf).
