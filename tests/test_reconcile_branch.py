"""``reconcile-branch``: a PR-mode leaf catches up with the integration branch after another leaf merged."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from tests.helpers import DOGFOOD, REPO, script_subprocess_env
from tests.review_repo_helpers import NODE, commit_file, git

from specy_road.bundled_scripts.export_roadmap_md import reexport_roadmap_md
from specy_road.digest import render_digest
from specy_road.finish_land_deterministic import merge_feature_deterministically
from specy_road.reconcile_branch import reconcile_branch

LEAVES = (("M1.1", "one", "11111111-1111-5111-8111-111111111111"),
          ("M1.2", "two", "22222222-2222-5222-8222-222222222222"))


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
                          cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True)


def _regenerate(root: Path) -> None:
    reexport_roadmap_md(root)
    (root / "roadmap-context.md").write_text(render_digest(root), encoding="utf-8")


def _row(codename: str, node_id: str) -> dict:
    return {"codename": codename, "node_id": node_id, "branch": f"feature/rm-{codename}",
            "touch_zones": ["src"], "started": "2026-11-01", "owner": "T"}


def _finish(root: Path, codename: str) -> None:
    """Finish's bookkeeping commit in PR mode: drop this leaf's row, render the generated files again."""
    reg_path = root / "roadmap" / "registry.yaml"
    doc = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    doc["entries"] = [e for e in doc["entries"] if e["codename"] != codename]
    reg_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    _regenerate(root)
    git(root, "commit", "-qam", f"chore(rm-{codename}): finish")


def _two_pr_leaves(tmp_path: Path, *, shared_code: bool) -> tuple[Path, Path]:
    """``dev`` with both leaves claimed; each branch finished and pushed; ``one`` merged into ``dev``.

    Returns ``(main checkout on dev, worktree of feature/rm-two)``.
    """
    remote, root = tmp_path / "origin.git", tmp_path / "r"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    (root / "roadmap" / "phases").mkdir(parents=True)
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    shutil.copytree(DOGFOOD / "schemas", root / "schemas")
    nodes = []
    for i, (nid, codename, key) in enumerate(LEAVES, start=1):
        sheet = f"planning/{nid}_{codename}_{key}.md"
        nodes.append({**NODE, "id": nid, "node_key": key, "codename": codename, "title": codename.title(),
                      "sibling_order": i, "status": "Not Started", "planning_dir": sheet})
        (root / sheet).parent.mkdir(exist_ok=True)
        (root / sheet).write_text(f"# {nid}\n\n## Intent\n\nDo it.\n\n## References\n", encoding="utf-8")
    rm = root / "roadmap"
    (rm / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8")
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": nodes}, indent=2), encoding="utf-8")
    (rm / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\non_complete: pr\n", encoding="utf-8")
    (rm / "registry.yaml").write_text(yaml.safe_dump(
        {"version": 1, "entries": [_row(c, n) for n, c, _ in LEAVES]}, sort_keys=False), encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "shared.py").write_text("x = 0\n", encoding="utf-8")
    _regenerate(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph with both claims")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "-u", "origin", "dev")
    for _, codename, _ in LEAVES:
        git(root, "checkout", "-q", "-b", f"feature/rm-{codename}", "dev")
        commit_file(root, f"src/{codename}.py", f"name = {codename!r}\n", f"{codename}: impl")
        if shared_code:
            commit_file(root, "src/shared.py", f"x = {codename!r}\n", f"{codename}: shared")
        _finish(root, codename)
        git(root, "push", "-q", "-u", "origin", f"feature/rm-{codename}")
    git(root, "checkout", "-q", "dev")
    ok, msg = merge_feature_deterministically(root, integration_branch="dev", feature_branch="feature/rm-one")
    assert ok, msg   # the first PR merges
    git(root, "push", "-q", "origin", "dev")
    wt = tmp_path / "wt-two"
    git(root, "worktree", "add", "-q", str(wt), "feature/rm-two")
    return root, wt


def test_reconcile_resolves_bookkeeping_and_pushes(tmp_path: Path, capsys) -> None:
    root, wt = _two_pr_leaves(tmp_path, shared_code=False)
    # without reconcile the PR conflicts on bookkeeping
    trial = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "HEAD", "origin/dev"],
                           cwd=wt, capture_output=True, text=True)
    assert trial.returncode == 1 and "roadmap/registry.yaml" in trial.stdout
    code_before = (wt / "src" / "two.py").read_text(encoding="utf-8")

    assert reconcile_branch(wt, ib="dev", remote="origin") == 0, capsys.readouterr().err

    assert git(wt, "rev-parse", "HEAD^2") == git(wt, "rev-parse", "origin/dev")
    assert git(wt, "rev-parse", "HEAD") == git(wt, "rev-parse", "origin/feature/rm-two")   # pushed
    for rel in ("roadmap/registry.yaml", "roadmap.md", "roadmap-context.md"):
        assert "<<<<<<<" not in (wt / rel).read_text(encoding="utf-8"), rel
    assert yaml.safe_load((wt / "roadmap" / "registry.yaml").read_text())["entries"] == []
    assert (wt / "src" / "two.py").read_text(encoding="utf-8") == code_before
    changed = set(git(wt, "diff", "--name-only", "HEAD^1", "HEAD").splitlines())
    assert changed <= {"src/one.py", "roadmap/registry.yaml", "roadmap.md", "roadmap-context.md"}
    for check in (("validate",), ("export", "--check"), ("digest", "--check")):
        r = _cli(wt, *check)
        assert r.returncode == 0, (check, r.stdout, r.stderr)
    assert git(wt, "status", "--porcelain", "--untracked-files=no") == ""
    # a forge merge of the PR is now clean
    clean = subprocess.run(["git", "merge-tree", "--write-tree", "origin/dev", "HEAD"], cwd=wt,
                           capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout


def test_reconcile_refuses_a_code_conflict_and_leaves_the_branch(tmp_path: Path, capsys) -> None:
    root, wt = _two_pr_leaves(tmp_path, shared_code=True)
    head = git(wt, "rev-parse", "HEAD")

    assert reconcile_branch(wt, ib="dev", remote="origin") == 1

    err = capsys.readouterr().err
    assert "src/shared.py" in err and "unchanged" in err
    assert git(wt, "rev-parse", "HEAD") == head
    assert git(wt, "rev-parse", "origin/feature/rm-two") == head
    assert git(wt, "status", "--porcelain", "--untracked-files=no") == ""
    assert subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=wt).returncode != 0


def test_reconcile_keeps_the_row_of_a_leaf_that_has_not_finished(tmp_path: Path, capsys) -> None:
    root, wt = _two_pr_leaves(tmp_path, shared_code=False)
    git(wt, "reset", "-q", "--hard", "HEAD^")   # before finish: the branch still holds its claim
    git(wt, "branch", "--unset-upstream")

    assert reconcile_branch(wt, ib="dev", remote="origin") == 0
    assert "has no upstream; nothing pushed" in capsys.readouterr().out

    rows = yaml.safe_load((wt / "roadmap" / "registry.yaml").read_text())["entries"]
    assert [r["codename"] for r in rows] == ["two"]


def test_reconcile_refuses_off_a_leaf_branch_and_on_the_wrong_leaf(tmp_path: Path, capsys) -> None:
    root, wt = _two_pr_leaves(tmp_path, shared_code=False)
    assert reconcile_branch(root, ib="dev", remote="origin") == 1
    assert "not a feature/rm-<codename> branch" in capsys.readouterr().err
    assert reconcile_branch(wt, ib="dev", remote="origin", codename="one") == 1
    assert "feature/rm-one" in capsys.readouterr().err
    r = _cli(wt, "reconcile-branch", "M1.2")
    assert r.returncode == 0, r.stderr
