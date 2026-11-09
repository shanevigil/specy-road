"""Lean-code gates: scripts/check_clones.py, check_test_private_imports.py, check_public_hygiene.py,
mutation_report.py."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MUTMUT_SAMPLE = ROOT / "tests" / "fixtures" / "mutation" / "results-sample.txt"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_clones = _load("check_clones")
private_imports = _load("check_test_private_imports")
mutation_report = _load("mutation_report")
hygiene = _load("check_public_hygiene")

PYLINT_OUTPUT = textwrap.dedent(
    """\
    ************* Module pkg.a
    pkg/a.py:1:0: R0801: Similar lines in 2 files
    ==pkg.b:[3:11]
    ==pkg.a:[3:11]
        x = 1
        y = 2 (duplicate-code)
    pkg/a.py:1:0: R0801: Similar lines in 2 files
    ==pkg.c:[10:17]
    ==pkg.a:[20:27]
        z = 3 (duplicate-code)
    """
)

CLONE_BODY = """
def build(items):
    total = 0
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        total += len(str(item)) * 3
    return total, sorted(seen)
"""


# --- check_clones -----------------------------------------------------------


def test_parse_clones_canonical_keys():
    assert check_clones.parse_clones(PYLINT_OUTPUT) == {
        ("pkg.a", "pkg.b", "8"),
        ("pkg.a", "pkg.c", "7"),
    }


def test_parse_clones_is_order_independent():
    swapped = PYLINT_OUTPUT.replace("==pkg.b:[3:11]\n==pkg.a:[3:11]", "==pkg.a:[3:11]\n==pkg.b:[3:11]")
    assert check_clones.parse_clones(swapped) == check_clones.parse_clones(PYLINT_OUTPUT)


def _pylint() -> str:
    exe = shutil.which("pylint")
    if exe is None:
        pytest.skip("pylint not installed")
    return exe


def test_check_clones_passes_on_committed_baseline(monkeypatch):
    exe = _pylint()
    monkeypatch.chdir(ROOT)
    assert check_clones.main(["--pylint", exe]) == 0


def test_check_clones_fails_on_new_clone(tmp_path, monkeypatch, capsys):
    exe = _pylint()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "one.py").write_text(CLONE_BODY)
    (pkg / "two.py").write_text(CLONE_BODY.replace("build", "make"))
    baseline = tmp_path / "clone-baseline.json"
    args = ["--pylint", exe, "--source", str(pkg), "--baseline", str(baseline)]

    assert check_clones.main(args) == 1
    assert "NEW CLONE: pkg.one <-> pkg.two" in capsys.readouterr().out

    assert check_clones.main([*args, "--update-baseline"]) == 0
    data = json.loads(baseline.read_text())
    assert data["clones"] == [{"modules": ["pkg.one", "pkg.two"], "lines": data["clones"][0]["lines"]}]
    assert check_clones.main(args) == 0


# --- check_test_private_imports ----------------------------------------------


def test_find_private_refs_forms():
    source = textwrap.dedent(
        """\
        import specy_road.pkg._impl
        from specy_road.mod import public, _helper
        from specy_road.bundled_scripts import thing as _alias
        import specy_road.other
        import specy_road.worker_process as wp
        from specy_road.pkg import mod

        def test_x(monkeypatch):
            monkeypatch.setattr("specy_road.gui._settings", None)
            mock.patch("specy_road.gui._client")
            label = "specy_road.gui._not_a_target"
            specy_road.other._deep.call()
            specy_road.other.public()
            obj.__dunder__
            wp._cmdline(1)
            mod._x
            monkeypatch.setattr(wp, "_pid", 1)
            mock.patch.object(mod, "_y")
            wp.public()
            monkeypatch.setattr(wp, "public", 1)
            _alias.public
        """
    )
    assert private_imports.find_private_refs(source, "t.py") == {
        "specy_road.pkg._impl",
        "specy_road.mod._helper",
        "specy_road.gui._settings",
        "specy_road.gui._client",
        "specy_road.other._deep",
        "specy_road.worker_process._cmdline",
        "specy_road.pkg.mod._x",
        "specy_road.worker_process._pid",
        "specy_road.pkg.mod._y",
    }


def test_private_imports_pass_on_committed_baseline(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert private_imports.main([]) == 0


@pytest.mark.parametrize(
    "source",
    [
        "from specy_road.core import _secret\n",
        "from specy_road import core as c\nc._secret()\n",
    ],
    ids=["import", "aliased-module-attribute"],
)
def test_private_imports_fail_on_new_reference(tmp_path, capsys, source):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_new.py").write_text(source)
    baseline = tmp_path / "baseline.txt"
    args = ["--tests-dir", str(tests_dir), "--baseline", str(baseline)]

    assert private_imports.main(args) == 1
    assert "NEW PRIVATE REFERENCE: tests/test_new.py: specy_road.core._secret" in capsys.readouterr().out

    assert private_imports.main([*args, "--update-baseline"]) == 0
    assert "tests/test_new.py: specy_road.core._secret" in baseline.read_text()
    assert private_imports.main(args) == 0


# --- check_public_hygiene ---------------------------------------------------
# Denied samples are split ("/Users/" + "alice/", "Claude-" + "Session:") so this file passes the repo scan itself.
# LOCAL is a synthetic local list: its tokens name no one, so this file needs no allow entry for them.

LOCAL = "name: Quillon\nname: qzuser\nhandle: qzuser\nhome: Vaultroom\nmachine: zedbox\nphrase: velvet ledger\n"
STRANGER = "rook" + "@corp.org"
PUBLIC = ("Pat", "pub@e.com")
SHIPPED = [
    "specy_road/templates/project/research/README.md",
    "specy_road/templates/project/work/handoff-ready.template.md",
    "specy_road/templates/specyrd/commands/specyrd-prompt.md",
]
ALLOWED = ["noreply@anthropic.com", "x@users.noreply.github.com", "noreply@github.com", "cursoragent@cursor.com",
           "git@github.com", "a@specy-road.invalid", "t@example.com", "t@example.invalid", "t@e.com", "t@e.st",
           "security@pypi.org", "security@npmjs.com"]


@pytest.fixture(autouse=True)
def no_hygiene_secret(monkeypatch):
    monkeypatch.delenv(hygiene.LOCAL_ENV, raising=False)


def _hygiene_repo(root: Path, files: dict[str, str] | None = None, local: str | None = None) -> Path:
    """A git repo holding the shipped allow file (untracked), ``files`` tracked and ``local`` as its local list."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "scripts").mkdir()
    shutil.copy(ROOT / hygiene.ALLOW_FILE, root / hygiene.ALLOW_FILE)
    if local is not None:
        (root / ".git" / hygiene.LOCAL_FILE).parent.mkdir(exist_ok=True)
        (root / ".git" / hygiene.LOCAL_FILE).write_text(local, encoding="utf-8")
    for name, text in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", name], cwd=root, check=True)
    return root


