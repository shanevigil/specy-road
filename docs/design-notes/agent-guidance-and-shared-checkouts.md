# Design: guiding agents outside a roadmap claim

> **Status:** proposed for the `0.3.x` line. Items 1 and 2 ship with this note;
> 3–6 are scoped here and built later. Companion to
> [`v0-3-0-orchestration-slices.md`](v0-3-0-orchestration-slices.md).

## What happened

On 2026-10-26 the maintainer ran four agents against one checkout of this
repository at the same time: this session building slice 1 of orchestration,
a second agent merging model research, a third poised to add
`grind-session --step`, and a cross-family verifier. None of that work was a
roadmap claim, so nothing in the toolkit — registry, touch zones, pickup —
knew it was happening. The failures were the ones proposal §3.4 predicts:

- One session switched branches in a tree another session was editing.
- One session ran `git add -A docs` while another's untracked files sat under
  `docs/`. Only timing kept them out of the commit.
- Two agents were set to edit the same two files (`CHANGELOG.md` and
  `docs/orchestration.md`) at once, uncommitted, on the same branch.
- Two plan files assumed branch and gate state that a later commit had
  changed; neither recorded the commit it was written against.
- Each agent learned about the others only when the maintainer told it.

Every rule that would have prevented this already existed in
[`docs/orchestration.md`](../orchestration.md) ("Working in one shared
checkout"). It was in the wrong place: a reference doc an agent reads after it
has picked up a leaf, not the file every agent reads first.

## Second problem: whose `AGENTS.md` is it?

`init project` writes a whole `AGENTS.md` and skips it when one exists, or
overwrites it under `--force`. A team with its own `AGENTS.md` therefore gets
no specy-road guidance at all, or loses its file. `specyrd init` solved the
same problem for `CLAUDE.md` with a managed block
([`managed_block.py`](../../specy_road/managed_block.py),
[`agent_guide_block.py`](../../specy_road/agent_guide_block.py)): one marked
section the toolkit rewrites, everything outside it untouched. `AGENTS.md`
never got that treatment, and the review-role and shared-tree rules added by
slice 1 make the whole-file scaffold heavier still.

Nothing tells an agent what wins when a repo's own rules and the toolkit's
disagree, either.

## Decisions

1. **The shared-checkout rules are part of what every agent reads first.**
   They go into the scaffold `AGENTS.md` and the `CLAUDE.md` managed block,
   not only `docs/orchestration.md`. Shipped with this note.
2. **Prompts and plans handed to an agent name the commit they were written
   against.** A `base: <sha>` line, plus "diff from that commit before
   starting". This is a convention for prompt authors, stated in
   [`suggested_prompts/bootstrap-agents-md.md`](../../suggested_prompts/bootstrap-agents-md.md)
   and in the scaffold. Shipped with this note.
3. **specy-road owns a block in `AGENTS.md`, not the file.** Extend
   `agent_guide_block` to `AGENTS.md` with the same HTML-comment markers:
   `init project` inserts the block into an existing file or creates the file
   with only the block; `refresh-stubs` rewrites it; `validate` warns when it
   is missing or stale, the way `warn_if_stubs_stale` does. The block carries
   the rules an agent needs before its first commit and points at `docs/` for
   the rest. `CLAUDE.md`'s block becomes a pointer to the `AGENTS.md` block
   instead of a second copy (proposal §3.5: one source, many entry points).
4. **Precedence is stated in the block.** The toolkit's rules on the
   registry, branches, review, and the shared tree are a floor: a repo's own
   rules may add to them, not relax them. On a conflict the agent stops and
   asks rather than choosing. This replaces the implicit "docs win" with a
   rule that names which docs.
5. **Presence files for unclaimed work.** `work/.sessions/<agent-id>.yaml`
   (gitignored) records the agent, its branch, its worktree, the paths it is
   editing, and an expiry. `handoff status` lists active sessions;
   `do-next-available-task` warns when another session's paths overlap the
   leaf's touch zones. The registry already does this for claimed leaves; this
   covers everything else. Expiry is what keeps a crashed session from
   holding paths forever.
6. **A staged-path guard.** A pre-commit check (shipped as a hook adapter in
   slice 5) that refuses a commit touching paths another active session has
   recorded, and warns on any commit staged with `-A`/`-a` in a tree with more
   than one session.

## Out of scope

Enforcing any of this inside a harness that bypasses hooks. The rules stay
advisory where the tool cannot see the agent; the presence file and the guard
make the common case visible, no more.
