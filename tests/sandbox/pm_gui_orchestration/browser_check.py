"""M17.9 browser pass: each CHECKLIST.md item against the wheel's server; one screenshot per item; results.json.

Playwright for Python, sync API, headless Chromium. Run it with the interpreter that has Playwright:

    python3 browser_check.py --wheel dist/specy_road-<v>-py3-none-any.whl --wheelhouse dist/wheelhouse

Exit status 0 when every item passes, 1 otherwise. Item numbers and titles match CHECKLIST.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import sandbox_setup as ss
from playwright.sync_api import Page, expect, sync_playwright

TITLES = {"M0.1": "Establish shared contracts and ADR skeleton", "M0.2": "Roadmap validator in CI",
          "M0.3": "Define API contract outline in shared/", "M2": "testing"}
BADGES = {"M0.1": "approved", "M0.2": "running", "M0.3": "held", "M2": "failed"}
READ_ONLY = "server is read-only (specy-road gui --read-only)"
NO_SCOPE = ("grind-session --status needs a scope: pass --until NODE or --under NODE, or start a milestone "
            "session with `specy-road start-milestone-session <PARENT_NODE_ID>`")
WRONG_CODE = "wrong or missing X-PM-Decision-Code: enter the code `specy-road gui` printed in its terminal"
WORDS = "failures should surface before review"
CHECKS: list[tuple[int, str, Callable[[Any], str]]] = []


def check(title: str):
    def register(fn: Callable[[Any], str]) -> Callable[[Any], str]:
        CHECKS.append((len(CHECKS) + 1, title, fn))
        return fn
    return register


class Ctx:
    def __init__(self, sb: ss.Sandbox, page: Page, aux: Page) -> None:
        self.sb, self.page, self.aux, self.shoot = sb, page, aux, page
        self.s = sb.seeded

    def fresh(self, url: str | None = None) -> Page:
        """Load the app and wait for the outline; every item starts here."""
        self.shoot = self.page
        self.page.goto(url or self.sb.server.url)
        expect(self.page.get_by_text(TITLES["M0.2"]).first).to_be_visible()
        return self.page

    def show(self, title: str, body: Any) -> str:
        """An API answer as a page of its own, for the item's screenshot."""
        text = body if isinstance(body, str) else json.dumps(body, indent=1)
        self.aux.set_content(f"<h3>{title}</h3><pre id=body></pre>")
        self.aux.locator("#body").evaluate("(el, t) => { el.textContent = t; }", text)
        self.shoot = self.aux
        return text

    def drawer(self):
        self.page.get_by_role("button", name="Orchestration", exact=True).click()
        dialog = self.page.get_by_role("dialog", name="Orchestration")
        expect(dialog.locator(".worker-group").first).to_be_visible()
        return dialog

    def group(self, dialog, leaf: str):
        head = self.page.locator("h4", has_text=re.compile(rf"^{re.escape(leaf)}\s"))
        return dialog.locator(".worker-group").filter(has=head)

    def detail(self, leaf: str):
        g = self.group(self.drawer(), leaf)
        g.get_by_role("button", name="Detail").click()
        return g.locator(".worker-detail")

    def status(self, under: str | None = "M0"):
        self.page.get_by_role("button", name="Status", exact=True).click()
        dialog = self.page.get_by_role("dialog", name="Grind status")
        if under:
            dialog.get_by_label("Under").fill(under)
            expect(dialog.get_by_text(f"Goal {under}:")).to_be_visible()
        return dialog


def rows(table) -> list[list[str]]:
    return [[c.strip() for c in r.locator("td").all_inner_texts()] for r in table.locator("tbody tr").all()]


def same(observed: Any, expected: Any, what: str) -> None:
    assert observed == expected, f"{what}: expected {expected!r}, got {observed!r}"


@check("The wheel's server is what the browser loads")
def wheel_served(c: Ctx) -> str:
    page = c.fresh()
    same("mock=" in page.url, False, "mock in URL")
    same(page.title(), "pm-gantt", "page title")
    import specy_road
    return f"{page.url} serves specy_road {specy_road.__version__} from {specy_road.__file__}"


@check("The running worker's pid is alive before the browser step")
def pid_alive(c: Ctx) -> str:
    live = [w for w in c.sb.snapshot["leaves"]["M0.2"]["workers"] if w["id"] == c.s.workers["running"]]
    same([w["pid_alive"] for w in live], [True], "pid_alive")
    return c.show("GET /api/orchestration before the browser step: M0.2 workers",
                  c.sb.snapshot["leaves"]["M0.2"]["workers"])


