"""A small offline project for the grind table: two authored leaves, merge mode, review gate off.

``build_template`` runs ``init project`` once, marks its ``M1.1`` Complete, adds leaves ``M1.2``
and ``M1.3`` (both ready), writes their planning sheets and pushes ``main`` to a bare ``origin``.
``copy_project`` copies that pair for one row and repoints ``origin``, so each row starts from the
same commits. Finish lands with ``on_complete: merge`` and
``require_implementation_review_before_finish: false``, so a cycle completes without a review
round. Nothing reaches a hosting service: ``gh`` and ``glab`` on PATH
fail, git may use the file protocol only, and a fake ``claude`` on PATH prints what the row asks.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

from tests.parity.support import cli_env, run_cli

LEAVES = (("M1.2", "write-the-alpha-module"), ("M1.3", "write-the-beta-module"))
SHEET = (
    "## Intent\n\n{title}.\n\n## Approach\n\nWrite the module.\n\n## Tasks / checklist\n\n"
    "- [ ] the module exists\n\n## References\n\n- Roadmap chunk for `{nid}`\n"
)


def git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd``; its stdout, stripped. Fails the test on a non-zero exit."""
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def offline_env(tmp: Path, claude_script: str = "exit 0\n") -> dict[str, str]:
    """The CLI's environment, with failing ``gh``/``glab`` and a scripted ``claude`` on PATH."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool, body in (("gh", "exit 1\n"), ("glab", "exit 1\n"), ("claude", claude_script)):
        stub = bin_dir / tool
        stub.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return cli_env(
        PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        GIT_ALLOW_PROTOCOL="file",
        GIT_AUTHOR_NAME="Parity", GIT_AUTHOR_EMAIL="parity@example.com",
        GIT_COMMITTER_NAME="Parity", GIT_COMMITTER_EMAIL="parity@example.com",
    )


def cli(root: Path, env: dict[str, str], *argv: str) -> subprocess.CompletedProcess[str]:
    """``specy-road <argv> --repo-root <root>`` from ``root``."""
    return run_cli("specy_road.cli", [*argv, "--repo-root", str(root)], cwd=root, env=env)


def _checked(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, f"{result.args}\n{result.stdout}\n{result.stderr}"


def build_template(tmp: Path) -> Path:
    """``tmp/app`` (the project) beside ``tmp/origin.git``; returns ``tmp``."""
    root, origin = tmp / "app", tmp / "origin.git"
    env = offline_env(tmp)
    git(tmp, "init", "-q", "-b", "main", str(root))
    git(root, "config", "user.email", "parity@example.com")
    git(root, "config", "user.name", "Parity")
    _checked(run_cli("specy_road.cli", ["init", "project", str(root)], cwd=root, env=env))
    workflow = root / "roadmap" / "git-workflow.yaml"
    text = workflow.read_text(encoding="utf-8")
    for old, new in (
        ("\non_complete: pr\n", "\non_complete: merge\n"),
        (
            "require_implementation_review_before_finish: true\n",
            "require_implementation_review_before_finish: false\n",
        ),
    ):
        assert old in text
        text = text.replace(old, new)
    workflow.write_text(text, encoding="utf-8")
    # No roster: with the review gate off, a reviewers_required policy fails validate.
    (root / "roadmap" / "orchestration.yaml").unlink()
    for nid, codename in LEAVES:
        add_leaf(root, env, nid, codename)
    edit_nodes(root, {"M1.1": lambda node: node.update(status="Complete")})
    git(root, "add", "-A")
    git(root, "commit", "-qm", "roadmap: two leaves")
    git(tmp, "init", "-q", "--bare", str(origin))
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "-u", "origin", "main")
    git(root, "remote", "set-head", "origin", "main")
    return tmp


def add_leaf(
    root: Path, env: dict[str, str], nid: str, codename: str, *extra: str, parent: str = "M1"
) -> None:
    """``add-node`` a task under ``parent`` with a zone and an acceptance line, and its sheet."""
    title = codename.replace("-", " ").capitalize()
    _checked(cli(
        root, env, "add-node", "--id", nid, "--type", "task", "--title", title,
        "--parent-id", parent, "--codename", codename, "--touch-zone", f"src/{nid}",
        "--acceptance", "the module exists", *extra,
    ))
    _checked(cli(root, env, "scaffold-planning", nid))
    node = nodes_by_id(root)[nid]
    (root / node["planning_dir"]).write_text(SHEET.format(title=title, nid=nid), encoding="utf-8")


def _chunks(root: Path) -> list[Path]:
    return sorted((root / "roadmap" / "phases").glob("*.json"))


def nodes_by_id(root: Path) -> dict[str, dict]:
    """Every node of the project's roadmap chunks, by display id."""
    return {
        n["id"]: n
        for chunk in _chunks(root)
        for n in json.loads(chunk.read_text(encoding="utf-8"))["nodes"]
    }


