# Orchestration: roles, hand-offs, and the review gate

## Agent quickstart

**Use this doc when:** you coordinate, execute or review a roadmap leaf and need the hand-off files, the review gate, or the rules for sharing one checkout.
**Not for:** choosing models or launching a leaf on another harness — [`orchestration-models.md`](orchestration-models.md) and [`orchestration-workers.md`](orchestration-workers.md).

**Must know without reading on:**
- The executor never reviews its own leaf, and the coordinator's own session is never a reviewer; every review record attests this and the gate checks it. The one exception is the default interactive human approval in `mark-implementation-reviewed`, which writes `REVIEW-human.md` with `is_coordinator: true` by design.
- A review is a file under `work/reviews/<NODE_ID>/` bound to one commit; any later commit (other than one touching only `roadmap/registry.yaml`) makes it stale.
- Order: `specy-road review-packet <NODE_ID>` → `specy-road review record <NODE_ID> --model <roster id> --verdict approve|block --file notes.md` → `specy-road mark-implementation-reviewed` (`--yes` never creates a review).
- The policy is `roadmap/orchestration.yaml` as read from the integration branch; a feature branch cannot lower its own bar.

**Read further for:**
- the step sequence from pickup to finish → "The flow"
- roster, policy keys, substitutions, model choice → "`roadmap/orchestration.yaml`", "Choosing and prompting models"
- READY, PACKET and REVIEW file shapes and what `review record` rejects → "Hand-off files: `work/reviews/<NODE_ID>/`"
- what counts, `Reviewed-by` trailers, signed reviews, `handoff status` → "The review gate"
- grind-session hooks and step mode → "Unattended loops"
- `session start|guard`, the harness hook adapters, several agents in one tree, migrating → "Presence: `specy-road session`", "Working in one shared checkout", "Upgrading from 0.2.x"

**Related:** [`orchestration-models.md`](orchestration-models.md), [`orchestration-workers.md`](orchestration-workers.md), [`grind-session.md`](grind-session.md), [`design-notes/v0-3-0-orchestration-slices.md`](design-notes/v0-3-0-orchestration-slices.md) (background).

specy-road separates three roles around a roadmap leaf and prescribes how work passes
between them — not **which** agent, IDE or vendor fills a role; a human, Claude Code, Cursor, Codex or a local model all fit.

- **Coordinator** — picks the leaf, creates the branch or worktree, assembles the
  review packet, closes the review gate, finishes the leaf, and changes roadmap status.
- **Executor** — reads the brief, changes only the leaf's touch zones, runs the
  verifiers, commits, writes a hand-off file, and **stops**.
- **Reviewer** — reads the review packet and nothing else, in a fresh session, and records approve or block.

## The flow

