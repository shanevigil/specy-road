# M17.9 results: the orchestration view in a real browser

## Run

- **Date:** 2026-11-15, 22:39:51 to 22:40:53 UTC.
- **Approval:** M17.10's re-run approval of 2026-11-15, within its limits: one sandbox VM, the default golden image and one run window. The sandbox operator approved the run, and the tool trials came first.
- **VM image:** the sandbox's default golden image for headless browsers: Ubuntu 24.04 LTS, Python 3.12.3, and Playwright for Python 1.60.0 with Chromium. The image has no node.
- **Wheel:** `specy_road-0.3.1rc2-py3-none-any.whl` (sha256 `1ce13512658857b9…`), built by `build_on_host.sh` from the branch head `faba4e28b9746e061421c812834b28f6e66f002c`. It was installed with `pip install --target` from the offline wheelhouse, and the module loaded is the installed wheel's (`0.3.1rc2`).
- **How it ran:**
  - The bundle went in through the sandbox's chunked push, with its sha256 checked in the guest.
  - The screenshot tool was tried first, on `about:blank`.
  - The sandbox's browser-test tool then ran `sandbox_pytest_entry.py`: 1 passed, 0 failed, in 69 s. That test runs `browser_check.py` and fails unless every item passes.
  - The results came back through the sandbox's artifact fetch. The VM was stopped and released, and the release reset it.

## Items

| # | Item | Result | Screenshot (under work/, gitignored) |
|---|---|---|---|
| 1 | The wheel's server is what the browser loads | pass | `01-the-wheel-s-server-is-what-the-browser-loads.png` |
| 2 | The running worker's pid is alive before the browser step | pass | `02-the-running-worker-s-pid-is-alive-before-the-brows.png` |
| 3 | The Orchestration drawer opens with one group per leaf, then No leaf | pass | `03-the-orchestration-drawer-opens-with-one-group-per-.png` |
| 4 | Each leaf group shows its badge | pass | `04-each-leaf-group-shows-its-badge.png` |
| 5 | Each leaf group shows the outline's id link and title | pass | `05-each-leaf-group-shows-the-outline-s-id-link-and-ti.png` |
| 6 | The running leaf: claim and both workers | pass | `06-the-running-leaf-claim-and-both-workers.png` |
| 7 | The failed worker shows its stalled flag | pass | `07-the-failed-worker-shows-its-stalled-flag.png` |
| 8 | Two worktrees, one dirty | pass | `08-two-worktrees-one-dirty.png` |
| 9 | READY with one approving and one stale review, gate approved | pass | `09-ready-with-one-approving-and-one-stale-review-gate.png` |
| 10 | The held leaf lists its hold | pass | `10-the-held-leaf-lists-its-hold.png` |
| 11 | The leafless worker is under No leaf | pass | `11-the-leafless-worker-is-under-no-leaf.png` |
| 12 | Outline badges, hover and click-through | pass | `12-outline-badges-hover-and-click-through.png` |
| 13 | Without the route (404) the drawer says so and the outline has no badges | pass | `13-without-the-route-404-the-drawer-says-so-and-the-o.png` |
| 14 | POST /api/orchestration under --read-only is 403 | pass | `14-post-api-orchestration-under-read-only-is-403.png` |
| 15 | The Status modal opens in the app's modal frame; no scope shows the server's refusal | pass | `15-the-status-modal-opens-in-the-app-s-modal-frame-no.png` |
| 16 | Status under M0: goal, totals, last updated, sections, estimate, decisions and sessions | pass | `16-status-under-m0-goal-totals-last-updated-sections-.png` |
| 17 | Status refreshes from the refresh icon and on its interval | pass | `17-status-refreshes-from-the-refresh-icon-and-on-its-.png` |
| 18 | The read-only server refuses a PM decision | pass | `18-the-read-only-server-refuses-a-pm-decision.png` |
| 19 | A PM decision needs typed words and the startup code | pass | `19-a-pm-decision-needs-typed-words-and-the-startup-co.png` |
| 20 | A recorded decision has channel pm-gui and shows as decided in the GUI, not yet processed | pass | `20-a-recorded-decision-has-channel-pm-gui-and-shows-a.png` |

**20 of 20 pass.**

## Defects

- **Found by the first run (same day) and fixed before this one:** the drawer's leaf groups followed the Gantt's dependency order instead of the outline's (item 3). That was filed and fixed as M17.17.
- **Not a defect:** the first run also reported outline badges missing (item 12). That was a timing error in the check, which read the outline before the page's own `GET /api/orchestration` answer arrived. The GUI already requests the snapshot on each roadmap load. Items 12 and 13 now wait for that answer.
- **This run:** none.
