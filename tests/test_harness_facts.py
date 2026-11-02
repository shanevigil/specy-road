"""M8.1: the harness facts fixture, what refresh-profiles renders from it, and the version-bump diff."""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from specy_road import harness_facts as hf
from specy_road.bundled_scripts import refresh_profiles as rp
from specy_road.init_project import project_template_root

ROSTER_HARNESSES = ("claude-code", "codex", "cursor")
OPUS = Path("model-profiles/anthropic-claude/claude-opus-5-5.md")
SOL = Path("model-profiles/openai-gpt/gpt-6.1-sol.md")


def run_main(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        rp.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    shutil.copytree(project_template_root() / "model-profiles", repo / "model-profiles")
    return repo


def _facts() -> dict:
    return copy.deepcopy(hf.load_facts())


# --- A1: fixture and schema --------------------------------------------------

def test_the_shipped_fixture_validates_and_covers_every_roster_harness() -> None:
    facts = hf.load_facts()
    assert tuple(h["id"] for h in facts["harnesses"]) == ROSTER_HARNESSES
    for rec in facts["harnesses"]:
        facts_with_labels = [v for v in rec.values() if isinstance(v, dict) and "value" in v] + rec["git_actions"]
        assert all(f["label"] == "unverified" or f.get("source") for f in facts_with_labels), rec["id"]


@pytest.mark.parametrize("break_it, message", [
    (lambda r: r.pop("quota"), "'quota' is a required property"),
    (lambda r: r["hooks"].pop("source"), "'source' is a required property"),
    (lambda r: r["skill_dirs"].update(label="guessed"), "is not one of"),
    (lambda r: r["relationships"].update({"--worktree": "maybe"}), "is not one of"),
    (lambda r: r["executor_template"].update(value="claude -p"), "does not match"),
    (lambda r: r["git_actions"][0].pop("switch"), "'switch' is a required property"),
])
def test_the_schema_rejects_a_broken_record(tmp_path: Path, break_it, message: str) -> None:
    facts = _facts()
    break_it(facts["harnesses"][0])
    path = tmp_path / hf.FACTS_NAME
    path.write_text(yaml.safe_dump(facts), encoding="utf-8")
    with pytest.raises(hf.HarnessFactsError, match=message):
        hf.load_facts(path)


def test_an_unverified_fact_needs_no_source_and_a_duplicate_id_is_refused(tmp_path: Path) -> None:
    facts = _facts()
    facts["harnesses"][0]["hooks"] = {"value": "x", "label": "unverified"}
    assert hf.schema_errors(facts) == []
    facts["harnesses"].append(copy.deepcopy(facts["harnesses"][0]))
    path = tmp_path / hf.FACTS_NAME
    path.write_text(yaml.safe_dump(facts), encoding="utf-8")
    with pytest.raises(hf.HarnessFactsError, match="duplicate id 'claude-code'"):
        hf.load_facts(path)


# --- A2: rendering and drift -------------------------------------------------

def test_the_shipped_profiles_are_already_rendered_from_the_fixture() -> None:
    plan = hf.plan_render(project_template_root(), hf.load_facts())
    assert plan.findings == [] and plan.updates == {}


def test_each_executor_template_renders_its_families_cli() -> None:
    facts = hf.load_facts()
    assert hf.rendered_cli(facts, "Anthropic Claude", "claude-opus-5-5") == 'claude -p "<prompt>"'
    assert hf.rendered_cli(facts, "OpenAI GPT", "gpt-6.1-sol").startswith("codex exec --model gpt-6.1-sol ")
    assert hf.rendered_cli(facts, "Cursor Composer", "unknown") == 'agent -p --force "<prompt>"'
    assert hf.rendered_cli(facts, "Google Gemini", "gemini-4-argon") is None


def test_a_hand_edited_cli_is_drift_and_render_puts_it_back(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    prof = repo / SOL
    shipped = prof.read_text(encoding="utf-8")
    prof.write_text(shipped.replace("approval_policy=never", "approval_policy=on-request"), encoding="utf-8")
    assert run_main("--check", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert f"drift: {SOL.as_posix()}: access.cli is" in err and "1 rendered region(s) differ" in err
    assert run_main("--render", "--repo-root", str(repo)) == 0
    assert f"rendered {SOL.as_posix()} (drift:" in capsys.readouterr().out
    assert prof.read_text(encoding="utf-8") == shipped
    assert run_main("--check", "--repo-root", str(repo)) == 0


def test_an_edit_inside_the_readme_block_is_drift_but_edits_outside_it_are_not(tmp_path: Path, capsys) -> None:
    readme = _repo(tmp_path) / "model-profiles" / hf.README_NAME
    repo = readme.parent.parent
    text = readme.read_text(encoding="utf-8")
    readme.write_text(text.replace("# Model profiles", "# Our model profiles"), encoding="utf-8")
    assert run_main("--check", "--repo-root", str(repo)) == 0
    readme.write_text(readme.read_text(encoding="utf-8").replace("#### Codex CLI", "#### Codex"), encoding="utf-8")
    assert run_main("--check", "--repo-root", str(repo)) == 1
    assert "drift: model-profiles/README.md: the harness block differs" in capsys.readouterr().err
    assert run_main("--render", "--repo-root", str(repo)) == 0
    assert readme.read_text(encoding="utf-8") == text.replace("# Model profiles", "# Our model profiles")


def test_a_readme_without_the_block_is_behind_not_drift(tmp_path: Path, capsys) -> None:
    readme = _repo(tmp_path) / "model-profiles" / hf.README_NAME
    repo = readme.parent.parent
    text = readme.read_text(encoding="utf-8")
    start, end = text.index(hf.BLOCK_START), text.index(hf.BLOCK_END) + len(hf.BLOCK_END) + 2
    readme.write_text(text[:start] + text[end:], encoding="utf-8")
    assert run_main("--check", "--repo-root", str(repo)) == 0
    assert "behind: model-profiles/README.md: no harness block yet" in capsys.readouterr().out
    assert run_main("--render", "--dry-run", "--repo-root", str(repo)) == 0
    assert hf.BLOCK_START not in readme.read_text(encoding="utf-8")
    assert run_main("--render", "--repo-root", str(repo)) == 0
    assert readme.read_text(encoding="utf-8") == text


def test_render_restores_a_removed_cli_and_check_then_passes(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    prof = repo / SOL
    shipped = prof.read_text(encoding="utf-8")
    cli_line = next(line for line in shipped.splitlines() if line.startswith("  cli: "))
    prof.write_text(shipped.replace(cli_line + "\n", ""), encoding="utf-8")
    assert run_main("--check", "--repo-root", str(repo)) == 1
    assert run_main("--render", "--repo-root", str(repo)) == 0
    assert f"rendered {SOL.as_posix()} (drift: access.cli is None" in capsys.readouterr().out
    assert run_main("--check", "--repo-root", str(repo)) == 0
    head = yaml.safe_load(prof.read_text(encoding="utf-8").split("---\n")[1])
    assert head["access"]["cli"] == yaml.safe_load(cli_line.strip())["cli"]
    assert prof.read_text(encoding="utf-8").split("---\n")[2] == shipped.split("---\n")[2]


def test_render_fails_on_a_region_it_cannot_write(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    prof = repo / SOL
    text = prof.read_text(encoding="utf-8")
    start = text.index("\naccess:\n") + 1
    end = text.index("\ncost_usd_per_mtok:")
    prof.write_text(text[:start] + "access: { cli: none }" + text[end:], encoding="utf-8")
    assert run_main("--render", "--repo-root", str(repo)) == 1
    out, err = capsys.readouterr()
    assert f"cannot render {SOL.as_posix()}" in err and f"rendered {SOL.as_posix()}" not in out
    assert "access: { cli: none }" in prof.read_text(encoding="utf-8")


def test_the_default_refresh_reports_drift_without_failing_or_rewriting(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    prof = repo / OPUS
    prof.write_text(prof.read_text(encoding="utf-8").replace('claude -p "<prompt>"', "claude -p {prompt}"),
                    encoding="utf-8")
    assert run_main("--repo-root", str(repo)) == 0
    assert f"drift: {OPUS.as_posix()}" in capsys.readouterr().err
    assert "claude -p {prompt}" in prof.read_text(encoding="utf-8")


def test_render_quotes_a_cli_yaml_would_misread() -> None:
    text = "---\nfamily: f\naccess:\n  cli: old\n  subagents: no\n---\nbody\n"
    out = hf.render_profile(text, "tool --opt: x #not-a-comment <prompt>")
    head = yaml.safe_load(out.split("---\n")[1])
    assert head["access"]["cli"] == "tool --opt: x #not-a-comment <prompt>"
    assert out.endswith("---\nbody\n")


# --- A3: version-bump diff ---------------------------------------------------

HELP = "Usage: tool [options]\n\nOptions:\n  --model <m>   Model\n\nCommands:\n  exec   Run\n  login|auth   Log in\n"


def _capture(version: str, help_text: str = HELP, **extra: str) -> dict[str, str]:
    """Every file any shipped record's capture_commands names (codex also captures help-exec.txt)."""
    return {hf.VERSION_FILE: version + "\n", "help.txt": help_text, "help-exec.txt": "", **extra}


def test_identifiers_are_flags_command_rows_and_inventory_lines() -> None:
    assert hf.identifiers("help.txt", HELP) == {"--model", "exec", "login", "auth"}
    assert hf.identifiers("inventory-slash.txt", "/batch  run many\n\n/loop\n") == {"/batch", "/loop"}


@pytest.mark.parametrize("word", hf.WORKFLOW_WORDS)
def test_a_new_identifier_with_a_workflow_word_fails_until_assigned(word: str) -> None:
    facts = _facts()
    flag = f"--auto-{word}-x"
    new = _capture("1.1", HELP + f"\nOptions:\n  {flag}   New\n")
    diff = hf.classify_capture(facts, "codex", _capture("1.0"), new)
    assert not diff.ok and diff.unassigned == {flag: word}
    facts["harnesses"][1]["relationships"][flag] = "avoid"
    diff = hf.classify_capture(facts, "codex", _capture("1.0"), new)
    assert diff.ok and diff.assigned == {flag: "avoid"} and diff.version == ("1.0", "1.1")


def test_new_subcommands_and_inventory_entries_are_classified_too() -> None:
    new = _capture("2", HELP + "  autopilot   Go\n", **{"inventory-slash.txt": "/schedule\n/help\n"})
    diff = hf.classify_capture(_facts(), "cursor", _capture("1"), new)
    assert diff.unassigned == {"autopilot": "autopilot", "/schedule": "schedule"}
    assert diff.other == ["/help"]


def test_a_neutral_addition_passes_and_a_removal_is_listed() -> None:
    old = _capture("1", HELP + "  --gone   Old\n")
    diff = hf.classify_capture(_facts(), "claude-code", old, _capture("2", HELP + "  --colour   New\n"))
    assert diff.ok and diff.other == ["--colour"] and diff.removed == ["--gone"]


def test_the_accepted_captures_pass_against_an_empty_baseline() -> None:
    """Every workflow identifier the shipped captures contain already has a relationship."""
    facts = hf.load_facts()
    for hid in ROSTER_HARNESSES:
        accepted = hf.read_capture(hf.bundled_captures_dir() / hid)
        assert hf.VERSION_FILE in accepted and "help.txt" in accepted, hid
        assert hf.classify_capture(facts, hid, {}, accepted).ok, hid
        assert hf.harness(facts, hid)["version"]["value"] in accepted[hf.VERSION_FILE], hid


def test_capture_cli_fails_on_unassigned_and_accept_stores_a_passing_one(tmp_path: Path, monkeypatch, capsys) -> None:
    accepted = tmp_path / "accepted"
    monkeypatch.setattr(hf, "bundled_captures_dir", lambda: accepted)
    hf.write_capture(accepted / "codex", _capture("codex-cli 0.165.0"))
    bad, good = tmp_path / "bad", tmp_path / "good"
    hf.write_capture(bad, _capture("codex-cli 0.166.0", HELP + "  --auto-push   New\n"))
    hf.write_capture(good, _capture("codex-cli 0.166.0", HELP + "  --colour   New\n"))
    assert run_main("--capture", "codex", "--from", str(bad), "--accept") == 1
    assert "UNASSIGNED --auto-push: contains 'push'" in capsys.readouterr().err
    assert "0.165.0" in (accepted / "codex" / hf.VERSION_FILE).read_text()
    assert run_main("--capture", "codex", "--from", str(good)) == 0
    assert "0.165.0" in (accepted / "codex" / hf.VERSION_FILE).read_text()
    assert run_main("--capture", "codex", "--from", str(good), "--accept") == 0
    out = capsys.readouterr().out
    assert "new --colour: no workflow word" in out and "note: update codex's version" in out
    assert hf.read_capture(accepted / "codex") == hf.read_capture(good)


def test_an_incomplete_capture_is_refused_and_the_accepted_one_is_kept(tmp_path: Path, monkeypatch, capsys) -> None:
    accepted = tmp_path / "accepted"
    shutil.copytree(hf.bundled_captures_dir() / "codex", accepted / "codex")
    (accepted / "codex" / "inventory-features.txt").write_text("memories  on\n", encoding="utf-8")
    monkeypatch.setattr(hf, "bundled_captures_dir", lambda: accepted)
    before = hf.read_capture(accepted / "codex")
    version_only, no_inventory = tmp_path / "version-only", tmp_path / "no-inventory"
    hf.write_capture(version_only, {hf.VERSION_FILE: "codex-cli 0.166.0\n"})
    hf.write_capture(no_inventory, {**{k: v for k, v in before.items() if k != "inventory-features.txt"},
                                    hf.VERSION_FILE: "codex-cli 0.166.0\n"})
    assert run_main("--capture", "codex", "--from", str(version_only), "--accept") == 1
    assert "incomplete codex capture: no help-exec.txt, help.txt, inventory-features.txt" in capsys.readouterr().err
    assert run_main("--capture", "codex", "--from", str(no_inventory), "--accept") == 1
    assert "incomplete codex capture: no inventory-features.txt" in capsys.readouterr().err
    assert hf.read_capture(accepted / "codex") == before


def test_capture_runs_the_fixture_commands(monkeypatch) -> None:
    facts = _facts()
    facts["harnesses"][0]["capture_commands"] = {
        hf.VERSION_FILE: [sys.executable, "-c", "print('9.9')"],
        "help.txt": [sys.executable, "-c", f"print({HELP!r})"],
    }
    monkeypatch.setattr(hf, "load_facts", lambda path=None: facts)
    assert rp.capture("claude-code", None) == {hf.VERSION_FILE: "9.9\n", "help.txt": HELP + "\n"}
    facts["harnesses"][0]["capture_commands"]["help.txt"] = [sys.executable, "-c", "raise SystemExit(3)"]
    with pytest.raises(ValueError, match="exited 3"):
        rp.capture("claude-code", None)


def test_capture_needs_a_version_file_and_a_known_harness(tmp_path: Path, capsys) -> None:
    with pytest.raises(hf.HarnessFactsError, match="version.txt"):
        hf.classify_capture(_facts(), "codex", {}, {"help.txt": HELP})
    with pytest.raises(hf.HarnessFactsError, match="no harness 'copilot'"):
        hf.harness(_facts(), "copilot")
    assert run_main("--capture", "codex", "--from", str(tmp_path)) == 1
    assert "no *.txt capture files" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        rp.main(["--accept"])
