"""M11.44: init project --profiles and refresh-profiles --only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.init_project import bundled_profiles_template_dir, run_init_project

REPO = Path(__file__).resolve().parent.parent


def run_main(mod, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        mod.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


def _model_profiles_paths(root: Path) -> list[Path]:
    mp = root / "model-profiles"
    if not mp.is_dir():
        return []
    return sorted(p for p in mp.rglob("*") if p.is_file())


def _bundled_profile_md_rels() -> set[str]:
    src = bundled_profiles_template_dir()
    return {
        p.relative_to(src).as_posix()
        for p in src.rglob("*.md")
        if p.name != "README.md"
    }


def test_init_project_default_installs_all_profiles(tmp_path: Path) -> None:
    assert run_init_project(tmp_path) == 0
    paths = _model_profiles_paths(tmp_path)
    assert (tmp_path / "model-profiles" / "harness-facts.yaml").is_file()
    assert (tmp_path / "model-profiles" / "harness-captures").is_dir()
    dst = tmp_path / "model-profiles"
    installed = {
        p.relative_to(dst).as_posix()
        for p in paths
        if p.suffix == ".md" and p.name != "README.md"
    }
    assert installed == _bundled_profile_md_rels()


def test_init_project_profiles_none_installs_readme_and_harness_facts_only(tmp_path: Path) -> None:
    assert run_init_project(tmp_path, profiles="none") == 0
    paths = _model_profiles_paths(tmp_path)
    assert paths == sorted(
        [
            tmp_path / "model-profiles" / "README.md",
            tmp_path / "model-profiles" / "harness-facts.yaml",
        ]
    )


def test_init_project_profiles_one_api_id(tmp_path: Path) -> None:
    assert run_init_project(tmp_path, profiles="composer-2.5") == 0
    paths = _model_profiles_paths(tmp_path)
    assert (tmp_path / "model-profiles" / "cursor-composer" / "composer-2.5.md") in paths
    assert len([p for p in paths if p.suffix == ".md" and p.name != "README.md"]) == 1
    assert not (tmp_path / "model-profiles" / "harness-captures").exists()


def test_init_project_profiles_cli_wires_flag(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "project",
            str(tmp_path),
            "--profiles",
            "none",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert _model_profiles_paths(tmp_path) == sorted(
        [
            tmp_path / "model-profiles" / "README.md",
            tmp_path / "model-profiles" / "harness-facts.yaml",
        ]
    )


def test_refresh_profiles_only_adds_one_missing_profile(tmp_path: Path, capsys) -> None:
    from specy_road.bundled_scripts import refresh_profiles as rp

    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "model-profiles").mkdir()
    (repo / "model-profiles" / "README.md").write_text("# kept\n")
    assert run_main(rp, "--only", "composer-2.5", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert out.count("wrote ") == 1
    assert "cursor-composer/composer-2.5.md" in out
    assert (repo / "model-profiles" / "cursor-composer" / "composer-2.5.md").is_file()
    assert not (repo / "model-profiles" / "anthropic-claude").exists()


def test_init_project_profiles_api_id_that_differs_from_stem(tmp_path: Path) -> None:
    assert run_init_project(tmp_path, profiles="deepseek-flash") == 0
    names = {
        p.name
        for p in _model_profiles_paths(tmp_path)
        if p.suffix == ".md" and p.name != "README.md"
    }
    assert names == {"deepseek-v4.1-flash-1017.md", "deepseek-v4.1-flash-20260910.md"}


def test_refresh_profiles_only_adds_every_match_for_shared_api_id(tmp_path: Path) -> None:
    from specy_road.bundled_scripts import refresh_profiles as rp

    repo = tmp_path / "r"
    repo.mkdir()
    written, kept = rp.refresh_profiles(repo, only="deepseek-flash")
    assert kept == []
    assert {Path(w).name for w in written} == {
        "deepseek-v4.1-flash-1017.md",
        "deepseek-v4.1-flash-20260910.md",
    }


def test_refresh_profiles_without_only_still_adds_every_missing(tmp_path: Path) -> None:
    from specy_road.bundled_scripts import refresh_profiles as rp

    repo = tmp_path / "r"
    repo.mkdir()
    src = bundled_profiles_template_dir()
    expected = [
        f"model-profiles/{p.relative_to(src).as_posix()}"
        for p in sorted(src.rglob("*.md"))
    ]
    written, kept = rp.refresh_profiles(repo)
    assert written == expected and kept == []
