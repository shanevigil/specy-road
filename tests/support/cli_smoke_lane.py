"""The CLI smoke lane: the only test items allowed to start the CLI as a child process.

Every other CLI test calls it in this process (:func:`tests.support.cli.run_cli`), where coverage
contexts and mutation runs see the code the test exercises. ``tests/conftest.py`` loads this
module, which wraps :class:`subprocess.Popen` in each pytest process. An item is counted when test
code (the first frame above the start that lies in ``tests/`` or the package) starts a CLI
spelling (:func:`starts_cli`); a start made by package code (git, a worker child, the CLI's own
children) is not counted. A counted item not listed in ``cli_smoke_lane.txt`` fails at teardown;
a listed id the run does not collect although its file lies under a collected path, or a lane
over :data:`MAX_ITEMS` ids, fails the teardown of the first item collected (:func:`lane_problems`).
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import specy_road

LANE_FILE = Path(__file__).with_name("cli_smoke_lane.txt")
MAX_ITEMS = 50
TESTS_DIR = Path(__file__).resolve().parents[1]
PACKAGE_DIR = Path(specy_road.__file__).resolve().parent
#: Worker wrappers: ``-m`` modules that launch a harness, not a CLI command.
WORKER_MODULES = frozenset(
    {"specy_road.orchestration.workers.worker_runner", "specy_road.worker_runner"}
)
_BUNDLED_SCRIPT = re.compile(r"(?:^|[\\/])specy_road[\\/]bundled_scripts[\\/][^\\/]+\.py$")
_THIS_FILE = Path(__file__).resolve()

#: The starts recorded for the running item, last; :func:`recorded_starts` pushes another list.
_recording: list[list[list[str]]] = [[]]
_lock = threading.Lock()


def lane_ids() -> list[str]:
    """The node ids listed in ``cli_smoke_lane.txt`` (comments and blank lines skipped)."""
    lines = LANE_FILE.read_text(encoding="utf-8").splitlines()
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]


def starts_cli(argv: list[str]) -> bool:
    """Whether ``argv`` starts the CLI: one of the console scripts, ``python -m specy_road...``
    (but not a worker wrapper), ``python -c`` code naming the package (an ``import`` statement or
    an ``importlib`` call), or a bundled script file. Interpreter options before them (``-P``,
    ``-X utf8``) are skipped.
    """
    program = os.path.basename(argv[0]) if argv else ""
    if program in ("specy-road", "specyrd"):
        return True
    if not argv or not (program.startswith("python") or argv[0] == sys.executable):
        return False
    rest = argv[1:]
    while rest and rest[0].startswith("-") and rest[0] not in ("-m", "-c"):
        rest = rest[2:] if rest[0] in ("-X", "-W") else rest[1:]
    match rest:
        case ["-m", module, *_]:
            found = module.split(".")[0] == "specy_road" and module not in WORKER_MODULES
        case ["-c", code, *_]:
            found = "specy_road" in code
        case [path, *_]:
            found = bool(_BUNDLED_SCRIPT.search(path))
        case _:
            found = False
    return found


def _argv(args: object) -> list[str]:
    if isinstance(args, (str, bytes)):
        text = os.fsdecode(args)
        return text.split()
    return [os.fsdecode(a) if isinstance(a, bytes) else str(a) for a in args]


def _started_by_tests() -> bool:
    """Whether the first frame above the start in ``tests/`` or the package is test code."""
    frame = sys._getframe(2)
    while frame is not None:
        path = Path(frame.f_code.co_filename)
        if path.is_relative_to(PACKAGE_DIR):
            return False
        if path.is_relative_to(TESTS_DIR) and path != _THIS_FILE:
            return True
        frame = frame.f_back
    return False


_original_init = subprocess.Popen.__init__


def _counting_init(self: subprocess.Popen, args: object, *a: object, **kw: object) -> None:
    argv = _argv(args)
    if starts_cli(argv) and _started_by_tests():
        with _lock:
            _recording[-1].append(argv)
    _original_init(self, args, *a, **kw)


def install() -> None:
    """Wrap :class:`subprocess.Popen` so each CLI start from test code is recorded."""
    subprocess.Popen.__init__ = _counting_init


@contextmanager
def recorded_starts() -> Iterator[list[list[str]]]:
    """The CLI starts made inside the block, kept apart from the running item's own count."""
    _recording.append([])
    try:
        yield _recording[-1]
    finally:
        _recording.pop()


#: Lane problems (:func:`lane_problems`), by the node id of the item whose teardown reports them.
_lane_errors: dict[str, str] = {}


def lane_problems(
    listed: list[str], collected: set[str], rootdir: Path, collect_paths: list[Path]
) -> list[str]:
    """What is wrong with the lane ``listed`` for a run that collected ``collected``.

    One rule for listed ids: an id must be collected when its file lies under a path the run
    collects (``collect_paths``: the command-line paths, or ``testpaths`` when none is given),
    whether or not anything else from that file was collected, so a deleted or renamed file is
    caught as well as a deleted or renamed test. A listed file outside every collected path is
    not checked. Separately, the lane may hold at most :data:`MAX_ITEMS` ids.
    """
    problems = [f"lists {len(listed)} ids; at most {MAX_ITEMS}"] if len(listed) > MAX_ITEMS else []
    roots = [path.resolve() for path in collect_paths]
    files = {nodeid: (rootdir / nodeid.split("::", 1)[0]).resolve() for nodeid in listed}
    missing = [
        nodeid for nodeid, file in files.items()
        if nodeid not in collected and any(file.is_relative_to(root) for root in roots)
    ]
    if missing:
        problems.append(f"lists ids that are not collected: {missing}")
    return problems


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Record :func:`lane_problems` on the first item collected, whose teardown reports them.

    With xdist every worker collects the same items, so whichever runs that item reports them.
    A run that names node ids (``file::test``) collects part of a file and is not checked.
    """
    if not items or any("::" in arg for arg in config.args):
        return
    paths = [config.invocation_params.dir / arg for arg in config.args]
    problems = lane_problems(lane_ids(), {i.nodeid for i in items}, config.rootpath, paths)
    if problems:
        _lane_errors[items[0].nodeid] = "; ".join(problems)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Iterator[None]:
    """Count the item's starts from its first setup to its last teardown."""
    _recording[-1].clear()
    yield
    _recording[-1].clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    """Fail the teardown of an item that started the CLI but is not in the smoke lane, and of the
    item that reports a lane-file problem."""
    outcome = yield
    report = outcome.get_result()
    if call.when != "teardown":
        return
    if item.nodeid in _lane_errors:
        report.outcome = "failed"
        report.longrepr = f"tests/support/{LANE_FILE.name} {_lane_errors[item.nodeid]}"
        return
    starts = _recording[-1]
    if not starts or item.nodeid in _lane():
        return
    report.outcome = "failed"
    report.longrepr = (
        f"{item.nodeid} started the CLI as a child process ({' '.join(starts[0][:4])} ...) "
        f"but is not in tests/support/{LANE_FILE.name}: call it in process with "
        "tests.support.cli.run_cli or run_main"
    )


@functools.cache
def _lane() -> frozenset[str]:
    return frozenset(lane_ids())
