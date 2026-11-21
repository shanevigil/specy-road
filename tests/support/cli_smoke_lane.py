"""The CLI smoke lane: the only test items allowed to start the CLI as a child process.

Every other CLI test calls it in this process (:func:`tests.support.cli.run_cli`), where coverage
contexts and mutation runs see the code the test exercises. ``tests/conftest.py`` loads this
module, which wraps :class:`subprocess.Popen` in each pytest process. An item is counted when test
code (the first frame above the start that lies in ``tests/`` or the package) starts a CLI
spelling (:func:`starts_cli`); a start made by package code (git, a worker child, the CLI's own
children) is not counted. A counted item not listed in ``cli_smoke_lane.txt`` fails at teardown.
A lane problem (:func:`lane_problems`: a listed id the run selects but does not collect, a
duplicate id, more than :data:`MAX_ITEMS` ids) fails the teardown of the first item left after
deselection, or a ``--collect-only`` run. A teardown failure keeps the test's own error text and
adds the lane message after it.

Limits: only the four spellings of :func:`starts_cli` are counted; any other way of reaching the
CLI (another launcher such as ``py`` or ``uv run``, ``os.system``, ``os.exec*``,
``multiprocessing``, a shell string that runs ``cd x && ...``) is not. A start in a module- or
session-scoped fixture's teardown, or from a background thread
left running by an earlier test, is charged to the item running at that moment; Windows-only
spellings (``specy-road.exe``, ``py -m``) are matched by name only; a selected file that collects
no item, or a run whose deselection leaves no item, is not checked; under ``--lf`` with
recorded failures the missing-id check is skipped, because the last-failed plugin drops items
before this module sees them. Counting never stops a child from starting: a start the counting
cannot read is not counted, and the real ``Popen.__init__`` runs once, after it.
"""

from __future__ import annotations

import ast
import functools
import os
import re
import shlex
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
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
_PYTHON = re.compile(r"python(\d+(\.\d+t?)?)?(\.exe)?")
#: The interpreter's long options that take a value as the next word.
_LONG_OPTIONS_WITH_VALUE = frozenset({"--check-hash-based-pycs"})

#: The running item's starts first, then one list per open :func:`recorded_starts` block; a start
#: is added to every list.
_recording: list[list[list[str]]] = [[]]
_lock = threading.Lock()


def lane_ids() -> list[str]:
    """The node ids listed in ``cli_smoke_lane.txt`` (comments and blank lines skipped)."""
    lines = LANE_FILE.read_text(encoding="utf-8").splitlines()
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]


def starts_cli(args: str | bytes | Sequence[str | bytes]) -> bool:
    """Whether the child ``args`` (as :class:`subprocess.Popen` takes them; a string is split as
    a shell would) starts the CLI: one of the console scripts; a Python interpreter (``python``,
    ``pythonN``, ``pythonN.M``, free-threaded ``pythonN.Mt``, optionally ``.exe``, or this
    interpreter) running ``-m`` on a ``specy_road`` module other than a worker wrapper, ``-c``
    code that imports ``specy_road`` (:func:`imports_package`), or a bundled script file. Short
    options may be combined or joined to their value (``-Im specy_road``, ``-mspecy_road``,
    ``-cimport specy_road``).
    """
    argv = _argv(args)
    program = os.path.basename(argv[0]) if argv else ""
    if program in ("specy-road", "specyrd"):
        return True
    if not argv or not (_PYTHON.fullmatch(program) or argv[0] == sys.executable):
        return False
    match _interpreter_target(argv[1:]):
        case ("-m", module):
            found = module.split(".")[0] == "specy_road" and module not in WORKER_MODULES
        case ("-c", code):
            found = imports_package(code)
        case ("script", path):
            found = bool(_BUNDLED_SCRIPT.search(path))
        case _:
            found = False
    return found


def _interpreter_target(args: list[str]) -> tuple[str, str] | None:
    """What a Python command line runs: ``("-m", module)``, ``("-c", code)``,
    ``("script", path)``, or None. Short options are read one letter at a time; ``-X`` and ``-W``
    take a value, and so does ``--check-hash-based-pycs``."""
    rest = list(args)
    while rest and rest[0].startswith("-") and rest[0] != "-":
        token = rest.pop(0)
        if token.startswith("--"):
            if token in _LONG_OPTIONS_WITH_VALUE and rest:
                rest.pop(0)
            continue
        for i, letter in enumerate(token[1:], start=2):
            if letter in "mcXW":
                value = token[i:] or (rest.pop(0) if rest else "")
                if letter in "mc":
                    return f"-{letter}", value
                break
    return ("script", rest[0]) if rest else None


