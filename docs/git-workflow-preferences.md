# Project preferences the workflow respects

Four settings for repositories with stricter rules than specy-road's defaults.
Each is optional; leaving it out keeps today's behaviour. The three
`roadmap/git-workflow.yaml` keys are checked by
`schemas/git-workflow.schema.json`. Branches, remotes and `on_complete` are
covered in [`git-workflow.md`](git-workflow.md).

## Local decisions: `decisions add --local`

`specy-road decisions add` writes the tracked `roadmap/decisions.yaml`. In a
repository that forbids commits to the integration branch, a preference
recorded there applies only after a PR merges. Add `--local` to write
`roadmap/decisions.local.yaml` instead:

```bash
specy-road decisions add --local --kind preference --summary "Docs leaves go to sol this week" --role executor --model sol
```

- The file is gitignored: it is in the managed `.gitignore` block that
  `init project`, `specyrd init` and `upgrade` write, so it applies in this
  clone only, and at once.
- Both files use the same schema. Readers (`decisions list`,
  `orchestrate plan`) merge the local file over the tracked one, matching by
  id: when an id is in both files, the local entry wins.
- `decisions list` shows where each entry comes from: `(local)` or `(shared)`
  at the end of its first line, and `"source"` in `--json`.
- New ids (`D#`, `P#`) skip ids already used in either file, so a new entry
  never hides an entry in the other file by accident. To override a tracked
  entry in this clone, reuse its id with `--id`.
- `decisions close <id>` closes the entry in the file it came from. `--supersedes`
  closes an entry only in the file being written.

## PR body footer: `pr_body_footer`

```yaml
pr_body_footer: "Generated with <your tool>; reviewed by <team>"
```

`finish-this-task` appends this text to the PR/MR body it writes
(`work/pr-body-<NODE_ID>.md`) after the brief snapshot, for attribution
lines or checklists that the project requires. Without it, the body is unchanged.
Surrounding whitespace is stripped. An empty or whitespace-only value fails the
schema, so `validate` reports it; it is never read as "no footer". Likewise an
`implementation_summary` or `land` value outside its enum fails `validate`.

## Implementation summary: `implementation_summary: commit | local`

- `commit` (the default): executor prompts (pickup's `work/prompt-<ID>.md` and
  `prompt --role executor`) say to commit `work/implementation-summary-<ID>.md`
  on the feature branch.
- `local`: the prompts say to leave the summary uncommitted. `review-packet`
  reads it from the worktree and labels it as working-tree text.

The prompts never tell a worker to force-add (`git add -f`) an ignored path.
Git is asked about each leaf's own summary path
(`work/implementation-summary-<ID>.md`), so a rule naming some ids and not
others decides per leaf, and a negated rule (`!pattern`) un-ignores. If
`.gitignore` ignores a leaf's summary, the ignore rule wins over `commit` for
that leaf: its prompts use the `local` wording, and `specy-road validate` prints
a notice naming each ignored leaf summary and its rule (`source:line:pattern`).

A leaf's `implementation_summary` and `pr_body_footer` are read in the checkout
that has its branch checked out, usually its linked worktree under
`work/.worktrees/`. It doesn't matter whether the prompt is built from there or
from the main checkout, so a setting committed on the leaf's branch applies to
that leaf. A leaf whose branch is checked out nowhere uses the checkout that asks. Set `implementation_summary: local` to
make the setting match, or drop the ignore rule to commit summaries. The
notice goes to stdout, so `validate --strict` does not count it.

## Root landing: `land: push | local`

`land` decides how `finish-this-task` lands the root repository in merge mode
(and in auto mode's merge attempt). Each `nested_repos` entry's `land` does the
same for its repository (M14.4.1).

- `push` (the default) merges onto `<remote>/<integration_branch>` and pushes.
  This is unchanged.
- `local` merges the leaf's branch into the **local** `integration_branch`,
  then stops. Nothing is fetched or pushed. The rest of the landing is the same
  as `push`: nested repositories land first, bookkeeping conflicts in the
  registry and generated files are resolved deterministically, and
  `land_check_cmd` runs on the merge commit (a failure puts the local branch
  back). Where another worktree has the integration branch checked out, the
  merge runs there, and only while that worktree is clean. Finish says before
  and after that nothing was pushed. Push the integration branch yourself when
  you are ready.
- With `land: local`, `--delete-branch` deletes only the local feature branch,
  because deleting the remote copy would be a push. A re-run after a failed
  landing checks the local integration branch, not the remote one.

`pr` mode does not read `land`.
