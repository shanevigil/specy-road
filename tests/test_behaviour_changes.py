"""M13.8: the behaviour-change catalogue and validate's notices for project text it contradicts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.agent_text_report import warn_contradicted_instructions
from specy_road.behaviour_changes import CATALOGUE
from specy_road.cli import registered_agent_command_names
from specy_road.managed_block import HTML_COMMENT

REPO = Path(__file__).resolve().parents[1]

CITED = [
    "- Approve with `specy-road mark-implementation-reviewed --yes` when tests pass.",
    "- Always run `specy-road finish-this-task --on-complete merge`.",
    "- `specy-road do-next-available-task` always pushes the claim to origin.",
    "- `specy-road finish-this-task` never deletes the source branch.",
    "- The first commit on the feature branch registers the work in registry.yaml.",
]


@pytest.mark.parametrize("command", sorted({entry.command for entry in CATALOGUE}))
def test_every_entry_names_a_registered_command_and_flag(command: str) -> None:
    assert command in registered_agent_command_names()["specy-road"]
    proc = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", command, "--help"],
        capture_output=True, text=True, check=True, cwd=REPO,
    )
    known = set(re.findall(r"--[a-z][a-z-]*", proc.stdout))
    for entry in CATALOGUE:
        if entry.command == command:
            assert entry.flags and set(entry.flags) <= known, (entry, known)


def test_cited_sentences_each_print_one_notice_outside_the_managed_block(tmp_path: Path, capsys) -> None:
    managed = [HTML_COMMENT.start, CITED[0], HTML_COMMENT.end]
    (tmp_path / "AGENTS.md").write_text("\n".join(["# Rules", *CITED[:3], *managed]) + "\n", encoding="utf-8")
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "AGENTS.team.md").write_text("\n".join(CITED[3:]) + "\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(
        "Run `specy-road finish-this-task` when done; pass --yes to nothing else.\n"
        "Pickup registers the claim on the integration branch first.\n",
        encoding="utf-8",
    )
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.md")}

    warn_contradicted_instructions(tmp_path)

    out = capsys.readouterr().out.splitlines()
    assert [line.split(": says")[0] for line in out] == [
        "agents: notice — AGENTS.md:2",
        "agents: notice — AGENTS.md:3",
        "agents: notice — AGENTS.md:4",
        "agents: notice — .specyrd/AGENTS.team.md:1",
        "agents: notice — .specyrd/AGENTS.team.md:2",
    ]
    for line, sentence, entry in zip(out, CITED, CATALOGUE, strict=True):
        assert f'says "{sentence}"; since {entry.since}: {entry.now}' in line
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.md")} == before


def test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work() -> None:
    pattern = next(e.contradicts for e in CATALOGUE if e.flags == ("--base",))
    hits = [
        f"{path.relative_to(REPO)}:{n}"
        for top in ("docs", "specy_road/templates")
        for path in sorted((REPO / top).rglob("*"))
        if path.is_file()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if pattern.search(line)
    ]
    assert hits == []


def _notices(tmp_path: Path, capsys, text: str) -> list[str]:
    (tmp_path / "AGENTS.md").write_text(text + "\n", encoding="utf-8")
    warn_contradicted_instructions(tmp_path)
    return capsys.readouterr().out.splitlines()


def test_a_line_matching_two_entries_prints_one_notice_with_both_behaviours(tmp_path: Path, capsys) -> None:
    line = "Run `specy-road finish-this-task --on-complete auto`; finish-this-task never deletes the source branch."
    out = _notices(tmp_path, capsys, line)
    assert len(out) == 1 and out[0].startswith("agents: notice — AGENTS.md:1:")
    for entry in CATALOGUE:
        if entry.command == "finish-this-task":
            assert f"since {entry.since}: {entry.now}" in out[0]


@pytest.mark.parametrize("line", [
    "The first commit registers the service worker.",
    "Register the plugin in the first commit of the app.",
    "`specy-road finish-this-task` never deletes uncommitted work.",
])
def test_unrelated_prose_prints_no_notice(tmp_path: Path, capsys, line: str) -> None:
    assert _notices(tmp_path, capsys, line) == []


def test_the_historical_commandless_first_commit_sentence_is_still_reported(tmp_path: Path, capsys) -> None:
    line = "4. **First commit** registers the work in `registry.yaml` — no implementation before that commit."
    out = _notices(tmp_path, capsys, line)
    assert len(out) == 1 and out[0].startswith("agents: notice — AGENTS.md:1:")
