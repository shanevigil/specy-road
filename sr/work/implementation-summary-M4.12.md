# Implementation summary for M4.12

## Summary

The `file-limits` function cap now covers TypeScript and JavaScript as well as Python. `run_file_limits_scan` measures `.ts`, `.tsx`, `.js`, `.jsx` and `.mjs` functions: `function` declarations, arrow functions bound by `const` / `let` / `var`, and class methods (arrow-valued class fields included). Over-cap functions fail the run, so the validator no longer prints `OK` while one exists.

Both languages now report in one shape, with the start line after the path:

```
file-limits: <rel>:<line> function `<name>` <N> lines (max M per function)
```

The hard-alerts warning gets the same `:<line>` and drops the "Python-only advisory" text. Nested functions and methods are named `Outer.inner`, as the Python report already did.

## Changes

- `specy_road/file_limits_js.py` (new): a scanner with no dependencies.
  - It blanks comments, strings and template literals (nested `${…}` included) without moving any newline.
  - It balances brackets on what is left.
  - It finds the three header forms, including TS generics, overload signatures, typed bindings and return types. Object return types (`): { a: T } {`) are handled.
  - It names methods `Class.method` and other nested functions by containment.
- `specy_road/file_limits_engine.py`: `python_function_metrics` now also returns the start line. A new `function_metrics` dispatches by suffix, and `run_file_limits_scan` uses it for every file. Both report lines gain `:<line>` and the "Python-only" labels are gone. The file is 379 lines, under its 400 cap.
- `constraints/file-limits.yaml` and `specy_road/templates/project/constraints/file-limits.yaml`: these policy files now say which languages and forms the function cap covers.
- `constraints/README.md` and `tests/fixtures/specy_road_dogfood/constraints/README.md`: the "Python-only" labels are replaced.
- `tests/fixtures/file_limits_js/`: one fixture per syntax form (`declaration.ts`, `arrow.tsx`, `class_methods.ts`), plus `literals.mjs` for masking. `legacy.js` and `widget.jsx` cover the last two suffixes.
- `tests/test_file_limits_js.py` (new), plus one assertion added to `tests/test_file_limits_engine.py`.

Final touch zones used: `specy_road/file_limits_engine.py`, `specy_road/file_limits_js.py`, `constraints/file-limits.yaml`, `specy_road/templates/project/constraints/file-limits.yaml`, `constraints/README.md`, `tests/fixtures/specy_road_dogfood/constraints/README.md`, `tests/`. Not touched: `specy_road/bundled_scripts/validate_file_limits.py` (it already exits non-zero before `OK` when the scan fails) and `docs/file-limits.md` (it does not exist, and the policy files carry the documentation A3 asks for).

## Known limits (by design, documented in the module docstring)

- **Regex literals are not masked.** One holding an unpaired quote or bracket can throw a span off.
- **JSX text is code to the scanner.** An apostrophe in it (`<p>Don't</p>`) is read as a string that runs to the end of that line. The damage stays on that one line, but a closing brace later on the same line is missed.
- **Some functions are not measured.** Unnamed callbacks (`useCallback(() => {…})`), arrows with expression bodies that are not bracketed, object-literal methods and anonymous `function` expressions all fall outside the three forms A1 names.
- **No-semicolon TS with a bodiless overload directly before its implementation.** The overload's name takes the implementation's body.

## Out of zone (not edited)

- `specy_road/templates/project/constraints/README.md:8` still says "Max function length (**Python `.py` only**)". Consumer scaffolds will carry that stale label until a follow-up fixes it.

## Verification

- `pytest -q tests/test_file_limits_js.py tests/test_file_limits_engine.py tests/test_file_limits_gitignore.py tests/test_validate_file_limits.py`: 30 passed.
- `pytest -q` (full suite): 2344 passed, 2 skipped.
- `python specy_road/bundled_scripts/validate_file_limits.py` (this repo): `OK: file limits satisfied.`
- `ruff check specy_road tests scripts`: all checks passed.
- Dogfood `validate`, `export --check` and `digest --check`: OK. I removed the `.specyrd/cache` those runs leave in the fixture.
- Manual check: I ran the scanner over `gui/pm-gantt/src`, 314 functions in 0.18 s. `App` (`App.tsx:154`, 1703 lines, ending on the file's last line), `SortableRow` and `ModalFrame` end on their real closing braces, and the handlers inside components come out as `SortableRow.handleTitleClick` and so on. This repo's policy does not apply the cap to `gui/`. Adding a `gui/**/*.tsx` glob would flag those components today.

## Walkthrough

1. Read the masking functions (`mask_source`, `_literal_end`, `_template_end`, `_expr_end`) in `specy_road/file_limits_js.py`, then `_spans` for the three forms.
2. `tests/test_file_limits_js.py::test_js_function_metrics_per_syntax_form` lists the expected `(name, line, span)` for each fixture.
3. `test_validator_does_not_print_ok_with_over_cap_ts_function` runs the real validator on an over-cap `.tsx` file.

## Added

- `specy_road/file_limits_js.py` `JS_SUFFIXES`: the five suffixes A1 names, used by the engine's dispatch.
- `mask_source`, `_literal_end`, `_quoted_end`, `_template_end`, `_expr_end`: blank comments, strings and templates so braces inside them are not counted (the brief's skipping requirement).
- `_quoted_end` stops an unterminated string at the line end: this keeps a stray quote (JSX text, regex) from masking the rest of the file.
- `_close`, `_angles_end`: bracket and type-parameter balancing. `_angles_end` ignores the `>` of `=>` so function types inside generics balance.
- `_type_end`: skips a type annotation up to `=>`, `=` or the body `{`. Treating an object type followed by `{`, `|`, `&` or `[]` as a type is how `): { a: T } {` gets handled.
- `_params_end`, `_decl_body`, `_arrow_body`: header parsing shared by declarations, bindings and class members. `_decl_body` returns None for overload and abstract signatures.
- `_class_members`: walks the top level of a class body only, skipping bracket groups, so `if (…) {` inside methods is never read as a member.
- `_spans`, `js_function_metrics`: collect the three forms and name them by containment (`Class.method`, `Outer.inner`), matching the Python report.
- `_ch`, `_ws`: out-of-range-safe character and whitespace helpers. `_close` returns `len(s)` when brackets are unbalanced.
- `file_limits_engine.function_metrics`: suffix dispatch, so `run_file_limits_scan` has one loop for both languages.
- The `python_function_metrics` tuple gains the start line, for the `:<line>` A2 requires.
- `tests/fixtures/file_limits_js/*`: one fixture per syntax form and suffix (A3).
- `tests/test_file_limits_js.py`:
  - `test_js_function_metrics_per_syntax_form`: exact spans per fixture.
  - `test_scan_reports_over_cap_js_function_with_line`: exact report line for each of the five suffixes.
  - `test_js_function_hard_alert`: TS hard-alert line and the strict flag.
  - `test_validator_does_not_print_ok_with_over_cap_ts_function`: A2, end to end.
- `tests/test_file_limits_engine.py`: one assertion on the exact Python report line, including `:4`.
- Mocks: none.
