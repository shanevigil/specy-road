# File limits

`specy-road file-limits` measures function length in Python (`.py`) and in TypeScript and JavaScript (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`). The TS/JS forms are `function` declarations, arrow functions bound by `const` / `let` / `var`, and class methods. The policy file (`constraints/file-limits.yaml`) names the same coverage.

When a run fails, the command prints one line pointing at `override_limits` in that file and `specy-road file-limits --write-baseline`. That flag appends `override_limits` entries (named `baseline-<date>-<n>`) so every file failing today passes at its current size: files are grouped into buckets by file length and worst function length, each rounded up (50 lines and 20 lines respectively). Files that already pass get no entry, so new files keep the default caps. Use `--write-baseline --dry-run` to print the entries without writing. Re-running `--write-baseline` when nothing fails adds nothing; existing comments and entries in the YAML are kept.

`specy-road upgrade` runs file-limits at the end, prints the failure count once (the running install is the only measurement available after the refresh), and never fails upgrade on that count. When failures remain, it notes that measurement rules may have changed and points at `--write-baseline`.

The TS/JS scan is a best-effort bracket heuristic (`specy_road/file_limits_js.py`). In `.jsx` and `.tsx` files, JSX text is blanked before that scan, so it is not read as code: an apostrophe in `<p>Don't</p>` does not open a string.

## Out of scope

These two forms are valid TypeScript or JavaScript and are not measured. The amended acceptance for this check leaves them out of the scanner on purpose.

- **Non-ASCII identifiers.** A name whose first character is outside ASCII is skipped. `function π`, `const λ = () => …`, and a method `δ()` produce no function metric.
- **A bodiless overload with no terminating semicolon.** An overload signature that ends at the line break, directly above its implementation, is not a separate span. The overload's name is reported with the implementation's body, so the implementation's own start line is lost. A semicolon after the signature (`load(a: string): string;`) keeps the two apart.
