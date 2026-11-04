#!/usr/bin/env python3
"""Add the model profiles this specy-road version ships that a repo lacks.

``init project`` scaffolds ``model-profiles/`` once, so a repo scaffolded by an
older version has none, and a repo whose roster names a model profiled only by
a newer version lacks that one file. This copies the **missing** profiles a roster
entry in ``roadmap/orchestration.yaml`` names (by ``id``, alias or ``profile:``),
or every missing one with ``--profiles all``, and the README, and never
overwrites: the adopter's copies are theirs to edit (prices, CLI syntax, their
own research), which is why the profiles are scaffolded rather than read from
the package. Use ``--force`` for one named profile to
take the toolkit's copy over yours.

Two regions of ``model-profiles/`` are rendered from the harness facts fixture
(:mod:`specy_road.harness_facts`): each profile's ``access.cli`` and the README's
harness block. ``--check`` reports a hand edit to either as drift (exit 1) and a
README that predates the block as behind, and fails on a Codex memory override
whose feature the accepted ``codex features list`` capture does not list; ``--render`` rewrites them. ``--capture
<harness>`` classifies a new ``--version``/``--help`` capture against the accepted
one and fails while a new workflow identifier has no relationship in the fixture;
``--accept`` then stores it as the accepted capture.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from specy_road import harness_facts as hf
from specy_road.init_project import index_bundled_profile_names, project_template_root
from specy_road.model_profiles import PROFILES_REL, load_profile
from specy_road.orchestration_config import load_orchestration_config
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root
from specy_road.worker_adapter_codex import CODEX_MEMORY_OFF


def bundled_profiles_dir() -> Path:
    return project_template_root() / PROFILES_REL


def _contained(repo_root: Path, path: Path) -> None:
    """Refuse a destination that is, or sits under, a symlink: every write must land inside the repo as spelled."""
    if path.is_symlink() or path.resolve() != path:
        raise ValueError(
            f"{path.relative_to(repo_root)} is or lies under a symlink; refresh-profiles writes only "
            "to real paths inside the repository (replace the link with a directory or file)"
        )


def _roster_rels(repo_root: Path, src_dir: Path) -> set[str]:
    """Bundled profile paths (relative to ``src_dir``) a roster entry names by ``id``/alias or ``profile:``."""
    config, _err = load_orchestration_config(repo_root)
    entries = [e for e in (config or {}).get("roster") or [] if isinstance(e, dict)]
    out: set[str] = set()
    for src in sorted(p for p in src_dir.rglob("*.md") if p.name != "README.md"):
        rel_in = src.relative_to(src_dir).as_posix()
        prof = load_profile(src)
        if any(Path(str(e.get("profile") or "")).as_posix() == f"{PROFILES_REL.as_posix()}/{rel_in}"
               or prof.for_id(e.get("id")) for e in entries):
            out.add(rel_in)
    return out


def refresh_profiles(
    repo_root: Path,
    *,
    dry_run: bool = False,
    force: list[str] | None = None,
    only: str | None = None,
    profiles: str = "roster",
) -> tuple[list[str], list[str]]:
    """``(written, kept)`` repo-relative paths. ``force`` names relative paths to overwrite.

    ``profiles="roster"`` limits it to the README and the profiles the roster names; ``"all"``
    to every bundled profile. ``only`` overrides either.
    """
    if profiles not in ("roster", "all"):
        raise ValueError(f"--profiles must be roster or all, not {profiles!r}")
    src_dir = bundled_profiles_dir()
    if not src_dir.is_dir():
        raise ValueError(f"missing bundled model profiles at {src_dir}")
    repo_root = repo_root.resolve()
    dst_dir = repo_root / PROFILES_REL
    _contained(repo_root, dst_dir)
    forced = {Path(f).as_posix() for f in force or []}
    only_rels: set[str] | None = None
    if only is not None:
        families, names, rels_by_token = index_bundled_profile_names(src_dir)
        if only not in names or only in families:
            raise ValueError(f"unknown api_id {only!r}")
        only_rels = set(rels_by_token[only])
    elif profiles == "roster":
        only_rels = _roster_rels(repo_root, src_dir) | {"README.md"} | {
            f.removeprefix(f"{PROFILES_REL.as_posix()}/") for f in forced}
    written: list[str] = []
    kept: list[str] = []
    for src in sorted(p for p in src_dir.rglob("*.md")):
        rel_in = src.relative_to(src_dir).as_posix()
        if only_rels is not None and rel_in not in only_rels:
            continue
        rel = f"{PROFILES_REL.as_posix()}/{rel_in}"
        dst = dst_dir / rel_in
        _contained(repo_root, dst)
        if dst.is_file() and rel not in forced and rel_in not in forced:
            kept.append(rel)
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        written.append(rel)
    return written, kept


def render_profiles(repo_root: Path, *, dry_run: bool = False) -> hf.RenderPlan:
    """Plan (and unless ``dry_run`` write) the fixture's rendered regions under ``repo_root``."""
    repo_root = repo_root.resolve()
    plan = hf.plan_render(repo_root, hf.load_facts())
    if not dry_run:
        for path, text in plan.updates.items():
            _contained(repo_root, path)
            path.write_text(text, encoding="utf-8")
    return plan


