"""No doc installs a release candidate with TestPyPI as the index and PyPI as an extra index.

With both indexes the resolver may take any dependency from TestPyPI, where names can be
squatted; the supported recipe downloads only the pinned wheel (docs/install-and-usage.md).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_FENCE = re.compile(r"^\s*(```|~~~)")
_TESTPYPI_INDEX = re.compile(r"(?:--index-url|-i)(?:\s+|=)\S*test\.pypi\.org")


def _fenced_commands(text: str) -> list[str]:
    """Logical lines inside code fences, with backslash continuations joined."""
    commands: list[str] = []
    fence: str | None = None
    pending = ""
    for line in text.splitlines():
        match = _FENCE.match(line)
        if match and (fence is None or match.group(1) == fence):
            fence = match.group(1) if fence is None else None
            pending = ""
            continue
        if fence is None:
            continue
        stripped = line.strip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        commands.append(pending + stripped)
        pending = ""
    return commands


def _two_index_testpypi(command: str) -> bool:
    return bool(_TESTPYPI_INDEX.search(command)) and "--extra-index-url" in command


def test_the_detector_flags_the_two_index_form_and_passes_the_recipe() -> None:
    old = "```bash\npip install --index-url https://test.pypi.org/simple/ \\\n" \
          "    --extra-index-url https://pypi.org/simple/ \\\n    \"specy-road==0.3.1rc1\"\n```\n"
    short = "   ```bash\n   pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ x\n   ```\n"
    recipe = "```bash\npip download --no-deps -d rc/ \\\n    --index-url https://test.pypi.org/simple/ \"specy-road==1rc1\"\n" \
             "pip install --no-deps rc/specy_road-1rc1-py3-none-any.whl\n```\n"
    prose = "Never pair `--index-url https://test.pypi.org/simple/` with `--extra-index-url`.\n"
    assert [c for c in _fenced_commands(old) if _two_index_testpypi(c)]
    assert [c for c in _fenced_commands(short) if _two_index_testpypi(c)]
    assert not [c for c in _fenced_commands(recipe + prose) if _two_index_testpypi(c)]


def test_no_doc_installs_from_testpypi_with_an_extra_index() -> None:
    docs = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]
    offenders = [f"{path.relative_to(REPO)}: {command}"
                 for path in docs
                 for command in _fenced_commands(path.read_text(encoding="utf-8"))
                 if _two_index_testpypi(command)]
    assert offenders == [], "use the download-check-install RC recipe instead:\n" + "\n".join(offenders)
