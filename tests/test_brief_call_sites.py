"""The brief lists, under the touch zones, the modules that import each zoned file.

One level of the ``specy-road impact`` import graph at ``HEAD``: every importer
is named, and one outside the zones is marked and listed first, since it is
where an executor would otherwise stop for a file outside its zones.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts import brief_call_sites as bcs
from specy_road.bundled_scripts import generate_brief as gb
from tests.integrity_repo_helpers import git
from tests.test_roadmap_crud import crud_fixture_repo

SOURCES = {
    "pkg/__init__.py": "",
    "pkg/core.py": "X = 1\n",
    "pkg/api.py": "from pkg import core\n",
    "pkg/cli.py": "from .core import X\n",
    "pkg/deep.py": "import pkg.api\n",   # imports core only through api: not one level
    "pkg/helper.py": "",
    "tests/test_core.py": "import pkg.core\nfrom pkg import helper\n",
}


def _repo(root: Path) -> Path:
    for rel, text in SOURCES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def test_direct_importers_are_one_level_and_resolve_relative_imports(tmp_path: Path) -> None:
    files = {p: t.encode() for p, t in SOURCES.items()}

    found = bcs.direct_importers(files, {"pkg/core.py"})

    assert found == {"pkg/core.py": ["pkg/api.py", "pkg/cli.py", "tests/test_core.py"]}


def test_every_importer_is_named_with_outside_ones_first_and_marked(tmp_path: Path) -> None:
    _repo(tmp_path)

    lines = bcs.call_site_lines(tmp_path, ["pkg/core.py", "pkg/helper.py", "tests/"])

    assert lines[0] == "### Call sites (one level)"
    assert (
        "- `pkg/core.py` ← `pkg/api.py` _(outside zones)_, `pkg/cli.py` _(outside zones)_, "
        "`tests/test_core.py`"
    ) in lines
    assert "- `pkg/helper.py` ← `tests/test_core.py`" in lines   # imported only from inside the zones
    assert not any("pkg/deep.py" in ln for ln in lines)


def test_zones_whose_importers_are_all_inside_still_list_each_file(tmp_path: Path) -> None:
    _repo(tmp_path)

    lines = bcs.call_site_lines(tmp_path, ["pkg/", "tests/"])

    assert "- `pkg/core.py` ← `pkg/api.py`, `pkg/cli.py`, `tests/test_core.py`" in lines
    assert "- `pkg/api.py` ← `pkg/deep.py`" in lines
    assert "- `pkg/helper.py` ← `tests/test_core.py`" in lines
    assert any(ln.startswith("- `pkg/__init__.py` ← ") for ln in lines)


def test_a_zone_nobody_imports_says_so(tmp_path: Path) -> None:
    _repo(tmp_path)

    assert bcs.call_site_lines(tmp_path, ["pkg/deep.py"])[-1] == "_none found (Python imports only)_"


def test_outside_git_the_section_says_it_cannot_compute(tmp_path: Path) -> None:
    assert bcs.call_site_lines(tmp_path, ["pkg/core.py"])[-1] == (
        "_(cannot compute: git could not read the tree)_"
    )


def test_long_lists_are_capped_and_counted(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path)
    monkeypatch.setattr(bcs, "IMPORTER_CAP", 1)
    monkeypatch.setattr(bcs, "FILE_CAP", 1)

    lines = bcs.call_site_lines(tmp_path, ["pkg/core.py", "pkg/helper.py", "tests/"])

    assert "- `pkg/core.py` ← `pkg/api.py` _(outside zones)_, _… and 2 more_" in lines
    assert lines[-1] == "- _… and 1 more zoned files with importers_"


def test_two_hundred_importers_list_twenty_then_count(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path)
    importers = [f"tests/test_{i:03d}.py" for i in range(200)]
    monkeypatch.setattr(
        bcs,
        "direct_importers",
        lambda _files, _targets: {"pkg/core.py": importers},
    )
    monkeypatch.setattr(bcs, "python_sources", lambda _root, _ref: {"pkg/core.py": b"x=1\n"})

    lines = bcs.call_site_lines(tmp_path, ["pkg/core.py"])
    line = next(ln for ln in lines if ln.startswith("- `pkg/core.py`"))

    assert line.count("_(outside zones)_") == 20
    assert "_… and 180 more_" in line


def test_the_brief_lists_call_sites_under_the_touch_zones(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    _repo(tmp_path)
    by_id = gb.index(gb.load_nodes(tmp_path))
    by_id["M99.1"]["touch_zones"] = ["pkg/core.py"]

    text = gb.render_brief("M99.1", by_id, repo_root=tmp_path, include_history=False)

    section = text.split("\n## 7. Touch zones")[1].split("\n## 8.")[0]
    assert "### Call sites (one level)" in section
    assert (
        "- `pkg/core.py` ← `pkg/api.py` _(outside zones)_, `pkg/cli.py` _(outside zones)_, "
        "`tests/test_core.py` _(outside zones)_"
    ) in section


def test_a_brief_without_zones_has_no_call_site_list(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    by_id = gb.index(gb.load_nodes(tmp_path))
    by_id["M99.1"]["touch_zones"] = []

    text = gb.render_brief("M99.1", by_id, repo_root=tmp_path, include_history=False)

    assert "### Call sites" not in text
