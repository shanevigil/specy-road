"""The same commands, the same answers, in both supported layouts.

specy-road supports two shapes, chosen per project:

* **embedded** — ``roadmap/``, ``planning/``, ``shared/`` at the repository root;
* **nested** — the same tree under a subfolder (``sr/``), so the coding root
  stays uncluttered.

Nested already half-worked: ``init project sr`` scaffolded it and every command
accepted ``--repo-root``. What did not work was resolving it *without* that
flag, because the CLI read no environment and did no discovery. These tests run
the real commands with no ``--repo-root`` at all, from three different working
directories, which is the only way the two layouts stay interchangeable a year
from now.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, script_subprocess_env

#: (script, extra args) — the read-mostly commands a consumer runs constantly.
COMMANDS = [
    ("validate_roadmap.py", []),
    ("export_roadmap_md.py", ["--check"]),
    ("generate_brief.py", ["M0.3", "--no-history"]),
    ("digest_cli.py", ["-o", "-"]),
    ("roadmap_crud.py", ["list-nodes"]),
    ("search_cli.py", ["contract"]),
    ("validate_file_limits.py", []),
]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture(params=["embedded", "nested"])
def layout(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[Path, Path]:
    """``(git_root, project_root)`` for each supported layout.

    The two are the same path when embedded and differ when nested — which is
    exactly the distinction every path bug in this area came from conflating.
    """
    top = tmp_path / "checkout"
    top.mkdir()
    prefix = "" if request.param == "embedded" else "sr/"
    project = (top / prefix) if prefix else top
    shutil.copytree(DOGFOOD, project, dirs_exist_ok=True)

    _git(top, "init", "-q", "-b", "main")
    manifest = top / ".specyrd" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"project_root": prefix.rstrip("/") or "."}) + "\n",
        encoding="utf-8",
    )
    _git(top, "add", "-A")
    _git(top, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    return top.resolve(), project.resolve()


def _run(script: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
        check=False,
    )


@pytest.mark.parametrize(("script", "args"), COMMANDS)
def test_command_works_with_no_repo_root_flag(
    layout: tuple[Path, Path], script: str, args: list[str]
) -> None:
    """Nested used to need an explicit --repo-root on every single invocation."""
    top, _project = layout
    proc = _run(script, args, cwd=top)

    assert proc.returncode == 0, f"{script} failed:\n{proc.stderr}"


@pytest.mark.parametrize(
    "where", ["git_root", "inside_project", "sibling_subdir"]
)
def test_resolution_agrees_from_any_working_directory(
    layout: tuple[Path, Path], where: str
) -> None:
    """cwd must not change which project a command operates on."""
    top, project = layout
    sibling = top / "src" / "deep"
    sibling.mkdir(parents=True, exist_ok=True)
    cwd = {
        "git_root": top,
        "inside_project": project / "planning",
        "sibling_subdir": sibling,
    }[where]

    proc = _run("validate_roadmap.py", [], cwd=cwd)

    assert proc.returncode == 0, f"from {where}:\n{proc.stderr}"


def test_the_gui_and_the_cli_resolve_the_same_root(
    layout: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One resolver, two callers — the split this work exists to close."""
    from specy_road.gui_app_helpers import get_repo_root
    from specy_road.runtime_paths import project_root

    top, project = layout
    monkeypatch.chdir(top)

    assert get_repo_root() == project_root() == project


def test_the_brief_is_identical_across_layouts(tmp_path: Path) -> None:
    """A brief must not depend on where in the checkout the project sits.

    Guards the whole class of bug at once: any path handled relative to the
    wrong root shows up here as a diff.
    """
    briefs = []
    for prefix in ("", "sr/"):
        top = tmp_path / f"c{len(briefs)}"
        top.mkdir()
        project = (top / prefix) if prefix else top
        shutil.copytree(DOGFOOD, project, dirs_exist_ok=True)
        _git(top, "init", "-q", "-b", "main")
        proc = _run(
            "generate_brief.py",
            ["M0.3", "--no-history", "--repo-root", str(project)],
            cwd=top,
        )
        assert proc.returncode == 0, proc.stderr
        briefs.append(proc.stdout)

    assert briefs[0] == briefs[1]


def test_ignore_blocks_land_at_the_git_root_and_match(
    layout: tuple[Path, Path],
) -> None:
    """The known breakage, end to end: archived material must really be ignored."""
    from specy_road.agent_ignores import apply_agent_ignores
    from specy_road.runtime_paths import prefix_within

    top, project = layout
    prefix = prefix_within(top, project)
    apply_agent_ignores(top, prefix)

    assert (top / ".gitignore").is_file()
    cache = project / ".specyrd" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "x.json").write_text("{}", encoding="utf-8")

    rel = (cache / "x.json").relative_to(top).as_posix()
    proc = subprocess.run(
        ["git", "-C", str(top), "check-ignore", rel],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"{rel} should be gitignored"


# --- init writes correct blocks regardless of command order -----------------


def _fresh(tmp_path: Path, prefix: str) -> tuple[Path, Path]:
    top = tmp_path / "checkout"
    top.mkdir(parents=True, exist_ok=True)
    _git(top, "init", "-q", "-b", "main")
    project = (top / prefix) if prefix else top
    return top.resolve(), project


@pytest.mark.parametrize("prefix", ["", "sr/"])
def test_specyrd_init_prefixes_the_blocks_using_the_recorded_root(
    tmp_path: Path, prefix: str
) -> None:
    """The bug end-to-end verification caught that the unit tests did not.

    ``specyrd init`` computed the prefix with ``discover_project_root``, which
    only walks *upward* — so run from the git root of a nested repo it found
    nothing and wrote an unprefixed block that matched no path at all. The
    recorded root is what it should have been reading.
    """
    from specy_road.init_project import run_init_project
    from specy_road.specyrd_init import run_init

    top, project = _fresh(tmp_path, prefix)
    run_init_project(project, dry_run=False, force=False)
    run_init(
        target=top,
        agent="claude-code",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
    )

    text = (top / ".cursorindexingignore").read_text(encoding="utf-8")
    assert f"{prefix}roadmap/archive/" in text
    if prefix:
        assert "\nroadmap/archive/" not in text


@pytest.mark.parametrize("prefix", ["", "sr/"])
def test_init_project_after_specyrd_init_still_ends_up_prefixed(
    tmp_path: Path, prefix: str
) -> None:
    """The reverse order: nothing is recorded yet when the blocks are first written."""
    from specy_road.init_project import run_init_project
    from specy_road.specyrd_init import run_init

    top, project = _fresh(tmp_path, prefix)
    run_init(
        target=top,
        agent="claude-code",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
    )
    run_init_project(project, dry_run=False, force=False)

    text = (top / ".cursorindexingignore").read_text(encoding="utf-8")
    assert f"{prefix}roadmap/archive/" in text
    if prefix:
        assert "\nroadmap/archive/" not in text
