# File limits

`specy-road file-limits` measures function length in Python (`.py`) and in TypeScript and JavaScript (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`). The TS/JS forms are `function` declarations, arrow functions bound by `const` / `let` / `var`, and class methods. The policy file (`constraints/file-limits.yaml`) names the same coverage.

The TS/JS scan is a best-effort bracket heuristic (`specy_road/file_limits_js.py`). In `.jsx` and `.tsx` files, JSX text is blanked before that scan, so it is not read as code: an apostrophe in `<p>Don't</p>` does not open a string.

## Out of scope

These two forms are valid TypeScript or JavaScript and are not measured. The amended acceptance for this check leaves them out of the scanner on purpose.

- **Non-ASCII identifiers.** A name whose first character is outside ASCII is skipped. `function π`, `const λ = () => …`, and a method `δ()` produce no function metric.
- **A bodiless overload with no terminating semicolon.** An overload signature that ends at the line break, directly above its implementation, is not a separate span. The overload's name is reported with the implementation's body, so the implementation's own start line is lost. A semicolon after the signature (`load(a: string): string;`) keeps the two apart.
