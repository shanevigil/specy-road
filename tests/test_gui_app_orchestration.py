"""M17.7: ``GET /api/orchestration`` serves the snapshot unchanged, and the GUI mock stays on the fixture."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

from specy_road.gui_app import create_app
from specy_road.orchestration import snapshot
from specy_road.review_files import reviews_dir
from specy_road.orchestration.workers.worker_sandbox import state_home
from specy_road.orchestration.workers.worker_state import create_record, set_state, workers_dir
from tests.helpers import REPO
from tests.review_repo_helpers import git, make_review_repo, review_text

NODE = "M1.1"
ROSTER = (
    "version: 1\nroster:\n"
    "  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
    "  - {id: opus, family: anthropic, roles: [reviewer]}\n"
)
SECRET = "seeded-secret-value"
CONFIG = "/accounts/seeded-secret-value/work/claude"
NOT_UTF8 = b"\xff\xfe"
LOOPBACK_CORS = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"
FIXTURE = REPO / "tests" / "fixtures" / "orchestration_snapshot_v2.json"
MOCK = REPO / "gui" / "pm-gantt" / "src" / "fixtures" / "orchestration_snapshot_mock.json"
TS = REPO / "gui" / "pm-gantt" / "src" / "orchestrationSnapshot.ts"


def client(**kw) -> TestClient:
    return TestClient(create_app(**kw))


def dumped(snap: dict) -> bytes:
    return json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode()


def key_paths(value: object, path: str = "", found: set[str] | None = None) -> set[str]:
    """Key paths: ``.`` between keys, ``*`` for a leaf id, ``[]`` for a list item."""
    found = found if found is not None else set()
    if isinstance(value, list):
        for item in value:
            key_paths(item, f"{path}[]", found)
    elif isinstance(value, dict):
        for key, item in value.items():
            seg = "*" if path == "leaves" else key
            child = f"{path}.{seg}" if path else seg
            found.add(child)
            key_paths(item, child, found)
    return found


def _quoted(block: str) -> list[str]:
    return re.findall(r'"([^"]*)"', block)


def required_key_paths() -> set[str]:
    """``requiredKeys`` in the GUI snapshot module (the same list the v2 fixture is tied to)."""
    src = TS.read_text(encoding="utf-8")
    match = re.search(r"export const requiredKeys:.*?= \[(.*?)\];", src, re.S)
    assert match is not None
    known = {"WORKER_REQUIRED": _quoted(re.search(r"const WORKER_REQUIRED = \[(.*?)\];", src, re.S).group(1))}
    out: list[str] = []
    for raw in match.group(1).splitlines():
        line = raw.strip().rstrip(",")
        spread = re.match(r"\.\.\.under\(\"([^\"]+)\",\s*(\[[^\]]*\]|[A-Z_]+)\)", line)
        if spread:
            prefix, keys = spread.group(1), spread.group(2)
            names = _quoted(keys) if keys.startswith("[") else known[keys]
            out.extend(f"{prefix}.{item}" for item in names)
        elif _quoted(line):
            out.append(_quoted(line)[0])
    return set(out)


def point(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(root))


def seed_live(repo: Path) -> None:
    """A claim (already in the repo), a running worker, a READY, a review and one leafless worker."""
    rec = create_record(repo, NODE, "generic", "opus", repo, branch="feature/rm-thing")
    set_state(repo, rec, "running", pid=None)
    commit, base = git(repo, "rev-parse", "HEAD"), git(repo, "rev-parse", "dev")
    folder = reviews_dir(repo, NODE)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "READY-composer.md").write_text(
        f"---\nnode_id: {NODE}\nagent: composer\nbranch: feature/rm-thing\n"
        f"commit: '{commit}'\nbase: '{base}'\nchanged_paths: [src/a.py]\n---\n",
        encoding="utf-8",
    )
    (folder / "REVIEW-opus.md").write_text(review_text(commit, model="opus"), encoding="utf-8")
    chores = repo / "work" / "chores"
    chores.mkdir(parents=True, exist_ok=True)
    (chores / "tidy.json").write_text('{"slug": "tidy"}\n', encoding="utf-8")
    other = create_record(repo, "tidy", "generic", "opus", repo, branch="feature/rm-thing")
    set_state(repo, other, "running", pid=None)


def make_live(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    seed_live(repo)
    return repo


def write_enclosing(top: Path) -> None:
    rm = top / "roadmap"
    (rm / "phases").mkdir(parents=True)
    (top / "roadmap" / "manifest.json").write_text(
        '{"version": 1, "includes": ["phases/E.json"]}\n', encoding="utf-8",
    )
    node = {
        "id": "ENCL", "node_key": "22222222-2222-5222-8222-222222222222", "codename": "enclosing-only",
        "title": "Enclosing", "type": "task", "parent_id": None, "sibling_order": 1, "status": "Not Started",
        "dependencies": [], "touch_zones": ["src"],
    }
    (rm / "phases" / "E.json").write_text(json.dumps({"nodes": [node]}), encoding="utf-8")
    (rm / "registry.yaml").write_text(
        "version: 1\nentries:\n  - {codename: enclosing-only, node_id: ENCL, branch: feature/rm-encl}\n",
        encoding="utf-8",
    )
    (top / ".specyrd").mkdir()
    (top / ".specyrd" / "manifest.json").write_text('{"project_root": "sr"}\n', encoding="utf-8")


def nested_checkout(tmp_path: Path) -> tuple[Path, Path]:
    """``(git root, project)``: the project is ``sr/``; the git root has a different roadmap."""
    flat = make_review_repo(tmp_path / "flat", orchestration=ROSTER)
    top = tmp_path / "top"
    shutil.copytree(flat, top / "sr", ignore=shutil.ignore_patterns(".git"))
    write_enclosing(top)
    git(top, "init", "-q", "-b", "dev")
    git(top, "config", "user.email", "t@e.com")
    git(top, "config", "user.name", "T")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "graph")
    return top, top / "sr"


def build_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = make_review_repo(tmp_path)
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    point(monkeypatch, repo)
    return repo


def build_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = make_live(tmp_path)
    point(monkeypatch, repo)
    return repo


def build_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    folder = reviews_dir(repo, NODE)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "READY-composer.md").write_bytes(NOT_UTF8)
    wdir = workers_dir(repo)
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / "w-0001.yaml").write_bytes(NOT_UTF8)
    point(monkeypatch, repo)
    return repo


def build_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = make_live(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", CONFIG)
    home = state_home(repo, "w-0001")
    home.mkdir(parents=True, exist_ok=True)
    (home / "claude-config-dir").write_text(CONFIG + "\n", encoding="utf-8")
    point(monkeypatch, repo)
    return repo


def build_nested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    top, project = nested_checkout(tmp_path)
    monkeypatch.delenv("SPECY_ROAD_REPO_ROOT", raising=False)
    monkeypatch.chdir(top)
    return project


def build_linked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, None]:
    """Serve from a linked worktree whose local claims, READY and workers differ from the main checkout."""
    top, project = nested_checkout(tmp_path)
    seed_live(project)
    leaf = tmp_path / "leaf"
    git(top, "worktree", "add", "--detach", "-q", str(leaf), "HEAD")
    linked = leaf / "sr"
    reg = yaml.safe_load((linked / "roadmap" / "registry.yaml").read_text(encoding="utf-8"))
    reg["entries"][0]["codename"] = "divergent-codename"
    (linked / "roadmap" / "registry.yaml").write_text(yaml.safe_dump(reg), encoding="utf-8")
    stray = linked / "work" / "reviews" / NODE
    stray.mkdir(parents=True)
    (stray / "READY-composer.md").write_text(
        "---\nnode_id: M1.1\nagent: divergent-agent\n---\n", encoding="utf-8",
    )
    (linked / "work" / ".workers").mkdir(parents=True)
    (linked / "work" / ".workers" / "w-0099.yaml").write_text("model: divergent-model\n", encoding="utf-8")
    monkeypatch.chdir(leaf)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(project.resolve()))
    return project.resolve()


def check_row(case: str, body: dict) -> None:
    if case == "empty":
        assert body == {"schema": 2, "leaves": {}, "leafless_workers": []}
    elif case == "live":
        leaf = body["leaves"][NODE]
        assert leaf["claim"]["codename"] == "thing" and leaf["status"] == "running"
        assert leaf["workers"][0]["status"] == "running" and isinstance(leaf["ready"], dict)
    elif case == "unreadable":
        leaf = body["leaves"][NODE]
        worker = body["leafless_workers"][0]
        assert leaf["ready"] == "unknown" and leaf["claim"]["codename"] == "thing"
        assert leaf["claim"] != "unknown" and leaf["status"] != "unknown"
        assert worker["id"] == "w-0001"
        assert all(worker[k] == "unknown" for k in worker if k != "id")
    elif case == "secret":
        blob = json.dumps(body)
        assert SECRET not in blob and CONFIG not in blob
    elif case in ("nested", "linked"):
        blob = json.dumps(body)
        assert NODE in body["leaves"] and "ENCL" not in body["leaves"]
        assert "enclosing-only" not in blob
        if case == "linked":
            assert body["leaves"][NODE]["claim"]["codename"] == "thing"
            assert "divergent-codename" not in blob and "divergent-agent" not in blob
            assert "divergent-model" not in blob and "w-0099" not in blob


@pytest.mark.parametrize("case", ["empty", "live", "unreadable", "secret", "nested", "linked"])
def test_fixture_repos(case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each row is the snapshot of the main project, with nothing added."""
    built = {
        "empty": build_empty, "live": build_live, "unreadable": build_unreadable,
        "secret": build_secret, "nested": build_nested, "linked": build_linked,
    }[case]
    root = built(tmp_path, monkeypatch)
    response = client().get("/api/orchestration")
    assert response.status_code == 200
    assert response.content == dumped(snapshot(root))
    check_row(case, response.json())


