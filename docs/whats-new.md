# What's new in specy-road

## Agent quickstart

**Use this doc when:** summarising a release for users, or checking what changed for an adopter upgrading.
**Not for:** the complete change list ([`CHANGELOG.md`](../CHANGELOG.md)) or how to cut a release ([`release-runbook.md`](release-runbook.md)).
**Must know:** one `## specy-road X.Y.Z` section per published version, newest first; *Upgrading* lists the breaking changes and adopter commands.

The curated, user-facing summary of each release: what you can now do, and
what to change when you upgrade. Newest first. For every change, including
fixes and internal work, see the [CHANGELOG](../CHANGELOG.md).

## specy-road 0.3.1

*Release candidate `v0.3.1-rc3`, 2026-11-04 (TestPyPI).*

0.3.1 makes specy-road a coordinator for several coding agents at once. You
keep one roadmap; specy-road decides which model should implement, which
should review, and whether a leaf may finish — and it can launch executors
and reviewers on Claude Code, Codex or Cursor in their own worktrees and keep
track of them while you work. rc3 adds the evidence the gate reads for
itself (test integrity, tests at risk, red-green, land checks), reviewers
that run like workers, and the worktree-first worker loop that rc2 field use
asked for. Upgrade if more than one agent (or more than one vendor) touches
your repo, or if you want independent review before work lands. The review
gate is a **breaking change**: read *Upgrading* first.

### Highlights

- **A review gate before finish.** A leaf finishes only when reviews from
  the models your policy names approve the exact commit under review, and a
  milestone gets one full review of its combined change.
  [Read more](orchestration-review.md)
- **Evidence, not claims.** `integrity`, `impact`, `review red-green` and
  `review check-pre-existing` tell the gate what a leaf did to the tests, and
  `land_check_cmd` runs on the merge commit before anything is pushed.
  [Read more](orchestration-review.md#test-integrity-in-the-review-packet)
- **Workers on other harnesses, in their own worktrees.** `worker delegate`
  runs a leaf's executor on Claude Code, Codex or Cursor; `review delegate`
  does the same for a reviewer; `worker sync --wait` tells you when either
  has something to say. [Read more](orchestration-workers.md)
- **Harness facts, not folklore.** Model profiles and executor commands are
  rendered from a sourced `harness-facts.yaml`, guard hooks ship per harness,
  and every profile lists what to switch off.
  [Read more](orchestration-models.md#harness-facts-what-refresh-profiles-renders)
- **Safer shared checkouts.** A pre-tool-call guard, a repository lock around
  pickup and finish, and overlap warnings that name the other worktree.
  [Read more](orchestration.md#working-in-one-shared-checkout)
- **Brainstorm v2 with structured promote.** Rounds, panel shards,
  quote-checked evidence (web pages or your own files), decisions as
  first-class outcomes, and promote plans that land ideas where you intend.
  [Read more](brainstorming.md)
- **One set of agent rules everywhere.** specy-road's rules live in
  `.specyrd/AGENTS.md`; `AGENTS.md` keeps a short stub with the rules that
  prevent damage, `CLAUDE.md` imports the rules file, your team's additions go
  in `.specyrd/AGENTS.team.md`, and a context meter counts what each harness
  injects. [Read more](optional-ai-tooling-patterns.md)

### Review gate and hand-offs

An executor writes a READY hand-off with `specy-road ready`; `review-packet`
assembles the brief, diff (capped, with generated files listed by size), test
integrity and tests at risk; reviewers in fresh sessions record verdicts; the
gate counts them against `roadmap/orchestration.yaml` as committed on the
integration branch. `handoff status` says who can still supply a missing
approval, small fix rounds get a delta packet, and a leaf that cannot meet a
criterion without weakening a test records `blocked_on` instead.

    specy-road review-packet M1.2 && specy-road integrity M1.2; specy-road handoff status M1.2

### Workers

Pick a leaf up into its own worktree, delegate it, keep working, and check in
when you like. Failed and stalled workers resume, follow-ups queue behind a
running turn, `worker timeline` and `worker usage` show where the time and
tokens went, and `chore` runs worker work that has no roadmap leaf.

    specy-road do-next-available-task --worktree && specy-road worker delegate M1.2 --model claude-opus-5.5

### Models, roster and prompts

`init project` scaffolds model profiles, a roster and `harness-facts.yaml`.
`orchestrate plan` staffs every ready leaf (strong reviewers for high-risk
zones, routing preferences from the decisions ledger); `prompt` writes the
role prompt with the model's rules, the project's review lessons and
per-role effort applied; `refresh-profiles --capture` classifies a harness
upgrade before you trust it.

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

### Removed

- The generic copy-paste prompts (`cleanup_prompts.md`,
  `compliance_prompts.md`, `features_changes_debuging_prompts.md`,
  `optional-agent-review-prompts.md`): use your harness's built-in review,
  cleanup and security skills; roadmap review lives in `orchestration.md`.

### Known limitations in this release candidate

- The review gate is cooperative attestation unless you require signed
  reviews: someone who can run commands in the clone that finishes (for
  example retarget `origin/HEAD`) can change what the gate reads. Reviewer
  runs are not yet read-only with specy-road writing the record from
  structured output; that is deferred.
- The guard errs towards refusing: `echo git stash` is refused while
  another session is live.
- A landing that has reached only the local integration branch keeps its
  worker's slot until the remote is fetched up to it.
- PM GUI: after changing the LLM key, *Test LLM* can report the old key's
  result until the server restarts; stopping `specy-road gui` can leave its
  server process on the port.

Full list of changes: [CHANGELOG](../CHANGELOG.md#v031-rc3---2026-11-04).
