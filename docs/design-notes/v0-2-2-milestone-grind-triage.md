# Triage: `v0.2.2` milestone-grind report

> **Status:** assessment only. Nothing here is fixed yet; the calls below are
> the proposed dispositions, not a changelog.

Assessment of a report written after a single-lane grind through two roadmap
phases — M1 start to the M2.14 human gate, thirteen of fourteen agentic
milestones closed — driven by `grind-session --plan` for wave planning and then
by **manually dispatched sub-agents** rather than `--implement-mode hook`. That
last detail is not incidental. Most of the friction in this report traces back
to the reporter never discovering the hook path at all (finding 35), and the
stall pattern they describe — sub-agents that `git pull`, read the brief, and
stop — is the failure mode the hook contract exists to prevent.

The run was against **`v0.2.2`**. `v0.2.3` has since landed and closes one of
the reported items outright; see finding 40.

Confirmed working, and worth preserving: `grind-session --plan` as a read-only
planning surface (the reporter used `--under M1` / `--under M2` to scope
parallel dispatch, which is what `parallel_batches` was built for), the pickup
artifact bundle — brief, prompt, `.on-complete` yaml and branch from one
command — and `search` / `show-node` / `history` for gate discovery. The final
plan snapshot reading `ready=0 closed=13 gates_open=1` is called out as the
thing that made stopping at M2.14 unambiguous, which is the intended use.

## Summary

Numbering continues the previous note, which ended at 29.

| # | Finding | Call |
|---|---|---|
| 30 | An in-flight claim is reported as a dependency block (exit 3) | **Defect** |
| 31 | Re-pickup treats "branch already exists" as a failed claim and clears the registry | **Defect** |
| 32 | `finish-this-task` cannot tell a claim from an implementation | **Feature** |
| 33 | `finish-this-task` does not commit sibling repositories | **Out of scope as stated** |
| 34 | `grind` is not a command, and nothing suggests `grind-session` | **Defect** |
| 35 | The orchestration path is invisible from the scaffold | **Defect** |
| 36 | No `why-blocked <NODE_ID>` | **Feature** |
| 37 | No CLI for open gates | **Feature** |
| 38 | `list-nodes --status` is unrecognised | **Feature** |
| 39 | Touch-zone warnings flood every invocation | **Feature** |
| 40 | Merge fallback; auto-pick order vs wave order | **Already fixed / as intended** |

## 30. Blocked and in-flight are not the same stop

The loop has three ways to run out of work, and only two of them are
distinguishable to a caller. `_handle_no_ready` consults `plan.blocked` first
and returns `EXIT_BLOCKED` with "N leaf/leaves waiting… Human action required".
It never consults `plan.active` — even though `session_plan.py` computes that
bucket, and `--plan` renders it as `_In flight (already claimed / In
Progress):_`. So the reporter got a message naming a dependency wait while the
plan output sitting next to it named the real cause: their own open claim on
`M1.3.2`.

The ordering is the bug, and reordering the two checks is not quite the fix.
**Blocked and active are not mutually exclusive, and in a healthy grind they
almost always co-occur** — every leaf downstream of the in-flight one is blocked
*on it*. "`blocked` is non-empty" is therefore nearly always true at the moment
the loop stops, which makes it close to worthless as a discriminator. The
question that actually separates the two states is whether the thing everything
is waiting on is a claim this operator already holds.

The two states also demand opposite responses, which is why conflating them
stalls an unattended run. A dependency block genuinely needs a human to go do
something else. An in-flight claim needs `finish-this-task` or
`abort-task-pickup` and then a re-run — no judgement required, and a supervisor
could do it unattended given the right signal.

Three things follow:

* **Name the node and its branch.** The reporter's suggested wording is right,
  and both fields are already in hand at the point the message is built.
* **A distinct exit code**, not a reuse of 3. Exit 3's documented contract is
  "human action required" and the previous reporter built an external supervisor
  against exactly these codes; widening 3 to mean "or maybe just finish your own
  task" would break that supervisor silently. `EXIT_IN_FLIGHT = 6`.
