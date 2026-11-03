# The review gate

How records count, `Reviewed-by` trailers, signed reviews, `handoff status`, and review-loop escalation. Roles, hand-off files, and sharing a checkout stay in [orchestration.md](orchestration.md).

`specy-road mark-implementation-reviewed`, run on the feature branch, counts a
review record only when:

- it validates, and its `node_id` is this node;
- its `commit` resolves, through git, to the commit under review — any later
  commit makes it stale, so a substantive fix restarts every review. Every
  merge counts as new work, including `git merge -s ours`, whose tree equals
  its first parent's; commits that touch only `roadmap/registry.yaml` are
  skipped, so claim bookkeeping does not;
- its model is a rostered reviewer, or the substitute in an active substitution that covers this
  node; its family comes from the roster, and its roster `may_process` includes the node's `sensitivity`;
- no other record from the same model already counts — one vote per model, and
  a block from any of a model's records wins;
- it attests a fresh session when policy requires one.

Executors write READY with `specy-road ready <NODE_ID> --model <roster id> --verify '<cmd>=<exit>' ...` (one `--verify` per verifier or test run; the last `=` splits, so the command may contain one). From any worktree it writes `READY-<model>.md` into the node's hand-off directory below, with `branch` the checked-out branch, `commit` the commit under review at `HEAD`, `base` its merge base with the integration branch, and `changed_paths` the branch's diff. It refuses, writing nothing, when a `--verify` exit is non-zero or the file would not pass the checks `handoff status` makes (a branch other than the registered one, an `agent` outside `[A-Za-z0-9._-]`). A check that fails without the fix on purpose is red-green evidence, not a verifier: pass it as `--red-green '<cmd>=<exit>'` and it goes under `## Red-green evidence` in the notes, where it does not gate; `--note` adds free text. A READY written by hand from `work/handoff-ready.template.md` is still read and validated the same way.

The newest valid `READY-<agent>.md` for the node's registered branch lists verifier commands the executor ran. A non-zero exit in that list is treated as a gate failure: `handoff status`, `mark-implementation-reviewed`, and `finish-this-task` all refuse while any failing command is unmarked. An approving review may name commands in `verify_pre_existing` when the same command already fails on the integration branch; only approving records count. The claim alone clears nothing: `specy-road review check-pre-existing <NODE_ID>` runs each claimed failing command twice through the shell, at the project root of a detached temporary worktree of the integration branch tip (removed afterwards), and writes `work/reviews/<NODE_ID>/PRE-EXISTING.md` with `integration_commit` and one `{cmd, exits: [first, second]}` per command. It exits 0 when every command failed both times, else 1 with `claim-rejected: <cmd>` for each command that exited 0. The gate clears a failing verifier only when that file lists it with two non-zero exits and its `integration_commit` is still the integration tip; otherwise the problem stays, ending with `(unverified)`, `(rejected)` or `(stale: <sha>)` — re-run the check after the tip moves. An empty `verify` block is still reported but does not by itself fail the gate.

The same READY file may declare optional `blocked_on`: a list of `{acceptance, reason}` naming acceptance ids (`A1`…`An` from the brief) the executor could not meet without deleting, skipping or weakening an existing test, or raising a baseline or cap. While that READY is current at the commit under review, `handoff status` reports `executor_blocked` (ahead of `blocked` and `escalated`, whose records and problems stay listed), prints one line per entry as `A<n>: <reason>`, and the gate stays unmet until the coordinator resolves the block (for example by amending the leaf on the integration branch) and the executor hands off again without `blocked_on`. A `blocked_on` on a READY for an earlier commit does not bind later commits; they are judged on their own records.

The gate passes when no counted review blocks and the counted approvals reach
`reviewers_required` (by distinct family when configured). On success it sets
`implementation_review: approved` in the registry and adds one
`Reviewed-by: <model> (<family>) approve <commit>` trailer per approval to that
commit.

