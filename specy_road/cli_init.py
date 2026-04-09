"""`specy-road init` helpers (PM-facing optional installs)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Skip npm's default audit (network; can look "hung") and funding prompts.
_NPM_INSTALL_EXTRAS = ["--no-audit", "--no-fund"]


def _npm_env() -> dict[str, str]:
    """Non-interactive npm: no TTY prompts; CI-style logging.

    Do not set ``NODE_ENV=production`` here — that would skip devDependencies
    on install and break ``npm run build`` (vite, typescript, etc.).
    """
    env = os.environ.copy()
    env.setdefault("CI", "true")
    return env


def _npm_run(argv: list[str], *, cwd: Path) -> None:
    subprocess.check_call(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        env=_npm_env(),
    )


def specy_road_repo_root_for_editable_install() -> Path | None:
    """If ``specy_road`` is from a source checkout, return that repo root.

    Used to run ``pip install -e ".[gui-next]"`` so contributors do not
    pull a PyPI wheel over their editable tree.
    """
    import specy_road

    pkg_dir = Path(specy_road.__file__).resolve().parent
    candidate = pkg_dir.parent
    pyproject = candidate / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    if 'name = "specy-road"' not in text and "name='specy-road'" not in text:
        return None
    return candidate


def pm_gantt_source_dir() -> Path | None:
    """Return ``gui/pm-gantt`` if ``package.json`` exists (editable repo or cwd)."""
    repo = specy_road_repo_root_for_editable_install()
    for base in (repo, Path.cwd()):
        if base is None:
            continue
        d = (base / "gui" / "pm-gantt").resolve()
        if (d / "package.json").is_file():
            return d
    return None


def run_npm_build_pm_gantt(*, dry_run: bool, require_npm: bool = True) -> None:
    """
    Run ``npm install`` (or ``npm ci``) and ``npm run build`` in ``gui/pm-gantt``.

    Writes to ``specy_road/pm_gantt_static/``. No-op if no sources.

    If ``require_npm`` is True (standalone ``--build-gui``), missing ``npm`` exits
    with an error. If False (after ``--install-gui``), missing ``npm`` only prints
    a notice — the wheel still ships a built UI for ``specy-road gui``.
    """
    pm = pm_gantt_source_dir()
    if pm is None:
        msg = "Would skip npm build: no gui/pm-gantt sources found."
        if dry_run:
            print(msg)
        else:
            print(
                "specy-road init: skipping local SPA build (no gui/pm-gantt in this tree). "
                "Using packaged UI from the specy-road install.",
                file=sys.stderr,
            )
        return
    use_ci = (pm / "package-lock.json").is_file()
    install_cmd = (
        ["npm", "ci", *_NPM_INSTALL_EXTRAS]
        if use_ci
        else ["npm", "install", *_NPM_INSTALL_EXTRAS]
    )
    build_cmd = ["npm", "run", "build"]
    npm_ok = shutil.which("npm") is not None
    if dry_run:
        if not npm_ok:
            print(
                "Would skip local SPA build: npm not on PATH "
                "(install Node.js to build from source; packaged UI still works)."
            )
            return
        print(
            "Would run: "
            + f"cd {pm} && {' '.join(install_cmd)} && {' '.join(build_cmd)}"
        )
        return
    if not npm_ok:
        if require_npm:
            print(
                "error: --build-gui needs npm on PATH (install Node.js LTS).\n"
                f"  Sources: {pm}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        print(
            "specy-road init: skipping local SPA build (npm not on PATH). "
            "Packaged UI from your specy-road install is still used by specy-road gui.",
            file=sys.stderr,
        )
        return
    print(
        f"specy-road init: installing npm dependencies in {pm} …",
        flush=True,
    )
    _npm_run(install_cmd, cwd=pm)
    print("specy-road init: running npm run build …", flush=True)
    _npm_run(build_cmd, cwd=pm)
    print(
        "PM Gantt UI built (Vite output under specy_road/pm_gantt_static/).",
        flush=True,
    )


def build_install_gui_command(*, reinstall: bool = False) -> tuple[list[str], Path | None]:
    """Return argv for ``python -m pip install ...`` and optional cwd.

    Always uses ``--upgrade`` so repeat runs pick up newer releases (or refresh
    editable installs). With ``reinstall=True``, also passes ``--force-reinstall``
    to reinstall packages even when versions match (repair broken envs).
    """
    repo = specy_road_repo_root_for_editable_install()
    base = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if reinstall:
        base.append("--force-reinstall")
    if repo is not None:
        return base + ["-e", ".[gui-next]"], repo
    return base + ["specy-road[gui-next]"], None


def run_install_gui(
    *,
    dry_run: bool,
    reinstall: bool = False,
    do_pip: bool = True,
    npm_only: bool = False,
    skip_npm_after_pip: bool = False,
) -> None:
    """Install Python gui-next deps and/or run the Vite/npm build.

    With ``--install-gui`` / ``--reinstall-gui``, pip runs first; the npm build
    runs automatically when ``gui/pm-gantt`` exists (unless ``skip_npm_after_pip``).
    ``--build-gui`` alone runs only npm (strict: npm required).
    """
    if npm_only:
        if dry_run:
            run_npm_build_pm_gantt(dry_run=True, require_npm=True)
            return
        run_npm_build_pm_gantt(dry_run=False, require_npm=True)
        return
    if not do_pip:
        return
    cmd, cwd = build_install_gui_command(reinstall=reinstall)
    if dry_run:
        suffix = f" (cwd={cwd})" if cwd is not None else ""
        print(f"Would run: {' '.join(cmd)}{suffix}")
        if skip_npm_after_pip:
            print("Would skip npm build (--skip-npm-build).")
        else:
            run_npm_build_pm_gantt(dry_run=True, require_npm=False)
        return
    subprocess.check_call(cmd, cwd=cwd)
    if not skip_npm_after_pip:
        run_npm_build_pm_gantt(dry_run=False, require_npm=False)
