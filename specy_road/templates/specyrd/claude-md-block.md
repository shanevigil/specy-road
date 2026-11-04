## specy-road

Written by specy-road {{SPECYRD_VERSION}}; `specy-road upgrade` rewrites only this section. Everything outside the markers around it is yours.

@{{PROJECT_PREFIX}}.specyrd/AGENTS.md
@{{PROJECT_PREFIX}}.specyrd/AGENTS.team.md

- The two imports above are specy-road's rules for every agent and this repository's additions to them; Claude Code loads both with this file. Read `{{PROJECT_PREFIX}}.specyrd/AGENTS.local.md` too when it exists (personal, gitignored). Addenda add to the rules, never relax them.
<!-- prevents: Claude Code sessions missing the rules that AGENTS.md only points at | enforced: Claude Code expands @ imports at launch; validate counts the imported files | ref: https://code.claude.com/docs/en/memory, Import additional files -->
- Claude Code skips `{{PROJECT_PREFIX}}AGENTS.md` while this file exists, so the project's own rules there reach you only if this file imports it (`@{{PROJECT_PREFIX}}AGENTS.md`, outside these markers).
<!-- prevents: a team's AGENTS.md rules silently unread in every Claude Code session | enforced: advisory | ref: https://code.claude.com/docs/en/memory, When Claude Code reads AGENTS.md -->
