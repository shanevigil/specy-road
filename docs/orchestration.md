# Orchestration: roles, hand-offs, and the review gate

## Agent quickstart

**Use this doc when:** you coordinate, execute or review a roadmap leaf and need the hand-off files, the review gate, or the rules for sharing one checkout.
**Not for:** choosing models or launching a leaf on another harness — [`orchestration-models.md`](orchestration-models.md) and [`orchestration-workers.md`](orchestration-workers.md).

**Must know without reading on:**
- The executor never reviews its own leaf, and the coordinator's own session is never a reviewer; every review record attests this and the gate checks it. The one exception is the default interactive human approval in `mark-implementation-reviewed`, which writes `REVIEW-human.md` with `is_coordinator: true` by design.
- A review is a file under `work/reviews/<NODE_ID>/` bound to one commit; any later commit (other than one touching only `roadmap/registry.yaml`) makes it stale.
- Order: `specy-road review-packet <NODE_ID>` → `specy-road review record <NODE_ID> --model <roster id> --verdict approve|block --file notes.md` → `specy-road mark-implementation-reviewed` (`--yes` never creates a review). The packet header and `handoff status` report a trial merge (`git merge-tree`, nothing checked out) of the integration branch into the leaf's branch: a conflict on any path outside `work/`, `roadmap/`, `planning/`, `roadmap.md` and `roadmap-context.md` means the executor merges and resolves before reviewers run, and `mark-implementation-reviewed` and `finish-this-task` refuse, before any bookkeeping commit, until it is resolved. The integration ref is the remote-tracking one as last fetched, else the local branch.
- The policy is `roadmap/orchestration.yaml` as read from the integration branch; a feature branch cannot lower its own bar.

**Read further for:**
- the step sequence from pickup to finish → "The flow"
- roster, policy keys, substitutions, model choice → "`roadmap/orchestration.yaml`", "Choosing and prompting models"
- READY, PACKET and REVIEW file shapes and what `review record` rejects → "Hand-off files: `work/reviews/<NODE_ID>/`"
- what counts, `Reviewed-by` trailers, signed reviews, `handoff status` → [orchestration-review.md](orchestration-review.md)
- grind-session hooks and step mode → "Unattended loops"
- `session start|guard`, the harness hook adapters, several agents in one tree, migrating → "Presence: `specy-road session`", "Working in one shared checkout", "Upgrading from 0.2.x"

**Related:** [`orchestration-models.md`](orchestration-models.md), [`orchestration-workers.md`](orchestration-workers.md), [`orchestration-review.md`](orchestration-review.md), [`grind-session.md`](grind-session.md), [`design-notes/v0-3-0-orchestration-slices.md`](design-notes/v0-3-0-orchestration-slices.md) (background).

specy-road separates three roles around a roadmap leaf and prescribes how work passes
between them — not **which** agent, IDE or vendor fills a role; a human, Claude Code, Cursor, Codex or a local model all fit. Other tools also drive those CLIs as workers; what is specy-road's is the governance around them, set out in [Where specy-road sits](philosophy-and-scope.md#where-specy-road-sits).

