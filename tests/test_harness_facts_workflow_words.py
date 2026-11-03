"""M11.60: the scope-escape workflow words, and a capture that adds one failing until it is classified."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from specy_road import harness_facts as hf
from specy_road.bundled_scripts import refresh_profiles as rp


def run_main(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        rp.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


def test_the_scope_escape_words_are_watched() -> None:
    """goal, loop, queue, persist, gist, fleet, teleport, remote and spawn name autonomy features."""
    assert {"goal", "loop", "queue", "persist", "gist", "fleet", "teleport", "remote", "spawn"} <= set(hf.WORKFLOW_WORDS)


def test_a_capture_that_adds_persist_fails_until_it_is_classified(tmp_path: Path, monkeypatch, capsys) -> None:
    """The accepted Cursor capture, against a baseline without its ``persist`` subcommand row."""
    accepted, new = tmp_path / "accepted", hf.bundled_captures_dir() / "cursor"
    capture = hf.read_capture(new)
    help_without = "".join(ln for ln in capture["help.txt"].splitlines(keepends=True) if not ln.startswith("  persist "))
    assert help_without != capture["help.txt"]
    hf.write_capture(accepted / "cursor", {**capture, "help.txt": help_without})
    monkeypatch.setattr(hf, "bundled_captures_dir", lambda: accepted)
    facts = copy.deepcopy(hf.load_facts())
    del hf.harness(facts, "cursor")["relationships"]["persist"]
    monkeypatch.setattr(hf, "load_facts", lambda path=None: facts)
    assert run_main("--capture", "cursor", "--from", str(new), "--accept") == 1
    assert "UNASSIGNED persist: contains 'persist'" in capsys.readouterr().err
    assert hf.read_capture(accepted / "cursor")["help.txt"] == help_without
    hf.harness(facts, "cursor")["relationships"]["persist"] = "avoid"
    assert run_main("--capture", "cursor", "--from", str(new), "--accept") == 0
    assert "new persist: avoid" in capsys.readouterr().out
    assert hf.read_capture(accepted / "cursor") == capture
