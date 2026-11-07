"""The command surface matches its goldens: the inventory both ways, and each ``--help`` transcript.

A difference fails naming the command, subcommand or alias, unless a row of command_map.yaml
declares it (old invocation, new invocation, allowed difference; the rule is in
``tests.parity.command_map``). Every current name needs a golden transcript, mapped or not.
"""

from __future__ import annotations

import argparse
import json

import pytest

from tests.parity.command_map import apply_rows, command_map_rows, inventory_differences
from tests.parity.help_surface import crawl, parse_help
from tests.parity.support import GOLDEN, REGEN, check_golden, help_text, normalise

pytestmark = pytest.mark.parity

INVENTORY = GOLDEN / "inventory.json"
HELP = GOLDEN / "help"


def _help_file(key: str):
    return HELP / (key.replace(" ", "__") + ".txt")


def _golden_inventory() -> dict[str, dict]:
    return json.loads(INVENTORY.read_text(encoding="utf-8")) if INVENTORY.is_file() else {}


def _regenerate(surface: dict[str, dict]) -> None:
    HELP.mkdir(parents=True, exist_ok=True)
    for stale in HELP.glob("*.txt"):
        stale.unlink()
    for key, entry in surface.items():
        _help_file(key).write_text(entry["transcript"], encoding="utf-8")
    inventory = {key: surface[key]["inventory"] for key in sorted(surface)}
    INVENTORY.write_text(json.dumps(inventory, indent=1) + "\n", encoding="utf-8")


def test_inventory_matches_golden_both_ways() -> None:
    surface = crawl()
    if REGEN:
        _regenerate(surface)
        return
    current = {key: entry["inventory"] for key, entry in surface.items()}
    expected, _covered, errors = apply_rows(_golden_inventory(), current, command_map_rows())
    problems = errors + inventory_differences(expected, current)
    assert not problems, "command surface changed:\n" + "\n".join(problems)


def test_inventory_starts_from_the_registered_names() -> None:
    from specy_road.cli import registered_agent_command_names

    roots = {key for key, entry in crawl().items() if len(entry["inventory"]["path"]) == 1}
    registered = {
        f"{prog} {name}"
        for prog, names in registered_agent_command_names().items()
        for name in names
    }
    assert roots == registered


def _covered_names() -> set[str]:
    current = {key: entry["inventory"] for key, entry in crawl().items()}
    return apply_rows(_golden_inventory(), current, command_map_rows())[1]


@pytest.mark.parametrize("key", sorted(_golden_inventory()))
def test_help_transcript_matches_golden(key: str) -> None:
    entry = crawl().get(key)
    if key in _covered_names():
        pytest.skip(f"{key} is covered by a command_map.yaml row")
    if REGEN and entry is None:
        return  # regeneration already dropped its golden
    assert entry is not None, f"{key} has a golden transcript but is gone from the CLI"
    check_golden(_help_file(key), entry["transcript"], help_text)


def test_every_current_name_has_a_golden_transcript() -> None:
    """A name a row adds still needs its transcript (``SPECY_ROAD_PARITY_REGEN=missing``)."""
    for key, entry in crawl().items():
        if key not in _golden_inventory():
            check_golden(_help_file(key), entry["transcript"], help_text)
    missing = [key for key in crawl() if not _help_file(key).is_file()]
    assert not missing, f"no golden transcript for {missing}; run SPECY_ROAD_PARITY_REGEN=missing"


@pytest.mark.parametrize(
    "nargs, usage_tail, passthrough",
    [
        (argparse.REMAINDER, "...", True),
        ("*", "[rest ...]", False),
    ],
)
def test_passthrough_is_read_from_usage(nargs, usage_tail: str, passthrough: bool) -> None:
    """The inventory's passthrough flag tells ``argparse.REMAINDER`` from a list positional."""
    parser = argparse.ArgumentParser(prog="specy-road demo")
    parser.add_argument("rest", nargs=nargs)
    text = parser.format_help()
    assert usage_tail in text
    assert parse_help(("specy-road", "demo"), text)["passthrough"] is passthrough


def _entry(path: list[str], subs=(), options=("-h",)) -> dict:
    return {
        "path": path,
        "subcommands": sorted(subs),
        "options": sorted(options),
        "passthrough": False,
    }


_GOLDEN_A = {
    "specy-road a": _entry(["a"], subs=("x", "y"), options=("-h", "--j")),
    "specy-road a x": _entry(["a", "x"]),
    "specy-road a y": _entry(["a", "y"]),
}