- **Coordinator** — picks the leaf, creates the branch or worktree, assembles the review packet, closes the review gate, finishes the leaf, and changes roadmap status.
- **Executor** — reads the brief, changes only the leaf's touch zones, runs the verifiers, commits, writes a hand-off file, and **stops**.
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
the defaults shown here, so upgrading does not strand a solo maintainer. The commented starter that `init project` writes has this policy and one more roster entry, a placeholder executor (`my-executor`) to rename to the model you run; `specy-road validate --generate-orchestration` writes the same starter into a repo that has no file, and leaves an existing one alone.

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
| `policy.stall_after_seconds` | A `running` worker with no stdout for this long is flagged `stalled` by `worker sync` and `worker list`, with one `stalled` event per silence ([orchestration-workers.md](orchestration-workers.md#the-model)). Default `600`. |
| `substitutions[]` | A recorded decision letting `use` review in place of a usual reviewer: `slot`, `use` (must be a roster id; its family comes from the roster), optional `scope` (non-empty list of node ids; omit for all), `decided` (does not count before this date), and an expiry — `expires_when` (prose), `expires` (date after which it stops counting), or both. |

Roster entries also accept `profile`, `harness_model` (the model id the harness CLI expects when the roster `id` is not one: [orchestration-models.md](orchestration-models.md#model-profiles-models-and-prompt)), `class` (the tag a leaf's `executor_eligibility` names: [orchestration-models.md](orchestration-models.md#planning-assignments-orchestrate-plan)), `public_key` (for signed reviews: [orchestration-review.md](orchestration-review.md#signed-reviews)), `channels` (including `channels.cli_resume`, the command a worker resume runs: [orchestration-workers.md](orchestration-workers.md#roster-setup)), `may_process`, `subagent_family_lock`, `preflight`, `harness`, `billing_route`, `routing` and `pinned` (a harness that picks its own model does not count as an independent family: [orchestration-models.md](orchestration-models.md#harnesses-that-route-models)), `available`, `paused_until`, and legacy `unavailable_until`; policy also takes `max_workers` (routing, prompts, and `worker delegate` use them), and `escalate_same_acceptance_blocks` (default 3) and `escalate_review_rounds` (default 5), the review-loop escalation thresholds under "The review gate".

**Choosing models.** [`model-profiles/`](../specy_road/templates/project/model-profiles/README.md),
scaffolded into your repo by `init project`, is the canonical guide to filling the roster: it ranks
models by role, lists independent reviewer pairs and pairs that share blind spots, names cheap
first-pass executors, gives the roster `family` value for each model, lists the points where the
research disagrees, and has one profile per model (limits, prices, headless CLI syntax, failure
modes, prompting rules). A roster `id` is your own label; naming it after the shipped profile
(`claude-opus-5-5` below, not `claude-opus-5.5`) finds the profile without `profile:`.

For independent review by two model families:

```yaml
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: claude-opus-5-5, family: anthropic, roles: [reviewer]}
  - {id: gpt-6.1-sol, family: openai, roles: [reviewer]}
  - {id: composer-2.5, family: cursor, roles: [executor]}
policy:
  reviewers_required: 2
  reviewers_distinct_families: true
```

`specy-road validate` fails on a file that is present but invalid, including
duplicate roster ids and a substitute that is not in the roster.

**Local availability overlay.** `roadmap/orchestration.local.yaml` (gitignored,
working tree only) can set `available: false` or `paused_until` on roster
entries by `id` without changing the committed roster. `orchestrate plan`,
`prompt`, `worker delegate` and `review delegate` read those fields merged onto
the integration-branch roster; past review records by a paused model still
count at the commit they reviewed.

**The gate reads this file from the integration branch** — its remote-tracking ref when there is
one, else the local branch — not from the branch under review, so a feature branch cannot lower its
own bar; the gate is also on when either that branch or the working tree sets
`require_implementation_review_before_finish`. In a repo with remotes, the branch's name comes from
`roadmap/git-workflow.yaml` as committed on the remote's default branch (`refs/remotes/<remote>/HEAD`,
which `git clone` sets and `git remote set-head <remote> --auto` restores; it must exist), whose copy
must also name the same remote as `HEAD`'s; in a repo with no remote, from the copy at `HEAD`. The
working tree and `SPECY_ROAD_INTEGRATION_BRANCH` / `SPECY_ROAD_REMOTE` are ignored. The named branch
must name itself in its own committed copy, and with remotes only `refs/remotes/<remote>/<branch>` is
read. If any of this is missing, unfetched or disagrees, the gate fails closed (on, and nothing passes
it). Outside this protection: a remote whose default branch the feature author can push to, and anyone who can run git in the
finishing clone (they can retarget `refs/remotes/<remote>/HEAD`); unsigned, the gate is cooperative attestation. Change policy on the integration branch; an edit on
a feature branch is ignored by the gate, flagged in the review packet, and, like any commit that touches more than `roadmap/registry.yaml`, makes that branch's reviews stale. Routing reads the roster from the same ref: `orchestrate plan` names it (`roster_ref` in `--json`, `origin/dev` with a remote) and, when the working tree's `roadmap/orchestration.yaml` is absent there, differs, or was deleted while the ref still has it, or the local integration branch has an unpushed commit that adds, deletes or changes it (even when the working tree matches the ref), says so (`roster_drift`) in place of the "needs a rostered executor with may_process …" hint, which would send you to a file routing does not read; `validate` warns the same. With a remote, committing is not enough: commit the roster (or its deletion) to the integration branch and push it, then fetch, to clear it. While the ref has a roster, `validate` does not print its "default policy applies" notice for a missing working-tree file. With no roster on that ref and none in the working tree, both say so and point here: the default roster is one human and no executor, so write one (`specy-road validate --generate-orchestration`), commit and push it.

## Choosing and prompting models

Profiles, `models`, `prompt` and `orchestrate plan`: [orchestration-models.md](orchestration-models.md);
`specy-road worker` (a leaf on another harness): [orchestration-workers.md](orchestration-workers.md); a roster in one command (`models roster`), a model coordinator and `orchestrate plan --spread`: [orchestration-roster.md](orchestration-roster.md).

**One readiness rule.** `do-next-available-task`, `grind-session --plan` and `orchestrate plan` agree on
which leaves are ready: the same dependency, claim and status check, minus leaves already Complete on an
unmerged `feature/rm-*` branch, minus unauthored leaves (a placeholder planning sheet and no
`acceptance`). `orchestrate plan` lists the unauthored ones apart (`unauthored` in `--json`) and staffs
none of them.

**Executor ranking.** Among capable executors, `orchestrate plan` orders by roster `class` first
(`cheap`, then untagged or any other tag, then `senior`), then list price from the profile, then
`billing_route` (a label containing `subscription` or `oauth` before none, before any other, such as
`api_key`). A roster whose cheaper entries have no profile, so no price, still routes to what it
declares `cheap` instead of the one priced model; a leaf with `executor_eligibility: senior` still gets
a `senior` executor.

## Human decisions ledger (`roadmap/decisions.yaml`)

Open questions for a person live in **`roadmap/decisions.yaml`** beside `registry.yaml`. The file is
schema-validated (`schemas/decisions.schema.json`, copied by `init project` / `specy-road refresh-schemas`).
Each **open** entry carries:

| Field | Meaning |
|---|---|
| `id` | Stable handle (for example `D1`); cite it in chat, never ask with a bare id alone |
| `node` | Roadmap leaf the decision belongs to |
| `kind` | `decision` or `human-action` |
| `summary` | Plain-words what this is |
| `why_now` | Why now and what it blocks |
| `options[]` | Each option's `label` and `effect` |
| `recommendation` / `recommendation_reason` | What you recommend and why |
| `default_if_unanswered` | What the agent applies if the human does not answer |
| `asked` | ISO date when opened |
| `needed_by` | Optional ISO date by which an answer is needed |

**CLI:** `specy-road decisions add|list|close`. Schema validation runs before `add` writes the file
and before `list` prints it. `list` prints every open entry, those with `needed_by` first in ascending
date order and those without a deadline last. `close` records the answer and the closed time only
after the same line appears in the planning-sheet **decision block** (optional list marker or
checkbox in front). That block is the first level-2 section whose heading normalises to
`decisions and notes` or `decisions`, chosen only after CommonMark fences (a backtick or tilde run of
at least 3, closed by a later run of the same character at least that long) are removed from the
whole sheet. A heading or matching line that exists only inside a fence does not count, and neither
does a matching line in another section. Indented code, HTML comments, and blockquotes are left as
written. `asked` and `needed_by` are calendar dates `YYYY-MM-DD`; `add` rejects any other string
before writing, and `list` rejects a file whose date is not a real calendar day (for example
`2026-99-99` or `2026-02-30`). Datetimes are out of scope for those two fields.

**Coordinator turn discipline:** at the start of each turn, run `specy-road decisions list` (as with
`worker sync`). Search the ledger and planning-sheet decision blocks
(`specy-road search "<topic>" --kind planning`) before asking anything new. Ask at
most four questions at once, each in the self-contained shape above. End any turn that still has open
entries with one **Decisions waiting on you** block listing all of them below your status.

**Routing preferences (`kind: preference`):** a routing rule the human states in chat (say, which
executor takes docs-only leaves until a provider resets) is a ledger entry: `decisions add --kind
preference --summary "<rule>"`, with optional `--role`, `--model` (roster ids, most preferred first),
`--applies-to` (leaf kinds), `--expires` (date, inclusive, or datetime) and `--why`; ids default to
`P1`. Preferences are **per project and session-durable**: they live in the tracked ledger, not one
agent's context, so they survive a context reset, an account switch or a different agent taking over.
They are **not roster config**: availability and pauses come only from the roster (`available`,
`paused_until`), and `orchestrate plan` flags a preferred model the roster lacks or marks unavailable.
`list` shows active preferences first and drops expired ones. `--supersedes <id>` closes the old rule as
it records the new; `close <id> --answer "<why>"` needs no sheet record. `orchestrate plan` never
applies them: it prints them (JSON `preferences_not_applied`); the coordinator reads them each session
and before each delegate or review launch. A project with its own `schemas/decisions.schema.json` runs
`refresh-schemas` first.

## Hand-off files: `work/reviews/<NODE_ID>/`

Plain files work across every harness, including IDE chats that cannot see each other. Each file is Markdown whose YAML front matter is the machine-readable part.
The directory always resolves to the **main** worktree: an executor in a linked worktree writes its hand-off there by absolute path, and every command — including the gate run from that worktree — reads the same files. Executors write READY with `specy-road ready <NODE_ID> --model <id> --run '<cmd>'`, which runs each verifier and records its exit and output `tail` ([orchestration-review.md](orchestration-review.md)); new scaffolds also ship `work/handoff-ready.template.md` (for `blocked_on`) and `work/review-record.template.md`.

Records are read from the working tree and are untracked by design (`work/reviews/` is gitignored), so they never travel with a push; the review policy, by contrast, comes from `roadmap/orchestration.yaml` on the integration branch. What persists is the outcome: the gate writes one `Reviewed-by:` trailer per approval into git history.
A repository that never pushes claims still sees its records: `handoff status <NODE_ID>` on a leaf with no claim lists the READY and REVIEW files with their verdicts, `--ref <branch>` checks them against that branch's commit, and `do-next-available-task --local` claims the leaf in this checkout only. Every read-only review command takes the same `--ref <branch or commit>` in place of a claim: `review-packet`, `prompt` (so a second-family reviewer prompt for a Complete node needs no claim; the prompt passes the `--ref` on to the reviewer's `review record`), `handoff status`, and `review list <NODE_ID>`, which prints each filed record's verdict, model, family and commit, then the gate evaluation, and writes nothing.

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
   `roadmap/registry.yaml` is labelled toolkit bookkeeping;
4. the diff, `roadmap/registry.yaml` included: only this node's claim row and approval stamp are expected there, anything else is under review;
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
commit, and exits 1 when it does not resolve. An empty diff is explained in the packet and warned about on stderr: the commit adds nothing past its merge base, as when the branch is already merged. `--base <ref>` diffs from the merge base with `<ref>` instead (the commit before the leaf, say); the commit under review stays the same. `-o <path>` writes a copy there too: `work/reviews/<NODE_ID>/PACKET.md`, the only path `prompt --role reviewer` reads, is always written.

### `REVIEW-<model>.md` — one reviewer's verdict

```yaml
---
node_id: M1.2
model: claude-opus-5-5
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
verify_pre_existing: ["pytest -q tests/regression.py"]
required_changes: ["restore the assertion", "revert src/session.ts"]
fresh_session: true
authored_fix: false
is_coordinator: false
---
Free-form notes.
```

File it with:

```bash
specy-road review record M1.2 --model claude-opus-5-5 --verdict block --file notes.md
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
requires distinct families, it relabels every counted record `independence: same-family` or `distinct-family` as reviews arrive. It overwrites `REVIEW-<model>.md` each round and keeps a copy of every record it files under `history/`, the round history escalation counts from. A filing (`review record`, and the human approval of `mark-implementation-reviewed`) takes the leaf's review lock: it waits up to 10 seconds for another filing, and while a `review delegate` or `prompt --channel cli --run` on the same leaf holds the lock it exits 1, writing nothing, so it never voids that reviewer's run; file again when the run ends (`review list <ID>`).

`handoff status` and `review list` report, per leaf, its review rounds (distinct reviewed commits) and the time from its first review to the latest (`n/a` with a single review). Two or more review rounds per leaf are normal under a two-family policy: the second family often blocks on something the first passed, and each fix is a new commit to review. Escalation (`escalate_review_rounds`, default 5) is what marks a loop that is not converging.

## The review gate

How records count, `Reviewed-by` trailers, signed reviews, `handoff status`, and review-loop escalation: [orchestration-review.md](orchestration-review.md). The gate never counts a record, approval or block, signed or not, from a model id that filed a valid `READY-<agent>.md` on the leaf (the executor or a fix author), and `review delegate` refuses that model before it writes anything. Another model of the same family still counts, judged against the other reviewers by `reviewers_distinct_families`. A READY is an unsigned file its writer creates, so this check is cooperative attestation, not enforcement, unless signing keys are out of the executor's reach.

## Unattended loops

`grind-session` calls `finish-this-task`, which needs the gate closed. With the gate on, the
loop has to record an independent review each cycle. One way is a pre-finish hook that runs a reviewer from another family headlessly:

```bash
specy-road grind-session --on-complete merge --implement-mode hook \
  --implement-cmd 'executor-cli "$SPECY_ROAD_PROMPT"' \
  --pre-finish-cmd 'ID="$SPECY_ROAD_NODE_ID"; specy-road review-packet "$ID" &&
    specy-road prompt "$ID" --role reviewer --model <reviewer-id> --channel paste &&
    reviewer-cli "$(cat work/prompt-"$ID"-reviewer-<reviewer-id>.md)" &&
    specy-road handoff status "$ID" &&
    specy-road mark-implementation-reviewed --yes'
```

The reviewer prompt has the reviewer file its own `review record`. A block, or no record,
leaves the gate unmet, so `--yes` refuses, the hook fails and the loop stops (exit `4`).

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
specy-road session start --path src/api docs/api.md --note "rate limits"   # or repeat --path
specy-road session touch            # renew; records expire after 4 hours by default
specy-road session end [<id>]       # yours, or an expired <id>; another agent's live one needs --force from a terminal
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
what the guard cannot see is refused, not waved through: a shell function, a git verb or command name built by expansion
that could be git (`$X`, `git${IFS}…`, `G=git; $G`; not `$HOME/bin/pytest`), `GIT_CONFIG*` in env, `--config-env=alias.*`, an interpreter one-liner.
Working-tree commands count only sessions in the caller's worktree (`git -C`, `stash`, `rebase`,
force-push count every session). The adapters (`--format`) know each harness's stdin shape;
`docs/optional-ai-tooling-patterns.md` wires them. A non-denial never sets a harness permission
decision (Claude Code gets context only; Codex nothing), so the harness's own prompt policy still applies.

Records are `work/.sessions/<agent-id>.yaml` (gitignored, main worktree): branch, worktree, paths, expiry. The id is
`$SPECY_ROAD_AGENT_ID`, else `<user>-s<POSIX session id>`, shared by every command from one terminal or harness process, so
`start`, `touch`, `end` and the hook name one record; `--agent` names it; `touch` keeps the paths. A crashed record ages
out; one that will not load counts as live to the guard until fixed or deleted. `session end` removes only the caller's own record (`$SPECY_ROAD_AGENT_ID`, else the derived id) or an expired one: `<id>` and `--agent` pick the target, never the caller. Another agent's live record is refused (it is kept, exit 1) unless a human passes `--force` from a terminal (stdin a TTY), so a closed terminal's record counts as a live peer to the guard until it expires; with no record for the caller's id, `end` names the id `session start` printed and ends nothing. A record keeps the `$USER` that started it, and one another user started is always refused. `handoff status` lists live sessions first,
`do-next-available-task` warns on touch-zone overlap, `grind-session --plan` and `orchestrate plan` never put two ready leaves sharing a zone in one parallel batch, and `session check` refuses a commit on another live session's paths.

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
- `roadmap/orchestration.yaml` is optional; `specy-road validate
  --generate-orchestration` writes the commented starter to change the policy.
- `work/reviews/` must be gitignored, as new scaffolds do (`specy-road
  upgrade` adds it to the managed `.gitignore` block): a review binds to
  the commit it read, so committing review files would move the branch past it
  (approvals are kept as `Reviewed-by` trailers). No consumer schema changed:
  `orchestration.schema.json` is new in `schemas/` for new scaffolds, and the
  hand-off and review schemas live in the installed package.