```text
coordinator  do-next-available-task            → work/brief-<ID>.md, feature/rm-<codename>
executor     implement, commit, commit summary → work/implementation-summary-<ID>.md
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
| `policy.reviewer_reruns_required` | An approval counts only when `commands_rerun` lists a command the reviewer re-ran; the interactive human approval is exempt. Default `false`. A `model: human` record is trusted as written unless `signed_reviews` is on, so under unsigned policy this switch is cooperative attestation, not enforcement. |
| `substitutions[]` | A recorded decision letting `use` review in place of a usual reviewer: `slot`, `use` (must be a roster id; its family comes from the roster), optional `scope` (non-empty list of node ids; omit for all), `decided` (does not count before this date), and an expiry — `expires_when` (prose), `expires` (date after which it stops counting), or both. |

Roster entries also accept `profile`, `channels`, `may_process`,
`subagent_family_lock`, `preflight`, `harness` and `billing_route`; policy
also takes `max_workers` (routing, prompts, and `worker delegate` use them).

**Choosing models.** [`model-profiles/`](../specy_road/templates/project/model-profiles/README.md),
scaffolded into your repo by `init project`, is the canonical guide to filling the roster: it ranks
models by role, lists independent reviewer pairs and pairs that share blind spots, names cheap
first-pass executors, gives the roster `family` value for each model, lists the points where the
research disagrees, and has one profile per model (limits, prices, headless CLI syntax, failure
modes, prompting rules). A roster `id` is your own label (`claude-opus-5.5` below); the vendor's API
id (`claude-opus-5-5`) lives in the profile that `profile` points at.

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

`specy-road validate` fails on a file that is present but invalid, including
duplicate roster ids and a substitute that is not in the roster.

**The gate reads this file from the integration branch** — its remote-tracking ref when there is
one, else the local branch — not from the branch under review, so a feature branch cannot lower its
own bar; the gate is also on when either that branch or the working tree sets
`require_implementation_review_before_finish`. The branch's name comes from `roadmap/git-workflow.yaml`
as committed on the remote's default branch (`refs/remotes/<remote>/HEAD`, which `git clone` sets and
`git remote set-head <remote> --auto` restores) when that carries the file, else at `HEAD`, whose copy
also names the remote; the working tree and `SPECY_ROAD_INTEGRATION_BRANCH` / `SPECY_ROAD_REMOTE` are
ignored. A feature commit can rewrite `HEAD`'s copy, so the named branch must name itself in its own
committed copy, and in a repo with remotes only `refs/remotes/<remote>/<branch>` of a configured remote
is read. If the branch is missing or unfetched, the names disagree, or the remote is not configured,
the gate fails closed (on, and nothing passes it). Change policy on the integration branch; an edit on
a feature branch is ignored by the gate, flagged in the review packet, and, like any commit that
touches more than `roadmap/registry.yaml`, makes that branch's reviews stale.

## Choosing and prompting models

Profiles, `models`, `prompt` and `orchestrate plan`: [orchestration-models.md](orchestration-models.md);
`specy-road worker` (a leaf on another harness): [orchestration-workers.md](orchestration-workers.md).

## Hand-off files: `work/reviews/<NODE_ID>/`

Plain files work across every harness, including IDE chats that cannot see each
other. Each file is Markdown whose YAML front matter is the machine-readable part.
The directory always resolves to the **main** worktree: an executor in a linked
worktree writes its hand-off there by absolute path, and every command — including the gate
run from that worktree — reads the same files. New scaffolds ship `work/handoff-ready.template.md` and `work/review-record.template.md`.

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

Quote SHAs: `commit` and `base` are read exactly as written, so YAML cannot turn
`0123456` into an octal number here, but quoting keeps other tools reading the file from doing so.

A non-zero `exit`, or no `verify` entry at all, is listed as a problem by
`handoff status` and marked in the packet; a reviewer, not the gate, judges it.
A READY naming another node or branch is misfiled: listed as invalid, never read by the packet or a worker.

### `PACKET.md` — what a reviewer reads

`specy-road review-packet <NODE_ID>` assembles:

1. the brief, with the node's goal and acceptance criteria numbered `A1..An`;
2. the implementation summary;
3. every changed path since the merge base, both sides of a rename or copy,
   with paths outside the touch zones flagged (roadmap bookkeeping is exempt);
   `roadmap/registry.yaml` is labelled toolkit bookkeeping, not under review;
4. the diff, minus `roadmap/registry.yaml` (claim and approval rows), with a one-line note when it changed;
5. verifier output from the newest READY file, plus any `--verify-cmd` run now;
   each section states if it was computed from git, executor-asserted, or run now.

The packet reviews the tip of the node's registered branch **without checking
it out**, so a coordinator in a checkout shared with executors never switches
branches. The branch is the local one, else `<remote>/<branch>` (run
`git fetch` first when the executor worked in another clone); when neither
exists, the command fails rather than review something else. The summary is read
as committed at the reviewed commit; a working-tree or missing one is labelled so, and one
without the `## Added` inventory the executor prompt asks for (helpers, guards, mocks and
tests, each with a reason) is noted, not failed. The reviewer prompt (`specy-road prompt
--role reviewer`) adds an excess checklist — tests pinning internals, unreachable defence,
duplicated logic, overlapping tests — that needs a caller trace or the covering test as
evidence and never recommends removing error handling without one. Changes to `roadmap/orchestration.yaml` or
`roadmap/git-workflow.yaml` are flagged. `--ref` reviews a different branch or
commit, and exits 1 when it does not resolve.

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
- names a commit other than the one under review;
- comes from a model that is not in the roster on the integration branch, or
  that has neither the reviewer role nor an active substitution;
- comes from `human` — a human approves only through the interactive menu of
  `mark-implementation-reviewed`, so an agent cannot file one.

It sets `family` from the roster; a `family` written in the file is ignored. When policy
requires distinct families, it relabels every counted record `independence: same-family` or `distinct-family` as reviews arrive.

## The review gate

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

### Signed reviews

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
| `blocked` | A counted review blocks. |
| `approved` | The policy is met. Run `mark-implementation-reviewed`. |
| `stale` | The branch moved past the READY commit. |
| `unclaimed` | Leftover files for a node with no open claim (finished or aborted); safe to delete. |

Below each node it lists every problem to fix. Naming a node that cannot be
resolved exits 1.

## Unattended loops

`grind-session` calls `finish-this-task`, which needs the gate closed. With the gate on, the
loop has to record an independent review each cycle. One way is a pre-finish hook that runs a reviewer from another family headlessly:

```bash
specy-road grind-session --on-complete merge --implement-mode hook \
  --implement-cmd 'executor-cli "$SPECY_ROAD_PROMPT"' \
  --pre-finish-cmd 'specy-road review-packet "$SPECY_ROAD_NODE_ID" &&
    reviewer-cli work/reviews/"$SPECY_ROAD_NODE_ID"/PACKET.md > work/reviews/"$SPECY_ROAD_NODE_ID"/notes.md &&
    specy-road review record "$SPECY_ROAD_NODE_ID" --model <reviewer-id> --verdict approve \
      --file work/reviews/"$SPECY_ROAD_NODE_ID"/notes.md &&
    specy-road mark-implementation-reviewed --yes'
```

`review record` refuses notes whose verdict disagrees with `--verdict`, so a
blocking reviewer fails the hook and stops the loop (exit `4`).

