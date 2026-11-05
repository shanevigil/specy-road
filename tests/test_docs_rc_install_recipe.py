"""No doc installs a release candidate with TestPyPI as one index and a second index beside it.

With both indexes the resolver may take any dependency from TestPyPI, where names can be
squatted; the supported recipe downloads only the pinned wheel (docs/install-and-usage.md).

The gate does not parse Markdown structure (fences, quotes, lists, HTML blocks): it checks
every line of every doc. A doc that shows the unsafe form on purpose, as a warning, puts
``<!-- unsafe-example -->`` on that line or the line just above it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOW = "<!-- unsafe-example -->"
_PREFIX = re.compile(r"^(?:\s+|>|[-*+](?=\s)|\d+[.)](?=\s))")
_INDEX_FLAG = re.compile(r"(?<![\w-])(?:--extra-index-url|--index-url|-i)(?![\w-])")


def _strip_prefix(line: str) -> str:
    """Drop leading indentation, blockquote markers (any depth) and list markers."""
    while (match := _PREFIX.match(line)) is not None:
        line = line[match.end():]
    return line


def _logical_lines(text: str) -> list[tuple[int, str, bool]]:
    """(first line number, joined text, allowed) per logical line; backslash continuations joined."""
    raw = text.splitlines()
    out: list[tuple[int, str, bool]] = []
    start, pending, allowed = 0, "", False
    for number, line in enumerate(raw):
        if not pending:
            start = number
            allowed = number > 0 and ALLOW in raw[number - 1]
        allowed = allowed or ALLOW in line
        body = _strip_prefix(line).rstrip()
        if body.endswith("\\"):
            pending += body[:-1] + " "
            continue
        out.append((start + 1, pending + body, allowed))
        pending = ""
    if pending:
        out.append((start + 1, pending, allowed))
    return out


def _two_index_testpypi(line: str) -> bool:
    """TestPyPI named on a line that also passes a second index flag, in either order."""
    return "test.pypi.org" in line and len(_INDEX_FLAG.findall(line)) >= 2


def _offenders(text: str) -> list[str]:
    return [f"{number}: {line}" for number, line, allowed in _logical_lines(text)
            if not allowed and _two_index_testpypi(line)]


_UNSAFE = ("pip install --index-url https://test.pypi.org/simple/ \\\n"
           "    --extra-index-url https://pypi.org/simple/ \\\n    \"specy-road==0.3.1rc1\"")


def test_the_detector_flags_the_two_index_form_wherever_it_sits() -> None:
    cases = {
        "original": f"```bash\n{_UNSAFE}\n```\n",
        "short_flag_indented_fence": "   ```bash\n   pip install -i https://test.pypi.org/simple/ "
                                     "--extra-index-url https://pypi.org/simple/ x\n   ```\n",
        "nested_fence": f"````markdown\nSmoke install:\n\n```bash\n{_UNSAFE}\n```\n````\n",
        "blockquote": "> ```bash\n> pip install --index-url=https://test.pypi.org/simple/ "
                      "--extra-index-url=https://pypi.org/simple/ specy-road==0.3.1rc1\n> ```\n",
        "blockquote_continuation": "> > ```bash\n> > pip install --index-url https://test.pypi.org/simple/ \\\n"
                                   "> >     --extra-index-url https://pypi.org/simple/ x\n> > ```\n",
        "list_item": "1. Install:\n\n   ```bash\n   " + _UNSAFE.replace("\n", "\n   ") + "\n   ```\n"
                     "- pip install -i https://pypi.org/simple/ --extra-index-url https://test.pypi.org/simple/ x\n",
        "prose": "Run `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ x`.\n",
    }
    missed = [name for name, text in cases.items() if not _offenders(text)]
    assert missed == []


def test_the_recipe_and_a_marked_warning_pass() -> None:
    recipe = "```bash\npip download --no-deps -d rc/ \\\n    --index-url https://test.pypi.org/simple/ \"specy-road==1rc1\"\n" \
             "pip install --no-deps rc/specy_road-1rc1-py3-none-any.whl\n```\n"
    prose = "Never pair TestPyPI as `--index-url` with PyPI as `--extra-index-url`.\n"
    marked_above = f"Do not do this:\n\n{ALLOW}\n{_UNSAFE}\n"
    marked_inline = f"- `pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ x` {ALLOW}\n"
    assert _offenders(recipe + prose + marked_above + marked_inline) == []
    # The marker covers only the line below it, not a later one.
    assert _offenders(f"{ALLOW}\n\n{_UNSAFE}\n")


def test_no_doc_installs_from_testpypi_with_an_extra_index() -> None:
    docs = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]
    offenders = [f"{path.relative_to(REPO)}:{hit}"
                 for path in docs
                 for hit in _offenders(path.read_text(encoding="utf-8"))]
    assert offenders == [], ("use the download-check-install RC recipe, or mark a deliberate warning with "
                             f"{ALLOW}:\n" + "\n".join(offenders))
