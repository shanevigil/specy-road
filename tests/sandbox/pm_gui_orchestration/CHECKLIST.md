# M17.9 checklist: the orchestration view in a browser

Expected values come from the code at this commit and from the seed in `sandbox_setup.py`, not from a
rendered page. `browser_check.py` walks the items in this order, with these numbers and titles.

## Seed

The fixture repo is a copy of `tests/fixtures/specy_road_dogfood` on `main`, with a bare `origin`.
Worker ids are assigned in creation order; harness `generic`, model `claude-opus-5-5`, no account.

| Leaf | Claim (codename, branch) | State |
|---|---|---|
| M0.1 | contracts-bootstrap, feature/rm-contracts-bootstrap | READY at the branch tip by claude-opus-5-5; review `human` approve at the tip; review `claude-opus-5-5` approve at the previous commit |
| M0.2 | roadmap-ci, feature/rm-roadmap-ci | w-0001 `terminated` in a detached worktree `wt-scratch` with an uncommitted edit; w-0002 `running` in worktree `wt-leaf` on the branch (one commit ahead of `main`), its pid an inert child the setup supervises |
| M0.3 | api-contract-outline, feature/rm-api-contract-outline | hold list line `M0.3 # waiting on the maintainer` |
| M2 | testing, feature/rm-testing | w-0003 `failed`, flag `stalled` |
| (none) | chore `tidy-docs` | w-0004 `idle` |

Also: local ledger entry `D1` (kind decision, node M0.2, options `every-push`, `main-only`), brainstorm
session `sandbox-ideas` with one idea, live session `planner` (note `planning M0`).

## Items

1. **The wheel's server is what the browser loads.** The page title is `pm-gantt`; the URL has no
   `mock=`; `results.json` names the wheel's sha256 and `COMMIT` (the branch head it was built from) and
   a `specy_road` imported from the install target, not a checkout. Item 6's screenshot shows `w-0002`,
   which the mock lacks.
2. **The running worker's pid is alive before the browser step.** `GET /api/orchestration`, read by the
   setup before Chromium starts: `leaves["M0.2"].workers` has `w-0002` with `pid_alive: true`.
3. **The Orchestration drawer opens with one group per leaf, then No leaf.** Header button
   **Orchestration** opens a dialog titled `Orchestration` containing "Read-only: nothing here changes a
   worker, claim or review."; groups in outline order `M0.1`, `M0.2`, `M0.3`, `M2`, then `No leaf`.
4. **Each leaf group shows its badge** (`leafBadge`, M17.1 precedence): M0.1 `approved`, M0.2 `running`,
   M0.3 `held`, M2 `stalled`.
5. **Each leaf group shows the outline's id link and title** (docs/pm-gui.md, Groups): the id is a link
   button, then the title: M0.1 "Establish shared contracts and ADR skeleton", M0.2 "Roadmap validator in
   CI", M0.3 "Define API contract outline in shared/", M2 "testing".
6. **The running leaf: claim and both workers.** M0.2: `Claim roadmap-ci · feature/rm-roadmap-ci ·
   registered <age>`; worker rows (worker, harness / model, account, status, ended):
   `w-0001 | generic / claude-opus-5-5 | (empty) | terminated | <age>` and
   `w-0002 | generic / claude-opus-5-5 | (empty) | running | —`.
7. **The failed worker shows its stalled flag.** M2: one row, `w-0003`, status `failed` (the record state,
   shown as the snapshot sends it), flags `stalled`.
8. **Two worktrees, one dirty.** M0.2 **Detail**, "Ahead and behind are against the integration branch.",
   rows (path, branch, dirty, ahead, behind) sorted by path:
   `<work>/wt-leaf | feature/rm-roadmap-ci | no | 1 | 0` and `<work>/wt-scratch | — | yes | unknown | unknown`.
