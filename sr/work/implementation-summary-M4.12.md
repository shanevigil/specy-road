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

Review round 4 (Sol, at 84faff9) blocked on three edges. The amended A1 on `WIP/improvements-0-3-1` (merged here) keeps one of them in scope:

- **JSX text is not lexed as code.** In `.jsx` and `.tsx`, `blank_jsx_text` runs before the mask. Text nodes become spaces (newlines and length stay), so `<p>Don't say "hello</p>; }` does not open a string and the `}` on that line still closes the function. Attributes and `{…}` expressions stay code; JSX inside an expression is blanked the same way (`{ready && <i>It's</i>}`). A `<` starts an element only where an expression may start (or after `return`, `yield`, `throw`, `await`, `else`, `case`, `void`), and `<T,>` / `<T extends …>` stay generics.
- **Out of scope, documented rather than scanned.** Non-ASCII identifiers, and a bodiless overload with no terminating semicolon. Both are named in `docs/file-limits.md` and in the `file_limits_js` docstring.

Review round 5 (Sol, at f4a1b0c) found one stale public description:

- **CLI help names TS/JS.** `validate_file_limits.py` passes its module docstring to `ArgumentParser`; that docstring now says the optional function counts cover Python and TS/JS, instead of Python only.

Review round 6 (Sol, at bb2887d) blocked on named arrows:

- **Grouped initializers.** `_arrow_body` now looks inside a `(` before treating it as a parameter list. `((x: number) => { … })` is measured under the `const` name; `(x) => { … }` is unchanged, because `=>` still follows that `(`.
- **Typed arrow fields.** A `:` after a class member name is skipped with `_type_end` up to `=`, so `onChange: (x: number) => number = (x) => { … }` is `Handler.onChange`, not `Handler.number`.

Review round 7 (Sol, at e7756d1) has one finding, and it is in scope. A1 still requires every named `const` / `let` / `var` arrow; the documented exclusions are only non-ASCII identifiers and a bodiless overload with no semicolon. Neither is this bug.

- **Generic commas in an earlier initializer.** `_body_end` was treating the comma in `Map<string, number>` as the next declarator. A `<…>` that closes with `>` before `{` or `;` is now one unit, so `const cache = new Map<string, number>(), oversized = () => { … }` reports `oversized`. A comparison (`a < b, after = …`) has no such `>`, so that comma still separates declarators. Round 8 found that this skip was too broad; see below.

Review round 8 (Grok, at 101eaf9) has one finding, and it is in scope. A1 requires every named `const` / `let` / `var` arrow, and this is neither documented exclusion (non-ASCII identifiers, a bodiless overload with no semicolon). It is also a regression from round 7.

- **A comparison `<` that pairs with a later `>`.** In `const ready = count < limit, oversized = () => count > 0 …`, the round-7 skip ran from the comparison's `<` to the `>` inside `oversized`'s body, jumped the declarator comma, and dropped `oversized`; the validator printed `OK`. Round 6 measured it. The skip now lives in `_type_args_end`, which rejects a span containing `=` outside `=>` (and, in this round, `{` and `;`). Type arguments never hold a bare `=`, and a later declarator always does. `Map<string, number>()`, `Foo<() => void, T>()` and `ids as Map<string, number>` stay one unit; `count < limit, oversized = …` and `() => a < b, big = () => c > d` split at the comma again. Round 9 drops the `{` reject; see below.
- **Line-cap gaming undone.** In round 7 I fitted `file_limits_js.py` under its 400-line cap by joining two statements onto one line (`last, j = end - 1, end; continue`). In round 6 I had deleted three explanatory comments for the same reason. Neither was mentioned in those summaries. Both are undone: the statements are on separate lines and the three comments are back, plus the computed-name note in `_class_members`. To make real room, the literal-masking layer (`mask_source` and the comment, string, template and regex helpers, about 145 lines) moved verbatim to `specy_road/file_limits_js_mask.py`. A verbatim check confirmed all nine functions; before the bug fix, round 7 and the moved code agreed on 93 files (the GUI tree plus every fixture). `file_limits_jsx.py` now imports from that module, so the in-function import in `js_function_metrics` is a normal top-level import.

