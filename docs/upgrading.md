# Upgrading specy-road

## Agent quickstart

**Use this doc when:** you upgrade a consumer repo and need to know where your own `AGENTS.md` text goes now that specy-road's rules live in `.specyrd/AGENTS.md`, want to try a version before installing it, or cannot tell which install you have.
**Not for:** the upgrade commands themselves ([`install-and-usage.md`](install-and-usage.md#keeping-a-consumer-repo-current-after-an-upgrade)) or which launcher is first on `PATH` ([`install-and-usage.md`](install-and-usage.md#which-install-is-running)).

**Must know without reading on:**
- Repository-specific specy-road policy goes in `.specyrd/AGENTS.team.md`, project rules stay in your root `AGENTS.md`, and copies of specy-road's generic mechanics can be deleted. Keep anything you are unsure about. Never edit inside the managed-block markers.
- Preview a version in a scratch virtualenv and run that venv's `specy-road upgrade --dry-run --repo-root <repo>`; delete the venv afterwards.
- `pip show specy-road` names the installed version even for 0.1.x, which has no `--version`; `pipx list` and `uv tool list` do the same for those tools.

---

## Migrating to the split rules files

Since the split, specy-road writes its full rule set to `.specyrd/AGENTS.md` (rewritten whole by every `upgrade`), keeps a short managed stub in your `AGENTS.md`, and creates `.specyrd/AGENTS.team.md` once for your team's own specy-road instructions ([agent rules](optional-ai-tooling-patterns.md#agent-rules-agentsmd-and-specyrd)). `upgrade` touches only the text inside the markers. Text you wrote outside them stays where it is until you move it. Sort it like this:

| Kind of text in your `AGENTS.md` | Where it goes | Example |
| -------------------------------- | ------------- | ------- |
| Repository-specific specy-road policy: how *this* repo uses the toolkit | Move to `.specyrd/AGENTS.team.md` | "Our integration branch is `dev`; leaves under M4 need a review from Alice and Bob before finish." |
| Project rules: build, test, style, domain, architecture | Stay in the root `AGENTS.md` | "Run `make test` before committing; money amounts are integer cents." |
| Generic specy-road mechanics, which `.specyrd/AGENTS.md` now holds: the load order, pickup, finish, review steps | Delete | "Run `specy-road do-next-available-task` to claim a leaf, then `finish-this-task` when done." |

- **Keep it when unsure.** A duplicated line costs a few lines of context; a deleted project rule is lost. Compare against `.specyrd/AGENTS.md` and delete only what it already says.
- **Never edit inside the markers.** Text between the `>>> specy-road managed block <<<` markers is replaced on every `upgrade`; anything you add there is lost (`git diff` shows it after the upgrade).
- `.specyrd/AGENTS.team.md` adds to specy-road's rules and never relaxes them; a team rule that conflicts with `.specyrd/AGENTS.md` makes an agent stop and ask.
- `.specyrd/AGENTS.local.md` (gitignored) is for your own notes, not the team's.

---

## Preview a version you have not installed

To see what a version would change in your repo without replacing the specy-road you use, install it into a scratch virtualenv and run that venv's `upgrade --dry-run`. Install it the same way as an RC ([install a release candidate](install-release-candidates.md)): the exact wheel with `--no-deps`, its sha256 checked, then its dependencies from PyPI only. Drop `--index-url` for a final release, which is on PyPI.

```bash
python3 -m venv /tmp/sr-preview
/tmp/sr-preview/bin/pip download --no-deps --only-binary :all: -d /tmp/sr-preview/rc/ \
    --index-url https://test.pypi.org/simple/ "specy-road==0.3.1rc1"
sha256sum /tmp/sr-preview/rc/specy_road-0.3.1rc1-py3-none-any.whl   # must equal the announced sha256
/tmp/sr-preview/bin/pip install --no-deps /tmp/sr-preview/rc/specy_road-0.3.1rc1-py3-none-any.whl
/tmp/sr-preview/bin/pip install /tmp/sr-preview/rc/specy_road-0.3.1rc1-py3-none-any.whl  # its dependencies, from PyPI only

/tmp/sr-preview/bin/specy-road upgrade --dry-run --repo-root /path/to/your/repo

rm -rf /tmp/sr-preview
```

Call the venv's `specy-road` by its full path: a bare `specy-road` runs whichever launcher is first on `PATH`, which is your usual install, not the preview. `--dry-run` writes nothing to the repo. It prints one line before copying the checkout into a temporary directory, and it builds that copy once. The copy, like the one a real upgrade uses to decide what to write, holds tracked files, untracked files git does not ignore, and files the refreshes read. Gitignored paths such as `.env` files, virtualenvs, `node_modules` and nested repositories are not copied, and a symlink to one of them does not copy it either. A directory that cannot be searched is left out, so the upgrade does not stop on it. A global excludes file applies to that choice on a dry run the same way it does on a real run. An ignored `roadmap-context.md` that is already current is still read, so the preview does not report a rewrite the real run skips.

---

## Which install is this

Several installs can coexist (a repo virtualenv, `pip install --user`, pipx, uv tool). 0.1.x has no `--version`, so ask the installer instead:

```bash
pip show specy-road        # Version: and Location: of the install in the active Python environment
pipx list                  # each pipx package with its version
uv tool list               # each uv tool with its version
```

`pip show` reports only the environment of the `pip` you run; run it with each environment's own `pip` (for example `.venv/bin/pip show specy-road`). To find which launcher actually runs, and where a symlinked one points, see [which install is running](install-and-usage.md#which-install-is-running).

**uv tool from a local wheel.** `uv tool install <path to a .whl>` records that file's path in uv's receipt for the tool, so `uv tool upgrade specy-road` reads the wheel from that path again and fails once the file is gone. Keep the wheel where it was, or reinstall from the index (`uv tool install --force specy-road`).
