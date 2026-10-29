# Git workflow and multi-agent coordination

## Agent quickstart

**Use this doc when:** claiming, branching, finishing or cleaning up roadmap work in a consumer repo, or reading a `roadmap/git-workflow.yaml` field.
**Not for:** the toolkit repo's own branch policy — [`../CLAUDE.md`](../CLAUDE.md) (Repository git workflow policy); the command-by-command dev loop — [`dev-workflow.md`](dev-workflow.md).

**Must know without reading on:**
- Register on the integration branch first (a registration-only commit), then `git checkout -b feature/rm-<codename>`; `specy-road do-next-available-task` does both and pushes.
- Never two active registry rows with overlapping touch zones; stay inside yours.
- Under `on_complete: pr`, after `finish-this-task` the integration branch still shows the row and the old status until the PR merges: leave the row alone and never run `abort-task-pickup` to tidy it.
- Precedence: CLI flags → env → `roadmap/git-workflow.yaml` → defaults (`main` / `origin`).
- Remove your registry row before merge; `specy-road registry-prune --remove <CODENAME>` is only for a claim whose branch is gone.

**Read further for:**
- every `git-workflow.yaml` field, the `on_complete` modes and finish precedence → "Machine-readable contract (`roadmap/git-workflow.yaml`)"
- `feature/rm-*` patterns and milestone rollups → "Branch naming"
- the pre-claim checklist → "Before implementation"
- the registration commit and `registry-prune` → "Registration commit (mandatory)"
- touch zones and worktrees while implementing → "While working"
- landing, then revert vs follow-up → "Merge back" and "Correcting merged work: revert vs follow-up"
- deleting merged `feature/rm-*` branches (`finish-this-task --delete-branch`, `branches prune`) → "Deleting merged feature branches"
- every leftover the loop leaves (branches, worktrees, registry rows, stashes) → "Finding leftovers: `doctor`"

**Related:** [`dev-workflow.md`](dev-workflow.md), [`grind-session.md`](grind-session.md), [`pm-workflow.md`](pm-workflow.md), [`orchestration.md`](orchestration.md).

This document is product-agnostic. Adapt branch names (`main` / `dev`) to your org; the **invariants** are registration, touch zones, and non-overlapping active claims.

## Scope and distinction

- This document describes the **consumer-repo workflow contract** used by `specy-road` commands and scaffolded project docs.
- Consumer repos choose their own integration branch and remote via `roadmap/git-workflow.yaml`.
- The `specy-road` toolkit repository can use a different maintainer policy for package development and release promotion. That maintainer policy is local to this repository and is not the canonical default for consumer app repos.

## Machine-readable contract (`roadmap/git-workflow.yaml`)

The scaffold includes **`roadmap/git-workflow.yaml`**: your team’s **integration branch** (daily trunk) and **remote** name. The specy-road CLI (`specy-road sync`, `do-next-available-task`, `abort-task-pickup`) and the **PM Gantt** read this file unless you override with `--base` / `--remote` or optional environment variables (`SPECY_ROAD_INTEGRATION_BRANCH`, `SPECY_ROAD_REMOTE`). If the file is missing, tools fall back to `main` / `origin` and may warn.

**Precedence:** CLI flags → env → `roadmap/git-workflow.yaml` → defaults.

Keep this file accurate so PMs see correct git status in the dashboard and validation can warn when local refs are stale (for example after `git fetch`).

## PM Gantt and `registry.yaml` visibility