def test_contract_ties_response_fixture_and_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A response key outside the v2 fixture fails, and so does a mock key the fixture lacks or a missing required one.

    On the claim, running worker and READY row the response has every required path, and dropping one field
    from the builder's output fails that check.
    """
    root = build_live(tmp_path, monkeypatch)
    allowed = key_paths(json.loads(FIXTURE.read_text(encoding="utf-8")))
    required = required_key_paths()
    mock_paths = key_paths(json.loads(MOCK.read_text(encoding="utf-8")))
    assert mock_paths <= allowed
    assert required <= mock_paths
    response = client().get("/api/orchestration")
    got = key_paths(response.json())
    assert got <= allowed
    assert required <= got
    extra = json.loads(response.content)
    extra["display_id"] = "M1.1"
    assert not key_paths(extra) <= allowed
    built = snapshot(root)
    del next(iter(built["leaves"].values()))["claim"]["codename"]
    assert not required <= key_paths(built)


def test_read_only_serves_the_get_and_refuses_the_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--read-only`` still serves the snapshot; ``POST /api/orchestration`` is the existing 403. CORS stays loopback."""
    root = build_empty(tmp_path, monkeypatch)
    app = create_app(read_only=True)
    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors.kwargs["allow_origin_regex"] == LOOPBACK_CORS
    c = TestClient(app)
    response = c.get("/api/orchestration")
    assert response.status_code == 200 and response.content == dumped(snapshot(root))
    post = c.post("/api/orchestration")
    assert post.status_code == 403 and "read-only" in post.json()["detail"]