9. **READY with one approving and one stale review, gate approved.** M0.1 **Detail**: READY
   `<tip, 12 chars> · claude-opus-5-5 · <age>`; Reviews (model, verdict, commit, fresh for HEAD), in the
   snapshot's order: `claude-opus-5-5 | approve | <previous commit> | stale`, `human | approve | <tip> |
   fresh`; Gate `approved · approvals 1 · blocks 0 · fresh for HEAD fresh` (the READY author's review does
   not count).
10. **The held leaf lists its hold.** M0.3 **Detail**, Holds: `hold list | M0.3 | waiting on the maintainer`.
11. **The leafless worker is under No leaf.** Group `No leaf`: one row, `w-0004`, status `idle`; no
    **Detail** button.
12. **Outline badges, hover and click-through.** Outline rows: M0.1 `approved`, M0.2 `running`, M0.3
    `held`, M2 `stalled`. The M0.2 badge's hover, line by line: `claim: roadmap-ci ·
    feature/rm-roadmap-ci · <age>`, `workers: w-0001 terminated, w-0002 running`, `worktrees: 2`,
    `READY: —`, `reviews: —`, `holds: —`. Clicking it opens the drawer with only the M0.2 group.
13. **Without the route (404) the drawer says so and the outline has no badges.** With `GET
    /api/orchestration` answered 404 by request interception: no outline badge, and the drawer shows
    "This server does not provide the orchestration snapshot yet."
14. **POST /api/orchestration under --read-only is 403**, body
    `{"detail": "server is read-only (specy-road gui --read-only)"}`.
15. **The Status modal opens in the app's modal frame; no scope shows the server's refusal.** Header
    button **Status** opens a dialog titled `Grind status` with class `modal-window` (the frame the
    Orchestration drawer uses). With Until and Under empty it shows the 400 detail: "grind-session
    --status needs a scope: pass --until NODE or --under NODE, or start a milestone session with
    `specy-road start-milestone-session <PARENT_NODE_ID>`".
16. **Status under M0.** With Under `M0`: `Goal M0: under M0: its subtree`; `totals: total 3, done 2,
    cancelled 0, remaining 1, held 0, active 1, ready 0, waiting 0, awaiting merge 0, not pickable 0`;
    `Last updated <time> (<n> s ago) · as of main @ <main, 12 chars>, this checkout, not fetched`;
    `Active (1)`: `M0.2 Roadmap validator in CI: review waiting; worker w-0002 (generic, running)`;
    Estimate: `not enough data: 0 completion(s) in scope, minimum 5`; Decisions waiting on a person:
    `D1 [decision] node M0.2 (local ledger), needed-by <seed date + 7 days>`; `Open brainstorm sessions
    (1)`: `sandbox-ideas (brainstorm, 1 ideas)`; `Live sessions (1)`: `planner on main, expires <time>,
    note: planning M0`.
17. **Status refreshes from the refresh icon and on its interval.** The interval select defaults to `60`
    (60 s); **Refresh now** sends `GET /api/grind-status?under=M0` at once; choosing `30 s` loads at
    once and then again 25 to 40 s later with no click.
18. **The read-only server refuses a PM decision.** Decide `D1`, option `every-push`, words and any code,
    **Review decision**, **Record decision**: "Not recorded (403): server is read-only (specy-road gui
    --read-only)"; `D1` stays `open` in `roadmap/decisions.local.yaml`.
19. **A PM decision needs typed words and the startup code** (a second server, not read-only, on the
    same repo; its code read from its terminal output). No words: "Say why, in your own words."; words,
    no code: "Enter the code `specy-road gui` printed in its terminal."; a wrong code, recorded: "Not
    recorded (403): wrong or missing X-PM-Decision-Code: enter the code `specy-road gui` printed in its
    terminal"; `D1` stays `open`.
20. **A recorded decision has channel pm-gui and shows as decided in the GUI, not yet processed.** With
    the code: the review shows `Recorded answer: every-push: <words>`; recording shows "Recorded D1 on
    local ledger. A coordinator processes it at its next status check."; `D1` in the ledger is `status:
    closed`, `channel: pm-gui`, `decided_by: operator`, `answer: every-push: <words>`; the modal shows
    "Decided in the GUI, not yet processed" with `D1 [answer] node M0.2: every-push: <words>`.

## Read from the code before the run

- Items 5 and 12 are expected to fail at this commit: `GET /api/orchestration` keys `leaves` by node id
  (`M0.2`, `specy_road/orchestration/state.py`), while the outline joins on `node_key`, a UUID
  (`OutlineTable.tsx`, `buildOrchestrationView`), and docs/pm-gui.md says the keys are node keys. The
  drawer would then show each leaf as missing from the outline (`<code>` id, title `—`) and the outline
  no badges.
- Item 7: docs/pm-gui.md lists worker statuses as `claimed`, `running`, `exited_ok`, `exited_failed`,
  `abandoned`; the snapshot sends the record state (`failed`), so `leafBadge` never sees
  `exited_failed` on a worker and a failed, stalled worker's leaf badge is `stalled`.
