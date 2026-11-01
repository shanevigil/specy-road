# Implementation summary: M4.18 — further TS/JS syntax forms for the function cap

Base: `a57bdf3`. Implementation commit: `f236dc2`.

## Forms covered

This leaf's planning sheet is still the template, so the forms come from where A1 points: M4.12's later review rounds. Its round at `35ff31c` (`REVIEW-cursor-grok-4.6-high.md`, Excess) recorded two forms for M4.18. The other reviews of that round recorded none.

1. **Definite-assignment bang on a class arrow field.** At base, `onChange! = () => {…}` and `onChange!: { a: string } = () => {…}` returned `[]`, and `onChange!: (x: number) => number = (x) => {…}` was reported as `Handler.number`. `_OPTIONAL_RE` now accepts `!` as well as `?` after a member name, so all three report under the field's name.
2. **`as` / `satisfies` after a grouped arrow.** At base, `const wrapped = ((x) => x + 1) as Foo, after = () => {…}` reported only `wrapped`, and the same happened with `satisfies Fn<number, number>`. After the group's `)`, `_declarators` now skips a cast keyword and its type (through `_body_end`, which already skips type arguments) before looking for the comma. Code at base gives `[('wrapped', 1, 1), ('checked', 6, 1)]` on the new fixture. The branch gives all four declarators.

## Acceptance

- **A1:** each form has its own fixture: `tests/fixtures/file_limits_js/definite_field.ts` (bare, object-typed and function-typed `!` fields) and `cast_after_group.ts` (`as Foo` and `satisfies Fn<number, number>`). Each fixture gets a span check in `test_js_function_metrics_per_syntax_form` and a public-validator check in `test_validator_does_not_print_ok_with_over_cap_ts_function` (exit 1, no `OK`, the report names the field or the later declarator).

## Final touch zones used

`specy_road/file_limits_js.py` and `tests/`. Zones not needed: `specy_road/file_limits_js_mask.py` and `specy_road/file_limits_jsx.py`. `docs/file-limits.md` lists only what is out of scope, so it needed no change.

## Verification

- `python -m pytest -q tests/test_file_limits_js.py tests/test_file_limits_engine.py tests/test_file_limits_gitignore.py tests/test_validate_file_limits.py`: 67 passed.
- `ruff check specy_road/file_limits_js.py specy_road/file_limits_js_mask.py specy_road/file_limits_jsx.py tests/test_file_limits_js.py`: all checks passed.
- `specy-road file-limits`: `OK: file limits satisfied.`
- Full `pytest`: **not completed.** Several other agents were running full suites on this machine at the same time (load average about 80 on 18 cores). Three tries, the whole suite, a third of it and a sixth of it, each ran past the 10-minute command limit. The sixth had passed 31 tests after 17 minutes, all green before it was stopped. The changed code is reached only through `file_limits_js.py` (`js_function_metrics`), and the four focused files above cover all of its callers (metrics, scan and validator). A reviewer on a quieter machine should rerun the full suite.

## Added

- `_OPTIONAL_RE` accepts `!` (`[?!]?`): makes form 1 measurable, and keeps a typed `!` field's name instead of the `T` in its type.
- `_CAST_RE` (`as` / `satisfies`): finds the cast that follows a grouped arrow (form 2).
- `_initializer_end` helper: the existing grouped-arrow comma logic, moved out of `_declarators` with the new cast skip. Without the move, ruff's C901 fails `_declarators` at 11 > 10.
- Fixture `definite_field.ts`: form 1 (bare, object-typed and function-typed field).
- Fixture `cast_after_group.ts`: form 2 (`as` and `satisfies` with a comma in the type arguments).
- Two `test_js_function_metrics_per_syntax_form` cases: spans and names for each form.
- Two `test_validator_does_not_print_ok_with_over_cap_ts_function` cases: at base, the public validator printed `OK` on both forms.
- Mocks: none.
