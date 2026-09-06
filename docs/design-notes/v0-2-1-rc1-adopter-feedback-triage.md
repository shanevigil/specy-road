# Triage: `v0.2.1-rc1` adopter feedback

> **Outcome:** everything classified as a defect below was fixed in
> **`v0.2.1-rc2`**; see the [CHANGELOG](../../CHANGELOG.md) entry for that
> release. This note is kept as the analysis record, in the same form as the
> [`v0.1.4-rc2` triage](rc2-adopter-feedback-triage.md).

Assessment of the handoff written after an adopter upgraded a real consumer
repository from `0.1.4` to `0.2.1rc1` — 107 nodes, 5 phase chunks, 67 open
leaves — exercised both new read-only subsystems, and ran two complete
pickup → implement → finish → PR → merge cycles. Their verdict was **ship it**,
with one defect they considered blocking.

Each item is classified as a **defect**, **working as designed** (documentation
gap), or **feature request**, with the reproduction that decided the call.

## 0. Two findings that had already moved — read this first

Two of the four "carryovers from `0.1.4`, re-verified as still present" do not
match the `0.2.1rc1` code.

| Reported | `0.2.1rc1` reality |
|---|---|
| **#12** "Parent phase status must be flipped by hand after its last leaf completes, or nothing downstream opens. `validate` only warns after the fact." | **Fixed before rc1.** [`finish_ancestor_rollup.py`](../../specy_road/finish_ancestor_rollup.py) closes every stale rolled-up ancestor inside the bookkeeping commit, wired at [`finish_task.py`](../../specy_road/bundled_scripts/finish_task.py); `warn_stale_parent_status` was restored in [`validate_roadmap_checks.py`](../../specy_road/bundled_scripts/validate_roadmap_checks.py). |
| **#16** "`id` is not in `EDIT_WHITELIST` and there is no `move-node`." | `parent_id` **is** whitelisted ([`roadmap_edit_fields.py`](../../specy_road/bundled_scripts/roadmap_edit_fields.py)). The real gap is narrower and was correctly felt: `edit-node --set parent_id=` moves the edge without renumbering. |

**#12 was almost certainly unobservable in their run,** and that is itself a
finding. The rollup fires only when the finished leaf was the *last* open one
under a parent. With 67 open leaves across 5 phases, finishing 2 left no parent
eligible — and the pass prints nothing when it has nothing to do, so it is
indistinguishable from not existing. There is also a real residual: it
deliberately skips nodes carrying `milestone_execution`, so on the
`start-milestone-session` path the manual flip **is** still required. Both are
now stated in `finish-this-task -h` and
[`dev-workflow.md`](../dev-workflow.md) — §4 below.

None of this makes the substance of the report wrong. The `--force` defect is
exactly as described, and worse than described.

## 1. `specyrd init --force` writes outside its own manifest — defect, confirmed

Reproduced. [`specyrd_init.py`](../../specy_road/specyrd_init.py) performed a
whole-file `write_text` of a 52-line template over the repo root's `CLAUDE.md`,
armed unconditionally for `--ai claude-code` by
[`specyrd_cli.py`](../../specy_road/specyrd_cli.py). There was no flag to opt
out and no prompt.

The adopter's argument that this is a scope violation rather than misuse is
correct, and their three pieces of evidence are the right three: the `--force`
help text promised only stubs and the README; `.specyrd/README.md` documents
re-running `init` as a supported flow; and `.specyrd/manifest.json` — the
toolkit's own record of what it manages — never listed `CLAUDE.md`.

**Three further hazards of the same shape**, found while confirming it, that the
report did not reach:

1. **`--force` also clobbered `~/.specy-road/gui-settings.json`**, replacing the
   user's saved OpenAI/Anthropic API keys with an empty stub. That file is
   **outside the repository**, so `git checkout --` — the adopter's recovery —
   would not have helped. Reached whenever `gui` is in `--extras`.
2. **Nested layouts got a wrong guide.** The project prefix was computed and
   applied only to the ignore blocks, so a project under `sr/` received a
   `CLAUDE.md` whose every `roadmap/`, `constitution/` and `shared/` pointer was
   wrong. The old template also pointed at `docs/git-workflow.md` and
   `docs/roadmap-authoring.md`, which `init project` does not scaffold.
3. **`--dry-run` under-reported.** The managed-block pass sat inside
   `if not dry_run:`, so a dry run never previewed the `.gitignore` /
   `.cursorindexingignore` changes. The adopter's "I ran it without `--dry-run`
   first" is fair self-criticism, but a dry run would not have shown them the
   whole picture either.

