# What's new in specy-road

## Agent quickstart

**Use this doc when:** summarising a release for users, or checking what changed for an adopter upgrading.
**Not for:** the complete change list ([`CHANGELOG.md`](../CHANGELOG.md)) or how to cut a release ([`release-runbook.md`](release-runbook.md)).
**Must know:** one `## specy-road X.Y.Z` section per published version, newest first; *Upgrading* lists the breaking changes and adopter commands.

The curated, user-facing summary of each release: what you can now do, and
what to change when you upgrade. Newest first. For every change, including
fixes and internal work, see the [CHANGELOG](../CHANGELOG.md).

## specy-road 0.3.1

*Release candidate `v0.3.1-rc4`, 2026-11-06 (TestPyPI).*

0.3.1 adds an orchestration harness to specy-road. With it you can put a
crew of frontier coding models to work on your roadmap, such as Claude, Codex
and Cursor, each running through its own CLI harness in its own worktree. You
choose which models implement and which review. specy-road launches them,
keeps track of them while you work, and holds each leaf until the reviews you
asked for approve it.

The release candidates exist to find and fix problems while specy-road is used
on real projects. rc3 and rc4 fixed what that testing turned up: a fresh
project now passes its own checks, landings recover from inherited conflicts,
and workers and reviewers launch with explicit permissions and authentication.
Work on the roadmap continued alongside the testing, and what landed is
included in this build, such as the test evidence the review gate checks for
itself, reviewers that run like workers in read-only mode, and commands to
restructure the outline without renumbering the rest of the roadmap.

It's worth upgrading if more than one agent or vendor works in your repo, or
if you want independent review before work lands. The review gate is a
**breaking change**, so read *Upgrading* first.

### Highlights

- **A review gate before finish.** You choose which models must review a leaf.
  The leaf finishes only when they approve the exact commit under review, and
  a milestone gets one full review of its combined change. [Read
  more](orchestration-review.md)