* **`--resume-in-flight` cannot resume blindly.** `plan.active` unions two
  populations: rows in `roadmap/registry.yaml`, and nodes whose status is *In
  Progress*. In a multi-lane setup — the configuration the previous note was
  entirely about — most of those belong to **other clones**. Resuming one would
  mean two lanes implementing the same leaf against one integration branch,
  which is a fresh instance of the corruption finding 27 closed. Any resume must
  be scoped to claims this worktree can prove are its own: the feature branch
  exists locally, and the registry row matches. Anything else must stay a
  report, not an action.

## 31. "Branch already exists" is a resume signal, not a failed claim

`push_and_branch_with_self_heal` wraps the push-then-branch sequence and treats
**any** exception raised before `branch_created` as evidence the claim did not
take, calling `attempt_self_cleanup` to strip the registry row and push the
removal. For a failed push that is correct. For `git checkout -b` failing with
`fatal: a branch named 'feature/rm-…' already exists` it is precisely backwards:
that error means the claim landed on an earlier run and its branch is still
sitting in the worktree with, quite possibly, work on it.

So the toolkit responds to "you already have this" by deleting the record that
says you have it. That is why the reporter saw the branch error and registry
churn as one event rather than two — they are one event.

The ordering inside pickup is what makes the correct handling safe to state:
the registry row is committed and **pushed to the integration branch before**
the feature branch is created. Branch-exists is therefore unreachable unless the
claim is already durable on the remote. The failure should be classified rather
than caught wholesale — branch-exists checks the branch out and keeps the row;
everything else keeps today's cleanup unchanged.

Worth flagging for whoever implements it: a branch left behind by
`abort-task-pickup` is not a case, because that command deletes the local
`feature/rm-*`. A branch left behind by a **crashed** finish is, and checking it
out is still the right move — the resumed run then finds either work to finish
or an empty branch, and finding 32 is what would catch the second.

## 32. A claim is not an implementation

Two items in the report are one finding: `M1.5.1` marked Complete with no
frontend code, and sub-agents that register and then never implement.
`finish-this-task` validates the graph, writes bookkeeping, regenerates the
derived files and lands the branch. At no point does it ask whether the branch
contains any work.

The honest framing is that the toolkit already has the human-facing version of
this check — `work/implementation-summary-<NODE_ID>.md` and
`mark-implementation-reviewed` — and it is opt-in, so an unattended grind sails
straight past it. The reporter's suggestion, refusing to finish when nothing was
implemented, is the machine-checkable floor underneath that gate.

The check should key on **commits touching any declared touch zone**, measured
against the branch's merge-base with integration, and the reason for that exact
shape is the false-positive it avoids: plenty of legitimate leaves are
small — a docs-only node whose touch zone is `docs/`, a config change — and
they still produce a commit inside their zone. "Zero commits anywhere in the
declared zones" describes only a branch where nobody did anything.

Whether that is a hard refusal or a loud warning is a policy call for the
maintainer. A refusal is the stronger guarantee and matches the reporter's ask;
it also means a leaf whose touch zones are wrong now fails at finish instead of
merging. Given that `validate` already warns when a touch zone matches nothing
in the working tree (v0.2.2), the wrong-zone case is at least detectable
earlier.

## 33. Sibling repositories are not a concept the toolkit has

F-015 asks `finish-this-task` to commit and push sibling repositories. There is
no notion of a sibling repository anywhere in the codebase: `--repo-root`
resolves one root, touch zones are paths relative to it, and the registry,
graph and generated files all live under it. This is a new capability with real
design surface — which repositories, discovered how, what happens when one of
them fails to push, what the registry row means when a claim spans three
roots — and not a defect in the current one.

Recommend deferring pending a written design. The adjacent problem that *is* in
scope is finding 32: if the reporter's real pain is "finish said done and the
code was not there", the implementation check catches that within one repo,
which is where the roadmap's own touch zones point.

## 34. `grind` is not a command

`cli.py` falls through to a bare `unknown command: {cmd}` and exit 2 with no
suggestion. The reporter notes every new agent in the session hit
`specy-road grind --help` first.

