#!/usr/bin/env python3
"""Strip the README pre-release notice + TODO + swap install block.

Run after the FIRST PyPI publish of a final release (v0.1.0+). Mutates
README.md in place. Idempotent: re-running is a no-op.

Usage:
    python scripts/post_release_readme_cleanup.py <version>

The release-publish workflow calls this from a checkout of `dev`,
then opens a PR with the resulting changes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

README = Path("README.md")

PRE_RELEASE_BLOCK_RE = re.compile(
    r"\n> ## ⚠️ Pre-release notice\n(?:> .*\n)*\n",
    re.MULTILINE,
)

TODO_COMMENT_RE = re.compile(
    r"<!--\s*\n?TODO\(post-release\):.*?-->\s*\n*",
    re.DOTALL,
)

INSTALL_BLOCK_OLD_RE = re.compile(
    r"## Install\n\n.*?```bash\n"
    r"git clone https://github\.com/shanevigil/specy-road\.git\n.*?```\n",
    re.DOTALL,
)

INSTALL_BLOCK_NEW = """## Install

Requires **Python 3.11+** and **git** (with a configured remote — `origin`
by default).

```bash
pip install specy-road
# optional extras:
#   pip install "specy-road[gui-next]"  # PM Gantt UI deps
#   pip install "specy-road[review]"    # LLM review (`specy-road review-node`)
```

The full install + everyday usage guide is at
**[docs/install-and-usage.md](docs/install-and-usage.md)**. Building from
source is documented in
**[docs/contributor-guide.md](docs/contributor-guide.md)**.
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: post_release_readme_cleanup.py <version>", file=sys.stderr)
        return 2
    version = argv[1]
    if not README.is_file():
        print(f"error: {README} not found", file=sys.stderr)
        return 1

    original = README.read_text(encoding="utf-8")
    text = original

    # 1. Strip the pre-release blockquote, if present.
    text = PRE_RELEASE_BLOCK_RE.sub("\n", text)

    # 2. Strip the TODO(post-release) HTML comment at the top.
    text = TODO_COMMENT_RE.sub("", text)

    # 3. Replace the install block.
    if INSTALL_BLOCK_OLD_RE.search(text):
        text = INSTALL_BLOCK_OLD_RE.sub(INSTALL_BLOCK_NEW, text)

    # 4. Collapse any leading blank lines that resulted from stripping.
    text = re.sub(r"^\s+", "", text)
    if not text.endswith("\n"):
        text += "\n"

    if text == original:
        print(f"ok: README already cleaned (idempotent); no changes for v{version}.")
        return 0

    README.write_text(text, encoding="utf-8")
    print(f"ok: README post-release cleanup applied for v{version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
