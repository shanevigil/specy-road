# Orchestration: roles, hand-offs, and the review gate

specy-road separates three roles around a roadmap leaf and prescribes how work
passes between them. It still does not prescribe **which** agent, IDE, or vendor
fills a role — a human, Claude Code, Cursor, Codex, or a local model all fit.

- **Coordinator** — picks the leaf, creates the branch or worktree, assembles
  the review packet, closes the review gate, finishes the leaf, and changes
  roadmap status.
- **Executor** — reads the brief, changes only the leaf's touch zones, runs the
  verifiers, commits, writes a hand-off file, and **stops**.
- **Reviewer** — reads the review packet and nothing else, in a fresh session,
  and records approve or block.

A session that wrote a change never reviews it, and the coordinator's own
session is never a reviewer. These rules are recorded in every review record
and checked by the gate.

Background and the slices still to come:
[design-notes/v0-3-0-orchestration-slices.md](design-notes/v0-3-0-orchestration-slices.md).

## The flow

```text
coordinator  do-next-available-task            → work/brief-<ID>.md, feature/rm-<codename>
executor     implement, commit, write summary  → work/implementation-summary-<ID>.md
executor     write READY-<agent>.md            → work/reviews/<ID>/READY-<agent>.md
coordinator  specy-road review-packet <ID>     → work/reviews/<ID>/PACKET.md
reviewer(s)  read PACKET.md, write notes       → specy-road review record <ID> …
coordinator  specy-road handoff status <ID>    → approved?
coordinator  specy-road mark-implementation-reviewed
coordinator  specy-road finish-this-task
```

The review gate applies when `roadmap/git-workflow.yaml` sets
`require_implementation_review_before_finish: true` (the scaffold default).
`roadmap/orchestration.yaml` decides what "reviewed" means.

## `roadmap/orchestration.yaml`

Scaffolded by `specy-road init project`. A repo without the file gets exactly
the defaults shown here, so upgrading does not strand a solo maintainer.

```yaml
version: 1
roster:
  - id: human
    family: human
    roles: [coordinator, reviewer]
policy:
  reviewers_required: 1
  reviewers_distinct_families: false
  reviewer_fresh_session: true
substitutions: []
```

| Key | Meaning |
|---|---|
| `roster[].id` | The id reviewers pass as `--model`. A review counts only when its model is rostered with the `reviewer` role. |
| `roster[].family` | Vendor family (`anthropic`, `openai`, `human`, …). Independence is judged by family. |
| `roster[].roles` | Any of `coordinator`, `executor`, `reviewer`. |
| `policy.reviewers_required` | Approving reviews needed at the commit under review. Minimum 1. |
| `policy.reviewers_distinct_families` | Count approvals by distinct family, so two sessions of one family count once. |
| `policy.reviewer_fresh_session` | Records must attest `fresh_session: true`. |
| `substitutions[]` | A recorded decision letting `use` review in place of a usual reviewer: `slot`, `use`, optional `scope` (node ids; omit for all), `decided`, `expires_when` (prose), optional `expires` (date after which it stops counting). |

Roster entries also accept `profile`, `channels`, `may_process`,
`subagent_family_lock`, and `preflight`. They are validated now and used by later
slices (prompt generation, data-sensitivity routing).

For independent review by two model families:

```yaml
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: claude-opus-5.5, family: anthropic, roles: [reviewer]}
  - {id: gpt-6.1-sol, family: openai, roles: [reviewer]}
  - {id: composer-2.5, family: cursor, roles: [executor]}
policy:
  reviewers_required: 2
  reviewers_distinct_families: true
```

`specy-road validate` fails on a file that is present but invalid.

## Hand-off files: `work/reviews/<NODE_ID>/`

Plain files work across every harness, including IDE chats that cannot see each
other. Each file is Markdown whose YAML front matter is the machine-readable
part. When an executor works in a separate worktree, it writes the file by
**absolute path** into the coordinator's checkout.

### `READY-<agent>.md` — the executor's hand-off

```yaml
---
node_id: M1.2
agent: composer-2.5
branch: feature/rm-login-form
commit: 3f9c2e1          # the implementation commit the executor stopped at
base: 8a71d04            # the commit it branched from
changed_paths: [src/login.ts, tests/login.test.ts]
verify:
  - {cmd: "npm test -- login", exit: 0, tail: "12 passed"}
---
Optional notes for the coordinator.
```

Quote an all-digit SHA (`commit: "1234567"`) or YAML reads it as a number. The
tools convert it back, but quoting is clearer.

### `PACKET.md` — what a reviewer reads

`specy-road review-packet <NODE_ID>` assembles:

1. the brief, including the node's goal and its acceptance criteria numbered
   `A1..An`;
2. the implementation summary;
3. every changed path since the merge base, with paths outside the touch zones
   flagged (roadmap bookkeeping is exempt);
4. the diff;
5. verifier output from the newest READY file, plus any `--verify-cmd` run now.

The packet reviews the tip of the node's registered branch **without checking
it out**, so a coordinator in a checkout shared with executors never switches
branches. `--ref` reviews a different branch or commit.