Review round 9 (Grok, at 233b90b) has two findings, both in scope. A1 still requires every named `const` / `let` / `var` arrow. The only documented exclusions are non-ASCII identifiers and a bodiless overload with no terminating semicolon (`docs/file-limits.md`). Neither finding is one of those. The first is a regression from round 6 (`aec8b7d`). The second is the object-type residual this summary called a heuristic limit; that limit is removed.

- **Comma after a grouped arrow.** `_arrow_body` returns the body inside `(x => x + 1)`, and `_body_end` stopped at that `)`, so `_declarators` never saw the comma and dropped `after`. At `bb2887d` the same source reported `after` and skipped `wrapped`. `(x) => body` is unchanged: `=>` follows that `(`, so the body starts past it. When the body starts inside the grouping `(`, the list now continues after the closing `)`. `const wrapped = (x => x + 1), after = () => { … }` reports both names, and the validator names `after`. The same path covers `let` and `(async (n) => n + 1), rest`.
- **Object types inside type arguments.** `_type_args_end` no longer rejects a span for `{`. It still rejects `;` and `=` outside `=>`, so `count < limit, oversized = () => count > 0` still splits. `new Map<{ id: string }, number>()` and `new Foo<string, { a: number }>()` are one unit, and the later arrow is reported. The validator names `oversized`.

Review round 10 (Grok, at 4dfe9f2) has one finding, and it is in scope. A1 still requires every named `const` / `let` / `var` arrow and class method. The scanner is a best-effort heuristic. The documented exclusions are only non-ASCII identifiers and a bodiless overload with no terminating semicolon (`docs/file-limits.md`). Neither is this bug. Round 9 ignored `{` but still rejected any `;` in the span.

- **A semicolon inside an object type in a type-argument list.** `_type_args_end` treated any `;` in `<…>` as a comparison. `{ id: string; n: number }` holds a semicolon, so `new Map<string, { id: string; n: number }>(), oversized = () => { … }` returned no functions and the validator printed `OK`. The same reject cut a concise body at the type-argument comma (`also` and `Handler.onChange` were 2 lines). `_type_args_end` now skips a balanced `{…}` while looking for those tokens. A `;`, or an `=` outside `=>`, that sits outside `{}` still rejects, so `count < limit, oversized = () => count > 0` still splits. `new Map<string, { id: string; n: number }>()`, `new Map<{ id: string; n: number }, string>()` and `new Foo<() => { a: string; b: number }, T>()` stay one unit. The concise body keeps the lines after that comma (`also` 8, `Handler.onChange` 8). The validator names `oversized`, exits 1, and does not print `OK`.

The review's Excess note `onChange!: (x) => T = (x) => { … }` is not in `required_changes`. The scan still fails under `Handler.number`, so it does not print `OK`. A1's documented out-of-scope forms are only non-ASCII identifiers and a bodiless overload with no semicolon.

## Changes

- `specy_road/file_limits_js.py` (new): the scanner. Round 4 calls `blank_jsx_text` for `.jsx` / `.tsx`. Round 8 moved its literal masking to `specy_road/file_limits_js_mask.py` (new).
  - It blanks comments, and reduces strings, template literals (nested `${…}` included) and regex literals to a single `"`, without moving any newline. The `"` keeps a literal-only concise body (`` => `#${n}` ``) from reading as empty.
  - It balances brackets on what is left.
  - Concise arrow bodies run to the end of their expression (`_body_end`).
  - It finds the three header forms, including TS generics, overload signatures, typed bindings and return types. Object return types (`): { a: T } {`) are handled.
  - It names methods `Class.method` (computed and string names as source text, `Class.[Symbol.iterator]`) and other nested functions by containment.
