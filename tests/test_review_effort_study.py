"""scripts/review_effort_study.py: recorded packets replayed through roster reviewers at two effort levels."""

from __future__ import annotations

import ast
import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "review_effort_study.py"
CLAUDE_PROFILES = REPO / "specy_road" / "templates" / "project" / "model-profiles" / "anthropic-claude"
_spec = importlib.util.spec_from_file_location("review_effort_study", SCRIPT)
study = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(study)

# Records its arguments in its working directory (the run's own), reads the prompt file it is given
# (its last argument; a missing file fails the run), and answers with a verdict block.
FAKE = """import pathlib, sys
pathlib.Path("argv.txt").write_text(" ".join(sys.argv[1:]))
assert "this replay files nothing" in pathlib.Path(sys.argv[-1]).read_text()
print("notes\\n```yaml\\nverdict: block\\nblock_reasons: [\\"A1 fails\\", \\"no test\\"]\\n```")
"""
PACKET = "# Review packet: `M1.1`\n\n- **Commit under review:** `abc1234def` (`feature/rm-x`)\n"


def make_project(tmp_path: Path, roster: list[dict], fake: str = FAKE) -> Path:
    (tmp_path / "fake.py").write_text(fake, encoding="utf-8")
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "orchestration.yaml").write_text(
        yaml.safe_dump({"version": 1, "roster": roster}), encoding="utf-8")
    for node in ("M1.1", "M1.2"):
        d = tmp_path / "work" / "reviews" / node
        d.mkdir(parents=True)
        (d / "PACKET.md").write_text(PACKET.replace("M1.1", node), encoding="utf-8")
    return tmp_path


def reviewer(rid: str, harness: str, args: str) -> dict:
    return {"id": rid, "family": "xai" if harness == "cursor" else "openai", "roles": ["reviewer"],
            "harness": harness, "channels": {"cli": f"{sys.executable} {{root}}/fake.py {args}"}}


def run(root: Path, *args: str) -> int:
    return study.main([*args, "--repo-root", str(root), "-o", str(root / "study")])


