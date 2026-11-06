# M21.43 implementation summary

`digest_cli.cmd_digest` now calls `discover_manifest_path(root)` before `render_digest`, the way
`export_roadmap_md.main` does. With no `roadmap/manifest.json`, plain `digest`, `digest --check` and
`digest -o -` print the one line `no roadmap manifest: expected <root>/roadmap/manifest.json` on stderr, exit 1
and write nothing. `render_digest` and the message text are unchanged.

Final touch zones (confirmed, none added or removed): `specy_road/bundled_scripts/digest_cli.py`,
`tests/test_digest.py`, `CHANGELOG.md`.

Call sites outside the zones stay unchanged. `upgrade.py` calls `cmd_digest` with `--check` semantics and uses
`== 0`, so a return of 1 reads as "not current" there; before, a missing manifest raised out of that call.
`tests/test_generated_files.py`, `tests/test_upgrade.py` and `tests/test_init_project_first_run.py` all run with a
manifest and pass unchanged.

Checked by hand in an empty `git init` directory: all three digest forms and `export --check` print the same line,
exit 1, and the directory holds only `.git` afterwards.

## Added

- `digest_cli.cmd_digest`: try/except around `discover_manifest_path` (the guard A1 asks for), printing `str(e)` on stderr and returning 1.
- `digest_cli`: import of `discover_manifest_path` for that guard.
- `tests/test_digest.py::test_no_manifest_is_one_clean_line_and_writes_nothing`, parametrized over plain, `--check` and `-o -`: the A3 cases (exact stderr line, no `Traceback`, exit 1, empty stdout, no `roadmap-context.md`). All three fail without the guard.
- `CHANGELOG.md`: one `[Unreleased]` Fixed entry (A3).
- Mocks: none.
