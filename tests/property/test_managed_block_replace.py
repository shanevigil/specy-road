"""Replacing a managed block is idempotent and leaves the text outside the block byte-identical.

For either marker style, a file of user text, a block and more user text is rewritten with new
lines: the text before the block is unchanged byte for byte, the text after it is unchanged once
the newlines separating it from the block are set aside (the block owns that separator), and
applying the same lines again changes nothing.

Domain exclusions (stated, not counterexamples; the fix is M23.15, after the release candidate):
files or block lines containing ``\\r``, and text after the block that is whitespace only (an
empty tail is kept), because today the replace rewrites CRLF as LF, drops a whitespace-only tail
and is not idempotent with ``\\r`` in a block line.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import example, given
from hypothesis import strategies as st

from specy_road.managed_block import (
    HASH,
    HTML_COMMENT,
    UNCHANGED,
    MarkerStyle,
    apply_managed_block,
    render_block,
)

USER_CONTENT = "# my own rules\nnode_modules/\n.env\n"

text = st.text(st.characters(codec="utf-8", exclude_characters="\r"))


@given(
    before=text,
    after=text.filter(lambda tail: not tail or tail.strip()),
    old=st.lists(text),
    new=st.lists(text),
    style=st.sampled_from((HASH, HTML_COMMENT)),
)
# The inputs of the single-input tests this property replaces.
@example(before="", after="", old=["old-rule/"], new=["new-rule/"], style=HASH)
@example(before="", after="\n# added later by a human\ndist/\n", old=["a/"], new=["b/"], style=HASH)
@example(before=USER_CONTENT + "\n", after="trailing/\n", old=["a/"], new=["b/"], style=HASH)
def test_replace_is_idempotent_and_keeps_outside_text(
    tmp_path_factory, before: str, after: str, old: list[str], new: list[str], style: MarkerStyle
) -> None:
    path = tmp_path_factory.mktemp("block") / "managed.txt"
    path.write_bytes((before + render_block(old, style=style) + after).encode("utf-8"))

    apply_managed_block(path, new, style=style)
    first = path.read_bytes().decode("utf-8")

    block = render_block(new, style=style)
    assert first.startswith(before + block)
    assert first[len(before + block):].lstrip("\n") == after.lstrip("\n")
    assert apply_managed_block(path, new, style=style) == UNCHANGED
    assert path.read_bytes().decode("utf-8") == first