def _commit(repo: Path, message: str, author: tuple[str, str] = PUBLIC, committer: tuple[str, str] = PUBLIC) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
           "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1]}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "--no-verify", "-m", message],
                   cwd=repo, env=env, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def test_public_hygiene_passes_on_this_repo():   # the script, its allow file and this file among them
    assert hygiene.main([]) == 0


MACHINE_ROWS = [
    ("cd /Users/" + "alice/repo", True),
    ("cd /home/" + "alice/repo", True),
    ('"/Users/' + 'alice"', True),
    ("~/.claude/projects/-home-" + "alice-repo", True),
    ("C:\\" + "Users\\alice\\repo", True),
    ("~/.claude/projects/-Users-" + "alice-repo", True),
    ("/private/tmp/claude-" + "501/scratchpad", True),
    ("/tmp/claude-" + "1000/scratchpad", True),
    ("alice@alices-" + "MacBook-Pro.local", True),
    ("an M3-" + "MacBook review", False),
    ("work-from-" + "home-policy and the-" + "Users-guide", False),
    ("~/.claude/projects/-home-" + "runner-work", False),
    ("C:" + "\\\\Users\\\\alice", True),
    ("C:\\" + "Users\\Public\\Desktop", False),
    ("cd /home/" + "x-user/repo", True),
    ("cd /Users/" + "runner-person/repo", True),
    ("C:\\" + "Users\\Default-user\\repo", True),
    ("c:\\" + "users\\alice\\repo", True),
    ("file:///" + "Users/alice/repo", True),
    ("https://example.com/" + "home/alice/page", True),   # no URL exemption: reword such a link
    ("cc -I/home/" + "alice/include -L/Users/" + "alice/lib", True),
    ("file://localhost/" + "Users/alice/repo", True),
    ("file://LOCALHOST/" + "Users/alice/repo", True),
    ("file://C:/" + "Users/alice/repo", True),
    ("ssh://host/" + "home/alice/repo", True),
    ("vscode://file/" + "Users/alice/repo", True),
    ("curl https://example.com|/home/" + "alice/bin/filter", True),
    ("cp x /Users/" + "Shared/ and /home/" + "runner/work", False),
    ('Path("/Users/x/my_app")', False),
    ("-Users-x-my-app-v2", False),
    ("no `/home/<name>/` or `C:\\Users\\<name>\\` paths", False),
]

