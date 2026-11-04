## Intent

Remove the friction two adopters hit upgrading from 0.3.1rc2 to rc3: not knowing which install was running, an upgrade dry run that could not show a breaking validate error, a managed AGENTS.md block that pushed a project file over its line cap and duplicated the project's own rules, a milestone rollup that silently changed under the new full-review hold, model profiles written for vendors the project never rostered, and an RC install recipe that let dependencies resolve from TestPyPI. The feedback is sanitized; no adopter is named anywhere in this phase.

## Approach

- Seven small leaves, each owning a distinct set of files so they can run in parallel. The one ordering: M13.2 (upgrade output) depends on M13.1 (the launcher/version helper it prints).
- Every change is a notice, an opt-in, or a safer default; nothing deletes adopter files or edits text outside managed blocks.
- Feedback item map: 1 → M13.2 (file-limits after writes) and M13.3 (block size); 2, 7d → M13.3; 3 → M13.4; 4 → M13.5; 5, 10, 12 → M13.1 (+ M13.2 header); 6, 8, 9, 10 (docs) → M13.6; 7a, 9 (help text), 11 → M13.2; 7b, 7c, 13 → M13.7.
- Done when all leaves are Complete; an rc upgrade on a scratch project shows the install, the dry-run validate, the held-milestone notices and no stray profiles.

## Tasks / checklist

- [ ] M13.1 — which install is running; managed blocks written by another version.
- [ ] M13.2 — upgrade header, dry-run validate, file-limits on its own writes, help text.
- [ ] M13.3 — pointer-only AGENTS.md block option; duplicate-text notice; per-harness totals.
- [ ] M13.4 — milestone review hold visible in validate, list-nodes, why-blocked.
- [ ] M13.5 — roster-only profiles; alias suggestion.
- [ ] M13.6 — RC install recipe, pipx/uv tool, which binary is on PATH (docs).
- [ ] M13.7 — symlinked skill dirs, new ignore rules over existing files, session end wording.
- Out of scope: changing the milestone full-review policy itself, release/version numbers, and anything that edits project text outside managed blocks.

## References

- Roadmap chunk for `M13` (`roadmap/phases/M13.json`)
- `specy_road/bundled_scripts/upgrade.py`, `docs/install-and-usage.md`
- No `shared/` contract applies.
