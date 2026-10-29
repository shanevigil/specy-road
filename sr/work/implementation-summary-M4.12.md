# Implementation summary for M4.12

## Summary

The `file-limits` function cap now covers TypeScript and JavaScript as well as Python. `run_file_limits_scan` measures `.ts`, `.tsx`, `.js`, `.jsx` and `.mjs` functions: `function` declarations, arrow functions bound by `const` / `let` / `var`, and class methods (arrow-valued class fields included). Over-cap functions fail the run, so the validator no longer prints `OK` while one exists.

Both languages now report in one shape, with the start line after the path:

```
file-limits: <rel>:<line> function `<name>` <N> lines (max M per function)
```

The hard-alerts warning gets the same `:<line>` and drops the "Python-only advisory" text. Nested functions and methods are named `Outer.inner`, as the Python report already did.

Review round 1 (Sol, at 4a0f5c9) blocked on two A1 gaps, both fixed in this round:

- **Concise-body arrows are now measured.** The span runs from the binding to the end of the expression: brackets are balanced, and it stops at the terminating `;`, a `,`, the enclosing statement's closing bracket, or a line break the next line does not continue (`.`, `?`, `:`, binary operators).
- **Regex literals are now masked** in the same pass as strings and comments. A `/` opens a regex at line start, after an operator, `(`, `,`, `=`, `:`, `[`, `!`, `&`, `|`, `?`, `{`, `}` or `;`, and after `return` and the other keywords that take an expression (`typeof`, `case`, `throw`, `await` and so on). After an identifier, number, `)`, `]` or another literal it is a division.

Review round 2 (Sol, at f680a73) asked for three changes, all made in this round:

- **Generic class headers.** Taking the class body now skips balanced type parameters and the heritage clause, braces inside them included. This reuses `_type_end(s, j, "{")`, the same skip that already finds a method's body past its return type. So `class Store<T extends { id: string }> extends Base<{ size: number }> {` measures its methods.
- **Every declarator.** Each `const` / `let` / `var` list is walked declarator by declarator (`_declarators`). Plain values, declarators without an initializer, annotations and destructuring patterns are stepped over, so `const limit = 10, clamp = (x) => { … }` measures `clamp`.
- **Template README.** `specy_road/templates/project/constraints/README.md` now describes the TS/JS coverage the same way `constraints/README.md` does.

Review round 3 (Sol, at 6ece457) blocked because computed class methods were skipped. That is fixed in this round:

- **Computed member names.** `_MEMBER_RE` now also accepts a `[` where the name goes. The name runs to the matching `]`, and the report uses the source text with its whitespace collapsed, so a multi-line key still prints on one line: `Bag.[Symbol.iterator]`, `Bag.["load" + "All"]`. Modifiers, `*`, `get` / `set`, `?`, and arrow-valued computed fields work as they do for plain names.
- **String and number member names.** These are the same gap in A1's class-method form, so I closed them too: `'my-key'() {}` (reported as `Bag.'my-key'`, ending at the source quote via `_quoted_end`) and `404() {}`. An index signature (`[key: string]: unknown;`) has no parameter list, so it is stepped over. The class-body walk now tries a member match before it skips a bracket group. A `(` or `{` can never start a member, so only `[` behaves differently.
- The name comes from the unmasked source, so `_spans` and `_class_members` now take `src` as well as the masked text. Offsets are the same in both.

## Changes

- `specy_road/file_limits_js.py` (new): a scanner with no dependencies.
  - It blanks comments, and reduces strings, template literals (nested `${…}` included) and regex literals to a single `"`, without moving any newline. The `"` keeps a literal-only concise body (`` => `#${n}` ``) from reading as empty.
  - It balances brackets on what is left.
  - Concise arrow bodies run to the end of their expression (`_body_end`).
  - It finds the three header forms, including TS generics, overload signatures, typed bindings and return types. Object return types (`): { a: T } {`) are handled.
  - It names methods `Class.method` (computed and string names as source text, `Class.[Symbol.iterator]`) and other nested functions by containment.
