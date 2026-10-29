"""TS/JS function spans for the file-limits function cap (one fixture per syntax form)."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.file_limits_engine import run_file_limits_scan
from specy_road.file_limits_js import js_function_metrics
from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "file_limits_js"


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        # Overload signatures have no body; generics and object return types do not end the header.
        (
            "declaration.ts",
            [("overloaded", 4, 3), ("load", 8, 6), ("ids", 15, 4), ("shape", 20, 3)],
        ),
        # Typed bindings, `<T,>` generics, `(…)` JSX and concise bodies; a call is not a function.
        ("arrow.tsx", [("Badge", 3, 5), ("usePick", 9, 3), ("parse", 13, 3), ("twice", 17, 1)]),
        # Concise bodies run on through continued lines and stop at the statement's end.
        (
            "concise_arrow.ts",
            [("total", 1, 6), ("curried", 8, 3), ("label", 11, 1), ("after", 12, 3)],
        ),
        # Modifiers, accessors, private names, arrow fields; abstract signatures have no body.
        (
            "class_methods.ts",
            [
                ("Store.constructor", 5, 3),
                ("Store.add", 11, 3),
                ("Store.size", 15, 3),
                ("Store.#reset", 19, 6),
                ("Store.#reset.clear", 20, 3),
                ("Store.onChange", 26, 3),
            ],
        ),
        # Computed (a multi-line one too), string and number names; index signatures are not methods.
        (
            "computed_method.ts",
            [
                ("Bag.[Symbol.iterator]", 4, 5),
                ('Bag.["load" + "All"]', 9, 3),
                ("Bag.[ Symbol.toStringTag ]", 12, 3),
                ("Bag.[Symbol.species]", 15, 3),
                ("Bag.'my-key'", 18, 3),
                ("Bag.404", 21, 3),
            ],
        ),
        # Braces in a type parameter's constraint or the heritage clause do not open the body.
        ("generic_class.ts", [("Store.find", 2, 6)]),
        # Every declarator of one statement, past plain values, annotations and patterns.
        ("declarators.ts", [("clamp", 1, 5), ("twice", 7, 1), ("reset", 7, 3)]),
        # A grouped initializer `((x) => { … })` is the arrow, not a parameter list.
        ("parenthesized.ts", [("wrapped", 1, 5), ("after", 6, 1)]),
        # The comma in `Map<string, number>` does not end the declarator list.
        ("generic_declarator.ts", [("oversized", 1, 5), ("after", 6, 1)]),
        # A typed arrow field keeps its name: `onChange: (x) => T = (x) => { … }`.
        ("typed_field.ts", [("Handler.onChange", 2, 5)]),
        # An apostrophe or quote in JSX text is not a string; the following function stays separate.
        ("jsx_text.tsx", [("Greeting", 1, 5), ("next", 6, 2), ("after", 8, 3)]),
        # Braces inside strings, nested template literals and comments are ignored.
        ("literals.mjs", [("render", 5, 5), ("after", 10, 3)]),
        # Braces inside regex literals are ignored; a `/` after an operand is a division.
        ("regex.js", [("strip", 1, 5), ("next", 7, 3)]),
        ("division.js", [("layout", 1, 5), ("next", 7, 3)]),
        (
            "legacy.js",
            [("Legacy", 1, 3), ("greet", 5, 3), ("double", 9, 3), ("Modern.greet", 14, 3)],
        ),
        ("widget.jsx", [("Widget", 1, 10), ("Widget.onClick", 2, 3)]),
    ],
)
def test_js_function_metrics_per_syntax_form(fixture: str, expected: list) -> None:
    assert js_function_metrics(FIXTURES / fixture) == expected


def _cfg(glob: str, **extra: object) -> dict:
    return {"max_lines_per_file": 9999, "max_lines_per_function": 4, "applies_to_globs": [glob], **extra}


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".js", ".jsx", ".mjs"])
def test_scan_reports_over_cap_js_function_with_line(tmp_path: Path, suffix: str) -> None:
    shutil.copy(FIXTURES / "widget.jsx", tmp_path / f"widget{suffix}")
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, _cfg(f"*{suffix}"), err=err) is True
    assert err.getvalue() == (
        f"file-limits: widget{suffix}:1 function `Widget` 10 lines (max 4 per function)\n"
    )


@pytest.mark.parametrize(
    ("fixture", "report"),
    [
        # A long concise-body arrow is measured to the end of its expression.
        ("concise_arrow.ts", "concise_arrow.ts:1 function `total` 6 lines"),
        # `/\}+$/` and `/[{]/` must not end or extend `strip`.
        ("regex.js", "regex.js:1 function `strip` 5 lines"),
        # Read as a regex, `/ 2 }; const r = height /` would hide a `}` and swallow `next`.
        ("division.js", "division.js:1 function `layout` 5 lines"),
        # A method of `class Store<T extends { id: string }>`.
        ("generic_class.ts", "generic_class.ts:2 function `Store.find` 6 lines"),
        # An arrow after the first declarator: `const limit = 10, clamp = (x) => {`.
        ("declarators.ts", "declarators.ts:1 function `clamp` 5 lines"),
        # `<p>Don't say "hello` must not hide the `}` on that line or swallow `next`.
        ("jsx_text.tsx", "jsx_text.tsx:1 function `Greeting` 5 lines"),
        # `((x: number) => {` is a named arrow, so an over-cap one fails under its name.
        ("parenthesized.ts", "parenthesized.ts:1 function `wrapped` 5 lines"),
        # The report names `onChange`, not the `number` in its type.
        ("typed_field.ts", "typed_field.ts:2 function `Handler.onChange` 5 lines"),
        # `new Map<string, number>(), oversized = () =>` still reports `oversized`.
        ("generic_declarator.ts", "generic_declarator.ts:1 function `oversized` 5 lines"),
    ],
)
def test_scan_measures_concise_arrows_regexes_and_divisions(
    tmp_path: Path, fixture: str, report: str
) -> None:
    shutil.copy(FIXTURES / fixture, tmp_path / fixture)
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, _cfg(fixture), err=err) is True
    assert err.getvalue() == f"file-limits: {report} (max 4 per function)\n"


def test_js_function_hard_alert(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / "declaration.ts", tmp_path / "declaration.ts")
    cfg = _cfg("*.ts", max_lines_per_function=99, hard_alerts={"max_lines_per_function": 5})
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, cfg, err=err) is False
    assert err.getvalue() == (
        "file-limits: WARNING: declaration.ts:8 function `load` 6 lines "
        "(hard_alerts.max_lines_per_function=5)\n"
    )
    assert run_file_limits_scan(tmp_path, cfg, err=io.StringIO(), strict_hard_alerts=True) is True


@pytest.mark.parametrize(
    ("fixture", "report"),
    [
        ("arrow.tsx", "arrow.tsx:3 function `Badge` 5 lines"),
        ("computed_method.ts", "computed_method.ts:4 function `Bag.[Symbol.iterator]` 5 lines"),
        ("generic_declarator.ts", "generic_declarator.ts:1 function `oversized` 5 lines"),
    ],
)
def test_validator_does_not_print_ok_with_over_cap_ts_function(
    tmp_path: Path, fixture: str, report: str
) -> None:
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        'max_lines_per_function: 4\napplies_to_globs:\n  - "src/**/*.ts*"\n', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    shutil.copy(FIXTURES / fixture, tmp_path / "src" / fixture)
    r = subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_file_limits.py"), "--repo-root", str(tmp_path)],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "OK" not in r.stdout
    assert f"file-limits: src/{report} (max 4 per function)" in r.stderr
