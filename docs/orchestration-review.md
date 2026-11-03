# The review gate

How records count, `Reviewed-by` trailers, signed reviews, `handoff status`, and review-loop escalation. Roles, hand-off files, and sharing a checkout stay in [orchestration.md](orchestration.md).

`specy-road mark-implementation-reviewed`, run on the feature branch, counts a
review record only when:

- it validates, and its `node_id` is this node;
- its `commit` resolves, through git, to the commit under review — any later
  commit makes it stale, so a substantive fix restarts every review. Every
  merge counts as new work, including `git merge -s ours`, whose tree equals
  its first parent's; commits that touch only `roadmap/registry.yaml` are
  skipped, so claim bookkeeping does not. When the only paths in
  `git diff <reviewed>..<commit>` are this leaf's planning sheet,
  `work/implementation-summary-<NODE_ID>.md`, or files under
  `work/reviews/<NODE_ID>/`, earlier approvals still count and `handoff status`
  says so in the policy line;
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

The gate is enforced only while `require_implementation_review_before_finish`
is on in `roadmap/git-workflow.yaml` (in the working tree or on the integration
branch); with it off, `mark-implementation-reviewed` has nothing to do and says
the gate is not enforced at finish. `roadmap/orchestration.yaml` alone does not
turn it on, so a project whose orchestration file requires reviewers
(`reviewers_required`, at least 1 whenever the file exists) while that switch is
off would see `review list` report a gate that finish never checks.
`specy-road validate` fails on that combination and `specy-road doctor` reports
it as an `error:` and exits 1, both naming the two settings and the fix: set
`require_implementation_review_before_finish: true`. Neither turns the switch on
for you; whether a project reviews is its own decision, and a project that does
not can delete `roadmap/orchestration.yaml`.

## What a reviewer probes

An evaluation of reviewer effectiveness on the 0.3.1 line found that the approving reviewer had usually seen the issues the second reviewer blocked on, and excused them: it re-ran only the executor's own tests, read loose acceptance text in the leaf's favour, and filed real defects as "advisory" or "non-blocking". So every reviewer prompt (`specy-road prompt --role reviewer`, and `review delegate`) tells the reviewer to:

1. run the tests that import each changed module, not only the executor's selection;
2. try at least one input per changed public function that the diff's tests do not use, and report it under `commands_rerun`;
3. fail an acceptance item whose observed behaviour differs from its text, even when the difference looks minor;
4. list every defect its notes or findings describe under `required_changes`, or explain on that line why it is not one, starting `not a defect because`.

`specy-road review record` enforces the fourth rule on an approve, which may not carry `required_changes`. It refuses, writing nothing, when a `findings` entry or a line of the notes calls something advisory, non-blocking (or not blocking), minor, a nit, cosmetic, residual, latent, an optional fix, a weak assertion, a bug or a defect, unless that line says `not a defect because`. Negated mentions ("no defect", "none blocking") don't count, and neither do headings, `>` quotes, code spans or fenced code, so a reviewer can quote acceptance text or test output. The message names each entry or line, for example `findings.correctness[1] says "Advisory"` or `notes line 3 says "Non-blocking"`. A block with the defect under `required_changes` is filed as before. The rules and the check live in `specy_road/review_record_rules.py`.

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
- if it names `delta_from` itself, its own delta qualifies and its basis still counts under this same rule.

The reviewer's latest record on a commit is its verdict there. A later block on that commit takes the approval back, and with it every delta approval that depends on it; a later eligible approval of the commit restores them.

A delta approval the gate rejected is therefore never the start of a later delta. Otherwise `handoff status` lists it as `does not count — a delta
review from <sha>, …; a full review is needed`. A delta approval is still one
model's vote, so `reviewers_distinct_families` still needs approvals from both
families at the current commit. A block is never affected. Like
`fresh_session`, `delta_from` is self-attested; a signature covers it.

With `policy.reviewer_resumed_delta: true` (**default false**), a reviewer that
approved a commit may be resumed for the next fix round instead of starting a
fresh session: its record sets `fresh_session: false` and names `delta_from`
(the commit it approved; with `commit`, that names the delta it read). The key
relaxes only `reviewer_fresh_session`, and only for an approval naming
`delta_from`; such an approval still counts only under the delta rule above.
A resumed full review (no `delta_from`) is still refused, and so is every resumed
approval while the key is off. A resumed block naming `delta_from` counts while
the key is on (a block is never held to the delta rule). The delta packet says
which applies, and with the key on `specy-road prompt --role reviewer` tells a
reviewer reading its own delta packet that, if it is the resumed session that
approved the delta's base, it sets `fresh_session: false`.

When a record is refused only for `fresh_session`, `handoff status` says so and
whether a resumed delta approval would count:

- `… the only reason it does not count; with policy.reviewer_resumed_delta: true this resumed delta approval would count`
  (it names `delta_from` and the delta qualifies; the key is off);
