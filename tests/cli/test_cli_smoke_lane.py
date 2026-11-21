"""The CLI smoke lane (tests/support/cli_smoke_lane.py): which child starts it counts, and the
bundled scripts it still runs as files."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env
from tests.support.cli import run_cli_subprocess
from tests.support.cli_smoke_lane import MAX_ITEMS, lane_problems, recorded_starts, starts_cli


def _start(argv: list[str]) -> None:
    subprocess.run(argv, capture_output=True, env=script_subprocess_env(), check=False)


def _console_script(name: str) -> Callable[[Path], None]:
    """Start a program named ``name`` (a stand-in that exits 0): the basename is what counts."""

    def start(tmp_path: Path) -> None:
        program = tmp_path / name
        program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        program.chmod(0o755)
        _start([str(program), "--version"])

    return start


@pytest.mark.parametrize(
    ("start", "counted"),
    [
        pytest.param(_console_script("specy-road"), 1, id="specy-road"),
        pytest.param(_console_script("specyrd"), 1, id="specyrd"),
        pytest.param(lambda _: _start([sys.executable, "-m", "specy_road.cli", "--version"]), 1,
                     id="python-m-specy_road"),
        pytest.param(lambda _: _start([sys.executable, "-c", "import specy_road.cli"]), 1,
                     id="python-c-importing-specy_road"),
        pytest.param(
            lambda _: _start([sys.executable, "-P", "-c", "import importlib; "
                              "importlib.import_module('specy_road.cli')"]),
            1, id="python-c-importlib-specy_road",
        ),
        pytest.param(
            lambda _: _start([sys.executable, str(BUNDLED_SCRIPTS / "digest_cli.py"), "-h"]),
            1, id="bundled-script-file",
        ),
        pytest.param(lambda _: run_cli_subprocess(["--version"]), 1, id="tests-support-helper"),
        pytest.param(lambda _: _start(["git", "--version"]), 0, id="git"),
        pytest.param(
            lambda _: _start(
                [sys.executable, "-m", "specy_road.orchestration.workers.worker_runner"]
            ),
            0, id="worker_runner",
        ),
    ],
)
def test_each_cli_start_from_test_code_is_counted_once(
    tmp_path: Path, start: Callable[[Path], None], counted: int
) -> None:
    """Each spelling of a CLI start counts once, through a tests/support helper too; git and the
    worker wrapper do not count."""
    with recorded_starts() as starts:
        start(tmp_path)
    assert len(starts) == counted, starts


def test_every_bundled_script_runs_as_a_file() -> None:
    """``python <bundled script> --help`` exits 0 with its usage, so each ``__main__`` guard runs.

    Every other test calls a bundled script's ``main`` in process; this is where each still starts
    as the file a user's ``python`` would run.
    """
    scripts = sorted(
        p for p in BUNDLED_SCRIPTS.glob("*.py") if 'if __name__ == "__main__":' in p.read_text()
    )
    children = {
        p.name: subprocess.Popen(
            [sys.executable, str(p), "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=script_subprocess_env(),
        )
        for p in scripts
    }
    for name, child in children.items():
        out, err = child.communicate(timeout=120)
        assert child.returncode == 0 and "usage:" in out.lower(), f"{name}: {err}"


def test_every_package_module_imports_without_running_a_command() -> None:
    """A fresh interpreter imports every ``specy_road`` module, bundled scripts included, and
    prints nothing: importing a bundled script never runs its command.

    Every other test imports the package once per pytest process, during collection; this child
    is where each module's import runs inside a test.
    """
    code = (
        "import importlib, pkgutil, specy_road\n"
        "for module in pkgutil.walk_packages(specy_road.__path__, 'specy_road.'):\n"
        "    importlib.import_module(module.name)\n"
    )
    child = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=script_subprocess_env(),
        check=False,
    )
    assert (child.returncode, child.stdout, child.stderr) == (0, "", "")


_LISTED = ["tests/a/test_x.py::test_one", "tests/b/test_gone.py::test_two"]
_TWO, _THREE = _LISTED[1], "tests/b/test_gone.py::test_three"


@pytest.mark.parametrize(
    ("listed", "collected", "paths", "problems"),
    [
        pytest.param(_LISTED, {_LISTED[0]}, ["tests"],
                     [f"lists ids that are not collected: {[_LISTED[1]]}"], id="whole-file-absent"),
        pytest.param(_LISTED, {_LISTED[0], "tests/b/test_gone.py::test_other"}, ["tests"],
                     [f"lists ids that are not collected: {[_LISTED[1]]}"],
                     id="test-absent-file-present"),
        pytest.param(_LISTED, {_LISTED[0]}, ["tests/a"], [], id="file-outside-the-collected-paths"),
        pytest.param(_LISTED, set(), [_TWO],
                     [f"lists ids that are not collected: {[_LISTED[1]]}"], id="named-node-absent"),
        pytest.param([f"{_TWO}[1]"], set(), [_TWO],
                     [f"lists ids that are not collected: {[f'{_TWO}[1]']}"],
                     id="row-of-the-named-node-absent"),
        pytest.param(_LISTED, {_THREE}, [_THREE], [], id="other-node-of-the-file-not-checked"),
        pytest.param(_LISTED, set(_LISTED), ["tests"], [], id="all-collected"),
        pytest.param([_LISTED[0], _LISTED[0]], {_LISTED[0]}, ["tests"],
                     [f"lists ids more than once: {[_LISTED[0]]}"], id="duplicate-id"),
        pytest.param([f"tests/t.py::test_{n}" for n in range(MAX_ITEMS + 1)],
                     {f"tests/t.py::test_{n}" for n in range(MAX_ITEMS + 1)}, ["tests"],
                     [f"lists {MAX_ITEMS + 1} ids; at most {MAX_ITEMS}"], id="over-the-cap"),
    ],
)
def test_lane_problems_names_listed_ids_a_run_should_collect_but_does_not(
    tmp_path: Path, listed: list[str], collected: set[str], paths: list[str], problems: list[str]
) -> None:
    """A listed id is required when it lies under a selection: a path containing its file (even
    when nothing else from that file was collected), or a named node that is it, a row of it or
    contains it. An id outside every selection is not checked."""
    selections = [str(tmp_path / p) for p in paths]
    assert lane_problems(listed, collected, tmp_path, selections) == problems


_PY = sys.executable


@pytest.mark.parametrize(
    ("args", "counted"),
    [
        pytest.param([_PY, "-c", "print('specy_road')"], False, id="c-prints-the-name"),
        pytest.param([_PY, "-c", "# import specy_road"], False, id="c-comment"),
        pytest.param([_PY, "-c", "x = 'import specy_road'"], False, id="c-string-literal"),
        pytest.param([_PY, "-c", "import specy_roadx"], False, id="c-other-package"),
        pytest.param([_PY, "-c", "import specy_road ("], False, id="c-does-not-parse"),
        pytest.param([_PY, "-c", "from specy_road.cli import main"], True, id="c-from-import"),
        pytest.param([_PY, "-c", "__import__('specy_road.cli')"], True, id="c-dunder-import"),
        pytest.param([_PY, "-mspecy_road.cli"], True, id="m-joined"),
        pytest.param([_PY, "-cimport specy_road"], True, id="c-joined"),
        pytest.param([_PY, "-Im", "specy_road.cli"], True, id="combined-short-flags"),
        pytest.param([_PY, "-Xutf8", "-c", "import specy_road"], True, id="joined-X-value"),
        pytest.param(f"{_PY} -c 'import specy_road'", True, id="shell-string"),
        pytest.param(["python3.11", "-m", "specy_road.cli"], True, id="versioned-interpreter"),
        pytest.param(["python-config", "-c", "import specy_road"], False, id="not-an-interpreter"),
    ],
)
def test_starts_cli_reads_each_argv_shape(args: str | list[str], counted: bool) -> None:
    """``-c`` code counts only when it imports the package; short options may be joined or
    combined; a shell string is split as a shell would; only a Python interpreter's name counts."""
    assert starts_cli(args) is counted


