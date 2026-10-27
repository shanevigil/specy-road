#!/usr/bin/env python3
"""CLI for `specy-road models list|show|stale`.

``list`` is the roster as the gate sees it — each entry's family, roles, and
whether its profile loads — plus any profile no roster entry points at.
``show`` prints one profile's machine fields and a chosen body section.
``stale`` names profiles whose research is too old, superseded, or served
under a moving alias (proposal §7.3), and exits 1 when any rostered model is.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from specy_road.model_profiles import (
    DEFAULT_MAX_AGE_DAYS,
    ROLES,
    Profile,
    list_profiles,
    profile_for_entry,
)
from specy_road.orchestration_config import effective_config
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _row(root: Path, entry: dict[str, Any], prof: Profile | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": entry.get("id"),
        "family": entry.get("family"),
        "roles": list(entry.get("roles") or []),
        "profile": str(prof.path.relative_to(root)) if prof else None,
        "profile_ok": bool(prof and prof.ok),
        "errors": list(prof.errors) if prof else [],
        "scores": {r: prof.role_score(r) for r in ROLES} if prof and prof.ok else {},
        "stale": prof.stale_reasons() if prof and prof.ok else [],
    }
    return row


def _roster_rows(root: Path) -> tuple[list[dict[str, Any]], list[Profile], str | None]:
    config, err = effective_config(root)
    rows = []
    used: set[Path] = set()
    for entry in config.get("roster") or []:
        prof = profile_for_entry(root, entry)
        if prof:
            used.add(prof.path)
        rows.append(_row(root, entry, prof))
    unrostered = [p for p in list_profiles(root) if p.path not in used]
    return rows, unrostered, err


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    rows, unrostered, err = _roster_rows(root)
    if ns.json:
        print(json.dumps({"roster": rows, "unrostered_profiles": [str(p.path.relative_to(root)) for p in unrostered]}, indent=2))
        return 0
    if err:
        print(f"warning: {err}; showing the default roster", file=sys.stderr)
    for r in rows:
        scores = "/".join(str(r["scores"].get(x, "?")) for x in ROLES) if r["scores"] else "no profile"
        flag = "" if r["profile_ok"] or r["profile"] is None else "  INVALID: " + "; ".join(r["errors"])
        stale = "  stale" if r["stale"] else ""
        print(f"{r['id']:<28} {r['family']:<10} {','.join(r['roles']) or '-':<30} C/E/R {scores}{stale}{flag}")
    if unrostered:
        print(f"\n{len(unrostered)} profile(s) not in the roster (add an entry with `profile:` to use one):")
        for p in unrostered:
            print(f"  {p.path.relative_to(root)}")
    return 0


def _find(root: Path, model_id: str) -> Profile | None:
    config, _ = effective_config(root)
    entry = next((e for e in config.get("roster") or [] if e.get("id") == model_id), None)
    if entry:
        return profile_for_entry(root, entry)
    return next((p for p in list_profiles(root) if p.api_id == model_id or p.path.stem == model_id), None)


def cmd_show(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    prof = _find(root, ns.model)
    if prof is None:
        print(f"error: no roster entry or profile for {ns.model!r} (see `specy-road models list`)", file=sys.stderr)
        return 1
    if ns.json:
        print(json.dumps({"path": str(prof.path.relative_to(root)), "front_matter": prof.data,
                          "sections": prof.sections, "errors": prof.errors}, indent=2, default=str))
        return 0
    print(f"# {prof.data.get('model', prof.api_id)}  ({prof.path.relative_to(root)})")
    if prof.errors:
        print("INVALID: " + "; ".join(prof.errors))
    for key in ("family", "track", "api_id", "version_rank", "researched", "researcher"):
        print(f"- {key}: {prof.data.get(key, 'unknown')}")
    access = prof.data.get("access") or {}
    print(f"- context/output: {access.get('context_tokens', '?')} / {access.get('output_tokens', '?')}")
    print(f"- cli: {prof.cli() or 'none'}  (verified from: {access.get('cli_verified_from', 'unverified')})")
    print(f"- cost (USD/MTok): {prof.data.get('cost_usd_per_mtok', 'unknown')}")
    for role in ROLES:
        fit = (prof.data.get("role_fit") or {}).get(role) or {}
        print(f"- {role}: {fit.get('score', '?')} — {fit.get('reason', '')}")
    for reason in prof.stale_reasons():
        print(f"- stale: {reason}")
    section = ns.section or "Prompting rules"
    print(f"\n## {section}")
    print("\n".join(prof.sections.get(section, ["_(no such section)_"])))
    return 0


def cmd_stale(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    today = date.fromisoformat(ns.today) if ns.today else None
    config, _ = effective_config(root)
    # Roster ids are labels (`opus`); the link to a profile is the entry's
    # `profile` path, or a file named after the id — the same lookup `list` does.
    rostered: set[Path] = set()
    for entry in config.get("roster") or []:
        prof = profile_for_entry(root, entry)
        if prof:
            rostered.add(prof.path)
    stale: list[tuple[Profile, list[str]]] = []
    for p in list_profiles(root):
        if not p.ok:
            stale.append((p, ["invalid: " + "; ".join(p.errors)]))
            continue
        reasons = p.stale_reasons(today, ns.max_age_days)
        if reasons:
            stale.append((p, reasons))
    if ns.json:
        print(json.dumps([{"path": str(p.path.relative_to(root)), "api_id": p.api_id, "rostered": p.path in rostered,
                           "reasons": r} for p, r in stale], indent=2))
    elif not stale:
        print("No stale profiles.")
    for p, reasons in stale if not ns.json else []:
        mark = " (rostered)" if p.path in rostered else ""
        print(f"{p.path.relative_to(root)}{mark}")
        for r in reasons:
            print(f"  - {r}")
    if stale and not ns.json:
        print("\nRe-run the research prompt for that family (docs/design-notes/model-aware-orchestration-proposal.md §7).")
    return 1 if any(p.path in rostered for p, _ in stale) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    models = sub.add_parser("models", help="Roster and model profiles")
    msub = models.add_subparsers(dest="models_cmd", required=True)

    ls = msub.add_parser("list", help="The roster with each model's profile, role scores, and staleness")
    ls.add_argument("--json", action="store_true")
    add_repo_root_arg(ls)
    ls.set_defaults(func=cmd_list)

    show = msub.add_parser("show", help="One model's profile: machine fields plus a body section")
    show.add_argument("model", help="Roster id or profile api_id")
    show.add_argument("--section", help="Body section to print (default: Prompting rules)")
    show.add_argument("--json", action="store_true")
    add_repo_root_arg(show)
    show.set_defaults(func=cmd_show)

    st = msub.add_parser("stale", help="Profiles whose research is old, superseded, or alias-moved; exit 1 if any is rostered")
    st.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    st.add_argument("--today", help="YYYY-MM-DD, for reproducible checks")
    st.add_argument("--json", action="store_true")
    add_repo_root_arg(st)
    st.set_defaults(func=cmd_stale)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