- `specy_road/file_limits_engine.py`: `python_function_metrics` now also returns the start line. A new `function_metrics` dispatches by suffix, and `run_file_limits_scan` uses it for every file. Both report lines gain `:<line>` and the "Python-only" labels are gone. The file is 379 lines, under its 400 cap.
- `specy_road/bundled_scripts/validate_file_limits.py`: round 5 updates the generated public help text to name Python and TS/JS function counts.
- `constraints/file-limits.yaml` and `specy_road/templates/project/constraints/file-limits.yaml`: these policy files now say which languages and forms the function cap covers.
- `constraints/README.md`, `specy_road/templates/project/constraints/README.md` (round 2) and `tests/fixtures/specy_road_dogfood/constraints/README.md`: the "Python-only" labels are replaced.
- `tests/fixtures/file_limits_js/`: one fixture per syntax form (`declaration.ts`, `arrow.tsx`, `class_methods.ts`), plus `literals.mjs` for masking. `legacy.js` and `widget.jsx` cover the last two suffixes. Round 1 adds `concise_arrow.ts`, `regex.js` and `division.js`; round 2 adds `generic_class.ts` and `declarators.ts`; round 3 adds `computed_method.ts`; round 4 adds `jsx_text.tsx`; round 6 adds `parenthesized.ts` and `typed_field.ts`; round 7 adds `generic_declarator.ts`; round 8 adds `comparison_declarator.ts` and a `Foo<() => void, T>()` line to `generic_declarator.ts`; round 9 adds `grouped_list.ts` and `object_type_arg.ts`; round 10 adds `semicolon_object_type.ts`.
- `tests/test_file_limits_js.py` (new), plus one assertion added to `tests/test_file_limits_engine.py`.

Final touch zones used: `specy_road/file_limits_engine.py`, `specy_road/file_limits_js.py`, `specy_road/file_limits_jsx.py` (round 4; the scanner was at its 400-line cap, so the JSX blanker is a sibling module rather than an exemption), `specy_road/file_limits_js_mask.py` (round 8, same reason; added under brief section 7), `specy_road/bundled_scripts/validate_file_limits.py` (round 5 module docstring for public `--help`), `constraints/file-limits.yaml`, `specy_road/templates/project/constraints/file-limits.yaml`, `constraints/README.md`, `specy_road/templates/project/constraints/README.md`, `tests/fixtures/specy_road_dogfood/constraints/README.md`, `docs/file-limits.md` (round 4), `tests/`.

## Known limits (by design)

The two forms the amended A1 leaves out of the scanner are documented in `docs/file-limits.md` and the `file_limits_js` module docstring. The rest are heuristic limits.

- **The regex rule is the usual heuristic.** A division at the start of a continuation line (`a\n  / b`) is read as a regex. That masks the rest of that line, or nothing when no closing `/` follows on it. A regex after `)` (`if (x) /re/.test(s)`) is read as a division.
- **`<` does not open a regex, and `/>` is never one.** This is a JSX exception to the operator rule, so `</div>` and `<Foo a={x} />` keep their braces. `a < /re/` and the regex `/>/` are read as divisions.
- **Regexes inside a template's `${…}` are not masked.**
- **Concise bodies in no-semicolon code end at a line break** unless one of the two lines carries a continuation token. A continuation that starts with a keyword (`instanceof`, `as`) on the next line ends the span early.
- **Non-ASCII identifiers are not measured** (amended A1). `function π`, `const λ = () => …` and a method `δ()` produce no metric.
- **A bodiless overload with no terminating semicolon** (amended A1). The overload's name takes the implementation's body. A semicolon after the signature keeps them apart.
- **Some functions are not measured.** Unnamed callbacks (`useCallback(() => {…})`), object-literal methods and anonymous `function` expressions all fall outside the three forms A1 names.
- **A class field whose value starts with `[` on the next line.** In no-semicolon code, `x = y` followed by a line starting `[k]() {` reads the second line as a computed method. JavaScript itself reads it as `y[k]()`.
- **JSX only in `.jsx` and `.tsx`.** A `.js` file that contains JSX is scanned as script. An unclosed tag blanks the rest of that file as text.
- **An empty class body directly followed by a block.** `class A {} {` reads the first `{}` as an object type in the header, because of the same lookahead that handles `): { a: T } {`.
- **A destructuring declarator names no function.** Its pattern is stepped over so later declarators are still found.
- **A type argument that contains `=` outside `=>` and outside `{…}`, or a `>` inside `{…}`.** `Foo<T = string>()` is still not one unit: that bare `=` is how a comparison is told from a type argument, so `count < limit, oversized = …` keeps splitting. A `;` outside `{…}` still rejects. `_angles_end` does not balance braces, so a `>` inside `{…}` (`Map<{ id: a > b }>`) closes the span early. `Map<string, { id: string; n: number }>` and `Map<{ id: string }, number>` have neither, and they are measured.

