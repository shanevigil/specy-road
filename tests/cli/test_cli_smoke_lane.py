"""The CLI smoke lane (tests/support/cli_smoke_lane.py): which child starts it counts, and the
bundled scripts it still runs as files."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, script_subprocess_env
from tests.support.cli import run_cli_subprocess
from tests.support.cli_smoke_lane import MAX_ITEMS, lane_problems, recorded_starts


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