`finish-this-task` checks the gate again at the current commit, so work
committed after approval cannot ship on the earlier reviews.

**Under the default policy** the interactive menu's **approve** files
`REVIEW-human.md` and closes the gate in one step; a human approval is offered
only when it would complete the policy. **`--yes` never creates a review:** it
commits an approval only when the recorded reviews already satisfy the policy,
and without a TTY and without `--yes` the command refuses, as in 0.2.x. A
coordinator that can satisfy the gate alone is no gate.

## Signed reviews

A review record is a file, so without more, any agent that can write under
`work/reviews/` can pose as a rostered reviewer. Signing closes that:

```yaml
roster:
  - id: opus
    family: anthropic
    roles: [reviewer]
    public_key: ssh-ed25519 AAAAC3...   # the reviewer's OpenSSH public key
policy:
  signed_reviews: true
```

The reviewer files its record with `specy-road review record … --sign-key
~/.ssh/opus_review` (an OpenSSH private key). The front matter is signed with
`ssh-keygen -Y sign` (namespace `specy-road-review`) and verified against the
roster `public_key` with `ssh-keygen -Y verify`; OpenSSH 8.1+, no other
dependency. With `signed_reviews: true` an unsigned record does not count;
with it off, a present signature is still verified, so a tampered front matter never
counts. `review record` also signs `notes_sha256`, the notes' hash, so a record whose
notes changed, or a signed one without it, never counts. A human approving interactively passes `--sign-key` to
`mark-implementation-reviewed`, with a `public_key` on the `human` entry; a wrong key is refused before any record is written.

The boundary is the key: run each reviewer with a private key the executor's
process does not hold. Still self-attested: the session flags inside a signed record
(the key proves who signed, not how they worked) and presence files, which stay advisory.

`specy-road handoff status [<NODE_ID>] [--json]` shows each node's state:

| State | Meaning |
|---|---|
| `waiting` | No valid READY file. |
| `in-review` | READY matches the commit under review; the policy is not met yet. |
| `executor_blocked` | The current READY declares `blocked_on` at the commit under review; the executor stopped rather than weaken tests or raise a baseline or cap. |
| `blocked` | A counted review blocks. |
| `approved` | The policy is met. Run `mark-implementation-reviewed`. |
| `stale` | The branch moved past the READY commit. |
| `escalated` | The review loop is not converging (see below) and no RCA record covers it; the trigger is named. |
| `complete_no_claim` | The node is Complete and its claim is released; its records are listed, not evaluated (`--ref` evaluates them). |
| `leaves_open` | A milestone with a leaf not yet Complete at the integration tip; its full review has not started (below). |
| `awaiting_full_review` | A milestone whose leaves are all finished waits for its full review at the integration tip (below); `approved` once the gate is met there. |
| `unclaimed`, `error` | No open claim names a commit, so the gate cannot be evaluated and the records are only listed (pass `--ref`); `error`: the node or `--ref` does not resolve. |

Below each node it lists every problem to fix. Given one `<NODE_ID>`, the exit status is for a polling script: `0` the policy is met (`approved`) or the node is `complete_no_claim`; `1` it is not met (`waiting`, `in-review`, `blocked`, `executor_blocked`, `stale`, `escalated`); `2` it cannot be determined (`unclaimed`, `error`, or `--ref` without a node). The sweep with no `<NODE_ID>` only reports and exits 0. **Review-loop escalation:** a round is one reviewed commit in `history/`; when the last `escalate_same_acceptance_blocks` rounds all block on one acceptance id, or after `escalate_review_rounds` rounds, an unapproved leaf is `escalated` with its trigger named (`review list` prints it too, and reviewer prompts say so). `specy-road prompt <NODE_ID> --role rca --model <id>` (a rostered reviewer that neither implemented nor reviewed the leaf) then builds a root-cause prompt from the brief, every round's records side by side and the diffs between them; the analyst writes `RCA-<round>.md` beside the reviews with a classification (specification, implementation, test, reviewer, environment, hard problem), cited evidence, the cheapest corrective action and, for a specification cause, a proposed acceptance rewrite for a human to approve. A valid record resolves the trigger and counting restarts; an invalid one is listed as a problem. Design: [design-notes/review-loop-rca.md](design-notes/review-loop-rca.md).

