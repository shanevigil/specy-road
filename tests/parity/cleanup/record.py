"""What each cleanup command selects on the fixture, as one action per row.

``python -m tests.parity.cleanup.record`` rewrites ``golden/old_selections.json`` from the commands
as this checkout has them; the committed file was written on the commit before the cleanup planner
(M16.4.1) and is the "old" column of ``reconciliation.yaml``. An action is ``remove`` (selected for
removal), ``keep`` (listed and left, with the reason) or ``list`` (reported, never removed by this
command); a row a command does not name is not in its list.

The dry-run commands run on a fresh fixture each. ``grind-session --delete-merged-branches`` has no
dry run: its end-of-session cleanup runs on a fresh fixture as if the session had finished every
local ``feature/rm-*`` branch, with ``--push``, and what it deleted is its selection.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from tests.parity.cleanup import fixture
from tests.parity.support import cli_env, normalise, run_cli

GOLDEN = Path(__file__).resolve().parent / "golden" / "old_selections.json"
_ENTRY = re.compile(r"^  (\S.*?)  — (.*)$")
_KEEP_SUFFIX = ("so --fix leaves it", "so --prune leaves it")

#: Each dry-run command, as the words after ``specy-road`` (the fixture's root is appended).
DRY_RUNS = {
    "doctor": ["doctor"],
    "branches prune": ["branches", "prune"],
    "registry-prune": ["registry-prune"],
    **{f"worktree prune {leaf}": ["worktree", "prune", leaf]
       for leaf in fixture.WORKTREE_LEAVES.values()},
}


def _run(argv: list[str], repo: Path) -> tuple[int, str, str]:
    result = run_cli("specy_road.cli", [*argv, "--repo-root", str(repo)], cwd=repo, env=cli_env())
    return result.returncode, result.stdout, result.stderr


def _listing(out: str, *, keep_marks: tuple[str, ...]) -> list[dict]:
    """``  name  — reason`` rows: ``keep`` when the reason ends with a keep mark, else ``remove``."""
    actions = []
    for line in out.splitlines():
        m = _ENTRY.match(line)
        row = fixture.row_of(line) if m else None
        if row:
            keep = m.group(2).endswith(keep_marks)
            actions.append({"row": row, "action": "keep" if keep else "remove",
                            "reason": m.group(2)})
    return actions


def doctor_actions(out: str) -> list[dict]:
    """doctor's sections, ending before its report-only claims section."""
    return _listing(out.split("Claims with no live worker")[0], keep_marks=_KEEP_SUFFIX)


def branches_prune_actions(out: str) -> list[dict]:
    return [{"row": row, "action": "remove", "reason": "merged into origin/dev and unclaimed"}
            for line in out.splitlines() if (row := fixture.row_of(line))]


def registry_prune_actions(err: str) -> list[dict]:
    return [{"row": row, "action": "list", "reason": "no feature branch in this clone"}
            for line in err.splitlines() if line.startswith("  ") and "node=" in line
            and (row := fixture.row_of(line))]


def worktree_prune_actions(leaf: str, code: int, err: str) -> list[dict]:
    row = next(item for item, node_id in fixture.WORKTREE_LEAVES.items() if node_id == leaf)
    if code == 0:
        return [{"row": row, "action": "remove", "reason": "merged and holds no unsaved work"}]
    reasons = [line.strip().removeprefix("- ") for line in err.splitlines() if line.startswith("  - ")]
    return [{"row": row, "action": "keep", "reason": "; ".join(reasons)}]


class _Events:
    """The grind cleanup's event sink: keeps each event's fields."""

    def __init__(self) -> None:
        self.events: dict[str, dict] = {}

    def emit(self, event: str, **fields) -> None:
        self.events[event] = fields


def grind_actions(repo: Path) -> list[dict]:
    """The grind cleanup with ``--push --delete-merged-branches`` after every local branch."""
    from specy_road.grind_session_cleanup import run_session_cleanup

    branches = sorted(fixture.git(repo, "for-each-ref", "--format=%(refname:short)",
                                  "refs/heads/feature/rm-*").splitlines())
    sink = _Events()
    args = SimpleNamespace(base=None, remote=None, push=True, delete_merged_branches=True)
    run_session_cleanup(args, repo, sink, branches)
    cleanup = sink.events["cleanup"]
    actions = [{"row": fixture.row_of(b), "action": "remove", "reason": "deleted"}
               for b in cleanup["deleted_local"]]
    actions += [{"row": fixture.row_of(f"origin    {b}"), "action": "remove", "reason": "deleted"}
                for b in cleanup["deleted_remote"]]
    actions += [{"row": fixture.row_of(f["branch"]), "action": "keep", "reason": f["step"]}
                for f in cleanup["failed"]]
    return actions


def _dry_run_actions(name: str, argv: list[str], tmp: Path) -> list[dict]:
    repo = fixture.build(tmp)
    code, out, err = _run(argv, repo)
    out, err = normalise(out, {repo: "<REPO>"}), normalise(err, {repo: "<REPO>"})
    if name == "doctor":
        return doctor_actions(out)
    if name == "branches prune":
        return branches_prune_actions(out)
    if name == "registry-prune":
        return registry_prune_actions(err)
    return worktree_prune_actions(argv[-1], code, err)


def selections() -> dict[str, list[dict]]:
    """Every command's actions on the fixture, each on its own fresh copy."""
    found: dict[str, list[dict]] = {}
    for name, argv in DRY_RUNS.items():
        with tempfile.TemporaryDirectory() as tmp:
            found[name] = _dry_run_actions(name, argv, Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        repo = fixture.build(Path(tmp))
        found["grind-session --delete-merged-branches"] = grind_actions(repo)
    return {name: sorted(actions, key=lambda a: a["row"]) for name, actions in found.items()}


def main() -> int:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(selections(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
