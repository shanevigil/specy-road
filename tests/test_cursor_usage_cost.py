"""M11.67: worker usage estimates Cursor turn cost from roster profile cost_usd_per_mtok."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_adapters import CURSOR_RESULT, RECORDED

from specy_road import worker_adapters as wa
from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli
from specy_road.orchestration_config import roster_entry
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.worker_adapter_parsers import estimate_usage_cost, mtok_rates
from specy_road.worker_adapters import Launch

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES = REPO_ROOT / "specy_road" / "templates" / "project" / "model-profiles"

CURSOR_ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: priced
    family: cursor
    harness: cursor
    profile: model-profiles/cursor-composer/composer-2.5.md
    roles: [executor]
  - id: unpriced
    family: cursor
    harness: cursor
    profile: model-profiles/cursor-composer/composer-2.md
    roles: [executor]
policy: {}
"""


def _cursor_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=CURSOR_ROSTER)
    for rel in ("cursor-composer/composer-2.5.md", "cursor-composer/composer-2.md"):
        dest = repo / "model-profiles" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROFILES / rel, dest)
    git(repo, "checkout", "-q", "dev")
    git(repo, "add", "model-profiles")
    git(repo, "commit", "-qm", "cursor profiles")
    return repo


def _cursor_workspace(tmp_path: Path, layout: str) -> tuple[Path, Path]:
    """``(workspace, project_root)``: workspace is the git worktree Cursor puts on ``--workspace``."""
    project = _cursor_repo(tmp_path / layout / "src")
    if layout == "embedded":
        return project, project
    top = tmp_path / layout / "top"
    git(project, "checkout", "-q", "dev")
    shutil.copytree(project, top / "sr", ignore=shutil.ignore_patterns(".git"))
    (top / ".specyrd").mkdir()
    (top / ".specyrd" / "manifest.json").write_text('{"project_root": "sr"}\n')
    git(top, "init", "-q", "-b", "dev")
    git(top, "config", "user.email", "t@e.com")
    git(top, "config", "user.name", "T")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "nested graph")
    git(top, "checkout", "-q", "-b", "feature/rm-thing")
    git(top, "checkout", "-q", "dev")
    wt = tmp_path / layout / "wt"
    git(top, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    return wt.resolve(), (wt / "sr").resolve()


def _api_id_for(repo: Path, roster_id: str) -> str | None:
    """The id ``worker_ops_launch._cli_for`` puts on argv: profile api_id, or none when unknown."""
    config, err = pinned_config(repo)
    assert err is None
    entry = roster_entry(config, roster_id)
    prof = pinned_profile_for_entry(repo, entry)
    assert prof is not None and prof.ok
    return None if prof.api_id.strip().lower() == "unknown" else prof.api_id


def _prompt(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.md"
    p.write_text("ok")
    return p


def test_estimate_usage_cost_prices_cached_input_at_cached_rate() -> None:
    rates = {"input": 4.0, "output": 20.0, "cached_input": 0.2}
    usage = {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 100}
    assert estimate_usage_cost(usage, rates) == 0.00296


def test_estimate_usage_cost_returns_none_without_list_prices() -> None:
    usage = {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 10}
    assert estimate_usage_cost(usage, mtok_rates({"cost_usd_per_mtok": {"input": "unknown", "output": "unknown"}})) is None


@pytest.mark.parametrize("layout", ["embedded", "nested"])
def test_cursor_parse_events_estimates_cost_for_cached_input(tmp_path: Path, layout: str) -> None:
    workspace, project = _cursor_workspace(tmp_path, layout)
    if layout == "nested":
        assert workspace != project and (workspace / ".specyrd" / "manifest.json").is_file()
        assert (project / "roadmap" / "orchestration.yaml").is_file()
    api_id = _api_id_for(project, "priced")
    assert api_id == "composer-2.5" and api_id != "priced"
    cu = wa.adapter_for("cursor")
    launch = cu.launch(_prompt(tmp_path), workspace, api_id, None)
    assert launch.argv[launch.argv.index("--model") + 1] == api_id
    assert Path(launch.argv[launch.argv.index("--workspace") + 1]).resolve() == workspace
    usage = cu.parse_events(json.dumps(CURSOR_RESULT), launch)[0].usage
    assert usage["input_tokens"] == 9323 + 4864 and usage["cached_input_tokens"] == 4864
    assert usage["cost_usd"] == 0.007156 and usage["cost_is_estimate"] is True


def test_cursor_resume_parse_events_estimates_cost_for_cached_input(tmp_path: Path) -> None:
    repo = _cursor_repo(tmp_path)
    api_id = _api_id_for(repo, "priced")
    cu = wa.adapter_for("cursor")
    resumed = cu.resume("c1", _prompt(tmp_path), repo, api_id, None)
    assert resumed.argv[resumed.argv.index("--model") + 1] == api_id
    usage = cu.parse_events(json.dumps(CURSOR_RESULT), resumed)[0].usage
    assert usage["cost_usd"] == 0.007156 and usage["cost_is_estimate"] is True


def test_cursor_parse_events_leaves_cost_null_when_profile_has_no_price(tmp_path: Path) -> None:
    repo = _cursor_repo(tmp_path)
    api_id = _api_id_for(repo, "unpriced")
    cu = wa.adapter_for("cursor")
    launch = cu.launch(_prompt(tmp_path), repo, api_id, None)
    usage = cu.parse_events(json.dumps(CURSOR_RESULT), launch)[0].usage
    assert usage["cost_usd"] is None and usage["cost_is_estimate"] is None


def test_worker_usage_shows_estimated_cursor_cost(tmp_path: Path, capsys) -> None:
    from specy_road import worker_runner as wr

    repo = _cursor_repo(tmp_path)
    api_id = _api_id_for(repo, "priced")
    script = tmp_path / "fake-cursor.py"
    script.write_text(
        "import json, sys\n"
        "for line in json.loads(open(sys.argv[1]).read())['lines']:\n"
        "    print(json.dumps(line), flush=True)\n"
    )
    rec = ws.create_record(repo, "M1.1", "cursor", "priced", repo)
    spec = tmp_path / "turn.json"
    spec.write_text(json.dumps({"lines": RECORDED["cursor"]["lines"], "exit": 0}))
    wr.run(repo, rec.worker_id, Launch([sys.executable, str(script), str(spec), "--model", api_id,
                                        "--workspace", str(repo)]))
    with pytest.raises(SystemExit) as exc:
        worker_cli.main(["worker", "usage", "M1.1", "--repo-root", str(repo)])
    assert (exc.value.code or 0) == 0
    out = capsys.readouterr().out
    assert "est." in out and "$?" not in out.split("attempt 1")[1].split("total")[0]
