"""The CLI must import with only the base install's dependencies.

``fastapi`` ships with the ``gui-next`` extra, not the base package, but a
development checkout always has it — so a CLI module that reaches into the
GUI package imports fine here and dies with ``ModuleNotFoundError`` on a
plain ``pip install specy-road``. These tests re-run the import with the
GUI-only distributions hidden, which is the only way that shows up before a
user hits it.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

#: Distributions that only arrive with an extra. A CLI-reachable module that
#: imports any of these is broken for the base install.
_EXTRA_ONLY = ("fastapi", "starlette", "uvicorn", "openai", "anthropic")

#: Every module the bare CLI can reach. `brainstorm_cli` is the one that
#: regressed: it pulled `next_child_id` from the GUI's helper module.
_CLI_MODULES = [
    "specy_road.cli",
    "specy_road.bundled_scripts.brainstorm_cli",
    "specy_road.bundled_scripts.brainstorm_cli_args",
    "specy_road.bundled_scripts.brainstorm_promote",
    "specy_road.bundled_scripts.brainstorm_session",
    "specy_road.bundled_scripts.brainstorm_prompt",
    "specy_road.bundled_scripts.roadmap_crud",
    "specy_road.bundled_scripts.roadmap_move_node",
]

_BLOCKER = """
import sys

class _Blocked:
    def find_module(self, name, path=None):
        return None
    def find_spec(self, name, path=None, target=None):
        root = name.split(".")[0]
        if root in {blocked!r}:
            raise AssertionError(
                "import of extra-only module '" + name + "' on the base install"
            )
        return None

sys.meta_path.insert(0, _Blocked())
import importlib
importlib.import_module({module!r})
"""


@pytest.mark.parametrize("module", _CLI_MODULES)
def test_cli_module_imports_without_extras(module: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _BLOCKER.format(blocked=set(_EXTRA_ONLY), module=module)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{module} does not import on a base install:\n{proc.stderr}"
    )