_INNER_CONFTEST = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(REPO)!r})
from tests.support import cli_smoke_lane
cli_smoke_lane.LANE_FILE = Path(__file__).with_name("cli_smoke_lane.txt")
cli_smoke_lane.TESTS_DIR = Path(__file__).resolve().parent


def pytest_configure(config):
    cli_smoke_lane.install()
    config.pluginmanager.register(cli_smoke_lane, "cli_smoke_lane")
"""
_STARTS_CLI = (
    "import subprocess, sys\n\n\n"
    "def start():\n"
    "    subprocess.run([sys.executable, '-c', 'import specy_road'], check=True)\n"
)


def _inner_pytest(project: Path, files: dict[str, str], lane: list[str], *args: str) -> str:
    """Run pytest in ``project`` with this plugin loaded through its real hooks; its output."""
    project.mkdir(exist_ok=True)
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (project / "conftest.py").write_text(_INNER_CONFTEST, encoding="utf-8")
    (project / "cli_smoke_lane.txt").write_text("\n".join(lane) + "\n", encoding="utf-8")
    for name, text in files.items():
        (project / name).write_text(text, encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", f"cache_dir={project / '.cache'}", *args],
        cwd=project, env=script_subprocess_env(), capture_output=True, text=True, check=False,
    )
    return f"exit {run.returncode}\n{run.stdout}{run.stderr}"


@pytest.mark.parametrize("workers", ["0", "2"])
def test_an_unlisted_start_fails_its_item_and_a_listed_one_passes(
    tmp_path: Path, workers: str
) -> None:
    """Through the real hooks: the unlisted item that starts the CLI fails at teardown."""
    test = _STARTS_CLI + (
        "\n\ndef test_listed():\n    start()\n\n\ndef test_unlisted():\n    start()\n"
    )
    out = _inner_pytest(tmp_path, {"test_a.py": test}, ["test_a.py::test_listed"], "-n", workers)
    assert out.startswith("exit 1"), out
    assert "test_a.py::test_unlisted started the CLI as a child process" in out
    assert "test_a.py::test_listed started" not in out
    assert "2 passed, 1 error" in out


@pytest.mark.parametrize("workers", ["0", "2"])
def test_a_missing_listed_id_fails_a_run_that_deselects_the_first_item(
    tmp_path: Path, workers: str
) -> None:
    """The lane problem goes to the first item left after ``-k``, and is reported once."""
    test = "def test_first():\n    pass\n\n\ndef test_second():\n    pass\n"
    out = _inner_pytest(
        tmp_path, {"test_b.py": test}, ["test_b.py::test_gone"], "-n", workers, "-k", "not first"
    )
    assert out.startswith("exit 1"), out
    assert out.count("lists ids that are not collected: ['test_b.py::test_gone']") == 1, out


def test_a_tests_own_teardown_error_is_kept_beside_the_lane_messages(tmp_path: Path) -> None:
    """The item reporting a lane problem also gets its own unlisted-start check, and the error its
    fixture raised at teardown stays in the report."""
    test = (
        _STARTS_CLI + "import pytest\n\n\n" "@pytest.fixture\ndef breaks():\n    yield\n"
        "    raise RuntimeError('own teardown error')\n\n\ndef test_c(breaks):\n    start()\n"
    )
    out = _inner_pytest(tmp_path, {"test_c.py": test}, ["test_c.py::test_gone"], "-p", "no:xdist")
    assert out.startswith("exit 1"), out
    for text in ("own teardown error", "lists ids that are not collected",
                 "test_c.py::test_c started the CLI as a child process"):
        assert text in out, out


def test_last_failed_reports_no_false_missing_id(tmp_path: Path) -> None:
    """``--lf`` collects only the failed test; the listed test it drops is not reported."""
    test = "def test_ok():\n    pass\n\n\ndef test_bad():\n    assert False\n"
    files, lane = {"test_d.py": test}, ["test_d.py::test_ok"]
    assert _inner_pytest(tmp_path, files, lane, "-p", "no:xdist").startswith("exit 1")
    out = _inner_pytest(tmp_path, files, lane, "-p", "no:xdist", "--lf")
    assert "1 failed" in out and "not collected" not in out, out


@pytest.mark.parametrize("workers", ["0", "2"])
def test_collect_only_reports_a_missing_listed_id(tmp_path: Path, workers: str) -> None:
    """``--collect-only`` runs no teardown; it ends as a usage error naming the id."""
    out = _inner_pytest(
        tmp_path, {"test_e.py": "def test_here():\n    pass\n"}, ["test_e.py::test_gone"],
        "-n", workers, "--collect-only",
    )
    assert out.startswith("exit 4"), out
    assert "lists ids that are not collected: ['test_e.py::test_gone']" in out