- **Test evidence for reviewers.** `integrity`, `impact` and `review
  red-green` show what a leaf did to the tests, `review check-pre-existing`
  separates old failures from new ones, and `land_check_cmd` runs your checks
  on the merge commit before anything is pushed. [Read
  more](orchestration-review.md#test-integrity-in-the-review-packet)
- **Hand a leaf to an agent.** `worker delegate` starts an executor on Claude
  Code, Codex or Cursor in the leaf's own worktree, and `review delegate`
  starts a reviewer the same way. `worker sync --wait` tells you when either
  one needs you. [Read more](orchestration-workers.md)
- **Shared checkouts stay safe.** Guard hooks for each harness and a
  repository lock stop agents from tripping over each other during pickup and
  finish. Model profiles and launch commands come from one sourced file,
  `harness-facts.yaml`. [Read
  more](orchestration-models.md#harness-facts-what-refresh-profiles-renders)
- **Restructure the outline without renumbering everything.** `move-node`,
  `indent`, `outdent` and `group-nodes` change only the ids of what you move.
  `remove-node` deletes a node that never started, `rename-refs` updates notes
  that cite old ids, and `apply` runs a batch of these as one checked change.
  [Read more](roadmap-authoring.md#batch-edits-apply)
- **Brainstorm v2.** Run several rounds of ideas with a panel of models, check
  every quoted source against its page or your own files, record decisions,
  and promote the ideas you keep into the roadmap exactly where you want them.
  [Read more](brainstorming.md)
- **One set of agent rules for every harness.** specy-road's rules now live in
  `.specyrd/AGENTS.md`. Your `AGENTS.md` keeps a short stub with the safety
  rules, `CLAUDE.md` imports the full set, your team's own rules go in
  `.specyrd/AGENTS.team.md`, and a context meter shows how much each harness
  loads. [Read more](optional-ai-tooling-patterns.md)

### Review gate and hand-offs

An executor writes a READY hand-off with `specy-road ready`; `review-packet`
assembles the brief, diff (capped, with generated files listed by size), test
integrity and tests at risk; reviewers in fresh sessions record verdicts; the
gate counts them against `roadmap/orchestration.yaml` as committed on the
integration branch. `handoff status` says who can still supply a missing
approval, small fix rounds get a delta packet, and a leaf that cannot meet a
criterion without weakening a test records `blocked_on` instead.

    specy-road review-packet M1.2 && specy-road integrity M1.2; specy-road handoff status M1.2

### Restructuring the outline

A move changes only the moved subtree's ids, so ids cited in sheets and notes
stay true; `--id` or `--fill-gaps` picks the new id, and
`--renumber-outline` keeps the old whole-tree renumber. `group-nodes` puts
siblings under a new parent in one transaction, `remove-node` names every
blocker before it deletes anything, and `validate` refuses a dependency cycle
made through an inherited group dependency.

    specy-road group-nodes --into-new M3.5 --title "Export" M3.1 M3.2 --rewrite-refs

### Workers

Pick a leaf up into its own worktree, delegate it, keep working, and check in
when you like. Failed and stalled workers resume, follow-ups queue behind a
running turn, `worker timeline` and `worker usage` show where the time and
tokens went, and `chore` runs worker work that has no roadmap leaf. Cursor
workers run sandboxed without `--force` unless the roster sets
`cursor_force`; Claude Code workers and reviewers check authentication before
launch, so a subscription login works; `finish-this-task` resolves roadmap
conflicts a branch only inherited and undoes its bookkeeping when a landing
fails.

    specy-road do-next-available-task --worktree && specy-road worker delegate M1.2 --model claude-opus-5.5

### Models, roster and prompts

`init project` scaffolds model profiles, a roster and `harness-facts.yaml`.
`orchestrate plan` suggests a model for each ready leaf, which you can
accept or change (strong reviewers for high-risk zones, routing preferences
from the decisions ledger); `prompt` writes the
role prompt with the model's rules, the project's review lessons and
per-role effort applied; `refresh-profiles --capture` classifies a harness
upgrade before you trust it. `models roster` writes roster entries for the
models you name, and `orchestrate plan --roster-from-worktree` tries a roster
before it lands. `policy.max_fix_rounds` and `review defer` move findings of a
new input class to a follow-up leaf instead of another fix round.

    specy-road orchestrate plan

### Shared checkouts and worktrees

`session start` records who is working where; `session guard` plugs into
Claude Code, Codex and Cursor hooks and refuses destructive git while another
session is live. `env_setup` and `nested_repos` make a fresh leaf worktree
usable, and `worktree prune` retires one only when nothing would be lost.

    specy-road worktree prune M1.2

### Brainstorm v2

Round 1 diverges without anchoring on the roadmap; later rounds and panel
shards widen it; `verify` checks each quote on its page or in your repository;
converge clusters ideas with critics; `decide` records a policy; `promote`
lands nodes by cluster, by plan file or under the parent you name, with the
converge judgement on each sheet.

    specy-road brainstorm start --topic "Offline notes" --under M3 --rounds 2

### Decisions and research

Open questions for a human live in `roadmap/decisions.yaml`, each
self-contained with a default if unanswered; the coordinator prompt reads
them. `research/` tracks deep-research topics with a cadence, and `validate`
says when one is due.

    specy-road decisions list

### Upgrading from 0.2.x

- **The review gate.** New projects scaffold with it on
  (`require_implementation_review_before_finish: true` in
  `roadmap/git-workflow.yaml`); where it is on, `mark-implementation-reviewed`
  needs review records and `--yes` never creates one. Unattended loops must
  record an independent review first, or turn the gate off on the
  integration branch.
- **The two gate settings must agree.** `validate` and `doctor` now exit 1
  when `roadmap/orchestration.yaml` requires reviewers but the switch above is
  off. Fix: set the switch to `true`, or remove `orchestration.yaml`.
- **Milestones need a full review** (`policy.milestone_full_review`, default
  on): a milestone's rollup stays In Progress until a review of its combined
  change passes and `mark-implementation-reviewed <MILESTONE_ID>` closes it.
  Set the key to `false` on the integration branch to keep the old rollup.
- **Approve notes have a form.** `review record` refuses an approve that
  describes a defect without `not a defect because <reason>` on the same
  line. Reviewer prompts say how; records already filed are not re-checked.
- **`finish-this-task` re-checks the gate at the current commit**; a 0.2.x
  approval with no review record needs a fresh `mark-implementation-reviewed`.
  Only a bookkeeping-only commit (planning sheet, implementation summary,
  review files) keeps earlier approvals.
- **The policy comes from the integration branch**, named by the remote's
  default branch. If your clone has no `origin/HEAD`, run
  `git remote set-head origin --auto`, or the gate stays shut.
- **One claim per checkout.** `do-next-available-task` refuses a second claim
  in a checkout that already holds one (exit 6); finish or abort it, or pass
  `--allow-second-claim`. Use `--worktree` to run several leaves from one
  main checkout.
- **`review record`** refuses `--model human` and models not in the roster.
- **Agent rules move out of `AGENTS.md`.** The first `upgrade` replaces the
  old specy-road block in `AGENTS.md` (and in an existing `CLAUDE.md`) with a
  stub, writes `.specyrd/AGENTS.md` and `.specyrd/AGENTS.team.md`, and prints a
  `migration:` line. Text outside the markers is kept; anything you added
  inside the old markers is replaced, so move it to `.specyrd/AGENTS.team.md`
  (check `git diff`). Commit the two new files.
- Then run, once per repo: `specy-road upgrade --prune`. It refreshes
  schemas (new policy keys, `planned_test_changes`, `decisions.schema.json`,
  `harness-facts.schema.json`, the git-workflow keys `land_check_cmd`,
  `verify_cmd`, `track_worker_logs`, `nested_repos`, `env_setup`), the
  profiles you lack, skills and the managed blocks (the `.gitignore` block
  gains the session-scoped `work/` files), deletes the pre-0.3 command stubs
  and stray skill copies, and validates. `harness-facts.yaml` and the captures
  ship with `init project`; `refresh-profiles --check` reads the toolkit's
  copy, so an existing repo needs nothing more. Add `constraints/review-lessons.md`
  with `specy-road lessons add` when you want it, and `specyrd init
  --install-orchestration-hooks` for the per-harness guard hooks. See
  [Upgrading from 0.2.x](install-and-usage.md#upgrading-from-02x).

- **From rc3 to rc4:**
  - `move-node` changes only the moved subtree's ids; pass
    `--renumber-outline` for the old whole-outline renumber.
  - `refresh-profiles` (and so `upgrade`) adds only the profiles your roster
    names; `--profiles all` adds every bundled one.
  - Reviewer runs are read-only: a reviewer that writes files (caches, build
    output, its own `REVIEW-*.md`) now fails, and a custom reviewer command
    must print the review record as JSON
    ([reviewer output](orchestration-reviewer-output.md)). A reviewer entry
    with no resolvable model needs `harness_model` or `routing: dynamic`.
  - Converging review loops are no longer escalated to root-cause analysis;
    `policy.escalate_when_converging: true` restores that.
  - Cursor workers no longer get `--force`. Where Cursor's sandbox cannot
    start (Ubuntu 24.04's AppArmor default), fix the host or set
    `cursor_force: true` on the roster entry
    ([Cursor permissions](orchestration-workers.md)).
  - `validate` refuses a dependency cycle through inherited group
    dependencies; `remove-dependency` on a dependency the node does not list
    exits 1; explicit codenames over 64 characters are refused.
  - `review record` files only under the caller's own model. A review you
    file by hand from a terminal needs `--human-filed "<who and why>"`, and the
    gate counts it only when it is signed or the integration branch sets
    `policy.count_human_filed_reviews: true`
    ([who may file](orchestration-review.md#who-may-file-a-review-record)).
  - A leaf's review policy is pinned when it is claimed. If the roster or
    review policy changes on the integration branch after the claim, the gate
    stays shut until a human runs `specy-road review accept-policy <ID>` in a
    terminal, or the leaf is re-claimed
    ([policy pin](orchestration-review.md#review-policy-pinned-at-claim)).
  - `session end` ends only your own session; ending another agent's live
    session needs `--force` from a terminal.
  - PM GUI Publish refuses when the repository has no git remote; add one
    first.
  - Run `specy-road upgrade`. It refreshes the schemas (for the new optional
    keys such as `max_fix_rounds`, `escalate_when_converging`,
    `count_human_filed_reviews`, `cursor_force` and `harness_bin`) and
    regenerates a drifted `roadmap-context.md` (and a tracked `roadmap.md`),
    so `digest --check` passes without a separate step.
    See [Upgrading](upgrading.md).

### Removed

- The generic copy-paste prompts (`cleanup_prompts.md`,
  `compliance_prompts.md`, `features_changes_debuging_prompts.md`,
  `optional-agent-review-prompts.md`): use your harness's built-in review,
  cleanup and security skills; roadmap review lives in `orchestration.md`.

### Known limitations in this release candidate

- The review gate is cooperative attestation unless you require signed
  reviews: someone who can run commands in the clone that finishes (for
  example retarget `origin/HEAD`) can change what the gate reads. Nothing
  yet stops an executor from changing the files that steer harnesses and
  specy-road unnoticed; that guard is planned for rc5.
- The review policy pin, the `POLICY-ACCEPTED.yaml` acceptance file, READY
  authorship and the caller check on `review record` are honour-system: an
  agent that edits those files or sets a harness marker can get past them.
  `signed_reviews` is the strong check.
- `worker terminate` cannot reach a process the harness started that was
  already re-parented to init before terminate ran.
- The brainstorm skill's "start is the single first call" is wording only;
  the CLI does not enforce it.
- The guard errs towards refusing: `echo git stash` is refused while
  another session is live.
- A landing that has reached only the local integration branch keeps its
  worker's slot until the remote is fetched up to it.
- PM GUI: after changing the LLM key, *Test LLM* can report the old key's
  result until the server restarts; stopping `specy-road gui` can leave its
  server process on the port.

Full list of changes: [CHANGELOG](../CHANGELOG.md#v031-rc4---2026-11-06).