@check("The Orchestration drawer opens with one group per leaf, then No leaf")
def drawer_groups(c: Ctx) -> str:
    c.fresh()
    dialog = c.drawer()
    expect(dialog).to_contain_text("Read-only: nothing here changes a worker, claim or review.")
    heads = [h.split()[0] if h.split() else h for h in
             dialog.locator(".worker-group > h4").all_inner_texts()]
    same(heads, ["M0.1", "M0.2", "M0.3", "M2", "No"], "group order")
    return " | ".join(dialog.locator(".worker-group > h4").all_inner_texts())


@check("Each leaf group shows its badge")
def drawer_badges(c: Ctx) -> str:
    c.fresh()
    dialog = c.drawer()
    got = {leaf: c.group(dialog, leaf).locator("h4 .worker-stall-badge").inner_text() for leaf in BADGES}
    same(got, BADGES, "badges")
    return json.dumps(got)


@check("Each leaf group shows the outline's id link and title")
def drawer_titles(c: Ctx) -> str:
    c.fresh()
    dialog = c.drawer()
    got = {leaf: c.group(dialog, leaf).locator("h4").inner_text() for leaf in TITLES}
    for leaf, title in TITLES.items():
        assert title in got[leaf], f"{leaf}: expected title {title!r} in {got[leaf]!r}"
        expect(c.group(dialog, leaf).locator("h4").get_by_role("button", name=leaf, exact=True)).to_be_visible()
    return json.dumps(got)


@check("The running leaf: claim and both workers")
def running_leaf(c: Ctx) -> str:
    c.fresh()
    g = c.group(c.drawer(), "M0.2")
    expect(g.locator("p.outline-meta").first).to_contain_text("Claim roadmap-ci · feature/rm-roadmap-ci · registered")
    got = [r[:4] + [r[6]] for r in rows(g.locator("table"))]
    model = f"generic / {ss.MODEL}"
    same(got, [[c.s.workers["terminated"], model, "", "terminated", got[0][4]],
               [c.s.workers["running"], model, "", "running", "—"]], "worker rows (id, model, account, status, ended)")
    assert got[0][4] != "—", "terminated worker has no ended age"
    return json.dumps(got)


@check("The failed worker shows its stalled flag")
def stalled(c: Ctx) -> str:
    c.fresh()
    got = rows(c.group(c.drawer(), "M2").locator("table"))
    same([(r[0], r[3], r[7]) for r in got], [(c.s.workers["failed"], "failed", "stalled")], "id, status, flags")
    return json.dumps(got)


@check("Two worktrees, one dirty")
def worktrees(c: Ctx) -> str:
    c.fresh()
    d = c.detail("M0.2")
    expect(d).to_contain_text("Ahead and behind are against the integration branch.")
    got = rows(d.locator("table").first)
    same(got, [[str(c.s.worktrees["leaf"]), "feature/rm-roadmap-ci", "no", "1", "0"],
               [str(c.s.worktrees["scratch"]), "—", "yes", "unknown", "unknown"]], "worktree rows")
    return json.dumps(got)


@check("READY with one approving and one stale review, gate approved")
def ready_reviews(c: Ctx) -> str:
    c.fresh()
    d = c.detail("M0.1")
    tip, old = c.s.commits["tip"], c.s.commits["old"]
    expect(d).to_contain_text(f"{tip[:12]} · {ss.MODEL} ·")
    got = rows(d.locator("table").last)
    same(got, [[ss.MODEL, "approve", old, "stale"], ["human", "approve", tip, "fresh"]], "review rows")
    expect(d).to_contain_text("approved · approvals 1 · blocks 0 · fresh for HEAD fresh")
    return json.dumps(got)


@check("The held leaf lists its hold")
def held(c: Ctx) -> str:
    c.fresh()
    got = rows(c.detail("M0.3").locator("table").last)
    same(got, [["hold list", "M0.3", ss.HOLD_REASON]], "hold rows")
    return json.dumps(got)


@check("The leafless worker is under No leaf")
def no_leaf(c: Ctx) -> str:
    c.fresh()
    dialog = c.drawer()
    g = dialog.locator(".worker-group").filter(has=c.page.locator("h4", has_text=re.compile(r"^\s*No leaf")))
    got = rows(g.locator("table"))
    same([(r[0], r[3]) for r in got], [(c.s.workers["idle"], "idle")], "id, status")
    same(g.get_by_role("button", name="Detail").count(), 0, "Detail buttons")
    return json.dumps(got)


