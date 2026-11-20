"""Front matter rendered by ``render_front_matter`` parses back to the same data and body.

Both readers are checked: the planning-sheet reader (``split_frontmatter``) and the READY
reader (``load_ready``, whose parsed data and body are returned whether or not the schema
accepts them).

Domain exclusions (stated, not counterexamples): no U+0085 (NEL) in front-matter values,
because PyYAML reads a raw NEL as a line break and the fix comes after the release candidate;
and no body that ends in a newline or contains a line-break character other than ``\\n``
(M22.75), because both readers split the file into lines.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from specy_road.planning_artifacts import split_frontmatter
from specy_road.review_files import load_ready, render_front_matter

text = st.text(st.characters(codec="utf-8", exclude_characters="\x85"))
scalars = st.one_of(text, st.integers(), st.booleans(), st.none())
values = st.recursive(
    scalars, lambda inner: st.lists(inner) | st.dictionaries(text, inner), max_leaves=6
)
#: Line breaks ``str.splitlines`` honours besides ``\n``.
OTHER_BREAKS = "\r\x0b\x0c\x1c\x1d\x1e\x85  "
bodies = st.text(st.characters(codec="utf-8", exclude_characters=OTHER_BREAKS)).filter(
    lambda b: not b.endswith("\n")
)


@given(data=st.dictionaries(text, values), body=bodies)
# A plain scalar that ends in whitespace YAML keeps unquoted (M22.75): the last line of the dump.
@example(data={"note": "kept\u00a0"}, body="")
def test_front_matter_render_then_parse_round_trips(
    tmp_path_factory, data: dict, body: str
) -> None:
    rendered = render_front_matter(data, body)
    assert split_frontmatter(rendered) == (data, body)

    path = tmp_path_factory.mktemp("ready") / "READY-x.md"
    path.write_bytes(rendered.encode("utf-8"))
    ready = load_ready(path)
    assert (ready.data, ready.body) == (data, body)
