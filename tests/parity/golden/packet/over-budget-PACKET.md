# Review packet: `M1.1` — Thing

- **Commit under review:** `eb92e263b920e3ca785ef857d5c3fe93449b16cd` (`feature/rm-thing`)
- **Base:** `e9d750fc895710837681be71cb3405beea8861c8` (merge base with `refs/remotes/origin/dev`)
- **Touch zones:** `src`
- **Policy source:** _refs/remotes/origin/HEAD (the remote's default branch) is missing, and with a remote configured the integration branch is named only there; run `git remote set-head origin dev` (`git remote set-head origin --auto` fails when the remote's HEAD is unborn)_ (the gate fails closed)
- **Generated:** 2020-01-15 by review-packet at HEAD `eb92e263b920e3ca785ef857d5c3fe93449b16cd`
- **Trial merge:** up to date with `refs/remotes/origin/dev`

Record your verdict with `specy-road review record M1.1 --model <id> --verdict approve|block --file <notes.md>`. Your record's `commit` must equal the commit above.

---

# Work-packet brief: `M1.1` — Thing `thing`

_Rendered from the roadmap at the working tree._

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

_Size: 2850 bytes. Largest sections: `## 7. Touch zones — implementing agent instruction` 836 B; `## 6. Dependency context (intent of upstream work)` 573 B; `## 1. Execution target` 367 B._

## 1. Execution target

- **Node id:** `M1.1`
- **Title:** Thing
- **Codename:** `thing`
- **Type:** task
- **Status (own):** In Progress — claim `feature/rm-thing`
- **Status (rollup):** In Progress
- **Execution (milestone hint):** —
- **Touch zones:** src

### Goal

Do the thing.

### Acceptance criteria

- **A1:** a.py exists
- **A2:** nothing else breaks

## 2. Ancestor context chain

_(no ancestors — this is a root node)_

## 3. Planning context (inlined)

### This node's planning sheet: `planning/M1.1_thing_11111111-1111-5111-8111-111111111111.md`

# M1.1 Thing

## Intent

Do the thing.

## References

## 4. Shared contracts (cited)

_(no `shared/` directory in this repo)_

## 5. Dependencies (must complete first)

- _none_

## 6. Dependency context (intent of upstream work)

_**Effective** dependencies below — this node's explicit `dependencies` plus every dependency inherited from an ancestor (same set the do-next-available-task picker uses). Each is **part of the brief on purpose** — do not ask the PM to repeat any of this prose inside this task's planning sheet. If something here is unclear or insufficient for this specific task, add a one-line clarification under `## Approach` (or `## Decisions and notes` for gates) citing the dep by display id._

- _no effective dependencies_

## 7. Touch zones — implementing agent instruction

The PM listed these touch zones: `src`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

### Call sites (one level)

Modules that import each zoned Python file at `HEAD`: likely call sites to read before starting. One marked _(outside zones)_ is a likely change outside this leaf's zones, so add it to the zones first or say why it stays unchanged.

_none found (Python imports only)_

**Running tests:** when other workers share this machine, cap parallel test workers (for example `pytest -n 4`, not `-n auto`): each full parallel suite starts one worker per core. A project can name the command as `verify_cmd` in `roadmap/git-workflow.yaml`.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

---

## Implementation summary

_Not provided: no summary at the reviewed commit, in the leaf's worktree, or in the working tree._

_(missing: `work/implementation-summary-M1.1.md` at `eb92e263b920e3ca785ef857d5c3fe93449b16cd`, `<ROOT>/work/implementation-summary-M1.1.md`)_

## Uncommitted references

_Computed by review-packet from git (`e9d750fc895710837681be71cb3405beea8861c8...eb92e263b920e3ca785ef857d5c3fe93449b16cd`)._

_none_

## Changed paths

_Computed by review-packet from git (`e9d750fc895710837681be71cb3405beea8861c8...eb92e263b920e3ca785ef857d5c3fe93449b16cd`)._

- `docs/x.md`  **← outside touch zones**
- `src/a.py`

**1 path(s) outside the touch zones.** An executor must stop for the coordinator rather than edit these.

## Test integrity

_Computed by review-packet from git (`e9d750fc895710837681be71cb3405beea8861c8...eb92e263b920e3ca785ef857d5c3fe93449b16cd`)._

_none_

## Tests at risk

_Computed by review-packet from git (`e9d750fc895710837681be71cb3405beea8861c8...eb92e263b920e3ca785ef857d5c3fe93449b16cd`)._ Python test files that import, at any depth, a module this diff changes (advisory; not a gate).

_none found_
- not analysed: 1 files

## Diff

_Computed by review-packet from git (`e9d750fc895710837681be71cb3405beea8861c8...eb92e263b920e3ca785ef857d5c3fe93449b16cd`)._

**Diff capped at 2 lines** and **200000 bytes** (14 lines, 260 bytes in all): the first 0 of 2 changed file(s) are inlined whole below; the full diff is at `<ROOT>/work/reviews/M1.1/DIFF.patch`.

- `docs/x.md` (+1 -0) — not inlined (128 bytes of diff)
- `src/a.py` (+1 -0) — not inlined (132 bytes of diff)

## Nested repositories

_Computed by review-packet from each nested repository's git (`nested_repos` in `roadmap/git-workflow.yaml`): the leaf's branch there, from its merge base with that repository's integration branch. Paths are project-relative._

### `src/engine`

_`ccc5a5ee6e31239ef626fe19d09059b9601a1573...408ea9a0a8d926b93da820ee50988aaf26cdcb2e` in `src/engine`._

- `src/engine/core.py`

**Diff capped at 2 lines** (7 lines, 115 bytes): the full diff is at `<ROOT>/work/reviews/M1.1/DIFF-nested-src+engine.patch`.

## Verifier output

_(no valid READY hand-off file for this node and branch)_