#: ``(text, fails in a tracked file, fails as a commit message)``
HYGIENE_ROWS = [
    ("mail someone" + "@corp.org", True, True),
    *[(f"mail {address}", False, False) for address in ALLOWED],
    ("t@example.com and b" + "@corp.org", True, True),            # an entry exempts its address, not the line
    ("x@AGENTS.team.md and n@pytest.mark.skip", False, False),    # a file name and a decorator, not addresses
    ("owner: qzuser", True, True),
    ("owner: Alice", False, False),
    ("agent qzuser-s123", True, True),
    ("thanks, Quillon", True, True),
    ("https://github.com/qzuser/specy-road", False, False),
    ("~/" + "Vaultroom/x", True, True),
    ("~/.ssh/config, ~/.codex and ~/.claude", False, False),
    ("~/" + "miniconda3/envs/x/bin/python", True, True),
    ("$HOME/" + ".venv/bin/python", True, True),
    ("CLAUDE_CONFIG_DIR=" + "/home/x", True, True),
    ("CLAUDE_CONFIG_DIR=" + "~/.claude-two", True, True),
    ("CLAUDE_CONFIG_DIR=$ALT_DIR", False, False),
    ("sysctl -w kernel.apparmor_restrict_unprivileged_userns=" + "0", True, True),
    ("sysctl -w kernel.apparmor_restrict_unprivileged_userns=<n>", False, False),
    ("ssh zedbox", True, True),
    ("AGENTS.local.md and settings.local.json", False, False),
    ("Claude-" + "Session: abc", True, True),
    ("see the deep-" + "research report", True, True),
    ("the velvet ledger", True, True),
    ("see sr/work/x", False, True),
    (f"subject\n\n# modified: sr/work/x\n{hygiene.SCISSORS}\n+sr/work/x\n", False, False),   # git's comments and -v diff
]


@pytest.mark.parametrize("text, in_file, in_msg", [(line, flagged, flagged) for line, flagged in MACHINE_ROWS]
                         + HYGIENE_ROWS)
def test_public_hygiene_content_rows(tmp_path, capsys, text, in_file, in_msg):
    repo = _hygiene_repo(tmp_path / "repo", {"notes.md": text + "\n"}, LOCAL)
    assert hygiene.main(["--root", str(repo)]) == int(in_file)
    assert ("notes.md:" in capsys.readouterr().out) is in_file

    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(text + "\n", encoding="utf-8")
    assert hygiene.main(["--root", str(repo), "--commit-msg", str(message)]) == int(in_msg)


@pytest.mark.parametrize("source, expected", [("file", 1), ("secret", 1), ("none", 0)])
def test_public_hygiene_reads_names_from_the_local_file_or_the_ci_secret(tmp_path, monkeypatch, source, expected):
    repo = _hygiene_repo(tmp_path, {"notes.md": "thanks, Quillon\n"}, LOCAL if source == "file" else None)
    if source == "secret":
        monkeypatch.setenv(hygiene.LOCAL_ENV, LOCAL)
    assert hygiene.main(["--root", str(repo)]) == expected


def test_public_hygiene_refuses_a_malformed_local_line_without_echoing_it(tmp_path):
    repo = _hygiene_repo(tmp_path, local="nmae: Quillon\n")
    with pytest.raises(SystemExit, match="line 1") as raised:
        hygiene.main(["--root", str(repo)])
    assert "Quillon" not in str(raised.value)


def test_public_hygiene_path_denylist_runs_under_promotion_only(tmp_path, capsys):
    repo = _hygiene_repo(tmp_path, {"sr/notes.md": "Claude-" + "Session: abc\n", "docs/design-notes/n.md": "n\n"})
    assert hygiene.main(["--root", str(repo)]) == 0
    assert hygiene.main(["--root", str(repo), "--promotion"]) == 1
    out = capsys.readouterr().out
    assert "sr/notes.md: process content path" in out and "docs/design-notes/n.md: process content path" in out


