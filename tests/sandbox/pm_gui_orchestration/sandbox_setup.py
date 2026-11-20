"""M17.9: install the wheel, seed a fixture repo with orchestration state, serve it with `specy-road gui`.

Standard library plus the installed specy-road. `browser_check.py` imports this module; run alone it
seeds, serves read-only, confirms the snapshot and exits (default) or serves until interrupted (`--serve`).
Every child it starts (the inert "running worker" and each server) is stopped on exit, pass or fail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from tests.support.bounded_wait import pause

HERE = Path(__file__).resolve().parent
DOGFOOD = HERE.parents[1] / "fixtures" / "specy_road_dogfood"
MODEL = "claude-opus-5-5"  # the dogfood roster's executor and reviewer
RUNNING, STALLED, READY, HELD, CHORE = "M0.2", "M2", "M0.1", "M0.3", "tidy-docs"
HOLD_REASON = "waiting on the maintainer"
DECISION = "D1"
CODE_LINE = re.compile(r"PM decisions: enter this code in the Status window to confirm a decision: (\S+)")
# Inert: sleeps until its supervisor is gone. The extra arguments make `ps` show a worker wrapper.
INERT = "import os, sys, time\nwhile os.getppid() == int(sys.argv[3]):\n    time.sleep(1)\n"


def install(wheel: Path, wheelhouse: Path | None, target: Path) -> None:
    """`pip install --target` the wheel with its [gui] extra; offline from ``wheelhouse`` when given."""
    cmd = [sys.executable, "-m", "pip", "install", "-q", "--target", str(target)]
    if wheelhouse:
        cmd += ["--no-index", "--find-links", str(wheelhouse)]
    subprocess.run([*cmd, f"specy-road[gui] @ {wheel.resolve().as_uri()}"], check=True)
    sys.path.insert(0, str(target))
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(target), os.environ.get("PYTHONPATH")]))


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, rel: str, text: str, message: str) -> str:
    (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@dataclass
class Seeded:
    repo: Path
    worktrees: dict[str, Path]
    workers: dict[str, str]  # role -> worker id
    commits: dict[str, str]  # READY leaf: old (stale review) and tip
    inert: subprocess.Popen
    branches: dict[str, str]


def _review(node: str, model: str, sha: str) -> str:
    data = {"node_id": node, "model": model, "date": date.today().isoformat(), "verdict": "approve",
            "commit": sha, "acceptance": {},  # the dogfood leaves list no criteria
            "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
            "commands_rerun": [], "required_changes": [], "fresh_session": True, "authored_fix": False,
            "is_coordinator": False}
    return "---\n" + json.dumps(data, indent=1) + "\n---\nseeded for the M17.9 sandbox run\n"


def git_fixture(work: Path) -> tuple[Path, dict[str, str], str, str]:
    """The dogfood copy on ``main`` with four claims, their branches and a bare ``origin``.

    Returns the repo, each leaf's branch, and the READY leaf's previous and tip commits.
    """
    repo = work / "repo"
    shutil.copytree(DOGFOOD, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "M17.9 seed")
    git(repo, "config", "user.email", "seed@example.invalid")
    # What a consumer repo's managed .gitignore block ignores, so the main checkout stays clean.
    (repo / ".gitignore").write_text("work/\nroadmap/decisions.local.yaml\n.specyrd/cache/\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "dogfood fixture")
    nodes = {n["id"]: n for f in sorted((repo / "roadmap" / "phases").glob("*.json"))
             for n in json.loads(f.read_text(encoding="utf-8"))["nodes"]}
    leaves = (READY, RUNNING, HELD, STALLED)
    branches = {n: f"feature/rm-{nodes[n]['codename']}" for n in leaves}
    rows = "".join(f"  - {{codename: {nodes[n]['codename']}, node_id: {n}, branch: {branches[n]}, "
                   f"started: '{date.today().isoformat()}'}}\n" for n in leaves)
    commit(repo, "roadmap/registry.yaml", f"version: 1\nentries:\n{rows}", "register four claims")
    for n in leaves:
        git(repo, "branch", branches[n])
    git(repo, "checkout", "-q", branches[READY])
    old = commit(repo, "READY-NOTES.md", "first pass\n", "first pass")
    tip = commit(repo, "READY-NOTES.md", "after review\n", "address review")
    git(repo, "checkout", "-q", branches[RUNNING])
    commit(repo, "RUNNING-NOTES.md", "in progress\n", "work in progress")
    git(repo, "checkout", "-q", "main")
    origin = work / "origin.git"
    git(work, "init", "-q", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main", *branches.values())
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "main")  # as clone does: the integration branch is named there
    return repo, branches, old, tip


def seed(work: Path, procs: list) -> Seeded:
    """The fixture repo under ``work``: four claimed leaves, a leafless worker, a hold, a decision, sessions."""
    from specy_road.brainstorm_session import BrainstormSession, add_idea, write_session
    from specy_road.orchestration.guard.session_presence import start_session
    from specy_road.orchestration.records.chore_records import chores_dir
    from specy_road.orchestration.records.decisions import add_entry
    from specy_road.orchestration.workers import worker_state as ws
    from specy_road.review_files import reviews_dir
    from specy_road.review_target import resolve_target

    repo, branches, old, tip = git_fixture(work)
    leaf_wt, scratch = work / "wt-leaf", work / "wt-scratch"
    git(repo, "worktree", "add", "-q", str(leaf_wt), branches[RUNNING])
    git(repo, "worktree", "add", "-q", "--detach", str(scratch), branches[RUNNING])
    (scratch / "vision.md").write_text("uncommitted scratch edit\n", encoding="utf-8")

    ended = ws.create_record(repo, RUNNING, "generic", MODEL, scratch)
    ws.set_state(repo, ended, "terminated", pid=None)
    live = ws.create_record(repo, RUNNING, "generic", MODEL, leaf_wt, branch=branches[RUNNING])
    inert = subprocess.Popen([sys.executable, "-c", INERT, "specy_road.worker_runner", live.worker_id,
                              str(os.getpid())], stdin=subprocess.DEVNULL, start_new_session=True)
    procs.append(inert)
    ws.set_state(repo, live, "running", pid=inert.pid)
    failed = ws.create_record(repo, STALLED, "generic", MODEL, repo, branch=branches[STALLED])
    ws.set_state(repo, failed, "failed", pid=None)
    ws.add_flag(repo, failed, "stalled")
    chores_dir(repo).mkdir(parents=True, exist_ok=True)
    (chores_dir(repo) / f"{CHORE}.json").write_text(json.dumps(
        {"slug": CHORE, "branch": f"chore/{CHORE}", "worktree": str(repo), "touch_zones": ["docs"]}),
        encoding="utf-8")
    idle = ws.create_record(repo, CHORE, "generic", MODEL, repo)
    ws.set_state(repo, idle, "idle", pid=None)

    folder = reviews_dir(repo, READY)
    folder.mkdir(parents=True, exist_ok=True)
    base = resolve_target(repo, READY).base
    (folder / f"READY-{MODEL}.md").write_text(
        f"---\nnode_id: {READY}\nagent: {MODEL}\nbranch: {branches[READY]}\ncommit: '{tip}'\n"
        f"base: '{base}'\nchanged_paths: [READY-NOTES.md]\n---\n", encoding="utf-8")
    # The READY's author cannot approve its own work: the counted approval is the human's.
    (folder / "REVIEW-human.md").write_text(_review(READY, "human", tip), encoding="utf-8")
    (folder / f"REVIEW-{MODEL}.md").write_text(_review(READY, MODEL, old), encoding="utf-8")
    (repo / "work" / "grind-hold.txt").write_text(f"{HELD} # {HOLD_REASON}\n", encoding="utf-8")

    add_entry(repo, node_id=RUNNING, kind="decision", decision_id=DECISION, local=True,
              summary="Run the roadmap validator on every push or only on main?",
              why_now="The CI job is being written now.",
              options=[{"label": "every-push", "effect": "slower pushes, earlier failures"},
                       {"label": "main-only", "effect": "faster pushes, later failures"}],
              recommendation="every-push", recommendation_reason="failures surface before review",
              default_if_unanswered="every-push", needed_by=(date.today() + timedelta(days=7)).isoformat())
    ideas = BrainstormSession(slug="sandbox-ideas", topic="what the CI validator should report")
    add_idea(ideas, title="Report broken dependencies first")
    write_session(repo, ideas)
    start_session(repo, "planner", paths=["roadmap"], note="planning M0")
    return Seeded(repo, {"leaf": leaf_wt.resolve(), "scratch": scratch.resolve()},
                  {"terminated": ended.worker_id, "running": live.worker_id, "failed": failed.worker_id,
                   "idle": idle.worker_id}, {"old": old, "tip": tip}, inert, branches)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """`specy-road gui` on a free loopback port, in its own process group; its output to ``log``.

    The PM decision code (writable server only) is kept in memory and masked in the log.
    """

    def __init__(self, repo: Path, *, read_only: bool, log: Path) -> None:
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.code: str | None = None
        cmd = [sys.executable, "-m", "specy_road.cli", "gui", "--port", str(self.port), "--repo-root", str(repo)]
        self.proc = subprocess.Popen([*cmd, *(["--read-only"] if read_only else [])], cwd=repo,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, start_new_session=True)
        self._log = log
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        with self._log.open("w", encoding="utf-8") as out:
            for line in self.proc.stdout:  # type: ignore[union-attr]
                if m := CODE_LINE.search(line):
                    self.code = m[1]
                    line = line.replace(m[1], "<code kept in memory>")
                out.write(line)
                out.flush()

    def wait_ready(self, timeout: float = 90.0) -> None:
        """Poll ``GET /`` until 200 (and the decision code, for a writable server); no fixed sleep."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited {self.proc.returncode}; see {self._log}")
            try:
                with urllib.request.urlopen(self.url + "/", timeout=2) as r:
                    if r.status == 200 and (self.code or "--read-only" in self.proc.args):
                        return
            except OSError:
                pass
            pause(0.2)
        raise RuntimeError(f"server not ready in {timeout:.0f} s; see {self._log}")

    def get_json(self, path: str) -> Any:
        with urllib.request.urlopen(self.url + path, timeout=30) as r:
            return json.load(r)


