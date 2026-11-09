"""`specy-road upgrade` never rewrites constraints/file-limits.yaml; it names the default once."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts.upgrade import run_upgrade
from tests.upgrade_repo_helpers import old_repo

RC3_CONSUMER = Path(__file__).parent / "parity" / "fixtures" / "rc3_consumer"
NOTICE = (
    "constraints/file-limits.yaml caps files at 400 lines with no warning; the template default"
    " is now 1000 lines with a warning at 750. upgrade leaves this file as it is; edit it to adopt"
    " the default."
)


@pytest.mark.parametrize(("project_file", "notice"), [
    ("rc3", True),         # 400 lines, no warning: as 0.3.1rc3's init project wrote it
    ("template", False),   # what init project writes now
    ("absent", False),
])
def test_upgrade_names_the_new_default_and_leaves_the_file(
    tmp_path: Path, capsys, project_file: str, notice: bool,
) -> None:
    root = old_repo(tmp_path)
    limits = root / "constraints" / "file-limits.yaml"
    if project_file == "rc3":
        limits.write_bytes((RC3_CONSUMER / "constraints" / "file-limits.yaml").read_bytes())
    elif project_file == "absent":
        limits.unlink()
    before = limits.read_bytes() if limits.exists() else None

    assert run_upgrade(root) == 0

    out = capsys.readouterr().out
    assert (NOTICE in out.splitlines()) is notice
    assert out.count("== file-limits default") == int(notice)
    assert (limits.read_bytes() if limits.exists() else None) == before
