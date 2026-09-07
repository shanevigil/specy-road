# Triage: `v0.2.2` unattended multi-lane report

> **Outcome:** all three findings were fixed in **`v0.2.3`**. See the
> [CHANGELOG](../../CHANGELOG.md) entry for that release.

Assessment of a report written after running `grind-session --implement-mode
hook --implement-cmd 'claude -p …'` across **two parallel lanes** — separate
clones, one roadmap phase each, against a single integration branch — unattended
for roughly six hours, finishing about a dozen leaves. That is the sub-agent
orchestration pattern the toolkit's own `specyrd-grind-session.md` template
recommends, which is why finding 27 is not an exotic configuration.

Confirmed working, and preserved deliberately: the `--json` event stream (the
reporter built an external supervisor against it and every failure mode they
needed to distinguish was already represented), and `--delete-merged-branches`
plus returning to the integration branch on a clean stop (the v0.2.2 fix).

## Summary

Numbering continues the previous note, which ended at 26.

| # | Finding | Call | Fixed by |
|---|---|---|---|
| 27 | Concurrent finishes conflict on — or silently corrupt — `roadmap/registry.yaml` | **Defect** | Registry and generated files are resolved from the integration branch, never 3-way-merged |
| 28 | The Claude resume path flattens command substitution in `--implement-cmd` | **Defect** | `--resume` is spliced into the original string instead of a `shlex` round trip |
| 29 | A hook killed with no output reads as a task failure; the bounds are hardcoded | **Feature** | Bounded `implementer_vanished` retry, plus four CLI/yaml knobs |

## 27. A keyed collection is not a text file

`roadmap/registry.yaml` holds one row per active claim, and `roadmap.md` /
`roadmap-context.md` are generated in full — but all three were landed by a
line-based `git merge`. The reporter hit both of its failure modes:

* **It conflicts**, which was the source of nearly every failure in the run.
  `--on-complete merge` correctly refuses to fall back to a PR (F-012), but the
  finish is then left half-done: the feature branch pushed with its bookkeeping
  commit, never merged, and the claim never cleared from shared truth. The loop
  turns that non-zero finish into `EXIT_GENERIC` and stops.
* **It succeeds and is wrong.** Git has no notion of "this row must be gone", so
  an unrelated nearby edit that shifts line context can retain a row a lane
  removed. The reporter saw this once in production.

The reporter's own diagnosis was right, and the reason it is right is worth
recording: the correct landed content is never actually ambiguous.
`do-next-available-task` registers every claim **on the integration branch** and
pushes it immediately, *then* branches. So integration's committed registry is
current for every claim except the one now finishing, and the only safe
post-condition is one computed from integration's own content —
**integration's registry at fetch time, minus the finishing node's row** —
independent of the feature branch's necessarily-stale copy.

The merge is therefore staged with `--no-commit --no-ff`, those three paths are
recomputed, and only then is the merge commit created. Conflicts anywhere else
abort with the existing wording, unchanged.

**Resolution is unconditional, not conflict-triggered.** This is the load-bearing
part, and the reason a "detect conflicts in these paths and resolve them" fix
would have been insufficient: the absence of a conflict is not evidence of a
correct result. The clean-but-wrong case never invokes a resolution path at all.

Two orderings are load-bearing, and both are easy to get backwards:

1. **Merge, then regenerate.** The node's status change lives in a roadmap JSON
   chunk, not in the three deterministic files. The chunks must merge normally —
   concurrent lanes touch different nodes' chunks — and only then can the derived
   files be re-rendered *from the merged result*. Regenerating first would drop
   the other lane's work.
2. **Regenerate the digest again after the commit exists.** `roadmap-context.md`
   lists dependency edges that were added and later removed, and that section
   comes from a `git log --first-parent` walk of **HEAD**. Rendered before the
   merge commit exists, the walk cannot reach the feature branch's commits at
   all — under `--first-parent` they only become visible as the merge's own step.
   Skipping that second pass lands a digest missing the line and hands CI the
   `digest --check` drift finding 20 closed one release ago. It converges in a
   single pass because the event feed is built from `roadmap/*.json` and
   `planning/*.md`, and the amend only ever rewrites the registry and the two
   generated files.

The **milestone rollup** path shares the flaw and is fixed the same way: it lands
bookkeeping with `git cherry-pick`, which is a 3-way merge over the same three
files. Cleanup could not be shared, though — `cherry-pick --abort` is unavailable
after `cherry-pick --no-commit`, because git never starts a sequencer and abort
exits 128 with "no cherry-pick or revert in progress", leaving the conflicted
paths in the worktree. That path resets to the commit it started from instead.