@check("Outline badges, hover and click-through")
def outline_badges(c: Ctx) -> str:
    page = c.fresh()
    badge = {leaf: page.locator(".outline-title-row", has_text=title).locator("button.worker-stall-badge")
             for leaf, title in TITLES.items()}
    got = {leaf: b.inner_text() if b.count() else None for leaf, b in badge.items()}
    same(got, BADGES, "outline badges")
    hover = badge["M0.2"].get_attribute("title") or ""
    expected = [f"claim: roadmap-ci · feature/rm-roadmap-ci · ", f"workers: {c.s.workers['terminated']} terminated, "
                f"{c.s.workers['running']} running", "worktrees: 2", "READY: —", "reviews: —", "holds: —"]
    lines = hover.splitlines()
    assert len(lines) == len(expected), f"hover has {len(lines)} lines, want {len(expected)}: {hover!r}"
    for line, want in zip(lines, expected, strict=True):
        assert line.startswith(want), f"hover line {line!r} does not start with {want!r}"
    badge["M0.2"].click()
    dialog = page.get_by_role("dialog", name="Orchestration")
    expect(dialog.locator(".worker-group")).to_have_count(1)
    return json.dumps({"badges": got, "hover": hover})


@check("Without the route (404) the drawer says so and the outline has no badges")
def not_found(c: Ctx) -> str:
    c.page.route("**/api/orchestration", lambda r: r.fulfill(
        status=404, content_type="application/json", body='{"detail":"no API route /api/orchestration"}'))
    try:
        page = c.fresh()
        same(page.locator(".outline-title-row button.worker-stall-badge").count(), 0, "outline badges")
        page.get_by_role("button", name="Orchestration", exact=True).click()
        msg = page.get_by_role("dialog", name="Orchestration").locator(".workspace-empty")
        expect(msg).to_have_text("This server does not provide the orchestration snapshot yet.")
        return msg.inner_text()
    finally:
        c.page.unroute("**/api/orchestration")


@check("POST /api/orchestration under --read-only is 403")
def post_refused(c: Ctx) -> str:
    c.fresh()
    status, body = c.page.evaluate(
        "async () => { const r = await fetch('/api/orchestration', {method: 'POST'}); return [r.status, await r.text()]; }")
    same((status, json.loads(body)), (403, {"detail": READ_ONLY}), "status and body")
    return c.show("POST /api/orchestration", f"{status} {body}")


@check("The Status modal opens in the app's modal frame; no scope shows the server's refusal")
def status_no_scope(c: Ctx) -> str:
    c.fresh()
    dialog = c.status(under=None)
    same(dialog.get_attribute("class"), "modal-window", "dialog class")
    expect(dialog.get_by_text(NO_SCOPE)).to_be_visible()
    return NO_SCOPE


@check("Status under M0: goal, totals, last updated, sections, estimate, decisions and sessions")
def status_content(c: Ctx) -> str:
    c.fresh()
    dialog = c.status()
    head = ss.git(c.s.repo, "rev-parse", "main")[:12]
    for text in ["Goal M0: under M0: its subtree",
                 "totals: total 3, done 2, cancelled 0, remaining 1, held 0, active 1, ready 0, waiting 0, "
                 "awaiting merge 0, not pickable 0",
                 f"as of main @ {head}, this checkout, not fetched", "Active (1)",
                 f"M0.2 Roadmap validator in CI: review waiting; worker {c.s.workers['running']} (generic, running)",
                 "not enough data: 0 completion(s) in scope, minimum 5", "Decisions waiting on a person",
                 "D1 [decision] node M0.2 (local ledger), needed-by", "Open brainstorm sessions (1)",
                 "sandbox-ideas (brainstorm, 1 ideas)", "Live sessions (1)", "planner on main, expires",
                 "note: planning M0"]:
        expect(dialog).to_contain_text(text)
    expect(dialog.get_by_text(re.compile(r"^Last updated .+ \(\d+ s ago\)"))).to_be_visible()
    return dialog.inner_text()


@check("Status refreshes from the refresh icon and on its interval")
def status_refresh(c: Ctx) -> str:
    c.fresh()
    dialog = c.status()
    same(dialog.get_by_label("Refresh every").input_value(), "60", "default interval")
    with c.page.expect_request(lambda r: "/api/grind-status?under=M0" in r.url, timeout=5000):
        dialog.get_by_role("button", name="Refresh now").click()
    with c.page.expect_request(lambda r: "/api/grind-status?under=M0" in r.url, timeout=5000):
        dialog.get_by_label("Refresh every").select_option("30")  # a new interval loads at once
    start = time.monotonic()
    with c.page.expect_request(lambda r: "/api/grind-status?under=M0" in r.url, timeout=45000):
        pass
    waited = time.monotonic() - start
    assert 25 <= waited <= 40, f"interval request after {waited:.1f} s, expected about 30 s"
    return f"refresh icon: request at once; 30 s interval: next request after {waited:.1f} s"


def decide(dialog, words: str, code: str) -> None:
    dialog.get_by_label("Decision").select_option(index=1)
    dialog.get_by_label("every-push (slower pushes, earlier failures)").check()
    dialog.get_by_label("Why, in your own words").fill(words)
    dialog.get_by_label("Code from the terminal that started the GUI").fill(code)
    dialog.get_by_role("button", name="Review decision").click()


