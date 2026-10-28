"""Point shipped skills and blocks at the toolkit docs they cite.

The skill templates and the ``AGENTS.md`` block say "see ``docs/X.md``", but
``docs/`` is the toolkit's, not the consumer's: ``init project`` ships only
``docs/supply-chain-security.md``. In a consumer repo every other reference
named a file that does not exist (rc1 feedback: ``docs/brainstorming.md``).
Rendering rewrites each one to the toolkit's GitHub copy at the installed
version's tag, so the doc matches the CLI that wrote the skill.
"""

from __future__ import annotations

import re

from specy_road import __version__

DOCS_URL = "https://github.com/shanevigil/specy-road/blob/{ref}/docs/{name}"

#: Docs ``init project`` copies into the consumer repo; those references stay local.
SHIPPED_DOCS = frozenset({"supply-chain-security.md"})

_DOC_REF = re.compile(r"(?<![\w/.-])docs/([\w-]+\.md)")
_RELEASE = re.compile(r"^(\d+\.\d+\.\d+)(?:(rc)(\d+))?$")


def docs_ref(version: str = __version__) -> str:
    """The git tag for a release (``0.3.1rc1`` → ``v0.3.1-rc1``), else ``main``."""
    m = _RELEASE.match(version)
    if m is None:
        return "main"
    base, rc, n = m.groups()
    return f"v{base}-rc{n}" if rc else f"v{base}"


def link_toolkit_docs(text: str, version: str = __version__) -> str:
    """Rewrite each ``docs/<name>.md`` the consumer does not have into a toolkit URL."""
    ref = docs_ref(version)

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        return m.group(0) if name in SHIPPED_DOCS else DOCS_URL.format(ref=ref, name=name)

    return _DOC_REF.sub(sub, text)