**Fix — their second suggestion, not their first.** They offered three, cheapest
first: restrict `--force` to the manifest; use the managed-block pattern; or
require a second flag. The managed block is the one that makes the other two
unnecessary, and they were right that it is the design to reuse.
[`managed_block`](../../specy_road/managed_block.py) grew a `MarkerStyle` —
`HASH` stays the default so the ignore files keep their exact bytes, and
`HTML_COMMENT` serves Markdown, where a `#` marker would render as a heading in
the middle of someone's document. `CLAUDE.md` is now one merged section, and it
**is** listed in the manifest, so `--force`'s blast radius is exactly what the
manifest records. The GUI settings file is never overwritten; `--dry-run`
reports both blocks.

## 2. No consumer-side refresh path — defect (missing command), confirmed

Confirmed, and their framing is the correct one: this is the gap that *caused*
§1. `specy-road update` is a git-clone fast-forward and says PyPI installs
cannot use it; `refresh-schemas` covers `schemas/`; `init` skips existing files.
`0.2.1rc1` made it bite harder by shipping three stubs — `specyrd-search`,
`specyrd-digest`, `specyrd-history` — that an existing consumer could obtain
only by force-overwriting.

**Fix — `specy-road refresh-stubs`, built as they specified.** Modeled directly
on [`refresh_schemas.py`](../../specy_road/bundled_scripts/refresh_schemas.py):
same file shape, same flags (`--repo-root`, `--dry-run`, deliberately no
`--force`), same output voice. It reads the manifest for the installed packs and
role, rewrites only those paths, adds newly-shipped stubs, bumps
`specyrd_version`, re-applies every managed block, and reports
added/updated/unchanged.

One deliberate departure from the suggestion. Re-running `init` with a narrower
`--role` replaces the manifest's path list wholesale, so a repo can hold stubs
that dropped out of it. Those orphans are **reported, not deleted** — quietly
removing a file we no longer claim to manage is the mistake this command exists
to undo.

Paired with their guardrail: `init` on an initialized repo now names
`refresh-stubs` before doing anything, and `validate` warns while the manifest's
`specyrd_version` lags — the passive-nag pattern `warn_if_schemas_stale`
established.

## 3. `history` sort orders — working as designed, undocumented

Confirmed exactly as reported, and pinned by tests both ways:
`feed` is newest-first and `node_timeline` is oldest-first
([`history_index.py`](../../specy_road/history_index.py)). Their own reading of
why — "a feed reads like a changelog, a node reads like a story" — is the
rationale, and it now appears in the `-h` text nearly verbatim.

Fixed as documentation plus the flag they offered as the alternative: both are
stated in the description and the positional's help, `--reverse` flips whichever
view is active, and `--limit` finally has a `help=` string at all. Its meaning
differs subtly between the views (`out[:limit]` versus `events[-limit:]`) while
selecting the same events, which is worth one sentence.

## 4. `digest --check` and tracking `roadmap-context.md` — working as designed, undocumented

Confirmed. The intent was already unambiguous in the code and in
[`agent-search.md`](../agent-search.md) ("Commit it"), and deliberately encoded
in the scaffold `.gitignore` by *omission* — but the `-h` text never said so,
and `.specyrd/README.md` was 14 lines that mentioned only `validate`, `brief`
and `export`.

Their inference was sound, so the gap is ours. Now stated in the `digest`
description, in `--check`'s help, in the scaffold `.gitignore` as an explicit
comment rather than a silent omission, and in a rewritten `.specyrd/README.md`.

**And we were not dogfooding it.** This repository gated CI on
`export --check` for the dogfood fixture and had no `digest --check` anywhere.
The fixture's `roadmap-context.md` is now committed with a drift gate, so the
asymmetry the adopter reasoned from no longer exists in our own tree. Fixing
that also surfaced a small bug of its own: `.specyrd/cache/` is anchored to the
git root, so the fixture's derived cache showed as untracked whenever a command
was run against it by hand.

## 5. `--under <LEAF_ID>` — working as designed, undocumented

Confirmed: `subtree_node_ids` includes the root id, so a leaf id yields a
one-leaf scope and nothing rejects it. The adopter is right that this is how a
human picks work out of outline order, and right that nothing said so — the
metavar read `PARENT_NODE_ID` in all three places, and the empty-scope error
said "under parent", which sends someone who passed an already-claimed leaf
looking for the wrong kind of mistake.