- `…; with policy.reviewer_resumed_delta: true it would still not count: a delta review from <sha>, but …`;
- `…; a resumed delta approval naming delta_from: <sha> would count` (a resumed
  full review whose round qualifies for a delta; `with policy.reviewer_resumed_delta: true`
  is added while the key is off);
- `…; a resumed delta approval would not count either (<why>): a fresh full review is needed`;
- for a block: `…; with policy.reviewer_resumed_delta: true this resumed block would count`
  (it names `delta_from`), else `…; a resumed block counts only when it names delta_from`.

A record that fails another check too lists `fresh_session` first, then that check.

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
| `leaves_open` | A milestone with a leaf not yet Complete at the integration tip; its full review has not started (below). |
| `awaiting_full_review` | A milestone whose leaves are all finished waits for its full review at the integration tip (below); `approved` once the gate is met there. |
| `unclaimed`, `error` | No open claim names a commit, so the gate cannot be evaluated and the records are only listed (pass `--ref`); `error`: the node or `--ref` does not resolve. |

Below each node it lists every problem to fix. Given one `<NODE_ID>`, the exit status is for a polling script: `0` the policy is met (`approved`) or the node is `complete_no_claim`; `1` it is not met (`waiting`, `in-review`, `blocked`, `executor_blocked`, `stale`, `escalated`); `2` it cannot be determined (`unclaimed`, `error`, or `--ref` without a node). The sweep with no `<NODE_ID>` only reports and exits 0. **Review-loop escalation:** a round is one reviewed commit in `history/`; when the last `escalate_same_acceptance_blocks` rounds all block on one acceptance id (`same_acceptance`), when one reviewer family (from the roster) blocked that many of the rounds it reviewed in a row, whatever acceptance ids or models of that family it named (`same_family`; an approval from the family resets its count), or after `escalate_review_rounds` rounds (`review_rounds`), an unapproved leaf is `escalated` with its trigger named (`review list` prints it too, and reviewer prompts say so). `specy-road prompt <NODE_ID> --role rca --model <id>` (a rostered reviewer that neither implemented nor reviewed the leaf) then builds a root-cause prompt from the brief, every round's records side by side and the diffs between them. A coordinator can start one on a leaf that is not escalated with `--force --reason '<why>'` (rule `forced`; it needs a review round since the last analysis, and an active escalation wins over it); the reason is in the prompt and in the record's `trigger.reason`; the analyst writes `RCA-<round>.md` beside the reviews with a classification (specification, implementation, test, reviewer, environment, hard problem), cited evidence, the cheapest corrective action and, for a specification cause, a proposed acceptance rewrite for a human to approve. A valid record resolves the trigger and counting restarts; an invalid one is listed as a problem. Design: [design-notes/review-loop-rca.md](design-notes/review-loop-rca.md).

## Milestone full review

Leaf reviews are leaf-sized, so a regression that only shows across two leaves of one milestone can pass both. With `policy.milestone_full_review: true` in `roadmap/orchestration.yaml` (the default, read from the integration branch like the rest of the policy) a milestone, meaning any node with leaf children, gets one full review of its combined change before it is marked Complete:

- **The hold.** When `finish-this-task` closes the last leaf under a milestone, it leaves the milestone's own status as authored instead of setting it Complete, prints `[hold] <MILESTONE_ID> rolled up to Complete but …` with the reason and the next commands, and opens `work/reviews/<MILESTONE_ID>/` so `handoff status` lists it. The public loader's computed `rollup_status` stays `In Progress` until the review is approved, so `roadmap.md`, the brief and the PM GUI agree with `list-nodes`. Every ancestor above the held milestone waits with it. The hold is released only by a gate met at an integration tip where every leaf under the milestone is Complete: at the last leaf's own finish that leaf has not landed yet, so the reason is `its leaves <ids> have not landed on <integration ref>`, and an approval recorded against the tip before the last leaf landed never counts, since that tip is not the combined change. The hold applies only while `require_implementation_review_before_finish` is on; a milestone owned by the milestone-rollup state machine (`milestone_execution`) is left to that machine as before.
- **The packet.** Once the branch has landed, `specy-road review-packet <MILESTONE_ID>` builds the packet for the integration tip; while a leaf is not Complete at that tip it refuses, as `review record <MILESTONE_ID>` does, naming the leaves. A milestone has no registry claim, so its commit under review is the tip of the integration branch (remote-tracking ref first, else local) and its base is the first parent of the oldest `chore(rm-<codename>): register as in-progress` commit of any leaf under it that the tip reaches: the point the first leaf branched from, so the diff is every leaf's change together. `--base <ref>` overrides it, and the command refuses with that hint when no leaf registration is reachable (leaves landed without pickup). The header names the leaves covered, and the implementation summary section says the leaf summaries were reviewed with their leaves. `--ref` reviews another commit instead of the tip.
- **The records.** Reviewers file `specy-road review record <MILESTONE_ID> --model <id> --verdict approve|block --file <notes.md>` against that commit, with an empty `acceptance` map (a milestone has no acceptance ids of its own). The gate is the leaf gate at that commit, so `reviewers_required` and `reviewers_distinct_families` apply unchanged, and a new commit on the integration branch makes the records stale as for a leaf.
- **The release.** `specy-road mark-implementation-reviewed <MILESTONE_ID>` must run on the integration branch checkout with `HEAD` at the commit under review (the remote-tracking tip when there is one): before it reads a record, prompts, or writes anything it refuses on another branch, on a local integration branch behind or ahead of that tip (pull or push first), or while a leaf is not Complete there. It then evaluates the gate at that commit (the interactive human approval and `--yes` behave as for a leaf) and on success sets the milestone and the stale ancestors above it Complete, regenerates the exported files, and commits them as `roadmap: <MILESTONE_ID> full review approved; status -> Complete` with the `Reviewed-by` trailers. That authored Complete is the recorded closure: later integration commits, including the closure commit itself, do not reopen the hold, so `load_roadmap` keeps `rollup_status` Complete. `handoff status <MILESTONE_ID>` shows `leaves_open` (exit 1) while a leaf is not Complete at the tip, `awaiting_full_review` (exit 1) until the gate is met, `approved` with the release command once it is, and `complete_no_claim` afterwards; `review list <MILESTONE_ID>` prints the same next step under the gate line.

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