Prefer a **did-you-mean** over an alias. An alias gives one command two true
names, and the usage text then has to document both or leave the second
undiscoverable; a suggestion built on `difflib.get_close_matches` over the
existing command names generalises to every command and every future typo, which
is the more useful shape for a CLI this wide. It costs about five lines in the
final `else`.

## 35. The orchestration path is invisible from the scaffold

The reporter never adopted hook mode and drove sub-agents by hand. That reads as
a preference until you look at what the toolkit tells them:

* `do_next_prompt.py` writes the post-pickup prompt and never mentions
  `--implement-mode hook`, `--implement-cmd`, or `grind-session` at all.
* `specy_road/templates/project/AGENTS.md` — the file every consumer repo gets,
  and the first thing an agent reads — documents `do-next-available-task` and
  `abort-task-pickup` and does not mention `grind-session` anywhere in its 50
  lines.

An agent working from the scaffold cannot learn that the orchestration path
exists. That is the root cause of the "hook mode never adopted" item and of half
the parallel-handoff item, and it is a documentation defect rather than a
preference.

The P2 papercut about a redundant `specy-road brief` after pickup belongs here
too: pickup already writes `work/brief-<NODE_ID>.md` and passes the path to the
prompt, but the prompt does not say so plainly enough for an agent to skip
re-running it. The same post-pickup banner fixes both.

## 36. `why-blocked <NODE_ID>`

Requested in the previous session's notes as well, which is a signal. Every
field the command needs already exists: `BlockedLeaf` carries `node_id`,
`codename`, `waiting_on` and a `reason` of `dependency` or `gate`, and
`--plan --json` already serialises all of it. The gap is purely that answering
"why is *this* node blocked" currently means computing and parsing a
whole-session plan. A thin wrapper over `compute_session_plan` that filters to
one id, and resolves the transitive chain rather than just the immediate
`waiting_on`, is a small piece of work.

## 37. No CLI for open gates

`plan.gates_open` already computes "gate nodes, not Complete, blocking at least
one scoped leaf" and `--plan` renders it under **Gates needing human action**.
`list-gates [--under NODE]` is that value with its own entrypoint, for the same
reason as 36: the reporter wanted the answer without the surrounding plan.

## 38. `list-nodes --status`

Confirmed — `roadmap_crud.py list-nodes` takes no arguments at all beyond
`-h`, so `--status` exits 2 on unrecognised arguments. A filter is a reasonable
addition; it should reuse the same status vocabulary the CRUD layer already
validates rather than introducing a second spelling.

## 39. Touch-zone warning volume

Nineteen lines per invocation, on every command that loads the graph. The
warning itself is the v0.2.2 addition that flags a touch zone matching nothing
in the working tree, and it is useful exactly once — the first time. A `--quiet`
flag is the reporter's ask and is fine, but consider whether the better default
is to collapse repeats into a count with the full list behind a flag: in an
unattended run nobody reads the log until something fails, and by then the
warnings have pushed the failure off the visible tail.

## 40. Already fixed, or working as intended

**Merge fallback** — "M1.4.2 finish succeeded on paper but dev wasn't merged" is
finding 27 from the previous note, and it was fixed in `v0.2.3`: landing a
finish no longer 3-way-merges `roadmap/registry.yaml`, which was the mechanism
by which a finish ended half-done with the branch pushed and nothing merged.
The reporter ran `v0.2.2`, one release short of it. Recommend confirming against
`v0.2.3` before treating this as open — and if it reproduces there, it is a new
finding with a different cause, not this one.

**Auto-pick order vs wave order** — this shipped in `v0.2.2` and the reporter
had it. `_parallel_batches` orders each batch by *pickup order* (tier, then
roadmap outline order) rather than by id, precisely so that a reader who
dispatches `parallel_batches[0]` in sequence sees the same first leaf the loop
would claim. `--interactive` already exists on `do-next-available-task` for
seam-first grinding. So the gap is documentation: neither `docs/grind-session.md`
nor the plan output explains the relationship, and the reporter reasonably
assumed a discrepancy. Worth a paragraph rather than a code change.