## Verification

- `pytest -q tests/test_file_limits_js.py tests/test_file_limits_engine.py tests/test_file_limits_gitignore.py tests/test_validate_file_limits.py`: 63 passed (round 10; 61 in round 9, 55 in round 8, 52 in round 7, 49 in round 6, 45 in round 5, 44 in round 4, 42 in round 3). Every earlier fixture still passes, including `object_type_arg.ts`, `comparison_declarator.ts`, `generic_declarator.ts` and `typed_field.ts`.
- Round 10 regression check: `semicolon_object_type.ts` reports `oversized` 5, `short` 1, `tiny` 1, `also` 8 and `Handler.onChange` 8. The public validator on that fixture exits 1, writes no `OK`, and names `oversized`. `comparison_declarator.ts` still reports `oversized`, `small` and `big`.
- Round 8 regression check: on `comparison_declarator.ts` the round-7 scanner returns only `small`, dropping `oversized` and `big`; the round-8 scanner returns all three. Grok's other probes (`count >= 1` on one line, `var`, `ids as Map<string, number>`, `new Foo<() => void, T>()`) each report the later arrow. Across `gui/pm-gantt/src` (77 files) the round-8 scanner agrees with round 6 and round 7 on every file.
- `pytest -q` (full suite, round 3 after the computed-name change): 2356 passed, 2 skipped. The string/number-name follow-up touched only `specy_road/file_limits_js.py` and its own test and fixture, so I reran the focused set after it.
- File caps: `specy_road/file_limits_js.py` is 296 lines (cap 400), `specy_road/file_limits_js_mask.py` 157, `specy_road/file_limits_jsx.py` 134, and the engine 379. No line holds two statements. In round 2 a separate `_class_body` helper took the scanner to 403, so I reused `_type_end` instead of adding an exemption. Round 4 put the JSX blanker in its own module, and round 8 the literal masking.
- Round 4 regression check: the round-3 scanner reports `jsx_text.tsx` as `Greeting` 11 lines containing `Greeting.next` and `Greeting.next.after`. The round-4 scanner reports `Greeting` 5, `next` 2 and `after` 3. `blank_jsx_text` keeps length and newline count. Across `gui/pm-gantt/src` (77 files, 318 functions) the round-3 and round-4 scanners return identical results.
- Round 3 regression check: the round-2 scanner returns no functions at all for `computed_method.ts`. Across that same GUI tree the round-2 and round-3 scanners agreed.
- `python specy_road/bundled_scripts/validate_file_limits.py` (this repo): `OK: file limits satisfied.`
- `python specy_road/bundled_scripts/validate_file_limits.py --help`: description includes `optional Python and TS/JS function counts`.
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
7. Round 4: `blank_jsx_text` in `specy_road/file_limits_jsx.py`, and the fixture `jsx_text.tsx`. The two out-of-scope forms are in `docs/file-limits.md`.
8. Round 5: the module docstring in `validate_file_limits.py` and `test_file_limits_help_names_ts_js_function_counts`.
9. Round 6: the grouping check in `_arrow_body` and the `:` skip in `_class_members`. Fixtures are `parenthesized.ts` and `typed_field.ts`.
10. Round 7: the `<…>` branch in `_body_end`, and `generic_declarator.ts` on the public validator (no `OK`).
11. Round 8: `_type_args_end`, then `comparison_declarator.ts`. `specy_road/file_limits_js_mask.py` is a verbatim move.
12. Round 9: the grouping-paren step in `_declarators`, and `_type_args_end` no longer rejecting `{`. Fixtures are `grouped_list.ts` and `object_type_arg.ts`.
13. Round 10: `_type_args_end` skips a balanced `{…}` before rejecting `;` or `=`. Fixture is `semicolon_object_type.ts` on the metrics test (`also` 8, `Handler.onChange` 8) and the public validator (exit 1, no `OK`, report names `oversized`).

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
  - Round 4: `jsx_text.tsx` added to that test and to `test_scan_measures_concise_arrows_regexes_and_divisions`. The round-3 scanner swallows `next` and `after` into `Greeting`; the assertions name the three spans and Greeting's 5-line report.