def stop(proc: subprocess.Popen) -> None:
    """SIGTERM the child's process group (each child leads its own), SIGKILL after 10 s."""
    if proc.poll() is not None:
        return
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(10)


def confirm(snap: dict[str, Any], s: Seeded) -> None:
    """The seeded state is in the snapshot and the running worker's pid is alive, before any browser step."""
    leaves = snap["leaves"]
    missing = {READY, RUNNING, HELD, STALLED} - leaves.keys()
    if missing:
        raise RuntimeError(f"snapshot lacks the seeded leaves {sorted(missing)}")
    live = [w for w in leaves[RUNNING]["workers"] if w["id"] == s.workers["running"]]
    if not live or live[0]["pid_alive"] is not True:
        raise RuntimeError(f"running worker {s.workers['running']} is not pid_alive: {live}")
    if [w["id"] for w in snap["leafless_workers"]] != [s.workers["idle"]]:
        raise RuntimeError(f"leafless workers: {snap['leafless_workers']}")


@dataclass
class Sandbox:
    work: Path
    seeded: Seeded
    server: Server
    snapshot: dict[str, Any]
    procs: list

    def writable_server(self) -> Server:
        """A second, writable server on the same repo (the PM decision items); stopped with the rest."""
        srv = Server(self.seeded.repo, read_only=False, log=self.work / "server-writable.log")
        self.procs.append(srv.proc)
        srv.wait_ready()
        return srv


