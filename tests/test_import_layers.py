"""The import-layer report records cycles and entry-point edges, and does not gate them."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# grind_session_cleanup now lives in specy_road, so it is not a bundled entry point.
ENTRY_POINT_STEMS = (
    "generate_brief",
    "validate_roadmap",
    "refresh_stubs",
    "chore_cli",
)


def _load_layers():
    path = ROOT / "scripts" / "check_import_layers.py"
    spec = importlib.util.spec_from_file_location("check_import_layers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layers = _load_layers()


def _write_module(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _section(text: str, title: str) -> list[str]:
    lines = text.splitlines()
    body = []
    for line in lines[lines.index(f"{title}:") + 1 :]:
        if not line.startswith(" "):
            break
        body.append(line.strip())
    return body


def _stems_of(component: dict) -> set[str]:
    return {module.rsplit(".", 1)[-1] for module in component["modules"]}


def _loader_component(report: dict) -> dict | None:
    """The component holding both the graph loader and the review gate, if any."""
    for component in report["components"]:
        stems = _stems_of(component)
        if "roadmap_load" in stems and "review_gate" in stems:
            return component
    return None


def _package_entry_targets(report: dict) -> set[str]:
    """Entry-point stems imported from outside bundled_scripts; the report must list edges."""
    assert report["entry_point_edges"], "the report lists no entry-point edges"
    return {
        edge["to"].rsplit(".", 1)[-1]
        for edge in report["entry_point_edges"]
        if not edge["from"].startswith("specy_road.bundled_scripts.")
    }


def _crud_component(report: dict) -> dict | None:
    for component in report["components"]:
        stems = _stems_of(component)
        if "chore_cli" in stems and any(stem.startswith("roadmap_crud") for stem in stems):
            return component
    return None


def test_function_level_and_relative_imports_are_edges(tmp_path):
    """A function-level relative import closes a cycle; a one-way import does not."""
    package = tmp_path / "specy_road"
    _write_module(package / "__init__.py", "")
    _write_module(
        package / "left.py",
        "def load():\n    from .right import value\n    return value\n",
    )
    _write_module(package / "right.py", "import specy_road.left\nvalue = 1\n")
    _write_module(package / "solo.py", "def load():\n    import specy_road.left\n")
    _write_module(package / "high.py", "from .... import nowhere\n")

    graph = layers.scan_imports(package)
    components = layers.strongly_connected(graph)

    assert graph["specy_road.left"] == {"specy_road.right"}
    assert graph["specy_road.high"] == set()
    assert components == [["specy_road.left", "specy_road.right"]]


def test_entry_point_edges_are_command_mains_and_grind_cleanup(tmp_path):
    """Entry-point edges are command mains and grind_session_cleanup, not library modules."""
    package = tmp_path / "specy_road"
    bundled = package / "bundled_scripts"
    _write_module(package / "__init__.py", "")
    _write_module(bundled / "__init__.py", "")
    _write_module(
        bundled / "generate_brief.py",
        "def render_brief():\n    return ''\n\ndef main():\n    return 0\n",
    )
    _write_module(bundled / "helper.py", "def thing():\n    return 1\n")
    _write_module(bundled / "grind_session_cleanup.py", "def merged_into():\n    return True\n")
    _write_module(
        package / "app.py",
        "def load():\n"
        "    from specy_road.bundled_scripts.generate_brief import render_brief\n"
        "    from specy_road.bundled_scripts.helper import thing\n"
        "    from specy_road.bundled_scripts.grind_session_cleanup import merged_into\n"
        "    return render_brief, thing, merged_into\n",
    )
    _write_module(
        bundled / "validate_roadmap.py",
        "from specy_road.bundled_scripts.generate_brief import render_brief\n"
        "def main():\n"
        "    return render_brief()\n",
    )

    report = layers.build_report(package)
    edges = {(edge["from"], edge["to"]) for edge in report["entry_point_edges"]}
    brief = "specy_road.bundled_scripts.generate_brief"
    cleanup = "specy_road.bundled_scripts.grind_session_cleanup"
    assert ("specy_road.app", brief) in edges
    assert ("specy_road.app", cleanup) in edges
    assert ("specy_road.bundled_scripts.validate_roadmap", brief) in edges
    assert all(target != "specy_road.bundled_scripts.helper" for _source, target in edges)


def test_gate_cli_and_gui_imports_of_orchestration_members_are_listed(tmp_path):
    """The gate, CLI entry points and gui_app importing past the package interface are listed."""
    package = tmp_path / "specy_road"
    bundled = package / "bundled_scripts"
    for init in (package, bundled, package / "orchestration"):
        _write_module(init / "__init__.py", "")
    _write_module(package / "orchestration" / "state.py", "def snapshot():\n    return {}\n")
    deep = "from specy_road.orchestration.state import snapshot\n"
    _write_module(bundled / "worker_cli.py", deep + "def main():\n    return 0\n")
    _write_module(package / "gui_app_routes_workers.py", deep)
    _write_module(package / "review_gate.py", "from specy_road.orchestration import snapshot\n")
    _write_module(package / "worker_ops.py", deep)

    report = layers.build_report(package)
    listed = [(edge["from"], edge["to"]) for edge in report["orchestration_internal_imports"]]
    assert listed == [
        ("specy_road.bundled_scripts.worker_cli", "specy_road.orchestration.state"),
        ("specy_road.gui_app_routes_workers", "specy_road.orchestration.state"),
    ]
    text = layers.render_difference(report, report)
    assert _section(text, "orchestration internals imported by the gate, CLI or GUI") == [
        f"{source} -> {target}" for source, target in listed
    ]


def test_difference_lists_every_change_and_main_exits_zero(tmp_path, capsys):
    """The difference lists every change kind, and a stale report still exits 0."""
    current = {
        "components": [
            {"size": 3, "modules": ["specy_road.a", "specy_road.b", "specy_road.c"]},
            {"size": 2, "modules": ["specy_road.d", "specy_road.e"]},
            {"size": 2, "modules": ["specy_road.f", "specy_road.z"]},
            {"size": 2, "modules": ["specy_road.x", "specy_road.y"]},
        ],
        "entry_point_edges": [
            {"from": "specy_road.a", "to": "specy_road.bundled_scripts.generate_brief"},
        ],
    }
    baseline = {
        "components": [
            {"size": 2, "modules": ["specy_road.a", "specy_road.b"]},
            {"size": 2, "modules": ["specy_road.c", "specy_road.gone"]},
            {"size": 3, "modules": ["specy_road.d", "specy_road.e", "specy_road.f"]},
        ],
        "entry_point_edges": [
            {"from": "specy_road.old", "to": "specy_road.bundled_scripts.chore_cli"},
        ],
    }
    text = layers.render_difference(current, baseline)
    assert _section(text, "members added") == ["specy_road.x", "specy_road.y", "specy_road.z"]
    assert _section(text, "members removed") == ["specy_road.gone"]
    assert "specy_road.a" in _section(text, "components merged")[0]
    assert "specy_road.c" in _section(text, "components merged")[0]
    assert "specy_road.f" in _section(text, "components split")[0]
    assert "specy_road.z" in _section(text, "components split")[0]
    assert _section(text, "entry-point edges added") == [
        "specy_road.a -> specy_road.bundled_scripts.generate_brief"
    ]
    assert _section(text, "entry-point edges removed") == [
        "specy_road.old -> specy_road.bundled_scripts.chore_cli"
    ]

    package = tmp_path / "specy_road"
    _write_module(package / "__init__.py", "")
    _write_module(package / "left.py", "def load():\n    import specy_road.right\n")
    _write_module(package / "right.py", "import specy_road.left\n")
    bundled = package / "bundled_scripts"
    _write_module(bundled / "__init__.py", "")
    _write_module(bundled / "generate_brief.py", "def main():\n    return 0\n")
    _write_module(
        package / "app.py",
        "from specy_road.bundled_scripts.generate_brief import main\n",
    )
    baseline_path = tmp_path / "missing-report.json"
    args = ["--package", str(package), "--baseline", str(baseline_path)]

    assert layers.main(args) == 0
    printed = capsys.readouterr().out
    assert "specy_road.left" in _section(printed, "members added")
    assert "generate_brief" in _section(printed, "entry-point edges added")[0]

    assert layers.main([*args, "--write"]) == 0
    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["components"]
    assert all(
        component["size"] == len(component["modules"]) for component in written["components"]
    )
    assert layers.main(args) == 0
    assert "no difference from the committed report" in capsys.readouterr().out


def test_report_names_the_cycles_and_running_it_exits_zero(monkeypatch):
    """The live scan and the committed report keep roadmap_load apart from review_gate and
    roadmap_crud apart from chore_cli, and the script exits 0."""
    monkeypatch.chdir(ROOT)
    report = layers.build_report(ROOT / "specy_road")
    loader = _loader_component(report)
    crud = _crud_component(report)
    assert loader is None
    assert crud is None
    assert _package_entry_targets(report).isdisjoint(ENTRY_POINT_STEMS)

    assert report["orchestration_internal_imports"] == []

    same = layers.render_difference(report, report)
    assert "no component contains roadmap_load and finish_ancestor_rollup" in same
    assert "no component contains a roadmap_crud module and chore_cli" in same
    assert "no difference from the committed report" in same

    committed = json.loads((ROOT / "constraints" / "import-layers-baseline.json").read_text())
    committed_loader = _loader_component(committed)
    committed_crud = _crud_component(committed)
    assert committed_loader is None
    assert committed_crud is None
    assert _package_entry_targets(committed).isdisjoint(ENTRY_POINT_STEMS)
    assert layers.main([]) == 0