- `specy_road/file_limits_engine.py`: `python_function_metrics` now also returns the start line. A new `function_metrics` dispatches by suffix, and `run_file_limits_scan` uses it for every file. Both report lines gain `:<line>` and the "Python-only" labels are gone. The file is 379 lines, under its 400 cap.
- `constraints/file-limits.yaml` and `specy_road/templates/project/constraints/file-limits.yaml`: these policy files now say which languages and forms the function cap covers.
- `constraints/README.md`, `specy_road/templates/project/constraints/README.md` (round 2) and `tests/fixtures/specy_road_dogfood/constraints/README.md`: the "Python-only" labels are replaced.
- `tests/fixtures/file_limits_js/`: one fixture per syntax form (`declaration.ts`, `arrow.tsx`, `class_methods.ts`), plus `literals.mjs` for masking. `legacy.js` and `widget.jsx` cover the last two suffixes. Round 1 adds `concise_arrow.ts`, `regex.js` and `division.js`; round 2 adds `generic_class.ts` and `declarators.ts`; round 3 adds `computed_method.ts`.
- `tests/test_file_limits_js.py` (new), plus one assertion added to `tests/test_file_limits_engine.py`.

Final touch zones used: `specy_road/file_limits_engine.py`, `specy_road/file_limits_js.py`, `constraints/file-limits.yaml`, `specy_road/templates/project/constraints/file-limits.yaml`, `constraints/README.md`, `specy_road/templates/project/constraints/README.md`, `tests/fixtures/specy_road_dogfood/constraints/README.md`, `tests/`. Not touched: `specy_road/bundled_scripts/validate_file_limits.py` (it already exits non-zero before `OK` when the scan fails) and `docs/file-limits.md` (it does not exist, and the policy files carry the documentation A3 asks for).

## Known limits (by design, documented in the module docstring)

- **The regex rule is the usual heuristic.** A division at the start of a continuation line (`a\n  / b`) is read as a regex. That masks the rest of that line, or nothing when no closing `/` follows on it. A regex after `)` (`if (x) /re/.test(s)`) is read as a division.
- **`<` does not open a regex, and `/>` is never one.** This is a JSX exception to the operator rule, so `</div>` and `<Foo a={x} />` keep their braces. `a < /re/` and the regex `/>/` are read as divisions.
- **Regexes inside a template's `${…}` are not masked.**
- **Concise bodies in no-semicolon code end at a line break** unless one of the two lines carries a continuation token. A continuation that starts with a keyword (`instanceof`, `as`) on the next line ends the span early.
- **JSX text is code to the scanner.** An apostrophe in it (`<p>Don't</p>`) is read as a string that runs to the end of that line. The damage stays on that one line, but a closing brace later on the same line is missed.
- **Some functions are not measured.** Unnamed callbacks (`useCallback(() => {…})`), object-literal methods and anonymous `function` expressions all fall outside the three forms A1 names.
- **A class field whose value starts with `[` on the next line.** In no-semicolon code, `x = y` followed by a line starting `[k]() {` reads the second line as a computed method. JavaScript itself reads it as `y[k]()`.
- **No-semicolon TS with a bodiless overload directly before its implementation.** The overload's name takes the implementation's body.
- **An empty class body directly followed by a block.** `class A {} {` reads the first `{}` as an object type in the header, because of the same lookahead that handles `): { a: T } {`.
- **A destructuring declarator names no function.** Its pattern is stepped over so later declarators are still found.

## Verification

