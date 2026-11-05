# Implementation summary: M13.8

## What changed

- **A1** — New `specy_road/behaviour_changes.py`: `BehaviourChange` frozen dataclass (`since`, `command`, `flags`, `now`, `contradicts`) and `CATALOGUE` with five entries:
  1. `mark-implementation-reviewed --yes` (0.3.1rc1): `--yes` never creates a review, so an agent never approves its own work.
  2. `finish-this-task --on-complete/--override-on-complete` (0.3.1rc3): a mode that differs from the recorded one is refused without the override.
  3. `do-next-available-task --local` (0.3.1rc1): pickup does not always push.
  4. `finish-this-task --delete-branch` (0.3.1rc2): finish can delete the branch.
  5. `do-next-available-task --base` (0.1.0rc1): pickup registers on the integration branch before the feature branch exists (A4).
  The `since` versions come from the CHANGELOG sections that introduced each change. Patterns 1–4 require the command's name on the same line (pattern 3 also accepts "pickup", but only on a line that also says "claim"). Pattern 4 also needs "branch" after the "delete" phrase. Pattern 5 has no command, so a line must contain "first commit", the verb "register" (or registers/registered/registering), and a specy-road claim term: feature branch, `registry.yaml`, or "register as in-progress".
- **A2** — New `specy_road/agent_text_report.py`: `warn_contradicted_instructions(project_root)` reads the files `validate_stale_commands.agent_files()` returns (root and git-root `AGENTS.md`/`CLAUDE.md`, plus `.specyrd/AGENTS.team.md`). It uses `managed_block.agent_file_lines_outside_block` to drop the managed block. That helper already wraps the `_split` logic and keeps the original line numbers. It prints one notice per matching source line on **stdout**: `agents: notice — <file>:<line>: says "<excerpt>"; since <since>: <now>`. When a line matches more than one entry, the `since …: …` parts are joined with `; ` in that same notice. That makes it a notice, so `--strict` does not count it. It never writes to the files.
- **A3** — `_REQUIREMENT_PIN`, `pinned_version` and `warn_if_pin_differs` moved to new `specy_road/version_pin.py`. `validate_roadmap.py` imports them back (they are still in `__all__`), so `vr.pinned_version` and `vr.warn_if_pin_differs` still work. Imports that became unused were removed. `validate_at` gains one call, `warn_contradicted_instructions(root)`, after `warn_unregistered_commands(root)`. `validate_roadmap.py` is now 359 lines (was 398).
- **A4** — `docs/roadmap-authoring.md` "Before starting implementation" steps 3 and 4 now give the real order: register on the integration branch first (push unless `--local`), then branch. The file is still 400 lines.

## Touch zones

The final list matches the PM list: `specy_road/behaviour_changes.py`, `specy_road/agent_text_report.py`, `specy_road/version_pin.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`, `docs/roadmap-authoring.md`. Nothing outside the zones changed. The callers of `validate_roadmap` outside the zones import only `validate_at`, which still works the same way.

## Rework (review by gpt-6.1-sol of 4f12fad3)

- **R1** (class: one source line matching several catalogue entries). `contradicted_lines` now yields `(line number, line, entries)` once per line, and the reporter prints one notice that lists every matching entry's current behaviour. Grouping happens where lines are produced, so no caller can emit more than one notice per line.
- **R2** (class: a catalogue pattern matching prose unrelated to the old instruction). The first-commit pattern now needs the verb "register" and a specy-road claim term (feature branch, `registry.yaml`, "register as in-progress"); fix round 1 removed the looser "claim"/"the work"/"registry" terms. The historical commandless sentence "**First commit** registers the work in `registry.yaml`" still matches. The same class reached the delete-branch pattern, which now needs "branch" after the delete phrase (for example, "finish-this-task never deletes uncommitted work" no longer matches).

## Verification

