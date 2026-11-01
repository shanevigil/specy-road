# Implementation summary for M7.1

## Summary

Consumer projects get a research register. `specy-road init project` now scaffolds
`research/README.md`. It describes the layout: register entries at `research/<topic>.md` with YAML
front matter (`purpose`, `prompt`, `cadence_days`, `last_run`, `fed`), and prompts under
`research/prompts/`, tracked rather than kept in `work/`. It also covers the fold-findings loop
(research → brainstorm → promote → update `last_run` / `fed`).

`specy-road validate` now runs `warn_research_register`. It prints one non-fatal
`research: warning — research/<topic>.md: …` line for each of these problems in an entry:

- it is past its cadence, or has never run;
- its prompt file does not exist;
- its prompt file is outside `research/`, which is how A3 is enforced (a prompt in `work/` is flagged);
- `cadence_days` or `last_run` cannot be read.

A project with no `research/` directory, or only the README, gets no warnings. `--strict` counts these lines like every other warning.

`docs/roadmap-authoring.md` gains a "Research register" section (and a "Read further for" line) that describes the register and the loop. The file was at 397 of its 400-line cap, so two pairs of adjacent paragraphs were merged without changing their text (the `registry.yaml` / "Enforced by" lines under "Line-count policy", and the `roadmap.md` / chunk-files lines under "Generated index"). It is now exactly 400 lines.

### Acceptance

- **A1:** `specy_road/templates/project/research/README.md` is copied by the existing `rglob` in `init_project.py`, with no code change. The README defines the entry fields: purpose, prompt, cadence, last run and nodes fed. Covered by `tests/test_init_project.py::test_init_project_scaffold_validates`.
- **A2:** `warn_research_register` in `validate_roadmap.py` is wired into `validate_at`. Covered by `tests/test_research_register.py`, which has a parametrized unit test and an end-to-end test that runs `validate` on a scaffolded project.
- **A3:** a prompt outside `research/` (for example `work/topic-prompt.md`) triggers a warning. The README and the docs both say prompts are tracked under `research/prompts/`.
- **A4:** `docs/roadmap-authoring.md` has a new "Research register" section.

### Touch zones (final)

These were used: `specy_road/templates/project/research/`, `specy_road/bundled_scripts/validate_roadmap.py`, `docs/roadmap-authoring.md`, `tests/`.

These were listed but needed no change:

- `specy_road/init_project.py`: it already copies every template file.
- `research/` at the git root: the toolkit's own register belongs to M7.2, and its project root is `sr/`, which is outside this leaf's zones.

### Follow-ups (outside this leaf)

- The toolkit's own tracked prompt `sr/work/research-prompt-agentic-performance-orchestration.md` is in `work/`. Moving it into `sr/research/prompts/`, along with an entry, fits M7.2 or a later leaf, because `sr/` is not in this leaf's touch zones.
- `suggested_prompts/` does not describe the project layout in a way that conflicts with the new `research/` directory, so it was not changed. A later pass could mention the register in `bootstrap-governance.md`.

## Changes

- `specy_road/templates/project/research/README.md` (new)
- `specy_road/bundled_scripts/validate_roadmap.py`: `warn_research_register`, `_register_entry_problems`, a call in `validate_at`, and an `__all__` entry
- `docs/roadmap-authoring.md`
- `tests/test_research_register.py` (new); `tests/test_init_project.py` (one assertion)

## Verification

- `ruff check .` passes (C901 complexity limit of 10).
- `specy-road file-limits`: OK. `docs/roadmap-authoring.md` is exactly 400 lines and `validate_roadmap.py` is 371.
- `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood` all pass. The `.specyrd/cache` they leave in the fixture was removed before running pytest.
- `pytest -q -p no:cacheprovider tests/test_research_register.py tests/test_init_project.py tests/test_validate_roadmap.py tests/test_doc_links.py` gives 44 passed.
- `pytest -q -p no:cacheprovider` on the related set (research_register, init_project, init_project_gitignore, validate_roadmap, validate_strict, doc_links, package_data_dotfiles, package_data_schemas, lean_gates, lean_rules, validate_file_limits, constitution_scaffold) gives 85 passed, 2 skipped.
- **The full suite was not completed.** The machine was shared with five or more concurrent pytest runs from other agents (load average 68–80). Three full or half-suite attempts each hit the 10-minute command cap. The furthest one ran the first 117 tests of `tests/test_a*`–`test_l*` with no failures before it was stopped. The reviewer or coordinator should run `pytest` on an idle machine.

## Added

- `warn_research_register(root, today=None)` in `validate_roadmap.py`: walks `research/*.md` (skipping `README.md`) and prints one warning per problem (A2). `today` makes the cadence check testable.
- `_register_entry_problems(root, data, today)`: the per-entry checks, split out so `warn_research_register` stays under ruff's C901 limit of 10.
- Branch: no `research/` directory → return early. Trigger: every project without a register, including the dogfood fixture and the existing tests.
- Branch: `README.md` is skipped. Trigger: every scaffolded project. Test: `test_register_entry_warnings[fresh]` writes a README and expects no warning.
- Guard: `prompt` is missing or empty. Test: `[no-front-matter]`.
- Guard: the prompt file does not exist (A2). Test: `[prompt-missing]`.
- Guard: the prompt file is outside `research/` (A3). Test: `[prompt-in-work]`.
- Guard: `cadence_days` is not a positive int. Without it the cadence check cannot run, so the entry would go silent. Tests: `[bad-cadence]`, `[no-front-matter]`.
- Branch: `last_run` is empty, so the entry has never run and is due. Test: `[never-run]`.
- Guard: `last_run` is not an ISO date (`except ValueError`). Test: `[bad-last-run]`.
- Branch: past cadence (A2). Test: `[overdue]`.
- Test `tests/test_research_register.py::test_register_entry_warnings`: 8 parametrized cases covering each warning, plus the clean case.
- Test `tests/test_research_register.py::test_validate_reports_an_overdue_entry_in_a_scaffolded_project`: end to end, `init project` then `validate` reports an overdue entry and still exits 0.
- Assertion in `tests/test_init_project.py::test_init_project_scaffold_validates`: `research/README.md` is scaffolded (A1). This extends an existing test rather than adding a new one.
- Mocks: none.
