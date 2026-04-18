"""Auto-FF / fetch race coverage for PM GUI optimistic concurrency.

These tests cover the specific race that previously caused the
"Roadmap or workspace changed elsewhere" banner to appear after a drag
even when the user did nothing wrong: ``GET /api/roadmap`` invokes
``maybe_auto_git_fetch`` and ``maybe_auto_integration_ff``, which can
move HEAD or update remote refs and thus shift the fingerprint
*between* the GET that issued the client's token and the next mutation
POST.

The mutation guard's contract — default for every install — is:

* the on-disk snapshot is canonical, so any mismatch is still 412;
* the 412 body always includes ``retryable: true`` and a ``current_fingerprint``
  freshly recomputed *after* re-running the same auto-fetch / auto-FF
  side effects the GET endpoints run, so the bundled UI's transparent
  one-shot retry can succeed without an extra round-trip;
* a true conflict that survives the client's one retry still surfaces
  the banner.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(cwd),
        },
    )
    return out.stdout.strip()


@pytest.fixture()
def autoff_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Bare remote + working tree where remote is 2 commits ahead of HEAD.

    Returns ``(working_tree, bare_remote)``. ``integration_branch=master``
    is set in ``roadmap/git-workflow.yaml`` so
    ``maybe_auto_integration_ff`` will engage without depending on the
    toolkit's default ``main`` branch.
    """
    work = tmp_path / "work"
    shutil.copytree(DOGFOOD, work)
    bare = tmp_path / "remote.git"
    _git(["init", "--bare", "-q", str(bare)], tmp_path)
    _git(["init", "-q", "-b", "master"], work)
    _git(["add", "-A"], work)
    _git(["commit", "-q", "-m", "initial"], work)
    gw = work / "roadmap" / "git-workflow.yaml"
    gw.write_text(
        gw.read_text(encoding="utf-8").replace(
            "integration_branch: main", "integration_branch: master"
        ),
        encoding="utf-8",
    )
    _git(["commit", "-q", "-am", "use master"], work)
    _git(["remote", "add", "origin", str(bare)], work)
    _git(["push", "-q", "-u", "origin", "master"], work)
    helper = tmp_path / "helper"
    _git(["clone", "-q", str(bare), str(helper)], tmp_path)
    _git(["commit", "-q", "--allow-empty", "-m", "ahead-1"], helper)
    _git(["commit", "-q", "--allow-empty", "-m", "ahead-2"], helper)
    _git(["push", "-q", "origin", "master"], helper)
    return work, bare


def _enable_overlay_and_autoff(
    monkeypatch: pytest.MonkeyPatch, work: Path
) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(work))
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "1")
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    from specy_road import registry_remote_overlay as rro

    rro._LAST_FETCH_MONO.clear()
    rro._LAST_INTEGRATION_FF_MONO.clear()


def _siblings_of(work: Path, parent: str) -> list[str]:
    """Display ids of children under ``parent`` ordered by ``sibling_order``."""
    out: list[tuple[int, str]] = []
    for chunk in (work / "roadmap" / "phases").glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        for n in doc.get("nodes") or []:
            if n.get("parent_id") == parent:
                out.append((int(n.get("sibling_order", 0)), str(n["id"])))
    out.sort()
    return [k for _, k in out]


def _sibling_keys_of(work: Path, parent: str) -> list[str]:
    """``node_key``s of children under ``parent`` ordered by ``sibling_order``.

    ``reorder_siblings`` may renumber display ids after a write so the
    *display* ordering can look unchanged even when the underlying rows
    moved. ``node_key`` is immutable across renumbers, so it's the right
    identity for "did the move actually persist?" assertions.
    """
    out: list[tuple[int, str]] = []
    for chunk in (work / "roadmap" / "phases").glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        for n in doc.get("nodes") or []:
            if n.get("parent_id") == parent:
                out.append((int(n.get("sibling_order", 0)), str(n["node_key"])))
    out.sort()
    return [k for _, k in out]


def _force_local_head_drift(work: Path) -> None:
    """Push two commits to the remote and FF-merge them into local HEAD.

    Mimics what an in-server ``maybe_auto_integration_ff`` would do during
    a polling GET that runs concurrently with the user's drag. We do it
    explicitly here so the POST under test sees a *local* HEAD that has
    moved since the captured fingerprint was issued — which is the actual
    on-disk state that triggers 412 in production.
    """
    helper = work.parent / "helper"
    _git(["fetch", "-q"], helper)
    _git(["reset", "--hard", "origin/master", "-q"], helper)
    _git(["commit", "-q", "--allow-empty", "-m", "race-1"], helper)
    _git(["commit", "-q", "--allow-empty", "-m", "race-2"], helper)
    _git(["push", "-q", "origin", "master"], helper)
    _git(["fetch", "-q", "origin"], work)
    _git(["merge", "-q", "--ff-only", "origin/master"], work)
    from specy_road import registry_remote_overlay as rro

    rro._LAST_FETCH_MONO.clear()
    rro._LAST_INTEGRATION_FF_MONO.clear()


