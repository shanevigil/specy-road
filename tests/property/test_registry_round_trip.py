"""A registry document dumped to YAML loads back equal, and dumping that load gives the same text.

Domain exclusion (stated, not a counterexample): no U+0085 (NEL) in generated registry text,
because PyYAML reads a raw NEL as a line break; the fix comes after the release candidate.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from specy_road.registry_yaml import dump_registry_text, read_registry

text = st.text(st.characters(codec="utf-8", exclude_characters="\x85"))
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
# The input of the single-input test this property replaces.
@example(entries=SAMPLE_ENTRIES)
def test_registry_dump_then_load_round_trips(tmp_path_factory, entries: list[dict]) -> None:
    doc = {"version": 1, "entries": entries}
    path = tmp_path_factory.mktemp("registry") / "registry.yaml"
    path.write_text(dump_registry_text(doc), encoding="utf-8")

    loaded = read_registry(path)

    assert loaded == doc
    assert dump_registry_text(loaded) == path.read_text(encoding="utf-8")