def _report(plan: hf.RenderPlan, *, check: bool) -> int:
    """Print findings; 1 when ``check`` and a rendered region drifted."""
    for f in plan.findings:
        print(f"{f.kind}: {f.rel}: {f.detail}", file=sys.stderr if f.kind == "drift" else sys.stdout)
    drift = [f for f in plan.findings if f.kind == "drift"]
    if drift:
        print(f"{len(drift)} rendered region(s) differ from harness-facts.yaml; "
              "`refresh-profiles --render` rewrites them (or --force <path> takes the toolkit's copy)",
              file=sys.stderr)
    elif check:
        print("no drift from harness-facts.yaml")
    return 1 if check and drift else 0


def _check_overrides() -> int:
    """1 when a Codex memory override the launch passes names a feature the accepted capture does not list."""
    capture = hf.read_capture(hf.bundled_captures_dir() / "codex")
    unlisted = hf.unlisted_overrides(CODEX_MEMORY_OFF, capture)
    for key in unlisted:
        print(f"unlisted: codex -c {key}: the captured `codex features list` ({hf.CODEX_FEATURES_FILE}) does not "
              "list its feature, so the launch would pass it and Codex ignore it", file=sys.stderr)
    return 1 if unlisted else 0


def _report_render(root: Path, plan: hf.RenderPlan, *, dry_run: bool) -> int:
    """Print what was (or would be) rendered; 1 when a drifted region could not be rendered."""
    updated = {p.relative_to(root).as_posix() for p in plan.updates}
    verb = "would render" if dry_run else "rendered"
    stuck = [f for f in plan.findings if f.rel not in updated]
    for f in plan.findings:
        if f.rel in updated:
            print(f"{verb} {f.rel} ({f.kind}: {f.detail})")
    for f in stuck:
        print(f"cannot render {f.rel} ({f.kind}: {f.detail}): left unchanged; fix it by hand "
              "or take the toolkit's copy with --force", file=sys.stderr)
    if not plan.findings:
        print("rendered regions already match harness-facts.yaml")
    return 1 if stuck else 0


def capture(harness_id: str, from_dir: Path | None) -> dict[str, str]:
    """A capture read from ``from_dir``, or taken by running the fixture's ``capture_commands``."""
    if from_dir is not None:
        got = hf.read_capture(from_dir)
        if not got:
            raise ValueError(f"no *.txt capture files in {from_dir}")
        return got
    rec = hf.harness(hf.load_facts(), harness_id)
    out: dict[str, str] = {}
    if not rec.get("capture_commands"):
        raise ValueError(f"{harness_id} has no capture_commands (no binary of its own); pass --from DIR")
    for name, argv in rec["capture_commands"].items():
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ValueError(f"cannot capture {name} with {' '.join(argv)}: {e}") from e
        if done.returncode != 0:
            raise ValueError(f"{' '.join(argv)} exited {done.returncode}: {done.stderr.strip()[:200]}")
        out[name] = done.stdout
    return out


def _print_diff(diff: hf.CaptureDiff) -> None:
    old, new = diff.version
    print(f"{diff.harness}: version {old or '(no accepted capture)'} -> {new}")
    for ident, rel in diff.assigned.items():
        print(f"  new {ident}: {rel}")
    for ident in diff.other:
        print(f"  new {ident}: no workflow word")
    for ident in diff.removed:
        print(f"  removed {ident}")
    for ident, word in diff.unassigned.items():
        print(f"  UNASSIGNED {ident}: contains {word!r}; give it a relationship in harness-facts.yaml",
              file=sys.stderr)


