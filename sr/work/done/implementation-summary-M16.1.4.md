# Implementation summary: M16.1.4

Commit `7af350ca` on `feature/rm-constitution-names-orchestration-as-part-of-the-product-bounds-scope-with-a-not-list-and-drops-contradictions` (base `4cbb1b22`). The previous worker (w-0180) left no commits; this is the first implementation.

## Acceptance

- **A1** — `constitution/purpose.md` says specy-road governs a repository's plan, its multi-agent execution (workers, roster, review delegation, grind) and its review trail, and carries the not-list word for word: "specy-road is not a CI system; not a hosted service; not an IDE or editor plugin; not an agent harness (it launches agent CLIs and does not replace them)."
- **A2** — `constitution/principles.md` is split into "Product invariants" (4-8) and "Engineering rules for this repository" (1-3, 9). Numbers are kept because code comments (`worker_state.py` cites principle 5, `do_next_prompt.py` principle 8), roadmap acceptance (principle 4) and `tests/test_lean_rules.py` (a line starting `9. `) cite them. Principle 5 keeps "no daemon and no MCP server" and says the PM GUI is a local server the user starts and detached workers are processes a command launches, neither a coordination daemon nor an MCP server. "Leave the choice of ... model to the team" (purpose) and "does not reinvent generic agent tooling" (principle 8) are reworded: specy-road launches the team's agent CLIs and adds prompts, records, guards and supervision; the roster names harness and model per role; model profiles are data the team chooses from. Principle 4's text is unchanged (asserted by `tests/test_review_round6_docs.py`).
- **A3** — `docs/philosophy-and-scope.md` goes from 88 to 34 lines: opinionated list, the four commitments, what is not prescribed, linking `constitution/purpose.md`. The `## Where specy-road sits` heading stays because `README.md` and `docs/orchestration.md` link its anchor; the dated third-party product quotes, the Spec-Kit section (covered in `docs/pm-workflow.md`), the duplicated agent load order (now a pointer to `AGENTS.md`) and the flow diagram are gone, as is the link to a design note as the source of principles. `AGENTS.md` and `docs/toolkit-development.md` now say the toolkit roadmap lives under `sr/` on the `WIP/improvements-x-y-z` line and is not in the tree on `main`.
- **A4** — net docs change: +73 / -87 lines across the seven files (-14 net; philosophy-and-scope.md -54). Lower than the -150 estimate because the purpose and principles grew to state the scope; informational only. `scripts/lean_metrics.py` is not on this branch yet (M16.1.7 not landed), so no deltas are reported.
- **A5** — `sr/constitution/purpose.md` is identical to `constitution/purpose.md`; `sr/constitution/principles.md` equals `constitution/principles.md` plus the A6 paragraph; both changed in the same commit. `constraints/` was not changed, so no constraints copy applies.
- **A6** — `sr/constitution/principles.md` alone carries: "Exception for this repository only: the coordinator dispatcher under `sr/work/` is an exception to principle 5's no-daemon rule. It is local maintainer tooling and never ships; adopters use `grind-session`, which has no daemon." It is not in the root copy because `sr/` is stripped on `main`, where the dispatcher does not exist.

## Touch zones

Confirmed as listed; no file outside them changed.

## Verification

- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` and `specy-road validate` (sr/): pass.
- `specy-road file-limits`: OK (one pre-existing warning on review_node.py).
- `pytest -n 4` on tests/test_doc_links.py, test_review_round6_docs.py, test_lean_rules.py, test_decisions.py, test_validate_touch_zones.py, test_agents_md_block.py, test_constitution_scaffold.py: 101 passed.
- The full suite did not finish within a 10-minute foreground limit on this shared machine, so it was not run to completion; the change is docs-only.

## Added

### Helpers
none

### Branches or guards
none

### Mocks
none

### Tests
none (docs-only leaf; the existing doc and constitution tests cover the asserted strings)