def imports_package(code: str) -> bool:
    """Whether Python ``code`` imports ``specy_road``: an ``import`` or ``from ... import`` of it
    or a submodule, or ``__import__`` / ``importlib.import_module`` called with a string naming
    one. Code that does not parse imports nothing."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Call) and _is_import_call(node.func) and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.append(first.value)
    return any(name.split(".")[0] == "specy_road" for name in names)


def _is_import_call(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id in ("__import__", "import_module")
    return isinstance(func, ast.Attribute) and func.attr == "import_module"


def _argv(args: object) -> list[str]:
    """``args`` as a list of words. A path-like is one word, and path-like items are words; a
    string is split as a shell would, or on whitespace when it is not valid shell-word syntax for
    :mod:`shlex` (``echo hi # don't``: an unbalanced quote)."""
    if isinstance(args, os.PathLike):
        return [os.fsdecode(args)]
    if isinstance(args, (str, bytes)):
        text = os.fsdecode(args)
        try:
            return shlex.split(text)
        except ValueError:
            return text.split()
    return [os.fsdecode(a) if isinstance(a, (bytes, os.PathLike)) else str(a) for a in args]


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
    """Record the start if it counts (:func:`_record`), then start the child, once."""
    _record(args)
    _original_init(self, args, *a, **kw)


def _record(args: object) -> None:
    """Add ``args`` to every open record when it starts the CLI from test code.

    Any error here means the start is not counted; it never reaches the caller, whose child
    starts as it would without this module.
    """
    try:
        argv = _argv(args)
        if starts_cli(argv) and _started_by_tests():
            with _lock:
                for record in _recording:
                    record.append(argv)
    except Exception:   # a start the counting cannot read is not counted
        return


def install() -> None:
    """Wrap :class:`subprocess.Popen` so each CLI start from test code is recorded."""
    subprocess.Popen.__init__ = _counting_init


@contextmanager
def recorded_starts() -> Iterator[list[list[str]]]:
    """The CLI starts made inside the block. They count for the running item too, like any other."""
    _recording.append([])
    try:
        yield _recording[-1]
    finally:
        _recording.pop()


#: Lane problems (:func:`lane_problems`) found when the run collected; reported by the first item
#: left after deselection (its node id is the key once known) or by a ``--collect-only`` run.
_lane_errors: dict[str, str] = {}
_pending: list[str] = []


def lane_problems(
    listed: list[str], collected: set[str], rootdir: Path, selections: list[str]
) -> list[str]:
    """What is wrong with the lane ``listed`` for a run that collected ``collected``.

    One rule for listed ids: an id must be collected when it lies under something the run selects
    (``selections``: the command-line arguments, or ``testpaths`` when none is given, each an
    absolute path with an optional ``::`` node part). It lies under a selection when its file is
    the selected path or inside it and, if the selection names a node, the id is that node, one
    of its parametrized rows (``node[...]``) or a member of it (``node::...``). So a deleted or
    renamed file, test or row is caught by a full run, a directory or file run and a run naming
    that test alike. A listed id outside every selection is not checked. Separately, an id may
    be listed once, and the lane may hold at most :data:`MAX_ITEMS` ids.
    """
    problems = [f"lists {len(listed)} ids; at most {MAX_ITEMS}"] if len(listed) > MAX_ITEMS else []
    duplicates = sorted({nodeid for nodeid in listed if listed.count(nodeid) > 1})
    if duplicates:
        problems.append(f"lists ids more than once: {duplicates}")
    missing = [
        nodeid for nodeid in dict.fromkeys(listed)
        if nodeid not in collected and any(_selects(s, rootdir, nodeid) for s in selections)
    ]
    if missing:
        problems.append(f"lists ids that are not collected: {missing}")
    return problems


def _selects(selection: str, rootdir: Path, nodeid: str) -> bool:
    """Whether ``selection`` (an absolute path, optionally ``::node``) selects ``nodeid``."""
    path, _, node = selection.partition("::")
    file, _, name = nodeid.partition("::")
    if not (rootdir / file).resolve().is_relative_to(Path(path).resolve()):
        return False
    return not node or name == node or name.startswith((f"{node}[", f"{node}::"))


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Find the lane problems against every collected item, before ``-k``, ``-m`` or
    ``--deselect`` drop any. Under ``--lf`` with recorded failures only the duplicate and cap
    checks run; with none, ``--lf`` runs every test and the missing-id check runs too."""
    selections = [str(config.invocation_params.dir / arg) for arg in config.args]
    if config.getoption("lf", False) and config.cache and config.cache.get("cache/lastfailed", {}):
        selections = []
    collected = {item.nodeid for item in items}
    _pending[:] = lane_problems(lane_ids(), collected, config.rootpath, selections)


class AfterDeselection:
    """The plugin that hands lane problems to the first item left after deselection."""

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        """That item's teardown reports them. With xdist every worker collects and deselects the
        same items, so whichever runs that item reports them, once."""
        if _pending and items:
            _lane_errors[items[0].nodeid] = "; ".join(_pending)


def pytest_configure(config: pytest.Config) -> None:
    """Register :class:`AfterDeselection` beside this module."""
    config.pluginmanager.register(AfterDeselection(), "cli_smoke_lane_after_deselection")


def pytest_collection_finish(session: pytest.Session) -> None:
    """A ``--collect-only`` run runs no teardown: it reports lane problems as a usage error.

    xdist does not distribute a collect-only run, so this is the one process that collected.
    """
    if session.config.option.collectonly and _pending:
        raise pytest.UsageError(f"tests/support/{LANE_FILE.name} " + "; ".join(_pending))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Iterator[None]:
    """Count the item's starts from its first setup to its last teardown."""
    _recording[0].clear()
    yield
    _recording[0].clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    """Fail the teardown of an item that started the CLI but is not in the smoke lane, and of the
    item that reports lane problems; a test's own teardown failure stays, the lane text after it."""
    outcome = yield
    report = outcome.get_result()
    if call.when != "teardown":
        return
    messages = []
    if item.nodeid in _lane_errors:
        messages.append(f"tests/support/{LANE_FILE.name} {_lane_errors[item.nodeid]}")
    starts = _recording[0]
    if starts and item.nodeid not in _lane():
        messages.append(
            f"{item.nodeid} started the CLI as a child process ({' '.join(starts[0][:4])} ...) "
            f"but is not in tests/support/{LANE_FILE.name}: call it in process with "
            "tests.support.cli.run_cli or run_main"
        )
    if messages:
        own = [str(report.longrepr)] if report.failed and report.longrepr else []
        report.outcome = "failed"
        report.longrepr = "\n\n".join(own + messages)


@functools.cache
def _lane() -> frozenset[str]:
    return frozenset(lane_ids())