@check("The read-only server refuses a PM decision")
def decision_read_only(c: Ctx) -> str:
    c.fresh()
    dialog = c.status()
    decide(dialog, WORDS, "not-the-code")
    dialog.get_by_role("button", name="Record decision").click()
    expect(dialog.get_by_text(f"Not recorded (403): {READ_ONLY}")).to_be_visible()
    same(ledger_entry(c)["status"], "open", "D1 status")
    return f"Not recorded (403): {READ_ONLY}"


def ledger_entry(c: Ctx) -> dict[str, Any]:
    import yaml
    doc = yaml.safe_load((c.s.repo / "roadmap" / "decisions.local.yaml").read_text(encoding="utf-8"))
    return next(e for e in doc["entries"] if e["id"] == ss.DECISION)


@check("A PM decision needs typed words and the startup code")
def decision_needs_code(c: Ctx) -> str:
    c.writable = c.sb.writable_server()
    c.fresh(c.writable.url)
    dialog = c.status()
    decide(dialog, "", "")
    expect(dialog.get_by_text("Say why, in your own words.")).to_be_visible()
    decide(dialog, WORDS, "")
    expect(dialog.get_by_text("Enter the code `specy-road gui` printed in its terminal.")).to_be_visible()
    decide(dialog, WORDS, "not-the-code")
    dialog.get_by_role("button", name="Record decision").click()
    expect(dialog.get_by_text(f"Not recorded (403): {WRONG_CODE}")).to_be_visible()
    same(ledger_entry(c)["status"], "open", "D1 status")
    return f"Not recorded (403): {WRONG_CODE}"


@check("A recorded decision has channel pm-gui and shows as decided in the GUI, not yet processed")
def decision_recorded(c: Ctx) -> str:
    c.fresh(c.writable.url)
    dialog = c.status()
    decide(dialog, WORDS, c.writable.code or "")
    answer = f"every-push: {WORDS}"
    expect(dialog).to_contain_text(f"Recorded answer: {answer}")
    dialog.get_by_role("button", name="Record decision").click()
    expect(dialog.get_by_text("Recorded D1 on local ledger. A coordinator processes it at its next status check.")
           ).to_be_visible()
    e = ledger_entry(c)
    same({k: e.get(k) for k in ("status", "channel", "decided_by", "answer")},
         {"status": "closed", "channel": "pm-gui", "decided_by": "operator", "answer": answer}, "D1 entry")
    expect(dialog).to_contain_text("Decided in the GUI, not yet processed")
    expect(dialog).to_contain_text(f"D1 [answer] node M0.2: {answer}")
    return dialog.inner_text()


def wheel_info(ns: argparse.Namespace) -> dict[str, Any]:
    if not ns.wheel:
        return {"path": None}
    return {"path": ns.wheel.name, "sha256": hashlib.sha256(ns.wheel.read_bytes()).hexdigest(),
            "commit": (ns.wheel.parent / "COMMIT").read_text(encoding="utf-8").strip()}


def run(sb: ss.Sandbox, shots: Path) -> list[dict[str, Any]]:
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        context.set_default_timeout(15000)
        expect.set_options(timeout=15000)
        c = Ctx(sb, context.new_page(), context.new_page())
        for n, title, fn in CHECKS:
            row: dict[str, Any] = {"n": n, "title": title}
            try:
                row.update(passed=True, observed=fn(c))
            except Exception as e:  # one item's failure is its result; the pass goes on
                row.update(passed=False, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=3))
            shot = shots / f"{n:02d}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:50]}.png"
            c.shoot.screenshot(path=str(shot), full_page=True)
            results.append({**row, "screenshot": shot.name})
            print(f"{n:2d} {'PASS' if row['passed'] else 'FAIL'} {title}", flush=True)
        browser.close()
    return results


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ss.add_install_args(p)
    ns = p.parse_args()
    work = ss.prepare(ns)
    import specy_road

    report: dict[str, Any] = {"wheel": wheel_info(ns), "specy_road": specy_road.__file__,
                              "version": specy_road.__version__,
                              "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        with ss.sandbox(work) as sb:
            report.update(url=sb.server.url, workers=sb.seeded.workers, commits=sb.seeded.commits)
            (work / "screens").mkdir()
            report["items"] = run(sb, work / "screens")
    except Exception as e:  # setup failed: the report says where the run stopped
        report["setup_error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        report["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if work.is_dir():
            (work / "results.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
            print(f"results: {work / 'results.json'}")
    sys.exit(0 if all(i["passed"] for i in report["items"]) else 1)


if __name__ == "__main__":
    main()
