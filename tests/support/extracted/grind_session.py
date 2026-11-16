"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from specy_road.orchestration.grind import grind_session as gs
from specy_road.orchestration.grind import grind_session_cleanup as gsc
from specy_road.orchestration.grind import grind_session_events as gse
from specy_road import merged_branch
from tests.helpers import REPO

#: Frozen event timestamp so `ts` can be asserted exactly.
TS = "2026-09-06T00:00:00Z"

def node(nid, codename=None):
    """Shared test helper."""
    return {"id": nid, "codename": codename or f"cn-{nid.lower().replace('.', '-')}"}

class Harness:
    """Drives a scripted sequence of plans and records subprocess calls."""

    def __init__(self, monkeypatch, plans, *, pickup_rc=0, finish_rc=0,
                 implement_rc=0, pre_finish_rc=0):
        self.plans = list(plans)
        self.idx = 0
        self.cli_calls: list[list[str]] = []
        self.shell_calls: list[str] = []
        self.git_calls: list[list[str]] = []
        #: Per-git-verb return codes for the end-of-session cleanup.
        self.git_rc: dict[str, int] = {}
        self.implement_rc = implement_rc
        self.pre_finish_rc = pre_finish_rc
        self.pickup_rc = pickup_rc
        self.finish_rc = finish_rc
        self.gather_allow: list[bool] = []

        def fake_gather(repo_root, under, *, allow_unauthored=False, prefer_agentic=None):
            self.gather_allow.append(allow_unauthored)
            plan = self.plans[min(self.idx, len(self.plans) - 1)]
            nodes = [node(nid) for nid in plan.ready]
            return nodes, {"version": 1, "entries": []}, plan

        def fake_run_cli(repo_root, cli_args):
            self.cli_calls.append(cli_args)
            if cli_args[0] == "do-next-available-task":
                return self.pickup_rc
            if cli_args[0] == "finish-this-task":
                # advance to the next scripted plan after a finish
                self.idx += 1
                return self.finish_rc
            return 0

        def fake_run_shell(cmd, env, repo_root):
            self.shell_calls.append(cmd)
            # distinguish pre-finish vs implement by env marker is not needed;
            # implement-cmd and pre-finish-cmd use different stored values.
            return 0

        def fake_current_branch(repo_root):
            plan = self.plans[min(self.idx, len(self.plans) - 1)]
            nid = plan.ready[0]
            return f"feature/rm-cn-{nid.lower().replace('.', '-')}"

        def fake_resolve(repo_root, branch, fallback):
            return fallback

        def fake_wait(repo_root, rel, timeout):
            return self.implement_rc == 0

        monkeypatch.setattr(gsc, "git_code", self._fake_git)
        monkeypatch.setattr(merged_branch, "git_code", self._fake_git)
        monkeypatch.setattr(gse, "utc_now", lambda: datetime.fromisoformat(TS.replace("Z", "+00:00")))
        monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", False)
        monkeypatch.setattr(gs, "gather_plan", fake_gather)
        monkeypatch.setattr(gs, "_run_cli", fake_run_cli)
        monkeypatch.setattr(gs, "_run_shell", fake_run_shell)
        monkeypatch.setattr(gs, "current_branch", fake_current_branch)
        monkeypatch.setattr(gs, "_resolve_picked", fake_resolve)
        monkeypatch.setattr(gs, "_wait_for_signal", fake_wait)

    def _fake_git(self, git_args, repo_root):
        self.git_calls.append(list(git_args))
        if git_args[0] == "rev-parse":
            return 0, "a" * 40
        return self.git_rc.get(git_args[0], 0), ""

def run(argv):
    """Shared test helper."""
    from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args

    args = parse_grind_session_args(argv)
    return gs.run_session(args)

def event(evs, name):
    """The last event of one kind. `cleanup` now trails `stopped`."""
    return [e for e in evs if e["event"] == name][-1]