## Changed paths in the review packet

The packet's **Changed paths** section lists every path the diff changes and marks each one outside the touch zones. Those zones, also named in the header, are the claim row's `touch_zones` plus the node's `touch_zones` as committed at the commit under review, read from git. A zone added to the node on the feature branch therefore counts when the packet is built from a checkout on the integration branch. When the node cannot be read at that commit, the claim row's zones (else the node's in the working tree) are used.

## Test integrity in the review packet

`specy-road review-packet` inserts a **Test integrity** section immediately after **Changed paths**. It lists the same one-line findings as `specy-road integrity <NODE_ID>` (removed tests, removed test files, new skips, lost asserts, pytest-related config edits, new lint suppressions, widened baselines), or `_none_` when there are none. The section is computed from git objects only and is byte-identical for the same base and head commits. Reviewers use it to spot test weakening without running the CLI separately.

Two findings work for any language. `new-suppression: <path>:<line>` marks each line the leaf adds, in any file, that contains `noqa`, `type: ignore`, `pragma: no cover`, `pylint: disable`, `eslint-disable`, `@ts-ignore`, `@ts-expect-error` or `nolint` (any case); `<line>` is its number at the commit under review. `baseline-widened: <path> +<added lines>` names each file listed in `policy.ratchet_paths` (git-root-relative paths, read from the integration branch like the rest of the policy) that the leaf adds lines to; a leaf that only removes lines from it gets nothing. List there the baseline files a leaf should only shrink, such as clone, private-import, mutation or size baselines. Design: [design-notes/regression-prevention.md](design-notes/regression-prevention.md).

## Tests at risk

`specy-road impact <NODE_ID> [--ref REF]` prints, sorted and one per line, every Python test file (`test_*.py` or `*_test.py`) that imports, directly or through the repository's own modules at any depth, a module whose file changed between the merge base and REF. The import graph is built with `ast` over every `.py` file in the git tree at REF, parsed from its bytes so a coding cookie is honoured, with relative imports resolved and namespace packages followed. Paths are git-root relative, like `specy-road integrity`. A changed `conftest.py` makes the output the single line `ALL`. Otherwise a final `not analysed: <n> files` line counts the changed files that are not Python, plus any `.py` file at REF that does not parse. With `--zones` it starts from the modules under the node's touch zones at REF instead of the diff. It is advisory: it exits 0 whatever it lists and never decides a gate.

The executor prompt written at pickup has a **Tests at risk** section with the `--zones` list at the pickup commit (or `_none found_`), and `review-packet` has a **Tests at risk** section after **Test integrity** with the diff list. Both show at most 50 paths, then a count of the rest; the packet's section is computed from git objects only and is byte-identical for the same base and head commits. Imports the static graph cannot see (a script run in a subprocess, `importlib` with a computed name) are not followed.

## The diff in the review packet

The packet's **Diff** section inlines whole files only, within two budgets: `--max-diff-lines` (default 1500) and `--max-diff-bytes` (default 200000), since a rebuilt minified bundle is a few very long lines that the line budget alone lets through. Files are inlined in diff order until one would pass either budget; it and every file after it are listed with their `+`/`-` counts and the bytes of their diff, and the full diff is written to `work/reviews/<NODE_ID>/DIFF.patch`. `0` lifts a budget.

A generated file is never inlined, whatever the budgets: one under `specy_road/pm_gantt_static/` (the packaged PM GUI bundle), one that a `.gitattributes` line marks `linguist-generated`, read at the commit under review, or a well-known lockfile (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `uv.lock`, `Cargo.lock`, `go.sum`, in any directory) with no `linguist-generated` entry there; `linguist-generated=false` opts a lockfile back in. It is listed the same way and marked `generated`, the packet says generated files are never inlined, and its diff is in `DIFF.patch`. A generated file uses up neither budget, so the files after it are still inlined. Review the source it is built from instead.

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
