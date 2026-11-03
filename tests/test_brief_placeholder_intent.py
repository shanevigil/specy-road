"""M11.46: a brief names a dependency or ancestor whose ``## Intent`` is still a placeholder in one line.

Planning roadmap-first leaves scaffold-planning's and brainstorm promote's
placeholder text in sheets that are not written yet; inlining it verbatim
padded every brief beneath them.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from tests.unauthored_repo_helpers import FILLED, unauthored_repo

from specy_road.bundled_scripts.brief_dependency_context import unwritten_sheet_line, without_placeholder_intent
from specy_road.bundled_scripts.generate_brief import index, load_nodes, render_brief
from specy_road.bundled_scripts.planning_sheet_bootstrap import PROMOTE_PLACEHOLDER, render_feature_sheet_template

PROMOTED = (
    "## Intent\n\nUsers wait.\n\nPromoted from brainstorm idea `i-1` (feature). "
    f"{PROMOTE_PLACEHOLDER}\n\n## Approach\n\nCache the export.\n"
)
SCAFFOLD_INTENT = "What **this** slice delivers"


def _key(nid: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, nid))


def _brief(tmp_path: Path, sheets: dict[str, str], **over: dict) -> str:
    """Brief for ``M1.1``: a task under phase ``M1`` depending on ``M2`` and ``M3``."""
    over = {"M1": {"type": "phase"},
            "M1.1": {"parent_id": "M1", "dependencies": [_key("M2"), _key("M3")]}, **over}
    root, _nodes = unauthored_repo(tmp_path, sheets, **over)
    return render_brief("M1.1", index(load_nodes(root)), repo_root=root, include_history=False)


def test_placeholder_intents_become_one_line_each(tmp_path: Path) -> None:
    brief = _brief(tmp_path, {"M1": "scaffold", "M1.1": FILLED, "M2": "scaffold", "M3": PROMOTED})

    assert SCAFFOLD_INTENT not in brief
    assert PROMOTE_PLACEHOLDER not in brief
    assert "Users wait." not in brief
    for nid, n in (("M1", 1), ("M2", 3), ("M3", 4)):
        assert brief.count(f"_`{nid}` (Leaf {n}): its planning sheet is not written yet._") == 1
    assert "**Intent (from this dependency's planning sheet):**" not in brief
    assert "Cache the export." not in brief   # a dep contributes its Intent only, as before
    assert "Constraints, major steps, and how you will verify done." in brief   # ancestor's other sections stay


def test_written_intents_are_inlined_as_before(tmp_path: Path) -> None:
    authored = FILLED.replace("one row per node", "one row per edge")
    brief = _brief(tmp_path, {"M1": authored, "M1.1": FILLED, "M2": FILLED, "M3": FILLED})

    assert "its planning sheet is not written yet" not in brief
    assert "The export writes one row per edge." in brief
    assert brief.count("**Intent (from this dependency's planning sheet):**") == 2


def test_without_placeholder_intent_swaps_only_the_intent_body() -> None:
    node = {"id": "M1", "title": "Export"}
    sheet = render_feature_sheet_template("M1")

    out = without_placeholder_intent(sheet, node)

    assert out.startswith(f"## Intent\n\n{unwritten_sheet_line(node)}\n\n## Approach\n")
    assert out.split("## Approach", 1)[1] == sheet.rstrip("\n").split("## Approach", 1)[1]
    written = FILLED.format(nid="M1")
    assert without_placeholder_intent(written, node) == written