Fixed as documentation: metavar `NODE_ID`, both cases named in every help
string, and a corrected empty-scope message.

## 6. Carryover #15 — `edit-node --set title=` rewrites the codename — defect, confirmed

Confirmed; `maybe_sync_codename_from_title` was unconditional. Their diagnosis
of the severity is right: the codename is the branch identity
(`feature/rm-<codename>`) and the registry key that `finish-this-task` matches a
branch against, so a retitle silently moved a live branch off its node.

**Their prescription was also right, including the part that looks like it needs
a schema change and does not.** They asked to "derive only when the codename is
missing or was itself auto-derived". The roadmap schema is
`additionalProperties: false`, so there is no room for a provenance field — but
none is needed: a codename equal to its own *old* title's slug is one specy-road
derived. A hand-picked one now stands, with a printed note naming both values,
and `--sync-codename` overrides.

`apply_set` also backs the PM GUI's node PATCH, so GUI title autosave inherits
the guard. That is the outcome we want, and it passes no notifier, so the
preservation is silent there.

## 7. Carryover #16 — no `move-node` — feature request, granted

The report's diagnosis is slightly off (`parent_id` is whitelisted) but its
conclusion is exactly right, and so is its suggestion: `roadmap_outline_ops.py`
already implements the move and renumber, GUI-only, and exposing it is the fix.

Two things had to be settled first.

**A move renumbers,** and the report does not mention that. The subtree takes new
ids and so do both sibling ranges it leaves and joins. That is correct — an id is
a position in the outline, not an identity, which is what `node_key` is for — but
a command that changed ids silently would be the same surprise §6 exists to
prevent, so `move-node` prints the `old -> new` map.
`renumber_display_ids_inplace` already returned it; everything but the registry
sync discarded it.

**It was not atomic.** `move_node_outline` persisted chunks, renamed planning
sheets and rewrote the registry, and only then validated — so a rejected move
left all three behind and the roadmap unloadable. That is §1a of the `v0.1.4`
triage, fixed for `edit-node` at the time and never fixed here. Putting a CLI
over it as-is would have shipped a known defect, so the move now stages the whole
transaction through `AtomicWritePlan`, and `move_node_outline` delegates to it —
which repairs the GUI's drag, indent and outdent too.

**Known adjacent gap, deliberately not fixed here:** `reorder_siblings` has the
same persist-then-validate shape. It is a smaller blast radius (no reparent, no
cross-chunk move) and out of scope for this batch, but it should get the same
treatment.

## 8. Carryover #14 — `--push` does not open the PR — feature request, deferred again

Unchanged from the `v0.1.4` triage, which deferred it: this is by design, the
printed command is correct and pasteable, and
[`work_artifact_rel_paths`](../../specy_road/finish_work_artifacts.py) documents
why the pr-body snapshot survives cleanup because of it.

The case for building it is stronger the second time it is asked, and
`print_finish_tail` is the natural hook — it already holds the branch, base,
title and body path. What it does not have is precedent: there is no `gh` or
`glab` invocation anywhere in the toolkit, so this adds an external-binary
dependency surface (availability probe, auth failure, non-GitHub forges) that
deserves its own change rather than riding along in a batch whose subject is a
data-loss path.

Deferred, with the reasoning recorded so the answer is visible rather than
silent for a second round. `--push`'s help text now says plainly that it does
not open the PR.

## Recommendation for `0.2.1`

Their priority ordering was followed as given.

**Fixed in `v0.2.1-rc2`:**

1. `specyrd init --force` restricted to the manifest, `CLAUDE.md` merged as a
   managed block — §1.
2. `specy-road refresh-stubs`, plus the `init` guardrail and a `validate`
   warning — §2.
3. `edit-node` codename guard and `--sync-codename` — §6.
4. `specy-road move-node`, and the atomicity repair it required — §7.
5. Help text and documentation for `history` ordering, `digest` tracking,
   `--under <LEAF_ID>`, and the ancestor rollup — §3, §4, §5, §0.

**Deferred:** opening the PR from `--push` — §8; making `reorder_siblings`
atomic — §7.

**Worth saying back to the adopter:** #12 is already fixed and they should
re-test it deliberately (finish the last open leaf under a parent), and their
`docs/commands.md` fix on their side is the right one — `init --force` was never
the post-upgrade step, and now there is a command that is.
