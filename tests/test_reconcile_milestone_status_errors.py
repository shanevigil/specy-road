"""Per-node error isolation for ``reconcile-milestone-status``.

The script must keep going when one milestone parent fails to apply,
print a clear warning to stderr, and (under ``--apply``) exit non-zero
so orchestration can see the partial failure.

These tests exercise the script via ``runpy``-style invocation in-process
so we can monkeypatch ``_plan_for_node`` to inject a failure on a single
node — closer to a real subprocess than a unit test, and avoids the
``__main__`` vs ``reconcile_milestone_status`` import-name aliasing
that would otherwise prevent a sitecustomize-style patch from working.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from tests.helpers import REPO

_BUNDLED = REPO / "specy_road" / "bundled_scripts"


def _stage_dogfood(tmp_path: Path) -> Path:
    src = REPO / "tests" / "fixtures" / "specy_road_dogfood"
    dst = tmp_path / "dogfood"
    shutil.copytree(src, dst)
    return dst


def _attach_active_milestone_executions(repo_root: Path, *, ids: list[str]) -> None:
    """Tag the named parent ids with an active ``milestone_execution`` block."""
    chunks_dir = repo_root / "roadmap" / "phases"
    found: set[str] = set()
    for chunk in sorted(chunks_dir.glob("*.json")):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        nodes = doc["nodes"] if isinstance(doc, dict) else doc
        changed = False
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if n.get("id") in ids:
                n["milestone_execution"] = {
                    "state": "active",
                    "rollup_branch": f"feature/rm-{n.get('codename') or 'tmp'}",
                    "integration_branch": "dev",
                    "remote": "origin",
                }
                found.add(n["id"])
                changed = True
        if changed:
            chunk.write_text(
                json.dumps(doc, indent=2) + "\n", encoding="utf-8"
            )
    missing = set(ids) - found
    assert not missing, f"could not tag milestone_execution on: {sorted(missing)}"


def _import_reconcile():
    """Fresh import of the bundled script as a regular module."""
    if str(_BUNDLED) not in sys.path:
        sys.path.insert(0, str(_BUNDLED))
    sys.modules.pop("reconcile_milestone_status", None)
    import reconcile_milestone_status as rms  # type: ignore[import-not-found]

    return rms


def test_reconcile_isolates_per_node_failures_dryrun(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run: one bad node must NOT abort the loop. Exit 0; warning on stderr."""
    repo = _stage_dogfood(tmp_path)
    _attach_active_milestone_executions(repo, ids=["M0", "M1"])

    rms = _import_reconcile()
    real = rms._plan_for_node

    def boom_on_M0(root, n, *, default_remote, args):
        if isinstance(n, dict) and n.get("id") == "M0":
            raise RuntimeError("forced failure for M0")
        return real(root, n, default_remote=default_remote, args=args)

    monkeypatch.setattr(rms, "_plan_for_node", boom_on_M0)

    rms.main(["--repo-root", str(repo)])  # dry-run; must not raise SystemExit
    out = capsys.readouterr()

    assert "could not reconcile 'M0'" in out.err
    assert "RuntimeError" in out.err
    # No "Nothing to reconcile" hard requirement — depends on whether other
    # active milestones produced plan lines. The point is no SystemExit.


def test_reconcile_isolates_per_node_failures_apply_exits_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--apply: a per-node failure must surface as SystemExit(1)."""
    repo = _stage_dogfood(tmp_path)
    _attach_active_milestone_executions(repo, ids=["M0", "M1"])

    rms = _import_reconcile()
    real = rms._plan_for_node

    def boom_on_M0(root, n, *, default_remote, args):
        if isinstance(n, dict) and n.get("id") == "M0":
            raise RuntimeError("forced failure for M0")
        return real(root, n, default_remote=default_remote, args=args)

    monkeypatch.setattr(rms, "_plan_for_node", boom_on_M0)

    with pytest.raises(SystemExit) as exc:
        rms.main(["--repo-root", str(repo), "--apply"])
    assert exc.value.code == 1
    out = capsys.readouterr()
    assert "could not reconcile 'M0'" in out.err
    assert "RuntimeError" in out.err