## Milestone full review

Leaf reviews are leaf-sized, so a regression that only shows across two leaves of one milestone can pass both. With `policy.milestone_full_review: true` in `roadmap/orchestration.yaml` (the default, read from the integration branch like the rest of the policy) a milestone, meaning any node with leaf children, gets one full review of its combined change before it is marked Complete:

- **The hold.** When `finish-this-task` closes the last leaf under a milestone, it leaves the milestone's own status as authored instead of setting it Complete, prints `[hold] <MILESTONE_ID> rolled up to Complete but …` with the reason and the next commands, and opens `work/reviews/<MILESTONE_ID>/` so `handoff status` lists it. The public loader's computed `rollup_status` stays `In Progress` until the review is approved, so `roadmap.md`, the brief and the PM GUI agree with `list-nodes`. Every ancestor above the held milestone waits with it. The hold is released only by a gate met at an integration tip where every leaf under the milestone is Complete: at the last leaf's own finish that leaf has not landed yet, so the reason is `its leaves <ids> have not landed on <integration ref>`, and an approval recorded against the tip before the last leaf landed never counts, since that tip is not the combined change. The hold applies only while `require_implementation_review_before_finish` is on; a milestone owned by the milestone-rollup state machine (`milestone_execution`) is left to that machine as before.
- **The packet.** Once the branch has landed, `specy-road review-packet <MILESTONE_ID>` builds the packet for the integration tip; while a leaf is not Complete at that tip it refuses, as `review record <MILESTONE_ID>` does, naming the leaves. A milestone has no registry claim, so its commit under review is the tip of the integration branch (remote-tracking ref first, else local) and its base is the first parent of the oldest `chore(rm-<codename>): register as in-progress` commit of any leaf under it that the tip reaches: the point the first leaf branched from, so the diff is every leaf's change together. `--base <ref>` overrides it, and the command refuses with that hint when no leaf registration is reachable (leaves landed without pickup). The header names the leaves covered, and the implementation summary section says the leaf summaries were reviewed with their leaves. `--ref` reviews another commit instead of the tip.
- **The records.** Reviewers file `specy-road review record <MILESTONE_ID> --model <id> --verdict approve|block --file <notes.md>` against that commit, with an empty `acceptance` map (a milestone has no acceptance ids of its own). The gate is the leaf gate at that commit, so `reviewers_required` and `reviewers_distinct_families` apply unchanged, and a new commit on the integration branch makes the records stale as for a leaf.
- **The release.** `specy-road mark-implementation-reviewed <MILESTONE_ID>` must run on the integration branch checkout with `HEAD` at the commit under review (the remote-tracking tip when there is one): before it reads a record, prompts, or writes anything it refuses on another branch, on a local integration branch behind or ahead of that tip (pull or push first), or while a leaf is not Complete there. It then evaluates the gate at that commit (the interactive human approval and `--yes` behave as for a leaf) and on success sets the milestone and the stale ancestors above it Complete, regenerates the exported files, and commits them as `roadmap: <MILESTONE_ID> full review approved; status -> Complete` with the `Reviewed-by` trailers. `handoff status <MILESTONE_ID>` shows `leaves_open` (exit 1) while a leaf is not Complete at the tip, `awaiting_full_review` (exit 1) until the gate is met, `approved` with the release command once it is, and `complete_no_claim` afterwards; `review list <MILESTONE_ID>` prints the same next step under the gate line.

With `milestone_full_review: false` the last leaf's finish sets the milestone Complete at once, as before, and the computed rollup is Complete as soon as every leaf is.

## The hand-off directory in a worktree

