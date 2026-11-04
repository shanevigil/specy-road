"""``specy-road doctor``'s checks of the checkout, printed before the listing.

- the review gate and the orchestration policy agree (:mod:`specy_road.review_gate_agreement`): an error.
- ``env_setup`` (:mod:`specy_road.worktree_env`), when configured: its copy sources exist in the main checkout
  and its command succeeds there; either failing is an error.
- each linked worktree's ``.venv`` runs the same Python (major.minor) as the main checkout's: a warning, since
  a pin file such as ``.python-version`` is usually ignored and so missing from a new worktree.

Split from :mod:`doctor` for the file limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.git_subprocess import git_text
from specy_road.review_gate_agreement import report_gate_mismatch
from specy_road.runtime_paths import project_prefix
from specy_road.worktree_env import EnvSetupError, copy_pairs, copy_source, env_setup_config, run_setup_cmd


def _worktree_tops(root: Path) -> list[Path]:
    """Every worktree's top directory, the main checkout's first (``git worktree list``)."""
    out = git_text(["worktree", "list", "--porcelain"], root) or ""
    return [Path(line.removeprefix("worktree ")) for line in out.splitlines() if line.startswith("worktree ")]


def env_python(project_root: Path, top: Path) -> str | None:
    """The Python version in ``.venv/pyvenv.cfg`` at ``project_root``, else at the git root ``top``."""
    for cfg in (project_root / ".venv" / "pyvenv.cfg", top / ".venv" / "pyvenv.cfg"):
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                key, _, value = line.partition("=")
                if key.strip() in ("version_info", "version"):   # uv and virtualenv; venv
                    return value.strip()
            return None
    return None


def _minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def report_env_setup(main: Path) -> bool:
    """Say what ``env_setup`` does and run it in the main checkout's project root ``main``; whether it failed."""
    conf = env_setup_config(main)
    if not conf:
        return False
    copies = ", ".join(src if src == dest else f"{src} -> {dest}" for src, dest in copy_pairs(conf))
    print(f"env_setup: copy {copies or 'nothing'}; cmd {conf.get('cmd') or 'none'}")
    missing = []
    for src, _dest in copy_pairs(conf):
        try:
            if not copy_source(main, src).is_file():
                missing.append(f"env_setup copies {src}, which is not a file in the main checkout ({main / src})")
        except EnvSetupError as e:   # climbs past the git root: the pickup would refuse it
            missing.append(str(e))
    for problem in missing:
        print(f"error: {problem}", file=sys.stderr)
    if not conf.get("cmd"):
        return bool(missing)
    code, out = run_setup_cmd(conf["cmd"], main)
    if code:
        print(f"error: env_setup fails in the main checkout {main} (exit {code}): {conf['cmd']}\n{out.rstrip()}",
              file=sys.stderr)
        return True
    print(f"env_setup: succeeds in the main checkout {main}")
    return bool(missing)


def report_python_mismatch(tops: list[Path], prefix: str) -> None:
    """Warn for each linked worktree whose ``.venv`` Python differs from the main checkout's."""
    want = env_python(tops[0] / prefix, tops[0]) if tops else None
    if want is None:
        return
    for top in tops[1:]:
        have = env_python(top / prefix, top)
        if have and _minor(have) != _minor(want):
            print(f"warning: worktree {top} has a Python {have} environment; the main checkout's is {want}. "
                  "Pin the version for env_setup (for example copy .python-version), then rebuild it there.",
                  file=sys.stderr)


def report_checkout(root: Path) -> bool:
    """The checks above; True when one is an error (doctor exits 1 after the listing)."""
    tops, prefix = _worktree_tops(root), project_prefix(root)
    bad = report_gate_mismatch(root)
    bad = report_env_setup(tops[0] / prefix if tops else root) or bad
    report_python_mismatch(tops, prefix)
    return bad