- `pytest -q tests/test_behaviour_changes.py tests/test_validate_roadmap.py tests/test_validate_stale_commands.py`: 68 passed (fix round 2; full suite not rerun in fix rounds, per instructions).
- `pytest -n 4 -q`: 4033 passed (after the rework).
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK. Plain `specy-road validate` on `sr/` prints no `agents: notice`.
- `specy-road file-limits`: OK.
- Red/green: with `HEAD`'s `docs/roadmap-authoring.md` restored, `test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work` fails (line 351 matches). With 4f12fad3's `behaviour_changes.py` and `agent_text_report.py`, the four new rework tests fail; with the fix they pass.

## Fix round 1 (after merging origin/WIP/improvements-0-3-1)

- The merge was clean; `validate_roadmap.py` keeps both sides (359 lines, single `warn_contradicted_instructions(root)` call after `warn_unregistered_commands(root)`).
- R2 extended to every entry: each pattern is now anchored to a specy-road term. Pattern 3's bare "pickup" now needs "claim" on the same line. Pattern 5's claim context is restricted to feature branch, `registry.yaml`, and "register as in-progress".
- R1 unchanged from the previous commit: one notice per source line, naming every matching change with its version and current behaviour.

## Fix round 1: precision probes

Each line below is a parametrized case in `test_unrelated_prose_prints_no_notice` and gives no notice. "old: hit" marks a line the pre-fix-round patterns matched.
- `mark-implementation-reviewed --yes`: "Answer --yes to the installer prompt once the review is marked done." / "Mark the implementation reviewed in the tracker, then run apt-get install --yes."
- `finish-this-task --on-complete`: "Finish this task with git merge; the on-complete hook runs auto formatting." / "Set --on-complete merge in the CI plugin config before you finish the task."
- `do-next-available-task --local`: "The pickup truck always pushes the trailer up the hill." (old: hit) / "Our deploy script always pushes the tag; claim your slot in the calendar."
- `finish-this-task --delete-branch`: "`specy-road finish-this-task` never deletes uncommitted work." / "Git never deletes a branch you have checked out when you finish the task."
- `do-next-available-task --base`: "The first commit registers the service worker." / "Register the plugin in the first commit of the app; the work starts there." (old: hit) / "The first commit registers the claim form with the insurer." (old: hit)
- Positives still reported: all five CITED sentences, including "`specy-road do-next-available-task` always pushes the claim to origin." and both first-commit sentences (the feature-branch sentence and the historical "**First commit** registers the work in `registry.yaml`").
- `test_the_near_miss_corpus_covers_every_entry` makes sure every catalogue entry has at least two near-misses, so a new entry cannot skip the corpus.

## Fix round 2: anchored catalogue

Merged `origin/WIP/improvements-0-3-1` cleanly first. Pattern tightening had failed two rounds, so this round changes the design.