`work/reviews/<NODE_ID>/` is one directory: the **main checkout's**, whichever
worktree a command runs in. `review-packet`, `review record`, `handoff status`,
`mark-implementation-reviewed` and `worker delegate` all resolve it through
one function, which reads the linked worktree's `.git` file (and the
`commondir` it points to) instead of running git, so a sandboxed process that
git refuses to serve still finds the same directory. A worktree's own
`work/reviews/` is never read. A project nested below the git root (`sr/`)
keeps its directory at the same place under the main checkout; a separate
clone has its own.

That directory is the one path a reviewer must be able to write: `review
record` files the verdict there. The reviewer prompt names it, absolute, as
the **writable root**, so a harness sandboxed to the leaf's worktree can be
launched with it as a writable root (Claude Code `--add-dir`, as below);
without it the record cannot be filed. The executor prompt names the same
directory for `READY-<agent>.md`.

## Reviewer launch mode

A reviewer is a fresh session reading a branch it did not write, so that branch
must not run code in the reviewer's session before the reviewer has read it.
Claude Code's headless docs say that without `--bare`, a `-p` session runs the
hooks in a project's `.claude/settings.json` and connects the servers in its
`.mcp.json`, even in a folder you have never trusted, with no trust dialog or
per-server prompt ([code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless)).
A leaf that edits those files would run its own code in its reviewer's session.
Bare mode loads none of them (nor skills, plugins or CLAUDE.md), and it starts
faster.

`specy-road prompt <NODE_ID> --role reviewer --model <id> --channel cli`, for a
roster entry with `harness: claude-code` and no `channels.cli`, therefore runs

```text
claude -p "<instruction>" --bare --model <api_id> [--effort <level>] --permission-mode acceptEdits \
  --allowedTools Read,Edit,Bash --add-dir <work/reviews/NODE_ID> < <prompt file>
```

`--add-dir` lets the reviewer write its notes into the hand-off directory, which
is in the main checkout even when the reviewer runs in a worktree. Bare mode
never reads OAuth credentials or the keychain, so it needs `ANTHROPIC_API_KEY`
(or an `apiKeyHelper`) instead of a subscription login; the command prints a
note saying so. A `channels.cli` is run as written, and other harnesses use
their profile's `access.cli` as before.

The reviewer prompt asks the reviewer to say how it was started:
`specy-road review record … --launch-mode full|bare|explicit` stores
`launch_mode` on the record (before signing, so a signature covers it):

| Value | The reviewer's harness |
|---|---|
| `full` | loaded the repository's hooks, MCP servers and instructions, as an interactive session does |
| `bare` | loaded none of them (Claude Code `--bare`) |
| `explicit` | loaded only the settings and MCP servers its command named (for example `--setting-sources` with `--strict-mcp-config`) |

The field is optional and self-attested, like `fresh_session`; the gate does
not read it. `handoff status` prints it on each review line (`launch mode
bare`) and in `--json` as each review's `launch_mode`.

## Delegating a reviewer

`specy-road review delegate <NODE_ID> --model <roster id>` runs one rostered reviewer the way `worker delegate` runs an executor, but waits for it: a reviewer has one turn to take, and the command's answer is whether it filed a record.

