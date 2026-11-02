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

The newest valid `READY-<agent>.md` for the node's registered branch lists verifier commands the executor ran. A non-zero exit in that list is treated as a gate failure: `handoff status`, `mark-implementation-reviewed`, and `finish-this-task` all refuse while any failing command is unmarked. An approving review may name commands in `verify_pre_existing` when the same command already fails on the integration branch; only approving records count. The claim alone clears nothing: `specy-road review check-pre-existing <NODE_ID>` runs each claimed failing command twice through the shell, at the project root of a detached temporary worktree of the integration branch tip (removed afterwards), and writes `work/reviews/<NODE_ID>/PRE-EXISTING.md` with `integration_commit` and one `{cmd, exits: [first, second]}` per command. It exits 0 when every command failed both times, else 1 with `claim-rejected: <cmd>` for each command that exited 0. The gate clears a failing verifier only when that file lists it with two non-zero exits and its `integration_commit` is still the integration tip; otherwise the problem stays, ending with `(unverified)`, `(rejected)` or `(stale: <sha>)` — re-run the check after the tip moves. An empty `verify` block is still reported but does not by itself fail the gate.

The same READY file may declare optional `blocked_on`: a list of `{acceptance, reason}` naming acceptance ids (`A1`…`An` from the brief) the executor could not meet without deleting, skipping or weakening an existing test, or raising a baseline or cap. While that READY is current at the commit under review, `handoff status` reports `executor_blocked` (ahead of `blocked` and `escalated`, whose records and problems stay listed), prints one line per entry as `A<n>: <reason>`, and the gate stays unmet until the coordinator resolves the block (for example by amending the leaf on the integration branch) and the executor hands off again without `blocked_on`. A `blocked_on` on a READY for an earlier commit does not bind later commits; they are judged on their own records.

The gate passes when no counted review blocks and the counted approvals reach
`reviewers_required` (by distinct family when configured). On success it sets
`implementation_review: approved` in the registry and adds one
`Reviewed-by: <model> (<family>) approve <commit>` trailer per approval to that
commit.

`finish-this-task` checks the gate again at the current commit, so work
committed after approval cannot ship on the earlier reviews.

## Delta review of small fix rounds

A new commit makes every record stale, so each fix round normally needs fresh
full reviews. With `policy.delta_review` (in `roadmap/orchestration.yaml`, read
from the integration branch like the rest of the policy; **default true**), a
reviewer whose last counting approval was of an earlier commit of the branch may
review the next round from a **delta packet** when the change since that commit
(`git diff <approved>..<commit>`) meets all of:

- every changed path is a documentation file (`.md`, `.rst`, `.txt`, `.adoc`) or a
  test file (under a `tests`, `test` or `__tests__` directory, or named `test_*.py`,
  `*_test.*`, `*.test.*` or `*.spec.*`);
- it touches at most three files (both sides of a rename count); there is no line limit;
- the `specy-road integrity` report for that change has no findings (no removed or
  skipped tests, no lost asserts, nothing else it reports);
- every path is inside the leaf's touch zones; the leaf's own
  `work/implementation-summary-<NODE_ID>.md` counts as inside.

Otherwise the round gets the full packet. `specy-road prompt <NODE_ID> --role
reviewer --model <id>` applies the rule for that reviewer: when it holds it
writes `work/reviews/<NODE_ID>/PACKET-<model>.md` and hands that reviewer that
packet instead of `PACKET.md`. It has the usual sections computed over the
change since the approved commit (the **Base** line names it), the whole diff
inlined, and a **Delta review** section with that reviewer's notes on the
approved commit. Every other reviewer gets `PACKET.md` as before.

The reviewer then adds `delta_from: "<approved commit>"` to its record's front
matter. The gate counts an approval naming `delta_from` only when a counting
approval of that commit by the same model is on file (`history/` keeps every
filing), and only while the change since still meets the rule above under the
current policy. An earlier approval counts only if it would have counted at its
own commit:
- it has a result for every acceptance id in the brief;
- it passes the roster, session and signature checks;
- if it names `delta_from` itself, its own delta qualified.

A delta approval the gate rejected is therefore never the start of a later delta. Otherwise `handoff status` lists it as `does not count — a delta
review from <sha>, …; a full review is needed`. A delta approval is still one
model's vote, so `reviewers_distinct_families` still needs approvals from both
families at the current commit. A block is never affected. Like
`fresh_session`, `delta_from` is self-attested; a signature covers it.

Full fresh review comes back two ways. `specy-road review-packet <NODE_ID>
--full` stamps `PACKET.md`; while that packet is the one for the commit under
review, no delta packet is built and no `delta_from` approval counts. Rebuilding
the packet without `--full`, or a new commit, lifts the stamp. `delta_review:
false` turns the rule off everywhere.

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
| `unclaimed`, `error` | No open claim names a commit, so the gate cannot be evaluated and the records are only listed (pass `--ref`); `error`: the node or `--ref` does not resolve. |

Below each node it lists every problem to fix. Given one `<NODE_ID>`, the exit status is for a polling script: `0` the policy is met (`approved`) or the node is `complete_no_claim`; `1` it is not met (`waiting`, `in-review`, `blocked`, `executor_blocked`, `stale`, `escalated`); `2` it cannot be determined (`unclaimed`, `error`, or `--ref` without a node). The sweep with no `<NODE_ID>` only reports and exits 0. **Review-loop escalation:** a round is one reviewed commit in `history/`; when the last `escalate_same_acceptance_blocks` rounds all block on one acceptance id, or after `escalate_review_rounds` rounds, an unapproved leaf is `escalated` with its trigger named (`review list` prints it too, and reviewer prompts say so). `specy-road prompt <NODE_ID> --role rca --model <id>` (a rostered reviewer that neither implemented nor reviewed the leaf) then builds a root-cause prompt from the brief, every round's records side by side and the diffs between them; the analyst writes `RCA-<round>.md` beside the reviews with a classification (specification, implementation, test, reviewer, environment, hard problem), cited evidence, the cheapest corrective action and, for a specification cause, a proposed acceptance rewrite for a human to approve. A valid record resolves the trigger and counting restarts; an invalid one is listed as a problem. Design: [design-notes/review-loop-rca.md](design-notes/review-loop-rca.md).

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