### `REVIEW-<model>.md` — one reviewer's verdict

```yaml
---
node_id: M1.2
model: claude-opus-5.5
date: 2026-10-26
verdict: block                       # approve | block
commit: 3f9c2e1                      # must be the packet's "Commit under review"
acceptance: {A1: pass, A2: fail}     # one entry per A# in the brief: pass | fail | n/a
findings:
  correctness: []
  regression: []
  boundary: ["src/session.ts changed outside touch zones"]
  test_integrity: ["login.test.ts assertion loosened"]
commands_rerun: ["npm test -- login"]
required_changes: ["restore the assertion", "revert src/session.ts"]
fresh_session: true
authored_fix: false
is_coordinator: false
---
Free-form notes.
```

File it with:

```bash
specy-road review record M1.2 --model claude-opus-5.5 --verdict block --file notes.md
```

`review record` rejects a record that:

- does not match the schema, or whose flags disagree with the front matter;
- approves with a failing acceptance item or with `required_changes`;
- does not give a result for every acceptance id, or names one the brief lacks;
- claims `authored_fix: true` or `is_coordinator: true`;
- names a commit other than the one under review.

It fills `family` from the roster. When policy requires distinct families, it
labels the record `independence: same-family` if another counted review shares
its family.

## The review gate

`specy-road mark-implementation-reviewed`, run on the feature branch, counts a
review record only when:

- it validates;
- its `commit` is the commit under review — any later commit makes it stale, so
  a substantive fix restarts every review (commits that touch only
  `roadmap/registry.yaml` are skipped, so claim bookkeeping does not);
- its model is a rostered reviewer, or the substitute in an active substitution
  that covers this node;
- it attests a fresh session when policy requires one.

The gate passes when no counted review blocks and the counted approvals reach
`reviewers_required` (by distinct family when configured). On success it sets
`implementation_review: approved` in the registry and adds one
`Reviewed-by: <model> (<family>) approve <commit>` trailer per approval to that
commit.

**Under the default policy** the interactive menu's **approve** files
`REVIEW-human.md` and closes the gate in one step. A human approval is offered
only when it would complete the policy.

**`--yes` never creates a review.** It commits an approval only when the
recorded reviews already satisfy the policy. A coordinator that can satisfy the
gate alone is no gate.

`specy-road handoff status [<NODE_ID>] [--json]` shows each node's state:

| State | Meaning |
|---|---|
| `waiting` | No valid READY file. |
| `in-review` | READY matches the commit under review; the policy is not met yet. |
| `blocked` | A counted review blocks. |
| `approved` | The policy is met. Run `mark-implementation-reviewed`. |
| `stale` | The branch moved past the READY commit. |

Below each node it lists every problem to fix.

## Unattended loops

`grind-session` calls `finish-this-task`, which needs the gate closed. With the
gate on, the loop has to record an independent review each cycle. One way is a
pre-finish hook that runs a reviewer from another family headlessly:

```bash
specy-road grind-session --on-complete merge --implement-mode hook \
  --implement-cmd 'executor-cli "$SPECY_ROAD_PROMPT"' \
  --pre-finish-cmd 'specy-road review-packet "$SPECY_ROAD_NODE_ID" &&
    reviewer-cli work/reviews/"$SPECY_ROAD_NODE_ID"/PACKET.md > work/notes.md &&
    specy-road review record "$SPECY_ROAD_NODE_ID" --model <reviewer-id> --verdict approve --file work/notes.md &&
    specy-road mark-implementation-reviewed --yes'
```

`review record` refuses notes whose verdict disagrees with `--verdict`, so a
reviewer that blocks fails the hook and stops the loop (exit `4`). Alternatively, set
`require_implementation_review_before_finish: false` for a loop that should not
gate on review.

## Working in one shared checkout

When several agents share one working tree:

- Commit by explicit path (`git commit --only <paths>`); never `git add -A`,
  `git commit -a`, or a bare commit.
- Each agent accounts for the files it touched. `git status` mixes peers' rows.
- Do not use tree-wide commands: `stash`, `reset --hard`, `checkout -- .`,
  `restore .`, `clean -fd`, branch switching, `rebase`, `commit --amend`, force
  push.
- Anything that checks out branches (pickup, finish, grind) runs in its own
  clone or worktree: `git worktree add ../<repo>-<leaf>-<agent> -b <branch> <base>`.
- Run one fresh session per leaf. Context carried over from a previous leaf
  causes scope bleed.

## Upgrading from 0.2.x

- With the review gate on, `mark-implementation-reviewed` now needs a review
  record. Interactive use works as before under the default policy, because
  **approve** files the human record. **`--yes` without a satisfying record now
  exits 1.**
- `roadmap/orchestration.yaml` is optional; copy it from a fresh
  `specy-road init project` to change the policy.
- Add `work/reviews/` to `.gitignore`, as new scaffolds do. A review binds to
  the commit it read, so committing review files would move the branch past
  it; the approving reviews are kept as `Reviewed-by` trailers instead.
- No consumer schema changed. `orchestration.schema.json` is new and ships in
  `schemas/` for new scaffolds; the hand-off and review schemas live in the
  installed package.