@pytest.mark.parametrize("archive_format", ["zip", "gztar"])
def test_public_hygiene_promotion_passes_shipped_paths_and_checks_archive_members(tmp_path, archive_format):
    repo = _hygiene_repo(tmp_path / "repo", {path: "x\n" for path in SHIPPED})
    tree = tmp_path / "tree" / "pkg-1.0"
    for path in [*SHIPPED, "sr/notes.md"]:
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        (tree / path).write_text("x\n", encoding="utf-8")
    bad = shutil.make_archive(str(tmp_path / "bad"), archive_format, tmp_path / "tree")
    shutil.rmtree(tree / "sr")
    good = shutil.make_archive(str(tmp_path / "good"), archive_format, tmp_path / "tree")

    assert hygiene.main(["--root", str(repo), "--promotion", "--archive", good]) == 0
    assert hygiene.main(["--root", str(repo), "--promotion", "--archive", bad]) == 1


@pytest.mark.parametrize("role", ["author", "committer"])
def test_public_hygiene_identity_check_reports_until_the_public_identity_is_set(tmp_path, capsys, role):
    repo = _hygiene_repo(tmp_path)
    base = _commit(repo, "base")
    _commit(repo, "merged on the web", committer=("GitHub", "noreply@github.com"))
    _commit(repo, "a change", **{role: ("Rook", STRANGER)})
    span = ["--root", str(repo), "--range", f"{base}..HEAD"]
    refused = f"{role} Rook <{STRANGER}>"

    assert hygiene.main(span) == 0                     # default mode: the WIP line never checks identities
    assert STRANGER not in capsys.readouterr().out
    assert hygiene.main([*span, "--promotion"]) == 0   # placeholder: report only
    assert refused in capsys.readouterr().out

    allow = repo / hygiene.ALLOW_FILE
    allow.write_text(allow.read_text(encoding="utf-8").replace(hygiene.UNSET, PUBLIC[1]), encoding="utf-8")
    assert hygiene.main([*span, "--promotion"]) == 1
    out = capsys.readouterr().out
    assert refused in out and PUBLIC[1] not in out and "noreply@github.com" not in out


def test_public_hygiene_range_checks_every_message_and_names_a_missing_endpoint(tmp_path, capsys):
    repo = _hygiene_repo(tmp_path)
    base = _commit(repo, "base")
    _commit(repo, "notes from sr/work/x")
    _commit(repo, "a clean change")

    assert hygiene.main(["--root", str(repo), "--range", f"{base}..HEAD"]) == 1
    capsys.readouterr()
    assert hygiene.main(["--root", str(repo), "--range", f"{base}..no-such-ref"]) == 1
    assert "no-such-ref" in capsys.readouterr().err


# --- mutation_report --------------------------------------------------------


def test_mutation_report_parses_real_mutmut_sample():
    per_module = mutation_report.parse_results(MUTMUT_SAMPLE.read_text())
    assert "specy_road.milestone_lock" in per_module
    counts = per_module["specy_road.milestone_lock"]
    assert counts["killed"] + counts["survived"] + counts["other"] > 0
    assert mutation_report.score(counts) == round(
        100 * counts["killed"] / (counts["killed"] + counts["survived"]), 1
    )


def test_mutation_report_table_and_no_baseline(tmp_path, monkeypatch, capsys):
    out = tmp_path / "report.md"
    assert mutation_report.main(
        [str(MUTMUT_SAMPLE), "--baseline", str(tmp_path / "missing.json"), "--output", str(out)]
    ) == 0
    text = out.read_text()
    assert text.startswith("| Module | Killed | Survived | Other | Score | Baseline | Delta |")
    assert "| `specy_road.milestone_lock` |" in text
    assert text.rstrip().splitlines()[-1].startswith("| **total** |")
    assert "no baseline" in capsys.readouterr().out


def _baseline(tmp_path: Path, shift: float) -> Path:
    current = mutation_report.scores(mutation_report.parse_results(MUTMUT_SAMPLE.read_text()))
    path = tmp_path / "mutation-baseline.json"
    path.write_text(json.dumps({"modules": {m: s + shift for m, s in current.items()}}))
    return path


def test_mutation_report_flags_three_point_drop(tmp_path, capsys):
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--baseline", str(_baseline(tmp_path, 3.0))]) == 1
    assert "MUTATION SCORE DROP: specy_road.milestone_lock" in capsys.readouterr().out


def test_mutation_report_tolerates_two_point_drop(tmp_path):
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--baseline", str(_baseline(tmp_path, 2.0))]) == 0
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--baseline", str(_baseline(tmp_path, -5.0))]) == 0


def test_mutation_report_write_baseline(tmp_path):
    target = tmp_path / "seed.json"
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--write-baseline", str(target)]) == 0
    data = json.loads(target.read_text())
    assert data["max_drop"] == 2.0
    assert "specy_road.milestone_lock" in data["modules"]
