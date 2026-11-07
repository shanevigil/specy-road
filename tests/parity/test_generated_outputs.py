"""Generated outputs match their goldens: dogfood validate, export and digest; rc3 upgrade preview.

Each fixture is copied into its own git repo first, so the output depends on the fixture alone and
not on the toolkit checkout around it. Paths and the running version are normalised; digest sections
derived from git history are left out, so the goldens do not depend on the branch.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD
from tests.parity.support import GOLDEN, PARITY, check_golden, cli_env, run_cli, transcript

pytestmark = pytest.mark.parity

RC3_CONSUMER = PARITY / "fixtures" / "rc3_consumer"

#: Digest sections built from git history (``specy_road.digest``); they change with the branch.
HISTORY_SECTIONS = ("Dependencies that were removed", "Quality by area")


def _repo_copy(src: Path, dest: Path) -> Path:
    shutil.copytree(src, dest)
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        [
            "-c",
            "user.email=parity@example.com",
            "-c",
            "user.name=Parity",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", *args], cwd=dest, check=True, capture_output=True)
    return dest


def without_history_sections(digest: str) -> str:
    """The digest with each ``## <history section>`` removed up to the next ``## `` heading."""
    names = "|".join(re.escape(n) for n in HISTORY_SECTIONS)
    return re.sub(rf"^## (?:{names})\n.*?(?=^## |\Z)", "", digest, flags=re.M | re.S)


DOGFOOD_COMMANDS = {
    "validate": ["validate"],
    "export-check": ["export", "--check"],
    "digest-check": ["digest", "--check"],
}


@pytest.mark.parametrize("name", sorted(DOGFOOD_COMMANDS))
def test_dogfood_command_matches_golden(tmp_path: Path, name: str) -> None:
    root = _repo_copy(DOGFOOD, tmp_path / "dogfood")
    argv = [*DOGFOOD_COMMANDS[name], "--repo-root", str(root)]
    result = run_cli("specy_road.cli", argv, cwd=root)
    check_golden(
        GOLDEN / "dogfood" / f"{name}.txt",
        transcript(["specy-road", *argv], result, {root: "<ROOT>"}),
    )


def test_dogfood_digest_matches_golden(tmp_path: Path) -> None:
    root = _repo_copy(DOGFOOD, tmp_path / "dogfood")
    result = run_cli("specy_road.cli", ["digest", "-o", "-", "--repo-root", str(root)], cwd=root)
    assert result.returncode == 0, result.stderr
    check_golden(GOLDEN / "dogfood" / "digest.md", without_history_sections(result.stdout))


def test_rc3_consumer_upgrade_dry_run_matches_golden(tmp_path: Path) -> None:
    """``upgrade --dry-run`` on a repo as ``init project --profiles none`` of 0.3.1rc3 left it.

    PATH holds only git's directory, so the install report lists no ``specy-road`` on PATH on any
    machine; the install prefix is normalised.
    """
    root = _repo_copy(RC3_CONSUMER, tmp_path / "app")
    env = cli_env(PATH=os.path.dirname(shutil.which("git") or "/usr/bin/git"))
    argv = ["upgrade", "--dry-run", "--repo-root", str(root)]
    result = run_cli("specy_road.cli", argv, cwd=root, env=env)
    check_golden(
        GOLDEN / "upgrade" / "rc3-dry-run.txt",
        transcript(["specy-road", *argv], result, {root: "<ROOT>"}),
    )
    assert not subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    ).stdout


def test_history_sections_are_left_out_of_the_digest_golden() -> None:
    kept = "# Roadmap context\n\n## Live roadmap\n\n- M1\n\n"
    footer = "## Reaching the detail behind this\n\nsearch\n"
    history = (
        "## Quality by area\n\n- src: 3 rounds\n\n"
        "## Dependencies that were removed\n\n- M2 -> M1\n\n"
    )
    assert without_history_sections(kept + history + footer) == kept + footer
