"""Each old refresh invocation and its ``upgrade --only`` form write the same files and output.

One row per flag and mode of ``refresh-stubs``, ``refresh-schemas`` and ``refresh-profiles``
(the map in M16.4.2's work notes). Both invocations run on their own copy of the rc3 fixture: the
exit code, stdout and every file under the repo afterwards must match. The old one is a deprecated
alias and adds exactly its one deprecation line on stderr; every other stderr line, the
version-skew warnings included, must match. ``--only`` is also given as ``--only=X`` and
abbreviated, the forms argparse reads. ``--capture --accept`` without ``--dry-run`` writes into the
installed package, so it is run only as a dry run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.parity.support import PARITY, cli_env, normalise, repo_copy, run_cli

pytestmark = pytest.mark.parity

RC3_CONSUMER = PARITY / "fixtures" / "rc3_consumer"
CAPTURE = Path(__file__).resolve().parents[2] / "specy_road" / "templates" / "project" / (
    "model-profiles/harness-captures/codex")
PROFILE = "model-profiles/anthropic-claude/claude-opus-5-5.md"

#: ``(old argv, new argv)``; ``--repo-root`` is appended to both.
ROWS = [
    (["refresh-stubs"], ["upgrade", "--only", "stubs"]),
    (["refresh-stubs", "--dry-run"], ["upgrade", "--only", "stubs", "--dry-run"]),
    (["refresh-stubs", "--prune"], ["upgrade", "--only", "stubs", "--prune"]),
    (["refresh-stubs", "--diff"], ["upgrade", "--only", "stubs", "--diff"]),
    (["refresh-schemas"], ["upgrade", "--only", "schemas"]),
    (["refresh-schemas", "--dry-run"], ["upgrade", "--only", "schemas", "--dry-run"]),
    (["refresh-schemas", "--dry-run"], ["upgrade", "--only=schemas", "--dry-run"]),
    (["refresh-stubs", "--dry-run"], ["upgrade", "--onl", "stubs", "--dry-run"]),
    (["refresh-profiles"], ["upgrade", "--only", "profiles"]),
    (["refresh-profiles", "--dry-run"], ["upgrade", "--only", "profiles", "--dry-run"]),
    (["refresh-profiles", "--profiles", "all"],
     ["upgrade", "--only", "profiles", "--profiles", "all"]),
    (["refresh-profiles", "--only", "claude-opus-5-5"],
     ["upgrade", "--only", "profiles", "--profile", "claude-opus-5-5"]),
    (["refresh-profiles", "--force", PROFILE],
     ["upgrade", "--only", "profiles", "--force", PROFILE]),
    (["refresh-profiles", "--check"], ["upgrade", "--only", "profiles", "--check"]),
    (["refresh-profiles", "--render"], ["upgrade", "--only", "profiles", "--render"]),
    (["refresh-profiles", "--render", "--dry-run"],
     ["upgrade", "--only", "profiles", "--render", "--dry-run"]),
    (["refresh-profiles", "--capture", "codex", "--from", str(CAPTURE)],
     ["upgrade", "--only", "profiles", "--capture", "codex", "--from", str(CAPTURE)]),
    (["refresh-profiles", "--capture", "codex", "--from", str(CAPTURE), "--accept", "--dry-run"],
     ["upgrade", "--only", "profiles", "--capture", "codex", "--from", str(CAPTURE), "--accept",
      "--dry-run"]),
    (["refresh-profiles", "--from", str(CAPTURE)],
     ["upgrade", "--only", "profiles", "--from", str(CAPTURE)]),
]


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts}


def _run(argv: list[str], tmp: Path) -> tuple[int, str, list[str], dict[str, bytes]]:
    root = repo_copy(RC3_CONSUMER, tmp)
    result = run_cli("specy_road.cli", [*argv, "--repo-root", str(root)], cwd=root, env=cli_env())
    out, err = (normalise(t, {root: "<ROOT>"}) for t in (result.stdout, result.stderr))
    return result.returncode, out, err.splitlines(), _files(root)


@pytest.mark.parametrize(("old", "new"), ROWS, ids=[" ".join(o) for o, _ in ROWS])
def test_old_and_new_invocation_give_the_same_files_and_output(
    tmp_path: Path, old: list[str], new: list[str]
) -> None:
    old_code, old_out, old_err, old_files = _run(old, tmp_path / "old")
    new_code, new_out, new_err, new_files = _run(new, tmp_path / "new")
    assert (new_code, new_out, new_files) == (old_code, old_out, old_files)
    component = old[0].removeprefix("refresh-")
    deprecation = (f"warning: `specy-road {old[0]}` is deprecated and is removed in the release"
                   f" after 0.3.1; use `specy-road upgrade --only {component}`.")
    assert old_err[0] == deprecation
    if new_code == 2:   # a usage error: the same rule; the usage lines name each command's options
        assert new_err[-1].replace("upgrade", old[0]) == old_err[-1]
    else:
        assert new_err == old_err[1:]
