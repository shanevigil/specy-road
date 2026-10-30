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

The newest valid `READY-<agent>.md` for the node's registered branch lists verifier commands the executor ran. A non-zero exit in that list is treated as a gate failure: `handoff status`, `mark-implementation-reviewed`, and `finish-this-task` all refuse while any failing command is unmarked. An approving review may name commands in `verify_pre_existing` when the same command already fails identically on the integration branch; only approving records count, and every failing READY verifier must be named by at least one approving reviewer before the gate can pass. An empty `verify` block is still reported but does not by itself fail the gate.

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
