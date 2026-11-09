# AGENTS — the specy-road toolkit repository

**This file is the one agent entry for contributors working on the `specy-road` package** (Python package, validators, optional PM UI). `CLAUDE.md` only imports it and adds Claude-specific notes. If you are building an **application** with specy-road, use the `AGENTS.md` created by `specy-road init project` in your repo instead.

Root `constitution/` here describes the **toolkit**; consumer application repos get their own scaffold from `specy-road init project` (see [`specy_road/templates/project/`](specy_road/templates/project/)).

**Docs win:** prefer tracked repo docs over chat history.

### Load order

Always (keep context small):

1. `constitution/purpose.md`
2. `constitution/principles.md`
3. `constraints/README.md` — limits for **this** repo (package + tests)

By task, only what it needs:

- **Orchestration or review** (workers, roster, review gate, grind): [`docs/orchestration.md`](docs/orchestration.md) and the `docs/orchestration-*.md` page it points to.
- **Roadmap data** (graph shape, registry, planning sheets, `init project` layout): [`docs/roadmap-authoring.md`](docs/roadmap-authoring.md) and [`docs/git-workflow.md`](docs/git-workflow.md); keep [`suggested_prompts/`](suggested_prompts/) in step with any format change.
- **Dependencies or release:** [`docs/supply-chain-security.md`](docs/supply-chain-security.md) for any dependency change; [`docs/release-runbook.md`](docs/release-runbook.md) to cut a release (see [Cutting a release](#cutting-a-release)).
- **The dogfood fixture** (validation and sample data only, not the toolkit's product roadmap): [`tests/fixtures/specy_road_dogfood/roadmap/`](tests/fixtures/specy_road_dogfood/roadmap/), its [flat `planning/*.md` sheets](tests/fixtures/specy_road_dogfood/planning/README.md), then its [`shared/README.md`](tests/fixtures/specy_road_dogfood/shared/README.md) and only the cited contracts. Brief: `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md --repo-root tests/fixtures/specy_road_dogfood`.
- **`sr/` roadmap work** (the toolkit's own product roadmap, on the `WIP/improvements-x-y-z` line only): [`sr/AGENTS.md`](sr/AGENTS.md), `sr/vision.md`, then `sr/roadmap-context.md`. `.specyrd/manifest.json` records `project_root: sr`; run roadmap commands from the checkout root and they resolve `sr/`. `sr/` is stripped before promotion and never ships.

## Coordination

The dogfood tree is a **test-fixture roadmap**, not the canonical product roadmap for the `specy-road` toolkit. Do not register ordinary toolkit implementation work in [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](tests/fixtures/specy_road_dogfood/roadmap/registry.yaml) unless the work is specifically exercising or updating the fixture.

**Branches:** the toolkit's branch, PR and promotion policy is stated once, in [`docs/toolkit-development.md`](docs/toolkit-development.md#maintainer-workflow-vs-consumer-workflow). For the consumer-repo contract and registry, read [`docs/git-workflow.md`](docs/git-workflow.md).

If this repository ran **`specyrd init`**, you may have skills under `.agents/skills/<name>/SKILL.md` (with `.claude/skills/` symlinks for Claude Code, or a flat stub directory for `--ai generic`; `.cursor/commands/` and `.claude/commands/` only in repos initialised before 0.3.0) — they delegate to `specy-road` / bundled scripts.

## Lean changes and tests

- Make the smallest behaviour-complete change; no configurability, fallbacks or abstractions the task did not ask for.
- Before adding a helper, search for an existing one (`specy-road search`, then grep the verb and noun); reuse or extend it and name it in your summary.
- Validate at boundaries only (CLI args, files, network, env, agent input). No guard or `except` without a nameable reachable trigger and a test that reaches it.
- One test per observable behaviour, through the public interface. Assert outputs, raised errors or file/state effects, not call order or mock counts; never import or patch a `_`-prefixed name in a test.
- Extend or parametrize an existing test before adding one. A review finding needs a new test only for a distinct regression.
- Merging or removing a test is allowed when another test covers the behaviour and the commit names it. This overrides any general "never remove or edit tests" instruction.
- Never weaken, rewrite or delete a failing behavioural test to make the suite pass.
- Never commit machine-, user- or developer-specific values (home or temp paths, hostnames); resolve them at run time.
- Stop when the behaviour list is covered and the gates pass. Then list every helper, branch or guard, mock and test you added, each with its reason.

## Maintainer hygiene

- **Reuse:** extend `specy_road/bundled_scripts/` and tests before adding new entrypoints.
- **Adoption prompts:** [`suggested_prompts/`](suggested_prompts/) must match the real formats (templates under `specy_road/templates/project/`, JSON schemas, validators, `docs/roadmap-authoring.md`). A significant change to graph shape, registry rules, the `init project` layout or another format those prompts describe updates the affected `suggested_prompts/*.md` in the same change set or immediately after.
- **PM Gantt UI:** after changing [`gui/pm-gantt/`](gui/pm-gantt/), run `npm ci && npm run lint && npm test && npm run build` there (ESLint 10 with `@eslint-react/eslint-plugin`; see [`docs/contributor-guide.md`](docs/contributor-guide.md#supply-chain--dependency-audits)).
- **Gates:** `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`, `specy-road file-limits`, `pytest -n auto` ([`docs/toolkit-development.md`](docs/toolkit-development.md#validate-and-test-dogfood-fixture)).

## Version numbers (human-owned)

Do **not** choose, bump, or retarget a toolkit version unless the user has stated the exact number in this conversation. That includes `pyproject.toml` `project.version`, `CHANGELOG.md` `## [v…]` headings, git tags, `WIP/improvements-x-y-z` names, `chore/release-v*` branches, and prose that treats an unpublished checkout as a released version. Patch vs minor vs major is not the agent's call; chat history, "this feels like a minor" or a WIP branch name is not approval. The user stating a number in this conversation **is** approval for that number only.

When a number is needed, stop, print this block, and wait for the user's reply with the exact version or tag; edit no version file, tag or branch until then:

```text
VERSION DECISION NEEDED
- Published on PyPI: <pip index / pypi.org>
- Declared in this checkout (`pyproject.toml`): <project.version>
- Git tags on this clone: <latest v* tag>
- Proposed next (optional, not chosen): <X.Y.Z or vX.Y.Z-rcN>
Please confirm the exact version/tag. I will not edit version files until you reply with the number.
```

**Release / tag parity:** a promotion PR to `main` bumps `project.version`, adds or extends the matching `## [v…]` section in `CHANGELOG.md`, and syncs maintainer prose that cites the current version; CI ([`scripts/check_release_version.py`](scripts/check_release_version.py)) checks the tag against `project.version`. `specyrd init` stubs and `.specyrd/manifest.json` read `specy_road.__version__`; if they look wrong, fix `project.version` or reinstall, not template placeholders.

## Cutting a release

When the user asks to publish (RC or final), follow [`docs/release-runbook.md`](docs/release-runbook.md) verbatim. Do **not** improvise. Two examples:

- *"Publish v0.3.1-rc1 to TestPyPI"* → runbook §A (RC flow). Tag form `v0.3.1-rc1`; pyproject `0.3.1rc1`; routes to TestPyPI.
- *"Publish v0.3.1 to PyPI"* → runbook §B (final flow). Tag form `v0.3.1`; pyproject `0.3.1`; routes to PyPI; back-merge to `dev` is mandatory.

A line's first tag is `x.y.1-rc1` and later candidates count up (`-rc2`, `-rc3`); `x.y.0` is never used. The maintainer chooses the number; the form above is fixed.

The user owns these runbook §2 steps: **choosing the exact version/tag (2.2)**, the **manual tag re-push** when `RELEASE_TAG_TOKEN` is unset (footgun ④), the **`pypi` environment approval** on finals (footgun ⑨), and the **live-on-(Test)PyPI confirmation**. The agent prints the exact commands and waits. Check whether 2.12 / 2.12a apply before starting — see the runbook matrix.
