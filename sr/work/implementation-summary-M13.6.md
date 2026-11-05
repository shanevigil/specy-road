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

## Fix round 1

Sol (gpt-6.1-sol) blocked A4 with R1. In the round-0 code, the fence recognizer cut every delimiter to three characters. An inner ```` ```bash ```` line therefore closed an outer ````` ````markdown ````` template, and a forbidden two-index install inside that template went undetected. Fixed in `d1c11d2b`, after merging `origin/WIP/improvements-0-3-1`.

- `_FENCE` now captures the full run (`` `{3,} `` or `~{3,}`) and the text after it.
- In `_fenced_commands`, a fence keeps its full opening delimiter. It closes only on a run of the same character that is at least as long and has nothing after it. An inner, shorter or info-string fence line is read as literal content of the outer fence.
- New control in `test_the_detector_flags_the_two_index_form_and_passes_the_recipe`: a four-backtick `markdown` template that contains a three-backtick `bash` two-index `pip install`. The test asserts that the scanner flags it.
- Red-green: the round-0 scanner (`c6cbce79`) does not flag that control (checked by running the old module on it), and the new scanner does. I also pointed the full gate at a temporary repo whose `README.md` holds the nested template, and it is now REJECTED.
- Docs gate re-run: `pytest -q tests/test_docs_rc_install_recipe.py tests/test_release_harness.py` passed (20 tests). `specy-road file-limits` reports OK. As instructed, I did not run the full suite.

### Added (round 1)

- `tests/test_docs_rc_install_recipe.py` `nested` control case (the R1 reproduction), so the gate cannot regress on templates with nested fences.
- Close-fence guard in `_fenced_commands` (same character, length at least the opener's, no info string), as R1 requires.

## Fix round 3

Sol blocked `9c551ecc` on A4 (R2). A two-index install inside a blockquoted fence (`> ```bash`) passed the gate, because the fence recognizer never matched a delimiter after a `>` prefix. Round 1 fixed nested fences and this round found blockquotes; lists, HTML blocks and indented code would come next. So this round replaces the design instead of adding another Markdown construct. Fixed in `test(M13.6): docs gate scans every line…` (`git log --oneline -1 -- tests/test_docs_rc_install_recipe.py`), after merging `origin/WIP/improvements-0-3-1`.

**Design change.** The gate no longer parses Markdown structure: there is no fence tracking at all. `tests/test_docs_rc_install_recipe.py` now works as follows:
- It reads every line of `README.md` and `docs/**/*.md`, inside and outside fences.
- `_strip_prefix` removes leading indentation, blockquote markers at any depth and nesting (`>`, `> >`), and list markers (`-`, `*`, `+`, `1.`, `1)`), repeating until none is left.
- `_logical_lines` joins backslash continuations after that stripping, so a quoted or indented multi-line command is seen as one line.
- `_two_index_testpypi` fails a line that contains `test.pypi.org` and at least two index flags (`--index-url`, `-i`, `--extra-index-url`, with a space or `=`). Order does not matter, so it also catches TestPyPI given as the `--extra-index-url` with PyPI as the `--index-url`.
- Allow marker: a line passes if `<!-- unsafe-example -->` appears on the line itself (any physical line of a joined command) or on the line just above its first line. This is for docs that show the unsafe form on purpose as a warning.

**Docs.** No doc currently shows the unsafe command. The warnings in `install-and-usage.md`, `release-runbook.md` and `supply-chain-security.md` describe it in prose without a TestPyPI URL, so they do not trip the check and need no marker. The gate passes on the current tree.

**Controls.**
- `test_the_detector_flags_the_two_index_form_wherever_it_sits` covers: the original case, `-i` in an indented fence, the nested `````markdown` fence (round 1), the reviewer's blockquote, a doubly quoted continuation, a list item (an indented fence under `1.` plus a `-` bullet with TestPyPI as the extra index), and inline prose.
- `test_the_recipe_and_a_marked_warning_pass` checks that the safe recipe, an unmarked prose warning, and an unsafe example marked above or inline all pass. It also checks that a marker separated from the unsafe line by a blank line does not cover it.

**Red-green.** `/tmp/m136_r3_probe.py` runs the public gate against a temporary README for two inputs: the reviewer's blockquote, and a list item holding a quoted fence with a continuation. The round-1 module at `9c551ecc` ACCEPTED both. The new module REJECTED both.

**Checks.** `pytest -q tests/test_docs_rc_install_recipe.py tests/test_release_harness.py` passed (21 tests). `specy-road file-limits` reports OK. I did not run the full suite.

### Added (round 3)

- `ALLOW` / `<!-- unsafe-example -->`: the explicit opt-out for a deliberate warning, which the design change requires.
- `_strip_prefix`: removes quote, list and indentation prefixes so that structure cannot hide a command.
- `_logical_lines`: replaces `_fenced_commands`. It scans all lines, joins continuations and records whether the marker applies.
- `_two_index_testpypi` (rewritten): order-independent check for a TestPyPI index plus a second index flag.
- `_offenders`: shared by the controls and the docs gate, so both run the same code path.
- `test_the_detector_flags_the_two_index_form_wherever_it_sits` and `test_the_recipe_and_a_marked_warning_pass`: replace the single round-1 control test and keep its original and nested-fence cases.