- **Class (Sol R1 and R2): a pattern matched words, not a stale specy-road instruction.** It fired on alias words alone (R2: "pickup … claim" with no command) and on sentences that state the *current* behaviour (R1: integration-branch registration). Three design changes remove the class:
  1. **Command anchor.** `BehaviourChange.contradicted_by(sentence)` only fires when the sentence names `command` as a literal token: `specy-road <command>`, or the command inside a backtick span. Aliases ("pickup", "first commit") may appear in `contradicts` but cannot trigger a match on their own; the bare-"pickup" alternative is gone.
  2. **Stale vs current.** Each entry has `contradicts` (the stale assertion) and `current` (today's guidance). A sentence that matches `current` is never reported.
  3. **Sentences, read whole.** `agent_text_report` joins wrapped Markdown lines into paragraphs, splits them into sentences, and reports at the line where each sentence starts, combining all hits on one line into one notice (R1 of round 0 still holds). A blank line, a list item, quote, table row, heading or a stripped managed block starts a new paragraph; each code-fence line stands alone.
- **Zero-notice invariant.** `test_the_toolkit_s_own_current_guidance_gets_zero_notices` lints `docs/*.md`, `specy_road/templates/specyrd/*.md`, `specy_road/templates/project/**/*.md` and `AGENTS.md`. No file is excluded. Its first run found six false positives in current docs: `--yes` after a recorded review (sandbox runbook, grind-session, orchestration ×2), and `--on-complete merge` given as a mode (install-and-usage ×2). The fix narrows the stale assertions in two entries (below), so `--yes` and `--on-complete merge` are no longer stale on their own.
- **Deviation from A2's literal minimum, called out for review.** A2 asks at minimum for "`--yes` with mark-implementation-reviewed" and "`--on-complete merge|auto` with finish-this-task". Current toolkit guidance uses both correctly, so the bare co-occurrence cannot be the stale claim without breaking the zero-notice invariant. The stale claims are now what the cited batch-C text said: approve with `--yes` (self-approval), and *always* pass `--on-complete merge|auto`.
- **Deviation from A4's commandless wording, called out for review.** Under the command anchor, a first-commit sentence that names no command (the init-era copies) no longer fires; the coordinator's rule 1 overrides that. Both historical positives used in the tests name `do-next-available-task`. One is the real former `docs/roadmap-authoring.md` step 4 ("… when using `do-next-available-task` or matching manually …"); the other is the CITED feature-branch sentence, now with the command added.

| Entry | Command anchor | Stale assertion (`contradicts`) | Current guidance (`current`, silences) | Positive tests | Negative tests |
|---|---|---|---|---|---|
| `--yes` | `mark-implementation-reviewed` | `--yes` + approve / sign off / when tests pass / your own | never, do not, must not, no longer, only when, refuse, independent, recorded, review record(s), already satisfied | CITED[0]; wrapped "Approve your own leaf with … when tests pass." | installer `--yes`; apt-get `--yes`; "Never pass `--yes` to `specy-road mark-implementation-reviewed` on your own work."; wrapped "With a recorded review … no longer approves"; zero-notice corpus |
| `--on-complete` | `finish-this-task` | always / every time / must pass + `--on-complete merge\|auto` | `--override-on-complete`, recorded, refuse, differ | CITED[1]; R1 line "Always run `…--on-complete auto`; … never deletes the source branch." | git merge/on-complete hook; CI plugin `--on-complete merge`; "`… --on-complete merge` is refused when it differs from the recorded mode."; code fence `specy-road finish-this-task --on-complete merge` |
| `--local` | `do-next-available-task` | always push | `--local`, unless | CITED[2] | pickup truck ×2 (incl. Sol's "…; claim your insurance discount online."); deploy script; "Pickup always pushes the claim to origin." (no command); "… always pushes the claim unless you pass `--local`." |
| `--delete-branch` | `finish-this-task` | does not / never / won't delete … branch | `--delete-branch`, unless | CITED[3]; R1 line | "never deletes uncommitted work"; Git never deletes a branch; "… never deletes the branch unless you pass `--delete-branch`." |
| `--base` | `do-next-available-task` | first commit + register + (feature branch \| `registry.yaml` \| register as in-progress) | integration branch, `--base` | CITED[4]; `HISTORICAL_FIRST_COMMIT` (former roadmap-authoring step 4) | service worker; plugin; claim form; Sol's "The first commit on the integration branch registers … before the feature branch is created."; "`… do-next-available-task` registers on the integration branch before creating the feature branch; …" |

## Probes

- Every catalogue pattern checked for prose false positives. Patterns 1–2 need the command plus a specific flag (and value): fine. Pattern 3 needs pickup/do-next-available-task plus "always push": fine. Pattern 4 matched "never deletes uncommitted work": narrowed and pinned by a test. Pattern 5 matched "registers the service worker" and "Register the plugin in the first commit": narrowed and both pinned by tests.
- Pattern 5 still catches the historical commandless roadmap-authoring sentence and the CITED feature-branch sentence: pinned by tests.
- One line matching several entries, in either order: only possible through `contradicted_lines`, which now groups per line. The R1 regression gives one notice that contains both finish-this-task behaviours.
- Duplicate files: `agent_files` already de-duplicates paths when the project root is the git root, so the same line in the same file is never read twice.
- Toolkit `docs/` and `specy_road/templates/` against the narrowed pattern 5: no hits (existing test). Plain `specy-road validate` on `sr/`: 0 notices.
- Behaviour `validate_at` relies on: unchanged. It still makes the single call; only the notice text changed, and only for lines that match several entries.

- Fix round 2: same class beyond the named instances. The lint was run over all 157 tracked Markdown files under `docs/**`, `specy_road/**`, `suggested_prompts/`, `constitution/`, `tests/fixtures/**`, `CLAUDE.md` and `README.md`. The only hits are two historical design notes that do state the old behaviour: `docs/design-notes/v0-3-0-orchestration-slices.md:137` ("`--yes` used to approve unconditionally") and `docs/design-notes/model-aware-orchestration-proposal.md:94` ("`do-next-available-task` always pushes the claim"). Both are outside the current-guidance corpus and are correct reports of old text; they are left alone.
- Fix round 2: a list number ("4. **First commit** …") does not end a sentence (`(?<![0-9])` in the splitter); the historical sentence is matched whole.
- Fix round 2: the managed-block gap starts a new paragraph, so a sentence cannot join text across a stripped block; the cited managed-block test still gives no notice from inside the block.

## Added

### Helpers
- `behaviour_changes.BehaviourChange`, `CATALOGUE`: the tracked catalogue (A1).
- `behaviour_changes._all_of`: "text contains all of these, in any order" regex, used for stale assertions with more than one part.
- `BehaviourChange.current` field and `BehaviourChange.contradicted_by`: command anchor plus stale-vs-current check, per sentence (fix round 2).
- `agent_text_report.sentences`, `_paragraphs`, `_sentence_starts`: read wrapped Markdown sentences whole and map each to its start line (fix round 2).
- `agent_text_report.contradicted_lines`: groups reported sentences and entries by start line (one tuple per line, R1); kept separate from printing.
- `agent_text_report.warn_contradicted_instructions`: validate's report (A2).
- `version_pin.py`: moved code only, nothing new (A3).

### Branches and guards
- `behaviour_changes`: claim-context term in pattern 5 and the "…branch" term in pattern 4 (R2 class); each entry's `current` silencer (fix round 2).
- `agent_text_report._paragraphs`: code-fence lines stand alone; a numbering gap (stripped managed block) breaks a paragraph.
- `agent_text_report`: skips a missing or unreadable file (`OSError`/`UnicodeDecodeError`), the same way the stale-command scan does.
- `agent_text_report`: cuts excerpts to 120 characters so a long line does not flood the notice.

### Mocks
- none

### Tests (`tests/test_behaviour_changes.py`)
- `test_every_entry_names_a_registered_command_and_flag`: each catalogue command is registered and every flag appears in that command's `--help` (A1).
- `test_cited_sentences_each_print_one_notice_outside_the_managed_block`: the four cited sentences plus the A4 sentence, spread over `AGENTS.md` and the team file, give exactly five notices with file:line and current behaviour. The same sentence inside a managed block and a clean `CLAUDE.md` give none. The files are byte-identical afterwards (A2, A4).
- `test_a_line_matching_two_entries_prints_one_notice_with_both_behaviours`: R1 regression. A finish-this-task line with `--on-complete auto` and "never deletes the source branch" gives one notice with both behaviours.
- `test_unrelated_prose_prints_no_notice` (19 cases, `NEAR_MISSES`, including Sol's two reproduced sentences and one current-guidance sentence per entry): R2 regression ("The first commit registers the service worker.") plus at least two near-miss lines per catalogue entry.
- `test_the_near_miss_corpus_covers_every_entry`: every catalogue entry has at least two near-misses in the corpus.
- `test_the_historical_first_commit_sentence_is_still_reported`: the former roadmap-authoring step 4, verbatim, still gives one notice (A4).
- `test_the_toolkit_s_own_current_guidance_gets_zero_notices`: zero notices over current toolkit guidance (fix round 2, rule 3).
- `test_a_sentence_wrapped_over_lines_is_read_whole`: a stale sentence wrapped over three lines is reported at its first line; a current one wrapped over two lines is not.
- `test_each_code_fence_line_is_its_own_sentence`: prose before a fence does not join a command line inside it.
- `test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work`: the A4 entry reports no sentence in `docs/` or `specy_road/templates/` (A4).