- `pytest -q tests/test_file_limits_js.py tests/test_file_limits_engine.py tests/test_file_limits_gitignore.py tests/test_validate_file_limits.py`: 42 passed (round 3; 40 in round 2, 36 in round 1, 30 before that).
- `pytest -q` (full suite, round 3 after the computed-name change): 2356 passed, 2 skipped. The string/number-name follow-up touched only `specy_road/file_limits_js.py` and its own test and fixture, so I reran the focused set after it.
- File caps: `specy_road/file_limits_js.py` is 397 lines (cap 400) and the engine is 379. In round 2 a separate `_class_body` helper took the scanner to 403, so I reused `_type_end` instead of adding an exemption.
- Round 3 regression check: the round-2 scanner returns no functions at all for `computed_method.ts`, so the new fixture and the new validator case both fail without this fix. Across `gui/pm-gantt/src` (77 files, 318 functions), the round-2 and round-3 scanners return identical results.
- `python specy_road/bundled_scripts/validate_file_limits.py` (this repo): `OK: file limits satisfied.`
- `ruff check specy_road tests scripts`: all checks passed.
- Dogfood `validate`, `export --check` and `digest --check`: OK. I removed the `.specyrd/cache` those runs leave in the fixture.
- Manual check (round 1): with `_regex_allowed` forced to always say yes, `division.js` gives `layout` 10 lines and swallows `next`. So `test_scan_measures_concise_arrows_regexes_and_divisions[division.js]` does catch a division misread as a regex.
- Manual check: I ran the scanner over `gui/pm-gantt/src`, 314 functions in 0.18 s. `App` (`App.tsx:154`, 1703 lines, ending on the file's last line), `SortableRow` and `ModalFrame` end on their real closing braces, and the handlers inside components come out as `SortableRow.handleTitleClick` and so on. Round 2 recheck: the round-1 and round-2 scanners agree on every function in every GUI file. Round 1 recheck: the round-0 and round-1 scanners agree on every one of those spans. The only difference is 4 new short concise arrows (at most 3 lines each). This repo's policy does not apply the cap to `gui/`. Adding a `gui/**/*.tsx` glob would flag those components today.

## Walkthrough

1. Read the masking functions (`mask_source`, `_literal_end`, `_template_end`, `_expr_end`) in `specy_road/file_limits_js.py`, then `_spans` for the three forms.
2. `tests/test_file_limits_js.py::test_js_function_metrics_per_syntax_form` lists the expected `(name, line, span)` for each fixture.
3. Round 2: `_declarators`, and the `_type_end(s, m.end(), "{")` call for class bodies in `_spans`; the fixtures are `generic_class.ts` and `declarators.ts`.
4. Round 1: `_regex_allowed` / `_regex_end` in `mask_source`, then `_body_end`; the fixtures are `concise_arrow.ts`, `regex.js` and `division.js`.
5. `test_validator_does_not_print_ok_with_over_cap_ts_function` runs the real validator on an over-cap `.tsx` arrow and (round 3) an over-cap computed `.ts` method.
6. Round 3: the computed-name branch in `_class_members` (`m.group(2)`), and the fixture `computed_method.ts`.

## Added

- `specy_road/file_limits_js.py` `JS_SUFFIXES`: the five suffixes A1 names, used by the engine's dispatch.
- `mask_source`, `_literal_end`, `_quoted_end`, `_template_end`, `_expr_end`: blank comments, strings and templates so braces inside them are not counted (the brief's skipping requirement).
- `_quoted_end` stops an unterminated string at the line end: this keeps a stray quote (JSX text, regex) from masking the rest of the file.
- `_close`, `_angles_end`: bracket and type-parameter balancing. `_angles_end` ignores the `>` of `=>` so function types inside generics balance.
- `_type_end`: skips a type annotation up to `=>`, `=` or the body `{`. Treating an object type followed by `{`, `|`, `&` or `[]` as a type is how `): { a: T } {` gets handled.
- `_params_end`, `_decl_body`, `_arrow_body`: header parsing shared by declarations, bindings and class members. `_decl_body` returns None for overload and abstract signatures.
- `_class_members`: walks the top level of a class body only, skipping bracket groups, so `if (…) {` inside methods is never read as a member.
- Round 1: `_regex_allowed`, `_regex_end`, `_REGEX_AFTER`, `_REGEX_AFTER_WORDS`, `_TRAILING_WORD_RE`, `_REGEX_FLAGS_RE`: regex masking by previous significant token (review item 2). `_regex_end` returns None when the line ends before a closing `/`, so an unterminated "regex" is left as a division rather than masked.
- Round 1: the `<` exclusion from `_REGEX_AFTER` and the `/>` guard in `_regex_allowed`: keep JSX closing and self-closing tags from opening a regex that would hide their braces.
- Round 1: the `"` placeholder in `mask_source`: a literal still reads as an operand, both for the regex/division decision and for concise bodies made of a single literal.
- Round 1: `_body_end`, `_CONTINUES_AFTER`, `_CONTINUES_BEFORE`: the span of a concise arrow body to the end of its expression (review item 1). `_arrow_body` now returns any body start, not only `{` or `(`.
- Round 2: `_declarators`: walks every declarator of a `const` / `let` / `var` list, so a named arrow after a comma is measured (review item 2). Its `[`/`{` branch steps over a destructuring pattern so later declarators are still reached. `_BINDING_RE` now matches only the keyword.
- Round 2: `,` as a stop in `_type_end(…, "=")`: ends the annotation of a declarator with no initializer (`let a: T, b = …`).
- Round 2: class bodies found with `_type_end(s, j, "{")`, and `_CLASS_RE` no longer consumes up to the first `{`: type parameters and heritage clauses holding braces no longer cut the body off (review item 1).
- Round 3: the `([\["])` alternative in `_MEMBER_RE` and its branch in `_class_members`: measure computed class methods and fields (review item), and string-named ones. A string name ends at `_quoted_end` on the source, because the masked text only keeps the opening `"`. The `\d[\w.]*` alternative measures number-named methods. `_OPTIONAL_RE` takes the `?` after either kind of name. The member match now runs before the bracket-group skip, so a `[` can start a member.
- Round 3: `" ".join(...split())` on the computed name: keeps a multi-line key (`[\n Symbol.toStringTag\n]`) to one report line (A2). It is reached by `computed_method.ts`.
- Round 3: the `src` parameter on `_spans` / `_class_members`: computed and string names are taken from the source, not from the masked text where strings are blanked.
- `_spans`, `js_function_metrics`: collect the three forms and name them by containment (`Class.method`, `Outer.inner`), matching the Python report.
- `_ch`, `_ws`: out-of-range-safe character and whitespace helpers. `_close` returns `len(s)` when brackets are unbalanced.
- `file_limits_engine.function_metrics`: suffix dispatch, so `run_file_limits_scan` has one loop for both languages.
- The `python_function_metrics` tuple gains the start line, for the `:<line>` A2 requires.
- `tests/fixtures/file_limits_js/*`: one fixture per syntax form and suffix (A3).
- `tests/test_file_limits_js.py`:
  - `test_js_function_metrics_per_syntax_form`: exact spans per fixture.
  - `test_scan_reports_over_cap_js_function_with_line`: exact report line for each of the five suffixes.
  - `test_scan_measures_concise_arrows_regexes_and_divisions` (round 1): `run_file_limits_scan` on a long concise arrow (reported), a regex holding braces (correct length) and divisions that must not be read as regexes. Round 2 adds an over-cap method in `class Store<T extends { id: string }>` and an over-cap arrow after a comma.
  - `test_js_function_hard_alert`: TS hard-alert line and the strict flag.
  - `test_validator_does_not_print_ok_with_over_cap_ts_function`: A2, end to end. Round 3 parametrizes it with `computed_method.ts` (the review's public-validator regression), and its glob widens to `src/**/*.ts*`.
  - Round 3: `computed_method.ts` added to `test_js_function_metrics_per_syntax_form`.
- `tests/test_file_limits_engine.py`: one assertion on the exact Python report line, including `:4`.
- Mocks: none.