def edit_nodes(root: Path, edits: dict[str, Callable[[dict], object]]) -> None:
    """Apply each edit to its node in place, in whichever chunk holds it."""
    for chunk in _chunks(root):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        hits = [n for n in doc["nodes"] if n["id"] in edits]
        for node in hits:
            edits[node["id"]](node)
        if hits:
            chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def copy_project(template: Path, tmp: Path) -> Path:
    """The template's project and origin copied under ``tmp``; returns the project root."""
    shutil.copytree(template / "app", tmp / "app", symlinks=True)
    shutil.copytree(template / "origin.git", tmp / "origin.git", symlinks=True)
    git(tmp / "app", "remote", "set-url", "origin", str(tmp / "origin.git"))
    return tmp / "app"


#: An implement hook that does the leaf's work: one file under its touch zone, committed.
IMPLEMENT = (
    'mkdir -p "src/$SPECY_ROAD_NODE_ID" && echo "x = 1" > "src/$SPECY_ROAD_NODE_ID/m.py"'
    ' && git add src && git commit -qm "implement $SPECY_ROAD_NODE_ID"'
)


def add_readiness_cases(root: Path, env: dict[str, str]) -> None:
    """Leaves whose readiness turns on the rollup, a gate, an archived key or an open leaf.

    ``M1.4`` is a milestone whose only leaf is Complete while its own status is not (virtually
    complete); ``M1.7`` depends on it and on ``M1.9.1``, whose milestone ``M1.9`` is then
    archived, so ``M1.7`` is ready. ``M1.6`` waits on the gate ``M1.5`` and ``M1.8`` on the open
    leaf ``M1.2``. Pickup's order: ``M1.7`` is Blocked (offered first), ``M1.2`` Human-led and
    ``M1.3`` Agentic-led (swapped under ``--prefer-agentic``); ``M1.10`` is In Progress with no
    claim. Committed and pushed to ``main``.
    """
    _checked(cli(
        root, env, "add-node", "--id", "M1.4", "--type", "milestone", "--title", "Shipped",
        "--parent-id", "M1", "--codename", "shipped",
    ))
    add_leaf(root, env, "M1.4.1", "shipped-leaf", parent="M1.4")
    _checked(cli(
        root, env, "add-node", "--id", "M1.5", "--type", "gate", "--title", "Sign-off",
        "--parent-id", "M1", "--codename", "sign-off",
    ))
    add_leaf(root, env, "M1.6", "after-the-gate", "--dependency", "M1.5")
    _checked(cli(
        root, env, "add-node", "--id", "M1.9", "--type", "milestone", "--title", "Archived",
        "--parent-id", "M1", "--codename", "archived",
    ))
    add_leaf(root, env, "M1.9.1", "archived-leaf", parent="M1.9")
    add_leaf(
        root, env, "M1.7", "after-the-milestone", "--dependency", "M1.4", "--dependency", "M1.9.1"
    )
    add_leaf(root, env, "M1.8", "after-alpha", "--dependency", "M1.2")
    add_leaf(root, env, "M1.10", "started-by-hand")
    complete = {nid: (lambda node: node.update(status="Complete")) for nid in ("M1.4.1", "M1.9.1")}
    edit_nodes(root, {
        **complete,
        "M1.9": lambda node: node.update(status="Complete"),
        "M1.7": lambda node: node.update(status="Blocked"),
        "M1.10": lambda node: node.update(status="In Progress"),
        "M1.2": lambda node: node.update(execution_milestone="Human-led"),
        "M1.3": lambda node: node.update(execution_milestone="Agentic-led"),
    })
    git(root, "add", "-A")
    git(root, "commit", "-qm", "roadmap: readiness cases")
    _checked(cli(root, env, "archive", "M1.9"))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "roadmap: archive M1.9")
    git(root, "push", "-q", "origin", "main")