The **PM Gantt** reads **`roadmap/registry.yaml` from the current working tree** (same repo root as other `specy-road` commands: discover from cwd / git, or **`SPECY_ROAD_REPO_ROOT`**), then **merges** registry rows from remote-tracking **`feature/rm-*`** refs when **remote registry overlay** is enabled in PM Gantt **Settings** (default **on** for new GUI profiles; requires Git remote + **Test Git**). See [design-notes/registry-hydration-remote-refs.md](design-notes/registry-hydration-remote-refs.md). Set **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`** to force HEAD-only behavior without changing saved settings.

**Default dev CLI path:** `specy-road do-next-available-task` **commits registration to the integration branch first**, then creates `feature/rm-*`. The execution target is always an actionable **leaf**; ancestor nodes are context containers and are never directly claimed by default pickup. **Coordination contract:** with the default CLI (sync + push), that registration is also **on the remote** integration branch so the team shares one source of truth. **`do-next-available-task --local`** is the one exception: it registers and branches without fetching or pushing, so the claim is invisible to peers until that checkout pushes the integration branch — use it offline or for a spike, and push before anyone else could pick the same leaf (see [dev-workflow.md](dev-workflow.md#agents-and-registration)). After **`git pull`** on the integration branch, **HEAD’s `registry.yaml` shows active rows** without relying on overlay. **Overlay** still helps for older flows or unpushed feature-only registration — it merges rows from remote **`feature/rm-*`** refs after **`git fetch`**. The outline **green accent** appears when your **checked-out branch name** matches a row’s **`branch`** field (usually the feature branch for implementers); see [pm-workflow.md](pm-workflow.md#monitoring-in-progress-work-while-on-the-integration-branch) and [design-notes/pm-gantt-registry-checkout.md](design-notes/pm-gantt-registry-checkout.md).

Optional field **`merge_request_requires_manual_approval`** (boolean) documents that MRs need human approval; the `finish-this-task` CLI may print a reminder.

Optional field **`require_implementation_before_finish`** (boolean, **default true**): `finish-this-task` refuses to close a node when the feature branch changes **no file under that node's declared `touch_zones`**, measured against its merge base with the integration branch. A claim is not an implementation, and a node marked `Complete` with nothing behind it looks exactly like one that shipped — this is the machine-checkable floor under the human review gate below, and unlike that gate it needs nobody in the loop, which is why it defaults on. Every ambiguity resolves toward allowing the finish: a node with **no** declared zones is skipped entirely (zones are optional, F-009), as is any case where git cannot compute the diff. For a leaf that genuinely needs no code change, pass **`--allow-empty-implementation`**; if the work is real but landed outside the zones, fix the zones with `specy-road edit-node <NODE_ID> --set touch_zones=<paths>`.

Optional field **`require_implementation_review_before_finish`** (boolean): when **true**, `finish-this-task` requires a prior **`specy-road mark-implementation-reviewed`**, which needs review records under `work/reviews/<NODE_ID>/` satisfying [`roadmap/orchestration.yaml`](orchestration.md) at the commit under review (the default policy is met by one interactive human approval). New scaffolds default this to **true**; omit or set **false** to use the streamlined single-command flow (`finish-this-task` only). While it is on, `specy-road validate` warns on open actionable leaves with no `acceptance`, since a review of them cannot attest per-criterion results. Schema: [`../specy_road/templates/project/schemas/git-workflow.schema.json`](../specy_road/templates/project/schemas/git-workflow.schema.json).

Optional field **`cleanup_work_artifacts_on_finish`** (boolean): when **true** or omitted (default), `finish-this-task` deletes per-node **`work/brief-`**, **`work/prompt-`**, and **`work/implementation-summary-`** files after validate/export/digest, staging deletions when tracked (a never-committed summary is copied to `work/reviews/<NODE_ID>/` first). Set **false** or pass **`--no-cleanup-work`** to keep them. See [dev-workflow.md](dev-workflow.md).

Optional fields **`grind_session_max_limit_waits`** (integer, default 3), **`grind_session_max_limit_wait_hours`** (number, default 6), **`grind_session_limit_wait_grace_seconds`** (integer, default 120) and **`grind_session_max_empty_retries`** (integer, default 2): bounds for a `grind-session` run whose `--implement-cmd` is the Claude CLI — how many times one leaf may wait out a usage limit, the ceiling on any single wait, the slack added after a stated reset, and how many times to re-run a hook killed from outside without printing anything. The matching CLI flags override this file. Ignored for any other implement command. See [grind-session.md](grind-session.md).

Optional field **`on_complete`** (`pr`, `merge`, or `auto`; default **`pr`**): controls how **`specy-road finish-this-task`** lands work after the bookkeeping commit on the feature branch.

- **`pr`** — Print guidance to push (if needed) and open a **pull request** or **merge request** targeting the integration branch. On GitHub this is a **PR**; on GitLab and many other hosts it is an **MR**. They are the same kind of integration review; this doc uses **PR/MR** when the forge is unspecified.
- **`merge`** — After bookkeeping, try **`git merge`** of the feature branch into the **integration branch** locally, then **`git push`** the integration branch. On failure (a source conflict, a non-fast-forward integration branch, a rejected push) it **exits non-zero with the reason and does not fall back to PR/MR hints** — `merge` means merge (F-012). Use **`auto`** if you want the fallback. If the integration branch is checked out in another worktree (the usual layout when the leaf lives in a `worker delegate` worktree), the merge and push run there; finish refuses before the bookkeeping commit if that worktree has uncommitted changes to tracked files, and never touches them.
- **`auto`** — Try the **`merge`** path first; if landing the merge fails, fall back to the PR/MR guidance (**merge pending**) instead of only failing.

**Bookkeeping is resolved, not merged.** Landing a finish never 3-way-merges
**`roadmap/registry.yaml`**, **`roadmap.md`** or **`roadmap-context.md`**. The
registry is a keyed collection (one row per active claim) and the other two are
generated in full, so a line-based merge of any of them can conflict — leaving a
finish half-done, with the branch pushed and the claim never cleared — or
succeed while keeping a row a lane had removed. Instead the merge is staged, the
registry is recomputed as *the integration branch's registry minus the finishing
node's row*, the two generated files are re-rendered from the merged graph, and
only then is the merge commit created. Conflicts anywhere else still fail hard.
This is what makes **concurrent lanes** against one integration branch safe; see
[grind-session.md](grind-session.md). Merging by hand still means removing your
own row yourself.

### What `pr` leaves behind (read this before re-running pickup)

Under **`pr`**, `finish-this-task` commits everything on the **feature branch** and touches the integration branch not at all. So the moment it returns, one node has two truths:

| | feature branch | integration branch |
| --- | --- | --- |
| node status | `Complete` | unchanged (`Not Started` / `In Progress`) |
| registry row | removed | **still there** |

That is correct, and it is the most misread state in the workflow, because from the integration branch a *finished* leaf and an *unclaimed* leaf look identical. **Merging the PR is what reconciles them.** Until then:

- **Leave the registry row alone.** It is what keeps the leaf off the available list.
- **Do not run `abort-task-pickup`** to "clean up" the row. Abort deletes the local `feature/rm-*` branch, and under `pr` that branch is the only place the work exists.
- `grind-session --plan` reports the leaf as **in flight**, not ready. That is the same fact from the other side.

`do-next-available-task` will not re-offer the leaf even if the row goes missing: pickup also checks whether a `feature/rm-<codename>` branch already has the node `Complete`, and skips it with a line naming the branch. That check is the backstop for a row removed by an abort, by F-014 self-heal, or by hand — not a substitute for keeping the row.

**Precedence for `finish-this-task`:** CLI **`--on-complete`** overrides **`work/.on-complete-<NODE_ID>.yaml`** (written by **`do-next-available-task`** for that task) overrides environment **`SPECY_ROAD_ON_COMPLETE`** overrides **`on_complete`** in this file, else **`pr`**.

**`grind-session` refuses to run when that resolution lands on `pr`**, because `pr` never merges and the loop cannot see its own finished work on the next cycle. New scaffolds therefore write **`on_complete`** into this file explicitly rather than relying on the built-in default, so the mode is never implicit. See [grind-session.md](grind-session.md).

**`do-next-available-task`:** On an interactive terminal, the command shows the resolved default and asks for **`pr`**, **`merge`**, or **`auto`** for **this task** (unless you pass **`--on-complete`**). Non-interactive runs use the default from the file/env without prompting.

**Examples** (schema: [`../specy_road/templates/project/schemas/git-workflow.schema.json`](../specy_road/templates/project/schemas/git-workflow.schema.json)):

`main` as the daily trunk:

```yaml
version: 1
integration_branch: main
remote: origin
```

`dev` as the daily trunk (feature work merges here before promotion to `staging` / `main`):

```yaml
version: 1
integration_branch: dev
remote: origin
```

## Branch naming

| Kind | Pattern | Example |
|------|---------|---------|
| Roadmap-driven feature | `feature/rm-<codename>` | `feature/rm-roadmap-ci` |
| Milestone rollup (parent container) | `feature/rm-<parent-codename>` | Same pattern; parent node must have `codename` set |
| Non-roadmap fix | `fix/<slug>` | `fix/validator-path` |
| Non-roadmap feature | `feature/<slug>` | `feature/docs-index` |

`<codename>` must match the milestone codename in the roadmap graph (JSON chunks under `roadmap/`; see [`roadmap/manifest.json`](../specy_road/templates/project/roadmap/manifest.json) in a scaffolded project) — kebab-case, globally unique.

**Milestone rollup workflow:** `specy-road start-milestone-session`, `do-next-available-task --milestone-subtree`, and `finish-this-task` with **`work/.milestone-session.yaml`** land **bookkeeping** on the integration branch via cherry-pick and accumulate **full implementation** on **`feature/rm-<parent-codename>`** for a single final PR to integration — see [dev-workflow.md](dev-workflow.md#milestone-scoped-execution-rollup-branch).

**Committed milestone state:** `start-milestone-session` also writes **`milestone_execution`** on the parent roadmap node (JSON chunk). That is the **team-visible** lock the PM Gantt uses: while `state` is `active` or `pending_mr`, outline and status edits under that subtree return **409**. **Rollup-complete** (all structural leaves `Complete`) is not the same as **delivery-complete** (rollup branch merged into the integration branch): the default closure path is the rollup **MR** (`open-milestone-pr`). Use **`specy-road reconcile-milestone-status`** (dry-run by default; `--apply` writes) to align `milestone_execution` and parent `status` after merge, or **`--fallback-head-delivery`** when work reached integration without that MR.

## Before implementation

1. Confirm **gates** and dependencies for your actionable leaf target (see root/index or generated tables).
2. Read `roadmap/registry.yaml` in your application repository — no overlapping **touch zones** with active entries (coordinate with PM / integration lead if unsure). Example layout: [`roadmap/registry.yaml`](../specy_road/templates/project/roadmap/registry.yaml). In this toolkit repository, [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](../tests/fixtures/specy_road_dogfood/roadmap/registry.yaml) belongs to the dogfood test fixture and should only be used for fixture/sample work.
3. **Register on the integration branch, then branch:** add your row to **`roadmap/registry.yaml`** and commit **on the integration branch** (e.g. `dev`) — registration only, no implementation in that commit. Message: `chore(rm-<codename>): register as in-progress`, optionally with CI-skip suffixes matching automation: `[skip ci] [ci skip] ***NO_CI***` (see [`do-next-available-task`](dev-workflow.md)). Push if others need visibility (the automated CLI pushes by default after registering). Then: `git checkout -b feature/rm-<codename>` and implement on that branch. (Automated path: [`do-next-available-task`](dev-workflow.md) does brief → register on integration → push integration branch → create feature branch → prompt.)

Teams using `docs/roadmap-status.md` instead of YAML should follow the same **register on integration before feature work** discipline.

## Registration commit (mandatory)

The **registration commit** contains **only** the registry update (or equivalent status row):

1. Add a row with: codename, `node_id` for a **leaf** node, branch `feature/rm-<codename>`, non-empty touch zones, optional `started` date.
2. Commit on the **integration branch** first; then create **`feature/rm-<codename>`** for implementation commits.

`specy-road do-next-available-task` appends common CI-skip tokens to the registration commit message by default (best-effort; your pipeline may still require `paths` / `paths-ignore` rules). Manual commits should use the same pattern if you want consistent CI behavior.

Only **after** registration (and branching) should you add implementation commits on the feature branch.

### Releasing a claim whose branch is gone (`registry-prune`)

**`abort-task-pickup`** is the command for releasing a claim you still hold: it runs from **`feature/rm-<codename>`**, deletes that branch, and cleans `work/`. It cannot help once the branch no longer exists, because it refuses to run anywhere else.

**`specy-road registry-prune`** covers that case. With no arguments it lists registry rows whose **`feature/rm-*`** branch is absent from your clone. **`--remove <CODENAME>`** (repeatable) drops the named rows, commits on the integration branch and pushes — the same way registration published them.

```bash
specy-road registry-prune                            # report only
specy-road registry-prune --remove trash-soft-delete # drop one, commit, push
```

**The report is advisory, and removal is never inferred from it.** Pickup pushes the *registry* and then creates the feature branch **locally, without pushing it**, so a perfectly healthy claim held by another clone is indistinguishable from an orphan when viewed from yours. That is why F-014 only warns, why this command lists rather than prunes, and why every removal has to name a codename. Confirm the lane is really gone before removing its row. If the branch is still in your clone, `registry-prune` refuses and points you at `abort-task-pickup`.

## While working

- Stay within declared **touch zones** unless explicitly expanding scope with team agreement.
- Prefer **git worktrees** for parallel agents when two items could touch disjoint paths.

## Merge back

1. Remove your registry entry (or table row) before merge.
2. Merge via PR/MR; green validation (e.g. `specy-road validate`) should pass.
3. Delete the feature branch after merge — see below.

### Deleting merged feature branches

Both commands delete only a branch the integration branch already contains, and the remote copy only while it is still the tip that passed that check. The delete is leased to that tip (`git push --force-with-lease=refs/heads/<branch>:<sha> --delete`), so a push that lands in between is refused and the branch stays.

- **`specy-road finish-this-task --delete-branch`** — once the merge lands (`on_complete: merge`, or `auto` when its merge succeeds), deletes the feature branch locally and on the remote and prints each deletion. The same flag on a re-run deletes it too: when the bookkeeping commit already exists, merge mode retries only the landing, and `--delete-branch` on that re-run still deletes the branch once the landing is on the remote. The error from a failed landing names that re-run, including the flag. A milestone rollup finish does the same after the leaf has merged into the rollup branch (that branch is what contains the leaf), including when a re-run lands the rollup because the bookkeeping commit already exists. That re-run lands only the finish commit: commits added after it are refused, and `--no-milestone-rollup` skips the rollup. `pr` does not refuse the flag on that path. A checked-out branch cannot be deleted, so the checkout moves to the integration branch first; when another worktree holds the integration branch (the `worker delegate` layout), it detaches at it instead. A failed deletion is a warning, not a failed finish: the work has already landed. Refused under **`pr`**, before the bookkeeping commit, when the finish is not a rollup landing, because there the branch is the only copy of the work until the PR merges.
- **`specy-road branches prune`** — for the backlog (PRs merged on the forge, earlier finishes). After `git fetch --prune`, lists every `feature/rm-*` branch, local and on the remote, that `<remote>/<integration-branch>` contains. **`--delete`** deletes them; without it nothing changes. Two kinds of branch look merged and are skipped: one with a registry row (locally or on the integration branch) — a fresh pickup's tip *is* an integration-branch commit — and an open milestone rollup branch (`milestone_execution.rollup_branch` with a state other than `closed`). Which rollups are open is read from the roadmap **at that fetched ref**, not from the working tree, so a checkout behind the remote cannot delete a rollup the remote still marks active. If that roadmap cannot be read, prune lists and deletes nothing. Run it from the up-to-date integration branch: `git branch -d` also wants `HEAD`, or the branch's upstream, to contain the branch. A failed fetch stops it, since a stale remote-tracking ref could delete work pushed since.

```bash
specy-road branches prune            # list only
specy-road branches prune --delete   # delete locally and on the remote
```

### Finding leftovers: `doctor`

**`specy-road doctor`** lists everything the task loop can leave behind, after `git fetch --prune`, without changing anything:

- **`feature/rm-*` branches**, local and on the remote, that nothing claims — the same test as `branches prune`: no registry row (locally or on the integration branch) and not an open milestone rollup. Each row says why: `merged`; `merged (same patch content)`; `leaf <ID> Complete`; or `claim gone`, and an unmerged one says how many commits the integration branch lacks. **Merged** is ancestry first. When that fails, patch content decides: every commit has an equivalent on `<remote>/<integration-branch>` (`git cherry`, which catches a rebase), or the branch's whole diff does (a squash merge). A rewritten landing therefore still counts as merged.
- **Worktrees** (never the main one, the current one or a locked one) whose directory is missing, whose branch is gone (detached at a commit the integration branch contains, which is how `finish-this-task --delete-branch` leaves a `worker delegate` worktree), or whose branch is one of the merged ones. A row names the ignored files (`work/` and so on) that removing the worktree would delete.
- **Registry rows** on the integration branch whose branch is in neither this clone nor the remote. Advisory, as with `registry-prune`: another clone's claim looks the same until it pushes its branch.
- **Stashes specy-road pushed** (messages starting `specy-road:`; pickup and review used to stash `work/`).

**`--fix`** removes what it listed, asking once per kind (`--yes` skips the questions), and prints each action. It removes worktrees first, then branches (a branch checked out in a kept worktree is not deleted and is reported), then stashes, then registry rows through `registry-prune --remove`, which checks out the integration branch, commits and pushes. A branch is deleted only at the tip that was listed: a local branch that moved is left alone, and the remote delete is leased to that tip. A dropped stash can still be restored with `git stash apply <sha>`, which the report prints, until `git gc`. An unmerged branch is deleted too when you confirm, so read the commit count first. A failed fetch stops `doctor`.

```bash
specy-road doctor              # list only
specy-road doctor --fix        # remove, asking once per kind
```

## Correcting merged work: revert vs follow-up

On a shared integration branch, **do not rewrite history** others may have pulled (avoid
`git push --force` to “un-merge”).

| Intent | Safer pattern |
| --- | --- |
| Remove the effect of a bad merge from `main` | Open a **revert** PR (revert the merge commit). History stays linear and auditable. |
| Improve code that is already merged | Branch from current `main` and land a **follow-up** PR (`fix/...`, `feature/...`, or a new roadmap-driven branch if the PM tracks it). |

Roadmap bookkeeping (registry, node status, follow-up tasks) lives in
[dev-workflow.md](dev-workflow.md).

## Roles

| Role | Responsibility |
|------|------------------|
| PM / Director | Specs, contracts, roadmap authoring — stays far ahead of execution |
| Developer (+ agent) | Implements against contracts; owns branch through merge |

Parallelism across milestones is allowed when **dependencies** and **touch zones** permit it — `specy-road validate` is the check, not a human approval.