- Round 5: `test_file_limits_help_names_ts_js_function_counts`: runs the public `--help` path and asserts its wrapped description names TS/JS.
- Round 6: the `(` branch in `_arrow_body` returns an arrow found inside a grouping paren when `=>` does not follow that paren. `(x) =>` still takes the parameter-list path.
- Round 6: `_class_members` skips a field type with `_type_end(…, "=")` before looking for `=`, so the declared name is kept.
- Round 6: `parenthesized.ts` and `typed_field.ts` are in the per-form metrics test and in `test_scan_measures_concise_arrows_regexes_and_divisions`. The scan assertions require `wrapped` and `Handler.onChange` over the cap.
- Round 7: `_body_end` skips a `<…>` whose matching `>` comes before `{` or `;`, so a comma in `Map<string, number>` is not a declarator break. `generic_declarator.ts` is on the metrics test, the scan test, and `test_validator_does_not_print_ok_with_over_cap_ts_function` (exit 1, no `OK`, report names `oversized`).
- Round 8: `_type_args_end` replaces the inline round-7 condition and also rejects a span with `=` outside `=>`, so a comparison's `<` cannot swallow the next declarator (review finding).
- Round 8: `comparison_declarator.ts` is on the metrics test, the scan test and the validator test. Its over-cap `oversized` and the one-line `big` are both dropped by the round-7 scanner. The new `generic_declarator.ts` line keeps `Foo<() => void, T>()` as one unit.
- Round 8: `specy_road/file_limits_js_mask.py`: a verbatim move of `mask_source`, `_literal_end`, `_quoted_end`, `_template_end`, `_expr_end`, `_regex_allowed`, `_regex_end`, `_ch`, `_ws` and their constants, made to bring the scanner under its cap without joined statements or deleted comments. Nothing new is in it.
- Round 9: `_declarators`, after measuring an arrow whose body starts inside a grouping `(`, continues the list after that `)`. `(x) => body` still starts past the parameter `(`. `grouped_list.ts` is on the metrics test, the scan test and the validator test (exit 1, no `OK`, report names `after`). Its `let also = (async (n) => n + 1), rest` line keeps `rest`.
- Round 9: `_type_args_end` rejects `;` and `=` outside `=>`, and no longer rejects `{`, so `Map<{ id: string }, number>` and `Foo<string, { a: number }>` are one unit. `object_type_arg.ts` is on the same three tests (exit 1, no `OK`, report names `oversized`). `comparison_declarator.ts` still splits.
- Round 10: `_type_args_end` walks the span, skips `=>` and a balanced `{…}` that closes before the `>`, and rejects only a `;` or `=` outside those, so `Map<string, { id: string; n: number }>` is one unit. `semicolon_object_type.ts` is on the metrics test and the public validator (exit 1, no `OK`, report names `oversized`). `also` is 8 lines and `Handler.onChange` is 8; the round-9 scanner reported both as 2 and dropped `oversized`. `comparison_declarator.ts` still splits.
- Round 4: `specy_road/file_limits_jsx.py` `blank_jsx_text`, `_jsx_open`, `_code`, `_jsx_attrs`, `_jsx_kids`, `_jsx_take`: blank JSX text, including text inside an expression's nested element, without moving newlines. `_jsx_open` rejects `<T,>` and `<T extends …>`. The import sits inside `js_function_metrics` so this module can import the literal helpers from `file_limits_js` without a cycle.
- Round 4: `docs/file-limits.md`: the two forms the amended A1 leaves unscanned.
- `tests/test_file_limits_engine.py`: one assertion on the exact Python report line, including `:4`.
- Mocks: none.