`--no-ff` is now unconditional on the feature merge, and that is required rather
than incidental: a fast-forward has no commit of its own, so there would be
nowhere to record the resolved registry and the stale feature copy would become
integration's tip verbatim.

The feature branch's bookkeeping commit still deregisters and still regenerates.
That is deliberate: `--on-complete pr` never reaches the landing path at all, so
moving the removal there would leak every PR-mode claim forever; the feature
branch also has to be self-consistent for its own CI. The consequence to expect
is that `roadmap/registry.yaml` now routinely differs between the bookkeeping
commit and the merge commit that lands it. The merge commit is authoritative.

**A note on reproduction.** The conflict half is trivial to reproduce and is
covered. The clean-but-wrong half was **not** reproducible here: 595 randomised
two-lane scenarios (uniform and variable-size entries, removals combined with
concurrent registrations) produced 205 clean merges and zero wrong ones. That is
not a challenge to the report — real registries carry content these fixtures do
not, and the reporter observed it — and it does not affect the fix, which is
unconditional either way. It does mean the regression test asserts the
*invariant* (landed content equals integration minus the row, whatever the stale
copy says) rather than trying to pin one of git's alignment quirks. That is the
more durable assertion regardless.

## 28. Quoting is not text

`docs/grind-session.md` recommends exactly this shape:

```bash
--implement-cmd 'claude -p --permission-mode acceptEdits "$(cat "$SPECY_ROAD_PROMPT")"'
```

`_resume_command` rebuilt it with `shlex.split` and then `shlex.quote` on every
token. That round trip is safe for literal arguments and destroys shell syntax:
the substitution flattens to the literal token `$(cat $SPECY_ROAD_PROMPT)` and
comes back single-quoted, so it can never expand. The command runs under a
shell, so on a genuine resume Claude silently received 26 characters of shell
source as its prompt — no error, no warning, and whatever it did with that
looked like ordinary output rather than a failure the loop would catch. The same
document promises "your own flags are passed through untouched", which is
precisely the guarantee that was broken.

Only real resumes were affected, because the first attempt always executed the
original, un-round-tripped string. `--resume` is now spliced in behind the
executable token and everything after it is copied byte for byte.

No warning is emitted for `$(…)` or backticks. With the splice they expand
correctly, and a warning nobody can act on is noise in an unattended log.

The test gap was structural and is worth naming: the `CLAUDE` fixture had no
command substitution in it, so no amount of testing around the old resume path
could have caught this. The new coverage includes a test that runs a real shell
against a fake `claude` on disk and asserts the *file's contents* — not its
source text — reach the resumed attempt.

## 29. A process that vanished is not a task that failed

`classify_limit("")` is `NONE`, so a hook whose process tree was killed before
it printed anything fell through to "an ordinary failure" and returned its raw
exit code — indistinguishable from a legitimate task failure, and the end of an
unattended run. The reporter's trigger was environmental rather than a toolkit
bug, but the handling gap was real.

The new category is deliberately narrow: it requires **both** entirely empty
output **and** a signal-shaped exit code (negative, or 128+). Empty output alone
would swallow a task that failed quietly — a linter exiting 1, a `set -e`
script — and turn one honest failure into three pointless runs; a signal code
alone would retry a real crash that already printed a traceback. Together they
describe only "something outside the run killed it".

It re-runs the **same command** rather than resuming. With no output there is no
session id from Claude, and `latest_session_id` matches on the repo rather than
the node, so it could easily resurrect the previous leaf's transcript — feeding
the wrong task context into a session that then commits, which is the same class
of silent-wrong-work bug as finding 28. The correlation also runs the right way:
`claude -p` streams, so a run that printed *nothing* died early, before
meaningful work.

`MAX_RESUMES`, `MAX_WAIT_SECONDS` and `GRACE_SECONDS` were module constants with
no override, so a plan whose limit resets on an 8-hour cadence hit the 6h ceiling
and stopped the run rather than waiting the extra two hours. All four bounds are
CLI flags now, also settable as `grind_session_*` keys in
`roadmap/git-workflow.yaml`, with the flag winning.

Two placement decisions worth recording. The resolver lives beside the loop
rather than in `git_workflow_config.py`, whose `_flag` helper is boolean-only and
which was within 55 lines of the file cap. And `ImplementLimits.defaults()` reads
the module constants **at call time** instead of binding them as dataclass field
defaults, which would fix the values at class creation and silently ignore the
tests that patch them.

A safety property that falls out for free: a schema-invalid `git-workflow.yaml`
cannot quietly downgrade these bounds to their defaults, because `on_complete`
resolution reads the same file first and the loop refuses to start.
