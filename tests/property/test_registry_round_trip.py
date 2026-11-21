"""A registry document dumped to YAML loads back equal, and dumping that load gives the same text.

Generated text includes U+0085 (NEL), U+2028 and U+2029. No domain exclusions.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from specy_road.registry_yaml import dump_registry_text, read_registry

text = st.text()
values = st.one_of(text, st.lists(text), st.integers(), st.booleans(), st.none())
entries = st.lists(st.dictionaries(text, values))

SAMPLE_ENTRIES = [
    {
        "codename": "vault-mcp-secrets",
        "node_id": "M10.2",
        "branch": "feature/rm-vault-mcp-secrets",
        "touch_zones": ["src/vault/", "docs/"],
        "started": "2026-06-07",
    },
    {
        "codename": "entry-api",
        "node_id": "M3.1",
        "branch": "feature/rm-entry-api",
        "touch_zones": [],
        "started": "2026-06-07",
        "implementation_review": "pending",
    },
]


@given(entries=entries)
# The inputs of the test this property replaces: the sample document, and the one with U+0085,
# U+2028 and U+2029 in a key, a value and list items.
@example(entries=SAMPLE_ENTRIES)
@example(entries=[{"\x85": "a\x85b", "notes": ["c\x85", "d\u2028e\u2029"]}])
def test_registry_dump_then_load_round_trips(tmp_path_factory, entries: list[dict]) -> None:
    """The loaded document equals the dumped one, and dumping it again gives the same text."""
    doc = {"version": 1, "entries": entries}
    path = tmp_path_factory.mktemp("registry") / "registry.yaml"
    path.write_text(dump_registry_text(doc), encoding="utf-8")

    loaded = read_registry(path)

    assert loaded == doc
    assert dump_registry_text(loaded) == path.read_text(encoding="utf-8")