def _without(*keys: str) -> dict:
    return {k: v for k, v in _GOLDEN_A.items() if k not in keys}


@pytest.mark.parametrize(
    "rows, current, problem",
    [
        # old with options: those options may go, nothing else
        (
            [{"old": "specy-road a --j"}],
            {**_GOLDEN_A, "specy-road a": _entry(["a"], ("x", "y"))},
            None,
        ),
        ([], {**_GOLDEN_A, "specy-road a": _entry(["a"], ("x", "y"))}, "options lost ['--j']"),
        (
            [{"old": "specy-road a --j"}],
            {**_GOLDEN_A, "specy-road a": _entry(["a"], ("x", "y"), ("-h", "--k"))},
            "options lost [], gained ['--k']",
        ),
        # old without options: that command may go, and its parent stops listing it
        (
            [{"old": "specy-road a y"}],
            {**_without("specy-road a y"), "specy-road a": _entry(["a"], ("x",), ("-h", "--j"))},
            None,
        ),
        (
            [{"old": "specy-road a y"}],
            {**_without("specy-road a y"), "specy-road a": _entry(["a"], ("x",), ("-h",))},
            "options lost ['--j']",
        ),
        # a kept alias must still match its golden
        (
            [{"old": "specy-road a y"}],
            {**_GOLDEN_A, "specy-road a y": _entry(["a", "y"], (), ("-h", "--q"))},
            "specy-road a y: options lost [], gained ['--q']",
        ),
        # new without options: the command is added and its parent lists it
        (
            [{"new": "specy-road a z"}],
            {
                **_GOLDEN_A,
                "specy-road a z": _entry(["a", "z"]),
                "specy-road a": _entry(["a"], ("x", "y", "z"), ("-h", "--j")),
            },
            None,
        ),
        ([], {**_GOLDEN_A, "specy-road a z": _entry(["a", "z"])}, "in the CLI, not in the golden"),
        # new with options: those options may be added
        (
            [{"new": "specy-road a --k"}],
            {**_GOLDEN_A, "specy-road a": _entry(["a"], ("x", "y"), ("-h", "--j", "--k"))},
            None,
        ),
        # a row naming nothing in the golden is an error
        ([{"old": "specy-road b"}], _GOLDEN_A, "not in the golden inventory"),
        ([{"old": "specy-road a --nope"}], _GOLDEN_A, "['--nope'] not in the golden"),
    ],
)
def test_command_map_rows_apply_as_declared_deltas(rows, current, problem) -> None:
    expected, _covered, errors = apply_rows(_GOLDEN_A, current, rows)
    problems = errors + inventory_differences(expected, current)
    if problem is None:
        assert problems == []
    else:
        assert any(problem in p for p in problems), problems


_DOCS = "  --x X  See https://github.com/o/r/blob/<DOCS_REF>/docs/a.md for\n        more.\n"


@pytest.mark.parametrize(
    "golden, actual, same",
    [
        ("  --a  one two\n", "  --a  one  two\n", False),  # whitespace outside a docs paragraph
        ("  --a  one\n       two\n", "  --a  one two\n", False),
        (
            _DOCS,
            "  --x X  See https://github.com/o/r/blob/<DOCS_REF>/docs/a.md\n        for more.\n",
            True,
        ),
        (_DOCS, _DOCS.replace("more", "less"), False),  # a changed word in a docs paragraph
        ("  --a  one\n" + _DOCS, "  --a  one \n" + _DOCS, False),  # its neighbour stays exact
    ],
)
def test_help_text_is_exact_outside_docs_url_paragraphs(
    golden: str, actual: str, same: bool
) -> None:
    assert (help_text(golden) == help_text(actual)) is same


def _version_cases() -> list[tuple[str, str]]:
    from specy_road import __version__ as v
    from specy_road.doc_links import docs_ref

    return [
        (f"specy-road {v}+0123abcd.dirty\n", "specy-road <VERSION>\n"),
        (f"blob/{docs_ref()}/docs/a.md", "blob/<DOCS_REF>/docs/a.md"),
        (f"adopters of {v}9 and {v}-x", f"adopters of {v}9 and {v}-x"),  # another version
        (f"blob/{docs_ref()}-rc9/docs", f"blob/{docs_ref()}-rc9/docs"),
    ]


@pytest.mark.parametrize("text, normalised", _version_cases())
def test_version_is_normalised_as_a_whole_token(text: str, normalised: str) -> None:
    assert normalise(text) == normalised
