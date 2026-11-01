"""Tests for the research register check in ``specy-road validate``."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env

from specy_road.bundled_scripts.validate_roadmap import warn_research_register

TODAY = date(2026, 10, 31)
FRESH = "prompt: research/prompts/topic.md\ncadence_days: 90\nlast_run: 2026-10-01\nfed: [M1.1]\n"


def _entry(root: Path, front_matter: str | None) -> None:
    research = root / "research"
    (research / "prompts").mkdir(parents=True)
    (research / "prompts" / "topic.md").write_text("# Prompt\n", encoding="utf-8")
    (research / "README.md").write_text("# Research register\n", encoding="utf-8")
    (root / "work").mkdir()
    (root / "work" / "topic-prompt.md").write_text("# Prompt\n", encoding="utf-8")
    text = "Notes only.\n" if front_matter is None else f"---\n{front_matter}---\n\nNotes.\n"
    (research / "topic.md").write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("front_matter", "expected"),
    [
        (FRESH, []),
        (FRESH.replace("2026-10-01", "2026-07-01"), ["past its cadence: last run 2026-07-01, every 90 days"]),
        (FRESH.replace("prompts/topic.md", "prompts/gone.md"), ["prompt file research/prompts/gone.md does not exist"]),
        (FRESH.replace("research/prompts/topic.md", "work/topic-prompt.md"), ["is not under research/"]),
        (FRESH.replace("2026-10-01", ""), ["due: never run"]),
        (FRESH.replace("90", "quarterly"), ["`cadence_days` is not a whole number of days: 'quarterly'"]),
        (FRESH.replace("2026-10-01", "last month"), ["`last_run` is not a date (YYYY-MM-DD): 'last month'"]),
        (None, ["no `prompt` file named", "`cadence_days` is not a whole number of days: None"]),
    ],
    ids=["fresh", "overdue", "prompt-missing", "prompt-in-work", "never-run", "bad-cadence",
         "bad-last-run", "no-front-matter"],
)
def test_register_entry_warnings(tmp_path: Path, capsys, front_matter, expected) -> None:
    """README.md and research/prompts/ are not entries; each problem is one warning line."""
    _entry(tmp_path, front_matter)
    warn_research_register(tmp_path, today=TODAY)
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == len(expected), lines
    for line, why in zip(lines, expected):
        assert line.startswith("research: warning — research/topic.md: ")
        assert why in line


def test_validate_reports_an_overdue_entry_in_a_scaffolded_project(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init", "project", str(tmp_path)],
        cwd=REPO, check=True, capture_output=True, text=True,
    )
    (tmp_path / "research" / "prompts").mkdir()
    (tmp_path / "research" / "prompts" / "topic.md").write_text("# Prompt\n", encoding="utf-8")
    (tmp_path / "research" / "topic.md").write_text(
        f"---\n{FRESH.replace('2026-10-01', '2020-01-01')}---\n", encoding="utf-8"
    )
    v = subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_roadmap.py"), "--repo-root", str(tmp_path)],
        cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True,
    )
    assert v.returncode == 0, v.stderr
    assert "research/topic.md: past its cadence: last run 2020-01-01" in v.stderr
