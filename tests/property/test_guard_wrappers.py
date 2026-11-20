"""Wrapping a guard case in wrappers and enclosing forms keeps its classify result.

``tests/unit/test_tool_call_guard.py::test_wrappers_keep_the_bare_verdict_and_reason`` checks
every single wrapper exhaustively. This property checks composition: for every classify-only case
of the guard tests, 0 to 2 prefix wrappers, each the bare or path-qualified name of a wrapper the
classifier unwraps with one of its options (a value where it takes one) or a ``NAME=value``
assignment in front, then 0 to 2 enclosing forms, give the same reason (or ``None``) as the bare
command.

Domain limits (stated, not counterexamples): no prefix wrapper before a case that starts with
``(`` (a bash syntax error); no enclosing form around a case whose bare reason is an unparseable
or unbalanced shape (wrapping changes the parse); ``env`` split-string spellings stay with the
enumerated test, because a split string re-tokenizes shell syntax by design.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from specy_road.orchestration.guard.tool_call_guard import classify
from tests.support.guard_cases import CLASSIFY_CASES, PATH_PREFIXES, WRAPPER_SPELLINGS

#: The bare reasons whose shape a wrapper or enclosing form would re-parse.
UNPARSEABLE = ("could not parse", "unbalanced")

ENCLOSING = (
    lambda c: f"({c})",
    lambda c: f"! {c}",
    lambda c: "{ " + c + "; }",
    lambda c: f"if true; then {c}; fi",
)


@st.composite
def prefix_wrapper(draw: st.DrawFn) -> str:
    """One wrapper word, bare or path-qualified, with an option or an assignment in front."""
    name, gap, spellings = draw(st.sampled_from(WRAPPER_SPELLINGS))
    word = draw(st.sampled_from(("", *PATH_PREFIXES))) + name
    if draw(st.booleans()):
        return f"{word} {draw(st.sampled_from(spellings))} {gap}"
    return f"FOO=1 {word} {gap}"


@pytest.mark.parametrize("command", CLASSIFY_CASES)
@given(
    prefixes=st.lists(prefix_wrapper(), max_size=2),
    enclosing=st.lists(st.sampled_from(ENCLOSING), max_size=2),
)
def test_wrapped_case_keeps_its_classify_result(command, prefixes, enclosing) -> None:
    """The wrapped command gets the bare command's classify result (reason or ``None``)."""
    bare = classify(command)
    if command.startswith("("):
        prefixes = []
    if bare and any(shape in bare for shape in UNPARSEABLE):
        enclosing = []
    wrapped = "".join(prefixes) + command
    for form in enclosing:
        wrapped = form(wrapped)
    assert classify(wrapped) == bare, wrapped