def _raise_exit(signum: int, _frame: Any) -> None:
    raise SystemExit(128 + signum)


@contextmanager
def sandbox(work: Path) -> Iterator[Sandbox]:
    """Seed, serve read-only, confirm; stop every child on exit, including on SIGTERM."""
    signal.signal(signal.SIGTERM, _raise_exit)
    work.mkdir(parents=True)
    procs: list[subprocess.Popen] = []
    try:
        s = seed(work, procs)
        srv = Server(s.repo, read_only=True, log=work / "server-read-only.log")
        procs.append(srv.proc)
        srv.wait_ready()
        snap = srv.get_json("/api/orchestration")
        confirm(snap, s)
        yield Sandbox(work, s, srv, snap, procs)
    finally:
        for p in reversed(procs):
            stop(p)


def default_work() -> Path:
    return Path.cwd() / "work" / f"m17.9-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def add_install_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--wheel", type=Path, help="the host-built wheel; omit to use the importable specy-road")
    p.add_argument("--wheelhouse", type=Path, help="dependency wheels for an offline install")
    p.add_argument("--work", type=Path, default=None, help="new output dir (default ./work/m17.9-<UTC time>)")


def prepare(ns: argparse.Namespace) -> Path:
    """Install when ``--wheel`` is given; the work dir, which must not exist yet."""
    work = (ns.work or default_work()).resolve()
    if ns.wheel:
        install(ns.wheel, ns.wheelhouse, work.parent / f"{work.name}-site")
    return work


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    add_install_args(p)
    p.add_argument("--serve", action="store_true", help="keep serving until interrupted")
    ns = p.parse_args()
    work = prepare(ns)
    import specy_road

    with sandbox(work) as sb:
        print(json.dumps({"url": sb.server.url, "repo": str(sb.seeded.repo), "workers": sb.seeded.workers,
                          "inert_pid": sb.seeded.inert.pid, "commits": sb.seeded.commits,
                          "specy_road": specy_road.__file__, "version": specy_road.__version__}, indent=1), flush=True)
        if ns.serve:
            try:
                sb.seeded.inert.wait()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