def run_capture(harness_id: str, from_dir: Path | None, *, accept: bool, dry_run: bool = False) -> int:
    facts = hf.load_facts()
    accepted_dir = hf.bundled_captures_dir() / harness_id
    new = capture(harness_id, from_dir)
    diff = hf.classify_capture(facts, harness_id, hf.read_capture(accepted_dir), new)
    _print_diff(diff)
    if not diff.ok:
        print(f"{len(diff.unassigned)} new workflow identifier(s) unassigned; capture not accepted", file=sys.stderr)
        return 1
    if accept and dry_run:
        print(f"would accept as {accepted_dir} (--dry-run: nothing written)")
    elif accept:
        hf.write_capture(accepted_dir, new)
        print(f"accepted as {accepted_dir}")
        if hf.harness(facts, harness_id)["version"]["value"] not in new[hf.VERSION_FILE]:
            print(f"note: update {harness_id}'s version in harness-facts.yaml to match {hf.VERSION_FILE}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road refresh-profiles",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_repo_root_arg(p)
    p.add_argument("--dry-run", action="store_true", help="Print what would be written; do not modify files.")
    p.add_argument(
        "--force", action="append", default=[], metavar="PATH",
        help="Overwrite this profile (repo-relative, e.g. model-profiles/openai-gpt/gpt-6.1-sol.md); repeatable.",
    )
    p.add_argument(
        "--only",
        metavar="API_ID",
        help="Add missing profile(s) whose front-matter api_id or file stem matches, whatever --profiles says.",
    )
    p.add_argument(
        "--profiles", choices=("roster", "all"), default="roster",
        help="roster (default): add the missing profiles a roadmap/orchestration.yaml roster entry names, "
             "and the README; all: every missing profile this specy-road ships.",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="Report rendered regions that differ from harness-facts.yaml, and Codex memory overrides the "
                           "captured features list does not list; exit 1 on either. Writes nothing.")
    mode.add_argument("--render", action="store_true",
                      help="Rewrite the rendered regions (each profile's access.cli, the README's harness block).")
    mode.add_argument("--capture", metavar="HARNESS",
                      help="Classify a new --version/--help capture of HARNESS against the accepted one.")
    p.add_argument("--from", dest="from_dir", type=Path, metavar="DIR",
                   help="With --capture: read the capture's *.txt files from DIR instead of running the harness.")
    p.add_argument("--accept", action="store_true", help="With --capture: store a passing capture as the accepted one.")
    return p


def _copy_missing(root: Path, args: argparse.Namespace) -> None:
    written, kept = refresh_profiles(root, dry_run=args.dry_run, force=args.force, only=args.only,
                                     profiles=args.profiles)
    verb = "would write" if args.dry_run else "wrote"
    for rel in written:
        print(f"{verb} {rel}")
    if args.profiles == "roster" and not args.only and all(r.endswith("/README.md") for r in written + kept):
        print("no roster entry in roadmap/orchestration.yaml names a profile this specy-road ships; "
              "`specy-road refresh-profiles --profiles all` adds every one")
    elif not written:
        which = "the roster names" if args.profiles == "roster" and not args.only else "this specy-road ships"
        print(f"model-profiles/ already has every profile {which} ({root})")
    elif kept:
        profiles = [k for k in kept if not k.endswith("/README.md")]
        readme = " and the README" if len(profiles) < len(kept) else ""
        print(f"kept {len(profiles)} existing profile(s){readme}; pass --force <path> to replace one")
    if written and not args.dry_run:
        print("Next: add roster entries with `profile:` in roadmap/orchestration.yaml, then `specy-road models list`.")


def main(argv: list[str] | None = None) -> None:
    p = _parser()
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    if (args.from_dir or args.accept) and not args.capture:
        p.error("--from and --accept need --capture")
    if (args.only or args.profiles != "roster") and (args.capture or args.check or args.render):
        p.error("--only and --profiles add missing profiles; do not combine with --check, --render or --capture")
    root = (args.repo_root or default_user_repo_root()).resolve()
    try:
        if args.capture:
            raise SystemExit(run_capture(args.capture, args.from_dir, accept=args.accept, dry_run=args.dry_run))
        if args.check or args.render:
            plan = render_profiles(root, dry_run=args.check or args.dry_run)
            if args.check:
                raise SystemExit(max(_report(plan, check=True), _check_overrides()))
            raise SystemExit(_report_render(root, plan, dry_run=args.dry_run))
        _copy_missing(root, args)
        _report(hf.plan_render(root, hf.load_facts()), check=False)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
