"""Replacing a managed block is idempotent and leaves the text outside the block byte-identical.

For either marker style, a file of user text, a block and more user text is rewritten with new
lines: every byte before the block and every byte after its end marker (the newline after the
marker included) is unchanged, and applying the same lines again changes nothing. Text and block
lines include ``\\r``, CRLF, whitespace-only tails and any number of blank lines. No domain
exclusions.
"""

from __future__ import annotations

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

text = st.text()


@given(
    before=text,
    after=text,
    lines=st.tuples(st.lists(text), st.lists(text)),
    style=st.sampled_from((HASH, HTML_COMMENT)),
)
# The inputs of the single-input tests this property replaces.
@example(before="", after="", lines=(["old-rule/"], ["new-rule/"]), style=HASH)
@example(before="", after="\n# added later by a human\ndist/\n", lines=(["a/"], ["b/"]), style=HASH)
@example(before=USER_CONTENT + "\n", after="trailing/\n", lines=(["a/"], ["b/"]), style=HASH)
def test_replace_is_idempotent_and_keeps_outside_text(
    tmp_path_factory,
    before: str,
    after: str,
    lines: tuple[list[str], list[str]],
    style: MarkerStyle,
) -> None:
    """Rewrite ``old``'s block with ``new``: outside text kept, a second apply a no-op."""
    old, new = lines
    path = tmp_path_factory.mktemp("block") / "managed.txt"
    path.write_bytes((before + render_block(old, style=style) + after).encode("utf-8"))

    apply_managed_block(path, new, style=style)
    first = path.read_bytes().decode("utf-8")

    assert first == before + render_block(new, style=style) + after
    assert apply_managed_block(path, new, style=style) == UNCHANGED
    assert path.read_bytes().decode("utf-8") == first