def rows(root: Path) -> list[dict]:
    with (root / "study" / "results.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def with_root(entry: dict, root: Path) -> dict:
    entry["channels"]["cli"] = entry["channels"]["cli"].replace("{root}", str(root))
    return entry


def test_flag_harness_passes_each_level_through_effort_and_writes_one_row_per_run(tmp_path: Path) -> None:
    root = make_project(tmp_path, [with_root(reviewer("sol", "codex", "{effort} {prompt}"), tmp_path)])
    assert run(root, "--model", "sol", "--levels", "high", "medium", "M1.1", "M1.2") == 0
    got = rows(root)
    assert [(r["node_id"], r["model"], r["level"]) for r in got] == [
        ("M1.1", "sol", "high"), ("M1.1", "sol", "medium"), ("M1.2", "sol", "high"), ("M1.2", "sol", "medium")]
    assert {(r["commit"], r["family"], r["verdict"], r["block_reasons"], r["exit_code"]) for r in got} == {
        ("abc1234def", "openai", "block", "A1 fails | no test", "0")}
    argv = (root / "study" / "runs" / "M1.1" / "sol-medium" / "argv.txt").read_text()
    assert argv.startswith("-c model_reasoning_effort=medium ") and argv.endswith("prompt.md")
    prompt = (root / "study" / "runs" / "M1.1" / "sol-medium" / "prompt.md").read_text()
    assert "this replay files nothing" in prompt and prompt.rstrip().endswith("(`feature/rm-x`)")


def test_relative_output_dir_still_hands_each_reviewer_a_readable_prompt(tmp_path: Path, monkeypatch) -> None:
    root = make_project(tmp_path, [with_root(reviewer("sol", "codex", "{effort} {prompt}"), tmp_path)])
    monkeypatch.chdir(root)
    assert study.main(["--model", "sol", "--levels", "high", "medium", "M1.1", "--repo-root", str(root),
                       "-o", "rel-study"]) == 0
    with (root / "rel-study" / "results.csv").open(encoding="utf-8") as f:
        assert {(r["verdict"], r["exit_code"]) for r in csv.DictReader(f)} == {("block", "0")}


def test_cursor_level_swaps_the_effort_suffix_of_the_model_id(tmp_path: Path) -> None:
    root = make_project(tmp_path, [with_root(reviewer("grok-4.7-high", "cursor", "grok-4.7-high {prompt}"), tmp_path)])
    assert run(root, "--model", "grok-4.7-high", "--levels", "high", "low", "M1.1") == 0
    runs = root / "study" / "runs" / "M1.1"
    assert (runs / "grok-4.7-high-high" / "argv.txt").read_text().startswith("grok-4.7-high ")
    assert (runs / "grok-4.7-high-low" / "argv.txt").read_text().startswith("grok-4.7-low ")


def test_flag_harness_without_effort_placeholder_is_refused_before_any_run(tmp_path: Path, capsys) -> None:
    root = make_project(tmp_path, [with_root(reviewer("sol", "codex", "{prompt}"), tmp_path)])
    assert run(root, "--model", "sol", "--levels", "high", "medium", "M1.1") == 1
    assert "names no {effort}" in capsys.readouterr().err
    assert not (root / "study").exists()


def test_cursor_id_without_effort_suffix_is_refused(tmp_path: Path, capsys) -> None:
    root = make_project(tmp_path, [with_root(reviewer("grok", "cursor", "grok {prompt}"), tmp_path)])
    assert run(root, "--model", "grok", "--levels", "high", "low", "M1.1") == 1
    assert "must end in" in capsys.readouterr().err


def test_duplicate_levels_are_refused_through_the_cli_before_anything_runs(tmp_path: Path) -> None:
    root = make_project(tmp_path, [with_root(reviewer("sol", "codex", "{effort} {prompt}"), tmp_path)])
    done = subprocess.run([sys.executable, str(SCRIPT), "--model", "sol", "--levels", "high", "high", "M1.1",
                           "--repo-root", str(root), "-o", str(root / "study")],
                          capture_output=True, text=True, check=False, env={**os.environ, "PYTHONPATH": str(REPO)})
    assert done.returncode == 1
    assert "the levels must differ" in done.stderr
    assert not (root / "study").exists()


def test_cursor_level_outside_the_suffix_set_is_refused_through_the_cli(tmp_path: Path) -> None:
    root = make_project(tmp_path, [with_root(reviewer("grok-4.7-high", "cursor", "grok-4.7-high {prompt}"), tmp_path)])
    for bad in ("high;touch PWNED", "ultra"):
        done = subprocess.run([sys.executable, str(SCRIPT), "--model", "grok-4.7-high", "--levels", "high", bad,
                               "M1.1", "--repo-root", str(root), "-o", str(root / "study")],
                              capture_output=True, text=True, check=False, cwd=root,
                              env={**os.environ, "PYTHONPATH": str(REPO)})
        assert done.returncode == 1 and "is not a cursor effort suffix" in done.stderr, bad
    assert not (root / "study").exists() and not list(root.rglob("PWNED"))


def test_study_over_budget_is_refused_whole(tmp_path: Path, capsys) -> None:
    root = make_project(tmp_path, [with_root(reviewer("sol", "codex", "{effort} {prompt}"), tmp_path)])
    assert run(root, "--model", "sol", "--levels", "high", "medium", "--max-runs", "3", "M1.1", "M1.2") == 1
    assert "4 reviewer runs, over the budget of 3" in capsys.readouterr().err
    assert not (root / "study").exists()


def test_non_reviewer_and_missing_packet_are_refused(tmp_path: Path, capsys) -> None:
    entry = with_root(reviewer("sol", "codex", "{effort} {prompt}"), tmp_path)
    root = make_project(tmp_path, [{**entry, "roles": ["executor"]}])
    assert run(root, "--model", "sol", "--levels", "high", "medium", "M1.1") == 1
    assert "not a reviewer" in capsys.readouterr().err
    assert run(root, "--model", "sol", "--levels", "high", "medium", "M9.9") == 1
    assert "no recorded packet" in capsys.readouterr().err


def test_reply_without_verdict_block_is_unparsed_with_exit_code(tmp_path: Path) -> None:
    fake = "import sys\nprint('I could not decide')\nsys.exit(3)\n"
    root = make_project(tmp_path, [with_root(reviewer("sol", "codex", "{effort} {prompt}"), tmp_path)], fake)
    assert run(root, "--model", "sol", "--levels", "high", "medium", "M1.1") == 0
    assert {(r["verdict"], r["block_reasons"], r["exit_code"]) for r in rows(root)} == {("unparsed", "", "3")}


def test_last_verdict_block_wins() -> None:
    out = "```yaml\nverdict: approve\n```\nthen\n```yaml\nverdict: block\nblock_reasons: one\n```\n"
    assert study.parse_verdict(out) == ("block", ["one"])


def test_script_imports_no_network_or_model_client() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not names & {"urllib", "http", "socket", "requests", "httpx", "anthropic", "openai"}


def test_shipped_claude_effort_by_role_cites_the_study_note() -> None:
    for path in sorted(CLAUDE_PROFILES.glob("*.md")):
        line = next(ln for ln in path.read_text(encoding="utf-8").splitlines() if "effort_by_role:" in ln)
        assert "docs/design-notes/reviewer-effort-study.md" in line, path.name
