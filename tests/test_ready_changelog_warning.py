"""ready warns when product files change and ``## [Unreleased]`` gains no line."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts import review_cli
from specy_road.changelog_check import missing_entry_warning
from specy_road.review_files import load_ready, reviews_dir
from tests.review_repo_helpers import commit_file, git, make_review_repo

_BASE = "## [Unreleased]\n\n### Added\n\n- old\n\n## [v0.1.0]\n\n- released\n"
_ADDED = "## [Unreleased]\n\n### Added\n\n- old\n- new\n\n## [v0.1.0]\n\n- released\n"
_EDITED = "## [Unreleased]\n\n### Added\n\n- edited\n\n## [v0.1.0]\n\n- released\n"
_VERSION = "## [Unreleased]\n\n### Added\n\n- old\n\n## [v0.1.0]\n\n- released\n- extra\n"
_EMPTY = "## [Unreleased]\n"
_LOG = "## [Unreleased]\n\n### Added\n\n- old\n"

# (changed, prefix, base, head, exempt, shown). ``shown`` is the product paths the
# warning names, in order; empty means silent.
_ROWS = [
    ("package change with no entry",
     ["specy_road/a.py", "specy_road/b.py", "docs/c.md", "specy_road/d.py"],
     "sr/", _BASE, _BASE, "", ("specy_road/a.py", "specy_road/b.py", "docs/c.md")),
    ("added entry", ["specy_road/a.py"], "sr/", _BASE, _ADDED, "", ()),
    ("edited entry", ["specy_road/a.py"], "sr/", _BASE, _EDITED, "", ("specy_road/a.py",)),
    ("line under a version heading only", ["specy_road/a.py"], "sr/", _BASE, _VERSION, "", ("specy_road/a.py",)),
    ("new changelog with empty unreleased",
     ["specy_road/a.py", "CHANGELOG.md"], "sr/", "", _EMPTY, "", ("specy_road/a.py",)),
    ("docs-only", ["docs/guide.md"], "sr/", _BASE, _BASE, "", ("docs/guide.md",)),
    ("tests-only", ["tests/test_a.py"], "sr/", _BASE, _BASE, "", ()),
    ("root file named tests", ["tests"], "sr/", _BASE, _BASE, "", ("tests",)),
    ("sr-only nested", ["sr/planning/x.md", "sr/src/a.py"], "sr/", _BASE, _BASE, "", ()),
    ("roadmap/planning-only unnested",
     ["roadmap/a.json", "planning/x.md", "work/n.md", "roadmap.md", "roadmap-context.md"],
     "", _BASE, _BASE, "", ()),
    ("acceptance exempt", ["specy_road/a.py"], "sr/", _BASE, _BASE, "no CHANGELOG entry", ()),
    ("planning sheet exempt", ["specy_road/a.py"], "sr/", _BASE, _BASE, "Notes: No Changelog Entry.\n", ()),
    ("no changelog", ["specy_road/a.py"], "sr/", "", "", "", ()),
    ("no heading", ["specy_road/a.py"], "sr/", _BASE, "# Changelog\n\n- a line\n", "", ()),
    ("newline in a product path",
     ["docs/line\nbreak.md", "docs/c\r\t\x01\\\u2028é.md"],
     "sr/", _BASE, _BASE, "",
     ("docs/line\\nbreak.md", "docs/c\\r\\t\\x01\\\\\\u2028é.md")),
]


@pytest.mark.parametrize(
    "changed,prefix,base,head,exempt,shown",
    [row[1:] for row in _ROWS],
    ids=[row[0] for row in _ROWS],
)
def test_missing_entry_warning(changed, prefix, base, head, exempt, shown) -> None:
    got = missing_entry_warning(changed, prefix, base, head, exempt)
    if not shown:
        assert got is None
        return
    assert got is not None and "## [Unreleased]" in got and "no CHANGELOG entry" in got
    assert len(got.splitlines()) == 1 and all(ch.isprintable() for ch in got)
    assert got.split("changes ", 1)[1].split(";", 1)[0] == ", ".join(shown)


def _sheet(repo: Path) -> Path:
    return next((repo / "planning").glob("*.md"))


def _sheet_dir(repo: Path) -> None:
    sheet = _sheet(repo)
    sheet.unlink()
    sheet.mkdir()


def _commit_sheet_loop(repo: Path) -> None:
    sheet = _sheet(repo)
    sheet.unlink()
    sheet.symlink_to(sheet.name)
    git(repo, "add", sheet.relative_to(repo).as_posix())
    git(repo, "commit", "-qm", "looping sheet")


def _with_base_changelog(repo: Path) -> None:
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "CHANGELOG.md", _LOG, "changelog")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")


_WARNING = (
    "warning: ## [Unreleased] in CHANGELOG.md gained no line, but this branch changes "
    "{names}; write `no CHANGELOG entry` in the leaf's acceptance or planning sheet to exempt it"
)
_NAMES = "docs/x.md, src/a.py"
_STDERR = {
    "warns": [_WARNING.format(names=_NAMES)],
    "silent": [],
    "new": [_WARNING.format(names=_NAMES)],
    "missing-sheet": [],
    "sheet-dir": [],
    "empty-sheet": [_WARNING.format(names=_NAMES)],
    "newline-path": [_WARNING.format(names="docs/line\\nbreak.md, docs/x.md, src/a.py")],
    "sheet-loop": [],
}


@pytest.mark.parametrize("mode", list(_STDERR))
def test_ready_changelog_reminder(tmp_path: Path, capsys, mode: str) -> None:
    repo = make_review_repo(tmp_path)
    if mode != "new":
        _with_base_changelog(repo)
    {
        "silent": lambda: commit_file(repo, "CHANGELOG.md", _ADDED, "changelog entry"),
        "new": lambda: commit_file(repo, "CHANGELOG.md", _EMPTY, "changelog"),
        "missing-sheet": lambda: _sheet(repo).unlink(),
        "sheet-dir": lambda: _sheet_dir(repo),
        "empty-sheet": lambda: _sheet(repo).write_text("", encoding="utf-8"),
        "newline-path": lambda: commit_file(repo, "docs/line\nbreak.md", "x\n", "newline path"),
        "sheet-loop": lambda: _commit_sheet_loop(repo),
    }.get(mode, lambda: None)()
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        review_cli.main(["ready", "M1.1", "--model", "opus", "--verify", "pytest=0", "--repo-root", str(repo)])
    assert caught.value.code == 0
    err = capsys.readouterr().err
    ready = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert ready.ok, ready.errors
    assert err.splitlines() == _STDERR[mode]
