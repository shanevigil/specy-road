# Dev workflow: consuming and executing roadmap items

This document is for the person (or agent) **executing** roadmap work — a developer or coding agent who picks up an `Agentic-led` milestone, implements it against contracts, and merges back.

The complementary guide for PMs is [pm-workflow.md](pm-workflow.md).

---

## Your role in the system

| You own | You do not touch |
| --- | --- |
| Branch, implementation, tests, merge | Roadmap YAML authoring (PM territory) |
| Registry claim (first commit) | Human-led gate decisions |
| Pre-commit validation passing | `shared/` contracts (read only; flag gaps to PM) |
| Removing registry entry before merge | Authoring new roadmap nodes |

If you find an `agentic` task whose `agentic_checklist` is incomplete or whose `spec_citation` does not exist — **stop**. Flag it to the PM before starting implementation. A missing contract is a gap in planning, not a gap to fill during implementation.

---

## Day-in-the-life: four stages

### 1. Find work

```bash
specy-road export            # regenerate index (or read roadmap.md if current)
```

Open [`roadmap.md`](../roadmap.md). Look for milestones where:
- `execution_milestone` is `Agentic-led` or `Mixed`
- `status` is `Not Started`
- All `dependencies` nodes are `Complete`

Check [`roadmap/registry.yaml`](../roadmap/registry.yaml) — confirm no active entry claims overlapping `touch_zones` with your intended milestone.

If two milestones look parallel-safe (no shared touch zones, no dependency edge), `specy-road validate` is your check — a clean run means it is safe to proceed concurrently.

### 2. Get context

Generate a focused brief for your node:

```bash
specy-road brief <NODE_ID>
# save it for in-session reference:
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md
```

The brief gives you: ancestor chain, node fields, dependencies, and the list of contracts in `shared/` to read selectively. **Read the contracts your task cites** — do not implement from the roadmap prose alone.

Full field reference if you need to interpret YAML directly: [roadmap-authoring.md — Node fields reference](roadmap-authoring.md#node-fields-reference).

### 3. Register and implement

**Branch naming:** `feature/rm-<codename>` where `<codename>` matches the milestone's `codename` field exactly.

```bash
git checkout -b feature/rm-<codename>
```

**First commit — registration (mandatory, no implementation before this):**

1. Add an entry to [`roadmap/registry.yaml`](../roadmap/registry.yaml):

```yaml
entries:
  - codename: <codename>
    node_id: <NODE_ID>
    branch: feature/rm-<codename>
    touch_zones:
      - path/to/affected/dir/
    started: "<YYYY-MM-DD>"
    owner: "<your name or agent ID>"
```

2. Commit: `chore(rm-<codename>): register as in-progress`

The pre-commit hook runs `specy-road validate` automatically — fix any errors before the commit lands.

**During implementation:**
- Stay within declared `touch_zones`. If scope expands, update the registry entry and notify the PM.
- The pre-commit hook validates on every commit. Fix validation errors immediately — do not accumulate them.
- CI runs the full suite on push: validate → export check → file limits → pytest.

### 4. Merge back

1. **Update the milestone status** in the relevant chunk YAML file (`status: Complete`).
2. **Remove your registry entry** from `roadmap/registry.yaml`.
3. Run `specy-road validate` and `specy-road export` locally — confirm both pass cleanly.
4. Open a PR/MR targeting your integration branch. CI must be green.
5. Merge when CI passes — you own this branch end-to-end. No PM sign-off required.
6. Delete the feature branch after merge.

---

## Validation and CI

| Command | When it runs | Owned by |
|---------|--------------|---------|
| `specy-road validate` | Every commit (pre-commit hook) | You |
| `specy-road export --check` | CI on push/PR | CI |
| `specy-road file-limits` | CI on push/PR | CI |
| `pytest` | CI on push/PR | CI |

Install the pre-commit hook once per repo clone:

```bash
pip install pre-commit
pre-commit install
```

If validation fails, read the error output — it names the offending node ID, field, or file. Do not bypass the hook (`--no-verify`) to make the commit land.

---

## Reading the agentic checklist

Every `agentic` sub-task in the roadmap has an `agentic_checklist`. These five fields define the contract for your implementation:

| Field | What it tells you |
|-------|------------------|
| `artifact_action` | Exactly what to build or change |
| `spec_citation` | Which doc/section to conform to — **read it** |
| `interface_contract` | Inputs → outputs (API shape, file format, component props) |
| `constraints_note` | Security, performance, or UX rules that bind you |
| `dependency_note` | What must exist before you start |

Optional fields:

| Field | What it tells you |
|-------|------------------|
| `success_signal` | Observable behavior or test that confirms done |
| `forbidden_patterns` | Explicit prohibitions — do not do these even if they seem simpler |

If any of the five required fields is empty or vague, flag it to the PM before writing code.

---

## Multi-agent coordination

When multiple developers or agents are running simultaneously:

1. **Check the registry first** — `specy-road validate` emits warnings on nested touch zone overlaps.
2. **Prefer git worktrees** for parallel agents on the same machine — they get isolated working directories on disjoint branches.
3. **Never start implementation** on a branch whose touch zones overlap an active registry entry — coordinate first.
4. **Milestone dependencies are hard stops** — a `dependencies: [M1.1]` means M1.1 must be `Complete` before you start M1.2, regardless of whether touch zones conflict.

Full parallelism rules: [git-workflow.md — Parallelism rules](git-workflow.md#parallelism-rules).

---

## Quick reference

```bash
specy-road validate          # validate roadmap YAML + registry
specy-road brief <NODE_ID>   # get focused brief for your node
specy-road export            # regenerate roadmap.md
specy-road file-limits       # check line-count constraints locally
```

Read the [git workflow guide](git-workflow.md) for branch conventions, first-commit registration details, and merge-back protocol.