From an IDE agent, use **step mode** ([grind-session.md](grind-session.md#driving-the-loop-from-an-ide-agent-step-mode)):
the agent session is the coordinator; it runs `grind-session --step pickup`, hands the prompt to a
fresh executor sub-agent, has a **different** fresh sub-agent of a rostered reviewer model read
`PACKET.md` and file `review record`, runs `mark-implementation-reviewed --yes` (its shell is not a
TTY), then `grind-session --step finish`. Anything that modifies files runs before the review, since a
later commit makes it stale. Under the default human-only roster the agent cannot close the gate; it stops and asks the human to approve in a terminal.

## Presence: `specy-road session`

The registry shows claimed leaves; work that is not a claim — a design note, a
merge, a review, a verifier's experiments — was invisible to every other agent in the checkout. A session announces itself instead:

```bash
specy-road session start --path src/api --path docs/api.md --note "rate limits"
specy-road session touch            # renew; records expire after 4 hours by default
specy-road session end
specy-road session list [--all]
specy-road session check            # exit 1 if staged paths overlap another live session
specy-road session guard --command "git stash"   # exit 2 with the reason when another session is live
specy-road session guard --format claude-code     # the same, reading a harness hook's stdin
```

`session guard` is the body of a harness hook (routing commands read the roster from the integration
branch, as the gate does): it denies a command that can move or discard another session's work —
`stash`, `reset --hard`, branch switching, `checkout -- …`, `restore <paths>`, `clean -f`, `rm -f`,
`rebase`, `commit --amend`, force push, `add -A`/`-u`/`.`, `commit -a`, a bare `commit`
(`commit --only <paths>`), a commit/add/rm pathspec that is a tree root, `..`, glob, `:` magic,
absolute path or `--pathspec-from-file` (a plain directory such as `src/` passes; so does plain
`rm <files>`, which git refuses for a changed file) — only while another session is live (`--always`
to deny regardless). Each `git` segment is judged, inside `sh -c`, `$(…)`, `<(…)`, `eval`, aliases,
after `if`/`then`/`do`/`!`, and where `git` follows another word (`case … a) git …`, `find -exec git …`);
what the guard cannot see is refused, not waved through: a shell function, variable command name or
git verb, `GIT_CONFIG*` in the environment, `--config-env=alias.*`, an interpreter one-liner.
Working-tree commands count only sessions in the caller's worktree (`git -C`, `stash`, `rebase`,
force-push count every session). The adapters (`--format`) know each harness's stdin shape;
`docs/optional-ai-tooling-patterns.md` wires them. A non-denial never sets a harness permission
decision (Claude Code gets context only; Codex nothing), so the harness's own prompt policy still applies.

Records are `work/.sessions/<agent-id>.yaml` (gitignored, main worktree): branch, worktree, paths, expiry. The id is
`$SPECY_ROAD_AGENT_ID`, else `<user>-s<POSIX session id>`, shared by every command from one terminal or harness process, so
`start`, `touch`, `end` and the hook name one record; `--agent` names it; `touch` keeps the paths. A crashed record ages
out; one that will not load counts as live to the guard until fixed or deleted. `handoff status` lists live sessions first,
`do-next-available-task` warns on touch-zone overlap, and `session check` refuses a commit on another live session's paths.

## Working in one shared checkout

When several agents share one working tree, with or without a roadmap claim (the
scaffold `AGENTS.md` repeats these rules; [design-notes/agent-guidance-and-shared-checkouts.md](design-notes/agent-guidance-and-shared-checkouts.md) records why):

- Commit by explicit path (`git commit --only <paths>`); never `git add -A`,
  `git commit -a`, or a bare commit.
- Each agent accounts for the files it touched. `git status` mixes peers' rows.
- Do not use tree-wide commands: `stash`, `reset --hard`, `checkout -- .`,
  `restore .`, `clean -fd`, branch switching, `rebase`, `commit --amend`, force
  push.
- Anything that checks out branches (pickup, finish, grind) runs in its own
  clone or worktree: `git worktree add ../<repo>-<leaf>-<agent> -b <branch> <base>`.
- Run one fresh session per leaf. Context carried over from a previous leaf causes scope bleed.
- Announce yourself with `specy-road session start --path …` before the first
  edit, and check `specy-road session list`. Before any git write, `git status`
  and `git worktree list`: files you did not create belong to another session. Edit only your own section of a file
  others are editing.
- A prompt or plan you hand an agent names the commit it was written against
  (`base: <sha>`); the agent diffs from there before starting.

## Upgrading from 0.2.x

- With the review gate on, `mark-implementation-reviewed` now needs a review
  record, and `finish-this-task` re-checks it at the current commit. Interactive use
  works as before under the default policy, because **approve** files the human record. **`--yes` without a satisfying record now exits 1.**
- `roadmap/orchestration.yaml` is optional; copy it from a fresh
  `specy-road init project` to change the policy.
- Add `work/reviews/` to `.gitignore`, as new scaffolds do: a review binds to
  the commit it read, so committing review files would move the branch past it
  (approvals are kept as `Reviewed-by` trailers). No consumer schema changed:
  `orchestration.schema.json` is new in `schemas/` for new scaffolds, and the
  hand-off and review schemas live in the installed package.
