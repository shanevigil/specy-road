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