def test_412_advertises_retryable_with_fresh_fingerprint(
    autoff_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default mutation guard always returns 412 + retryable:true with a
    ``current_fingerprint`` that matches what
    ``GET /api/roadmap/fingerprint`` returns next, so the bundled UI's
    one-shot retry can succeed without an extra round-trip."""
    work, _ = autoff_repo
    _enable_overlay_and_autoff(monkeypatch, work)

    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    client.get("/api/roadmap")  # warm-up
    fp_stale = client.get("/api/roadmap").json()["fingerprint"]
    _force_local_head_drift(work)

    sibs = _siblings_of(work, "M0")
    rotated = sibs[-1:] + sibs[:-1]
    keys_before = _sibling_keys_of(work, "M0")
    keys_target = keys_before[-1:] + keys_before[:-1]
    r = client.post(
        "/api/outline/reorder",
        headers={"X-PM-Gui-Fingerprint": str(fp_stale)},
        json={"parent_id": "M0", "ordered_child_ids": rotated},
    )
    assert r.status_code == 412, r.text
    det = r.json()["detail"]
    assert isinstance(det, dict)
    assert det.get("retryable") is True
    assert isinstance(det.get("current_fingerprint"), int)

    # The bundled UI's one-shot retry would now refresh and resend with
    # the fresh fp. Simulate that and assert the on-disk row identities
    # (node_key, immutable across renumbering) actually rotated.
    fp_fresh = client.get("/api/roadmap/fingerprint").json()["fingerprint"]
    r2 = client.post(
        "/api/outline/reorder",
        headers={"X-PM-Gui-Fingerprint": str(fp_fresh)},
        json={"parent_id": "M0", "ordered_child_ids": rotated},
    )
    assert r2.status_code == 200, r2.text

    keys_after = _sibling_keys_of(work, "M0")
    assert keys_after == keys_target, (
        f"on-disk reorder did not land: before={keys_before} "
        f"target={keys_target} after={keys_after}"
    )


def test_passthrough_when_token_matches(
    autoff_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path under the default guard: matching token still returns 200."""
    work, _ = autoff_repo
    _enable_overlay_and_autoff(monkeypatch, work)

    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    fp = client.get("/api/roadmap").json()["fingerprint"]
    sibs = _siblings_of(work, "M0")
    rotated = sibs[-1:] + sibs[:-1]
    keys_before = _sibling_keys_of(work, "M0")
    keys_target = keys_before[-1:] + keys_before[:-1]
    r = client.post(
        "/api/outline/reorder",
        headers={"X-PM-Gui-Fingerprint": str(fp)},
        json={"parent_id": "M0", "ordered_child_ids": rotated},
    )
    assert r.status_code == 200, r.text
    assert _sibling_keys_of(work, "M0") == keys_target


def test_outline_move_persists_after_retry(
    autoff_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The M9.2-shaped scenario: cross-parent move under the same race.

    Picks the last sibling under M0 and moves it to be the first child of M1.
    """
    work, _ = autoff_repo
    _enable_overlay_and_autoff(monkeypatch, work)

    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    payload = client.get("/api/roadmap").json()
    nodes_by_id = {n["id"]: n for n in payload["nodes"]}
    sibs_m0 = _siblings_of(work, "M0")
    assert sibs_m0, "fixture must have children under M0"
    moved_display = sibs_m0[-1]
    moved_key = nodes_by_id[moved_display]["node_key"]
    fp_stale = payload["fingerprint"]
    _force_local_head_drift(work)

    body = {"node_key": moved_key, "new_parent_id": "M1", "new_index": 0}
    r = client.post(
        "/api/outline/move",
        headers={"X-PM-Gui-Fingerprint": str(fp_stale)},
        json=body,
    )
    assert r.status_code == 412
    assert r.json()["detail"].get("retryable") is True

    fp_fresh = client.get("/api/roadmap/fingerprint").json()["fingerprint"]
    r2 = client.post(
        "/api/outline/move",
        headers={"X-PM-Gui-Fingerprint": str(fp_fresh)},
        json=body,
    )
    assert r2.status_code == 200, r2.text

    # Confirm cross-parent move persisted on disk via display id renumbering.
    refreshed = client.get("/api/roadmap").json()
    new_node = next(
        n for n in refreshed["nodes"] if n.get("node_key") == moved_key
    )
    assert new_node.get("parent_id") == "M1", new_node
