"""``specy-road impact`` and the Tests at risk sections of the executor prompt and review packet."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integrity_repo_helpers import commit, git, make_repo, merge_dev, on_dev
from tests.review_repo_helpers import NODE
from specy_road.bundled_scripts import do_next_prompt as dnp
from specy_road.bundled_scripts import impact_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.impact import impact_for_zones
from specy_road.review_target import resolve_target_or_exit

# Ten Python files under a src/ layout. tests/test_api.py reaches src/pkg/core.py
# only through src/pkg/api.py's relative import: the two-level chain.
_FILES = {
    "src/pkg/__init__.py": "",
    "src/pkg/core.py": "VALUE = 1\n",
    "src/pkg/api.py": "from .core import VALUE\n",
    "src/pkg/util.py": "def helper():\n    return 2\n",
    "lib/other.py": "OTHER = 3\n",
    "tests/conftest.py": "import pytest\n",
    "tests/test_api.py": "from pkg.api import VALUE\n\n\ndef test_api():\n    assert VALUE\n",
    "tests/core_test.py": "from pkg import core\n\n\ndef test_core():\n    assert core.VALUE\n",
    "tests/test_util.py": "import pkg.util\n\n\ndef test_util():\n    assert pkg.util.helper()\n",
    "tests/test_other.py": "import other\n\n\ndef test_other():\n    assert other.OTHER\n",
}


def _commit_all(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", *files)
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> Path:
    """Leaf ``T1`` (touch zone ``src``) on ``feature``, with the fixture merged in from ``dev``."""
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    _commit_all(repo, _FILES, "fixture")
    merge_dev(repo)
    return repo


def _cli(repo: Path, capsys, *args: str) -> str:
    impact_cli.main(["T1", "--repo-root", str(repo), "--ref", git(repo, "rev-parse", "HEAD"), *args])
    return capsys.readouterr().out


def test_diff_lists_tests_through_a_two_level_chain_and_counts_other_files(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    _commit_all(repo, {"src/pkg/core.py": "VALUE = 2\n", "README.md": "# changed\n"}, "change core")
    assert _cli(repo, capsys) == "tests/core_test.py\ntests/test_api.py\nnot analysed: 1 files\n"


def test_zones_use_the_modules_under_the_touch_zones(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _cli(repo, capsys, "--zones") == "tests/core_test.py\ntests/test_api.py\ntests/test_util.py\n"
    head = git(repo, "rev-parse", "HEAD")
    assert impact_for_zones(repo, head, ["lib"]).lines() == ["tests/test_other.py"]


def test_conftest_change_prints_all(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    _commit_all(repo, {"tests/conftest.py": "import pytest\n\nX = 1\n", "src/pkg/core.py": "VALUE = 2\n",
                       "README.md": "# changed\n"}, "conftest")
    assert _cli(repo, capsys) == "ALL\n"


def test_deleted_module_still_lists_its_importers(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    git(repo, "rm", "-q", "src/pkg/util.py")
    git(repo, "commit", "-qm", "delete util")
    assert _cli(repo, capsys) == "tests/test_util.py\n"


def _many_tests(n: int) -> dict[str, str]:
    return {f"tests/test_many_{i:03d}.py": "from pkg import util\n" for i in range(n)}


@pytest.mark.parametrize(("extra", "tail"), [(0, None), (52, "- _… and 5 more (`specy-road impact T1 --zones`")],
                         ids=["three", "fifty-five"])
def test_pickup_prompt_lists_zone_tests_capped_at_fifty(tmp_path: Path, extra: int, tail: str | None) -> None:
    repo = _repo(tmp_path)
    _commit_all(repo, _many_tests(extra) or {"README.md": "# x\n"}, "more tests")
    brief = repo / "work" / "brief-T1.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("# brief\n", encoding="utf-8")
    node = {**NODE, "id": "T1", "touch_zones": ["src"]}
    text = dnp.write_agent_prompt(node, [node], brief, repo_root=repo, work_dir=repo / "work").read_text()
    listed = text.split("## Tests at risk", 1)[1].split("## Instructions", 1)[0]
    paths = [ln for ln in listed.splitlines() if ln.startswith("- `")]
    assert len(paths) == min(50, 3 + extra)
    assert paths[0] == "- `tests/core_test.py`"
    assert (tail in listed) if tail else ("more" not in listed)


def test_pickup_prompt_says_none_found(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    brief = repo / "work" / "brief-T1.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("# brief\n", encoding="utf-8")
    node = {**NODE, "id": "T1", "touch_zones": ["docs"]}
    text = dnp.write_agent_prompt(node, [node], brief, repo_root=repo, work_dir=repo / "work").read_text()
    assert "_none found_" in text.split("## Tests at risk", 1)[1].split("## Instructions", 1)[0]


def test_packet_section_lists_diff_tests_capped_and_byte_identical(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit_all(repo, {**_many_tests(52), "src/pkg/util.py": "def helper():\n    return 3\n"}, "util + tests")
    head = git(repo, "rev-parse", "HEAD")
    first = rp.tests_at_risk_section(repo, resolve_target_or_exit(repo, "T1", head))
    second = rp.tests_at_risk_section(repo, resolve_target_or_exit(repo, "T1", head))
    assert first == second
    paths = [ln for ln in first if ln.startswith("- `")]
    assert len(paths) == 50 and paths[0] == "- `tests/test_many_000.py`"
    assert f"- _… and 3 more (`specy-road impact T1 --ref {head}` lists them all)_" in first
    assert "- not analysed: 0 files" not in first
    packet = rp.build_packet(repo, "T1", ref=head, verify_cmds=[])
    assert packet.index("## Test integrity") < packet.index("## Tests at risk") < packet.index("## Diff")
