"""Help text names only what a pip install has.

The rc4 clean-VM rehearsal read help written for a source checkout: ``python
specy_road/bundled_scripts/...`` paths, ``usage: roadmap_crud.py ...`` lines and
``docs/*.md`` files a wheel does not ship. Every command's help is scanned here.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from specy_road.cli import registered_agent_command_names
from specy_road.doc_links import SHIPPED_DOCS
from tests.helpers import script_subprocess_env

_DOC_REF = re.compile(r"(?<![\w/.-])docs/([\w-]+\.md)")
_PY_FILE = re.compile(r"[\w/.-]+\.py\b")

_ROWS = [["--help"]] + [
    ["orchestration", "guard", "-h"] if name == "orchestration" else [name, "-h"]
    for name in sorted(registered_agent_command_names()["specy-road"] - {"version"})
]


def _help(args: list[str], cwd) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args],
        cwd=cwd,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.parametrize("args", _ROWS, ids=" ".join)
def test_help_names_installed_commands(args: list[str], tmp_path) -> None:
    out = _help(args, tmp_path)
    usage = next(ln for ln in out.splitlines() if ln.lower().startswith("usage:"))
    assert usage.lower().startswith("usage: specy-road"), usage
    assert "bundled_scripts/" not in out
    for line in out.splitlines():
        if line.lower().startswith("usage:") or re.search(r"\bpython3?\s", line):
            assert not _PY_FILE.search(line), line
    bare = [m.group(0) for m in _DOC_REF.finditer(out) if m.group(1) not in SHIPPED_DOCS]
    assert bare == []


def test_top_level_help_names_canonical_commands(tmp_path) -> None:
    out = _help(["--help"], tmp_path)
    for want in (
        "specy-road init gui --install-gui",
        "pip install 'specy-road[gui-next]'",
        "specy-road add-node -h",
        "specy-road scaffold-planning -h",
    ):
        assert want in out
    assert "specy-road init --install-gui" not in out
