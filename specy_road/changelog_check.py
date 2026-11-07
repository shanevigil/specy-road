"""Whether ``specy-road ready`` should remind the executor about ``CHANGELOG.md``.

The decision is :func:`missing_entry_warning`. Callers supply the diff and the
changelog text; this module does not run git.
"""

from __future__ import annotations

from specy_road.review_gate_ready import is_trial_merge_bookkeeping

_UNRELEASED = "## [Unreleased]"
_EXEMPT = "no changelog entry"
_SHOWN = 3


def missing_entry_warning(
    changed: list[str], prefix: str, base_text: str, head_text: str, exempt_text: str,
) -> str | None:
    """One warning line, or None when the branch needs no CHANGELOG reminder.

    ``changed`` paths are git-root relative. ``prefix`` is ``project_prefix``
    (``sr/`` or ``""``). ``base_text`` is ``CHANGELOG.md`` at the merge base, empty
    when that file is absent, and an absent heading there counts as an empty section.
    ``head_text`` is ``CHANGELOG.md`` at HEAD: no file or no ``## [Unreleased]`` heading
    returns None. The section is the lines after that heading up to the next ``## ``
    heading; an edited line keeps the non-blank count, so it still warns. ``exempt_text``
    is the leaf's acceptance plus its planning sheet; ``no CHANGELOG entry`` in any case
    returns None.
    """
    if _EXEMPT in exempt_text.lower():
        return None
    head = _unreleased_nonblank(head_text)
    if head is None:
        return None
    base = _unreleased_nonblank(base_text)
    if head > (0 if base is None else base):
        return None
    products = [path for path in changed if _product(path, prefix)]
    if not products:
        return None
    names = ", ".join(products[:_SHOWN])
    return (
        "warning: ## [Unreleased] in CHANGELOG.md gained no line, but this branch changes "
        f"{names}; write `no CHANGELOG entry` in the leaf's acceptance or planning sheet to exempt it"
    )


def _unreleased_nonblank(text: str) -> int | None:
    """Non-blank lines under ``## [Unreleased]`` until the next ``## `` heading, or None."""
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if _unreleased_heading(line)), None)
    if start is None:
        return None
    count = 0
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            count += 1
    return count


def _unreleased_heading(line: str) -> bool:
    rest = line[len(_UNRELEASED):] if line.startswith(_UNRELEASED) else None
    return rest is not None and not rest.strip()


def _product(path: str, prefix: str) -> bool:
    """True for a changed path that is not ``CHANGELOG.md``, ``tests/``, or project bookkeeping.

    In a nested layout (non-empty ``prefix``) bookkeeping is every path under the project
    directory. Otherwise it is :func:`is_trial_merge_bookkeeping`.
    """
    if path == "CHANGELOG.md" or path == "tests" or path.startswith("tests/"):
        return False
    if prefix:
        return not path.startswith(prefix)
    return not is_trial_merge_bookkeeping(path)