1. It builds the reviewer prompt (`specy-road prompt --role reviewer`, so the packet must exist: run `review-packet` first) and writes it to `work/prompt-<NODE_ID>-reviewer-<model>.md`. The model needs the reviewer role or an active substitution, as for `review record`.
2. It runs the roster entry's `preflight`, then launches the entry's harness in this checkout's git root (`--worktree` names another). A `claude-code` entry without `channels.cli` runs bare, as above, with `--session-id <uuid>` and `--output-format stream-json` added; any other entry runs its `channels.cli` (with `{session}` or `{session_flag}` for a session id) or its harness's default command, which for Codex is `codex exec` with a `workspace-write` sandbox: the hand-off directory must lie inside it, so run a Codex reviewer from the main checkout.
3. It records the run in `work/reviews/<NODE_ID>/RUN-<model>.json`: the commit under review, the harness's native session id, one entry per attempt (exit, whether it was a capacity error, the error text) and the final `state`. Raw output goes to `RUN-<model>.log` beside it.
4. When an attempt fails with a provider capacity or rate-limit error (`429`, `529`, `overloaded`, `rate limit`, `usage limit`, `quota`, `RESOURCE_EXHAUSTED`, …), it waits `--backoff` seconds (default 30, doubled each time) and tries again, at most `--retries` times (default 3). A retry resumes the session the harness reported, with a short continue prompt; when none was reported, it launches afresh. Any other failure is not retried.
5. The run is `complete` when a valid `REVIEW-<model>.md` for the commit under review exists afterwards, and the command exits 0; otherwise it is `incomplete`, with the reason (the capacity error after the last attempt, the harness's exit, no record filed, an invalid record, or a record for another commit), and the command exits 1. Exit 2: the harness cannot resume.

`--resume` continues the recorded session with the continue prompt instead of starting a fresh one. It is refused when the run file has no session, names another harness, or was for another commit: a session that reviewed an earlier commit starts a fresh review instead. `--json` prints the run record.

`handoff status` lists each run under the node (`RUN-opus.json: incomplete run by opus at <sha>, session <id>: <reason>`, marked `not the commit under review` when it is for an older commit), and in `--json` as `review_runs`, each with `current`. An incomplete run at the commit under review is also a problem naming the command to re-run. A record left from an older commit is never shown as the current verdict: it is listed only as a problem (`reviewed <sha>, not the current commit — re-review`); without a claim each record line says the commit it reviewed (`at <sha>, not evaluated`), and `review list` marks one that is not the commit under review `stale`.

## Test integrity in the review packet

`specy-road review-packet` inserts a **Test integrity** section immediately after **Changed paths**. It lists the same one-line findings as `specy-road integrity <NODE_ID>` (removed tests, removed test files, new skips, lost asserts, pytest-related config edits, new lint suppressions, widened baselines), or `_none_` when there are none. The section is computed from git objects only and is byte-identical for the same base and head commits. Reviewers use it to spot test weakening without running the CLI separately.

Two findings work for any language. `new-suppression: <path>:<line>` marks each line the leaf adds, in any file, that contains `noqa`, `type: ignore`, `pragma: no cover`, `pylint: disable`, `eslint-disable`, `@ts-ignore`, `@ts-expect-error` or `nolint` (any case); `<line>` is its number at the commit under review. `baseline-widened: <path> +<added lines>` names each file listed in `policy.ratchet_paths` (git-root-relative paths, read from the integration branch like the rest of the policy) that the leaf adds lines to; a leaf that only removes lines from it gets nothing. List there the baseline files a leaf should only shrink, such as clone, private-import, mutation or size baselines. Design: [design-notes/regression-prevention.md](design-notes/regression-prevention.md).

## Tests at risk

`specy-road impact <NODE_ID> [--ref REF]` prints, sorted and one per line, every Python test file (`test_*.py` or `*_test.py`) that imports, directly or through the repository's own modules at any depth, a module whose file changed between the merge base and REF. The import graph is built with `ast` over every `.py` file in the git tree at REF, parsed from its bytes so a coding cookie is honoured, with relative imports resolved and namespace packages followed. Paths are git-root relative, like `specy-road integrity`. A changed `conftest.py` makes the output the single line `ALL`. Otherwise a final `not analysed: <n> files` line counts the changed files that are not Python, plus any `.py` file at REF that does not parse. With `--zones` it starts from the modules under the node's touch zones at REF instead of the diff. It is advisory: it exits 0 whatever it lists and never decides a gate.

The executor prompt written at pickup has a **Tests at risk** section with the `--zones` list at the pickup commit (or `_none found_`), and `review-packet` has a **Tests at risk** section after **Test integrity** with the diff list. Both show at most 50 paths, then a count of the rest; the packet's section is computed from git objects only and is byte-identical for the same base and head commits. Imports the static graph cannot see (a script run in a subprocess, `importlib` with a computed name) are not followed.

## The diff in the review packet

The packet's **Diff** section inlines whole files only, within two budgets: `--max-diff-lines` (default 1500) and `--max-diff-bytes` (default 200000), since a rebuilt minified bundle is a few very long lines that the line budget alone lets through. Files are inlined in diff order until one would pass either budget; it and every file after it are listed with their `+`/`-` counts and the bytes of their diff, and the full diff is written to `work/reviews/<NODE_ID>/DIFF.patch`. `0` lifts a budget.

A generated file is never inlined, whatever the budgets: one under `specy_road/pm_gantt_static/` (the packaged PM GUI bundle), or one that a `.gitattributes` line marks `linguist-generated`, read at the commit under review. It is listed the same way and marked `generated`, the packet says generated files are never inlined, and its diff is in `DIFF.patch`. Review the source it is built from instead.

## The integrity gate

With `policy.integrity_gate: true` in `roadmap/orchestration.yaml` (default false), read from the integration branch like the rest of the policy, each `specy-road integrity` finding for the commit under review (against its merge base with the integration branch) is a gate problem unless its exact line is in the node's `planned_test_changes` **as committed on the integration branch**. `handoff status` lists each one as `integrity (undeclared): <finding>`, and `mark-implementation-reviewed --yes` and `finish-this-task` refuse while any remains. A declaration on the leaf branch does not count: the leaf approved before pickup is the waiver, so an executor cannot write one. A removal discovered mid-implementation is a `blocked_on` stop until the coordinator amends `planned_test_changes` on the integration branch; see [roadmap-authoring.md](roadmap-authoring.md). With the policy off or absent the gate ignores findings.

## Red-green evidence

A passing test proves little unless it would have failed without the change. With `policy.red_green: true` in `roadmap/orchestration.yaml` (default false), read from the integration branch like the rest of the policy, the tests under check are exactly the Python test functions (`test_*` in `test_*.py` or `*_test.py`, at module or class scope) whose source differs between the merge base and the commit under review, or that exist only at that commit.

`specy-road review red-green <NODE_ID> [--ref <branch or commit>]` runs each test under check by node id (`python -m pytest <path>::<name>`, one run per test, with the interpreter that runs specy-road, from the worktree's git root) twice: in a detached temporary worktree of the merge base with only the head's versions of the changed test files overlaid, and in a detached temporary worktree of the commit under review. Both worktrees are removed afterwards, so `git worktree list` ends as it began. It writes `work/reviews/<NODE_ID>/RED-GREEN.md`:

```yaml
---
commit: <full sha of the commit under review>
base: <full sha of the merge base>
tests:
  - {test: tests/test_x.py::test_new, base: fail, head: pass}
---
```

Each outcome is `pass`, `fail` (a failure in the call phase in pytest's JUnit XML) or `error` (a collection or setup error, or nothing ran: the node id was not found or every case skipped). A test the node lists in `planned_test_changes` (on the integration branch) as `preserve: <path>::<name>` must pass at base and at head; every other test under check must fail at base and pass at head. The command prints the same problems the gate would and exits 1 when there are any.

With the policy on, the gate adds `red-green: missing` when the file is absent or unreadable, `red-green: stale (<sha>)` when its `commit` is not the commit under review (re-run the command after every new commit), and otherwise one problem per test that breaks the rule: `not-green: <id>` when it does not pass at head (or, for a `preserve` test, at base), else `not-red: <id>` when it does not fail at base. The tests under check are computed again from git, so a test left out of the record is a problem too. A test that errors at base (for example, its module cannot import the function the leaf adds) is not red: only an assertion that fails in the call phase is evidence. With the policy off or absent the gate ignores red-green evidence. This checks test-first evidence; it does not tell executors to work test-first. Design: [design-notes/regression-prevention.md](design-notes/regression-prevention.md).
