"""The operations behind ``specy-road worker`` (slice 7c).

Each function does one lifecycle step on a worker record and raises
:class:`WorkerError` (or :class:`Unsupported`) with the sentence the CLI
prints. The CLI module is argument parsing and output only.

``delegate`` runs **after pickup**: the leaf must already hold a registry
claim with a branch, because pickup switches branches and pushes the
registry, which is not something a coordinator's checkout should do on a
worker's behalf (design note, slice 7). The worker's worktree is the
coordinator's checkout when it has the claim's branch checked out, otherwise
a linked worktree under ``work/.worktrees/<codename>``.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.finish_implementation_check import zone_matches
from specy_road.git_subprocess import git_text, run
from specy_road.model_profiles import profile_for_entry
from specy_road.orchestrate_plan import ANY, is_available, may_handle, node_eligibility, node_sensitivity
from specy_road.orchestration_config import effective_config, roster_entry
from specy_road.review_files import reviews_root
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.worker_adapters import Unsupported, adapter_for
from specy_road.worker_runner import pid_alive, spawn
from specy_road.worker_state import (
    FLAG_EXTERNAL,
    FLAG_RECONCILE,
    WorkerError,
    WorkerRecord,
    active_for_node,
    add_flag,
    append_event,
    clear_flag,
    create_record,
    events_since,
    list_records,
    load_record,
    record_intervention,
    record_path,
    require_writer,
    save_record,
    set_lease,
    set_state,
    take_checkpoint,
    workers_dir,
)

CONTINUE_PROMPT = ("Continue the task from where you stopped. Re-read the brief and the precondition "
                   "first; if the hand-off is already written, say so and stop.\n")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def interventions_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".interventions.jsonl")


def _target(repo_root: Path, node_id: str):
    try:
        t = resolve_target(repo_root, node_id)
    except ReviewTargetError as e:
        raise WorkerError(f"{e}; `delegate` runs after pickup (do-next-available-task --under {node_id})") from None
    if not t.entry or not t.entry.get("branch"):
        raise WorkerError(f"{node_id} has no registry claim with a branch; pick it up first")
    return t


def _entry_and_harness(repo_root: Path, model: str, harness: str | None) -> tuple[dict[str, Any], str]:
    config, err = effective_config(repo_root)
    if err:
        raise WorkerError(f"orchestration config: {err}")
    entry = roster_entry(config, model)
    if entry is None:
        raise WorkerError(f"{model!r} is not in the roster (roadmap/orchestration.yaml)")
    return entry, str(harness or entry.get("harness") or "generic")


def _check_eligible(entry: dict[str, Any], node: dict[str, Any], model: str) -> None:
    if "executor" not in (entry.get("roles") or []):
        raise WorkerError(f"{model!r} does not have the executor role in the roster")
    if not is_available(entry):
        raise WorkerError(f"{model!r} is unavailable until {entry.get('unavailable_until')}")
    sens = node_sensitivity(node)
    if not may_handle(entry, sens):
        raise WorkerError(f"{node['id']} is {sens!r}; {model!r} may not process it (`orchestrate plan`)")
    need = node_eligibility(node)
    if need != ANY and str(entry.get("class") or "") != need:
        raise WorkerError(f"{node['id']} needs executor class {need!r}; {model!r} is {entry.get('class') or 'unclassed'}")


def _worktree_for(repo_root: Path, branch: str, codename: str, explicit: Path | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    if git_text(["branch", "--show-current"], repo_root) == branch:
        return repo_root.resolve()
    wt = reviews_root(repo_root).parent / ".worktrees" / codename
    if not wt.is_dir():
        wt.parent.mkdir(parents=True, exist_ok=True)
        r = run(["worktree", "add", str(wt), branch], repo_root)
        if not r.ok:
            raise WorkerError(f"cannot create a worktree for {branch}: {r.err.strip()}")
    return wt.resolve()


def _cli_for(repo_root: Path, entry: dict[str, Any]) -> tuple[str | None, str]:
    """``(custom cli, model id the harness is told)``."""
    prof = profile_for_entry(repo_root, entry)
    cli = (entry.get("channels") or {}).get("cli") or (prof.cli() if prof and prof.ok else None)
    return cli, (prof.api_id if prof and prof.ok else str(entry["id"]))


def delegate(repo_root: Path, node_id: str, model: str, *, harness: str | None = None,
             worktree: Path | None = None) -> tuple[WorkerRecord, bool]:
    """``(record, created)``: an active worker on the leaf is returned, not duplicated."""
    existing = active_for_node(repo_root, node_id)
    if existing:
        return existing, False
    entry, harness = _entry_and_harness(repo_root, model, harness)
    config, _ = effective_config(repo_root)
    limit = int(config["policy"]["max_workers"])
    active = list_records(repo_root, active_only=True)
    if len(active) >= limit:
        raise WorkerError(f"{len(active)} workers active, policy max_workers is {limit}; "
                          "wait for one to finish or raise the limit")
    t = _target(repo_root, node_id)
    _check_eligible(entry, t.node, model)
    text, _prof, err = build_prompt(repo_root, node_id, role="executor", model=model)
    if err:
        raise WorkerError(err)
    prompt = repo_root / "work" / f"prompt-{node_id}-executor-{model}.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(text, encoding="utf-8")
    branch = str(t.entry["branch"])
    wt = _worktree_for(repo_root, branch, str(t.node.get("codename") or node_id), worktree)
    cli, api_id = _cli_for(repo_root, entry)
    launch = adapter_for(harness).launch(prompt, wt, api_id, cli)
    rec = create_record(repo_root, node_id, harness, model, wt, branch=branch,
                        contract_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        billing_route=entry.get("billing_route"))
    spawn(repo_root, rec, launch)
    return rec, True


def _send(repo_root: Path, rec: WorkerRecord, text: str, kind: str) -> WorkerRecord:
    require_writer(rec)
    if not rec.active:
        raise WorkerError(f"{rec.worker_id} is {rec.state}; delegate again instead")
    if pid_alive(rec.pid):
        raise WorkerError(f"{rec.worker_id} is still running (pid {rec.pid}); the CLI adapters cannot steer a "
                          "live turn — wait for it to end, or terminate it")
    adapter = adapter_for(rec.harness)
    if not adapter.caps.resume:
        raise Unsupported(f"unsupported by {rec.harness}: resume")
    if not rec.provider_session_id:
        raise WorkerError(f"{rec.worker_id} has no native session id yet; nothing to resume")
    entry, _ = _entry_and_harness(repo_root, rec.model, rec.harness)
    cli, api_id = _cli_for(repo_root, entry)
    n = rec.last_event_seq + 1
    prompt = repo_root / "work" / f"prompt-{rec.worker_id}-{kind}-{n}.md"
    prompt.write_text(text, encoding="utf-8")
    launch = adapter.resume(rec.provider_session_id, prompt, Path(rec.worktree), api_id, cli)
    append_event(repo_root, rec, "message", source="orchestrator", authority="orchestrator",
                 summary=f"{kind}: {' '.join(text.split())[:300]}")
    spawn(repo_root, rec, launch, resumed=True)
    return rec


def message(repo_root: Path, worker_id: str, text: str) -> WorkerRecord:
    return _send(repo_root, load_record(repo_root, worker_id), text, "message")


def resume(repo_root: Path, worker_id: str) -> WorkerRecord:
    return _send(repo_root, load_record(repo_root, worker_id), CONTINUE_PROMPT, "resume")


def interrupt(repo_root: Path, worker_id: str) -> None:
    rec = load_record(repo_root, worker_id)
    if not adapter_for(rec.harness).caps.interrupt:
        raise Unsupported(f"unsupported by {rec.harness}: interrupt (a one-shot CLI has no interrupt short of "
                          "`worker terminate`, which loses the turn)")


def terminate(repo_root: Path, worker_id: str) -> WorkerRecord:
    rec = load_record(repo_root, worker_id)
    if rec.state == "terminated":
        return rec
    if pid_alive(rec.pid):
        try:
            os.kill(int(rec.pid), signal.SIGTERM)
        except OSError as e:
            raise WorkerError(f"cannot signal pid {rec.pid}: {e}") from None
    set_state(repo_root, rec, "terminated", pid=None)
    append_event(repo_root, rec, "terminated", source="orchestrator", authority="orchestrator",
                 summary="terminated by the coordinator")
    return rec


def handoff(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, list[str]]:
    """Lease the worker to a human; returns the native resume command."""
    rec = load_record(repo_root, worker_id)
    if rec.lease.get("holder") == "human":
        return rec, adapter_for(rec.harness).human_resume(rec.provider_session_id or "", Path(rec.worktree))
    require_writer(rec)
    if pid_alive(rec.pid):
        raise WorkerError(f"{rec.worker_id} is running (pid {rec.pid}); wait for idle or terminate first")
    adapter = adapter_for(rec.harness)
    if not adapter.caps.handoff or not rec.provider_session_id:
        raise Unsupported(f"unsupported by {rec.harness}: handoff (no native session to resume)")
    cmd = adapter.human_resume(rec.provider_session_id, Path(rec.worktree))
    take_checkpoint(repo_root, rec)
    set_lease(repo_root, rec, "human")
    set_state(repo_root, rec, "handed_off")
    append_event(repo_root, rec, "handoff", source="orchestrator", authority="orchestrator",
                 summary=f"handed off; resume with: {' '.join(cmd)} (in {rec.worktree})")
    return rec, cmd


def _hook_prompts(repo_root: Path, rec: WorkerRecord, since: str) -> list[dict[str, Any]]:
    path = interventions_path(repo_root, rec.worker_id)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and str(d.get("at", "")) >= since:
            out.append(d)
    return out


def _diff_stat(worktree: Path, since_sha: str | None) -> str:
    """``git diff --stat`` since the checkpoint plus the untracked files, which a diff omits."""
    stat = (git_text(["diff", "--stat", since_sha], worktree) or "") if since_sha else ""
    new = git_text(["ls-files", "--others", "--exclude-standard"], worktree) or ""
    return "\n".join(x for x in [stat, *(f" {p} | new" for p in new.splitlines() if p.strip())] if x)


def reclaim(repo_root: Path, worker_id: str, note: str = "") -> tuple[WorkerRecord, dict[str, Any]]:
    rec = load_record(repo_root, worker_id)
    if rec.lease.get("holder") != "human":
        raise WorkerError(f"{rec.worker_id} is not handed off (lease: {rec.lease.get('holder')})")
    cp = rec.checkpoint or {}
    prompts = _hook_prompts(repo_root, rec, str(cp.get("at") or ""))
    stat = _diff_stat(Path(rec.worktree), cp.get("git_head"))
    heard = [str(p.get("prompt", ""))[:200] for p in prompts]
    summary = (f"human direction ({len(heard)} prompt(s) recorded by hook): " + " | ".join(heard)
               if heard else "human session returned without hook evidence")
    if note:
        summary += f" — note: {note}"
    detail = {"prompts": heard, "diff_stat": stat, "checkpoint": cp}
    record_intervention(repo_root, rec, summary, source="hook" if heard else "human", detail=detail)
    if not heard:
        add_flag(repo_root, rec, FLAG_EXTERNAL)
    set_lease(repo_root, rec, "broker")
    set_state(repo_root, rec, "idle")
    append_event(repo_root, rec, "reclaim", source="orchestrator", authority="orchestrator",
                 summary=f"lease back to broker; epoch {rec.instruction_epoch}")
    return rec, detail


def adopt(repo_root: Path, node_id: str, harness: str, session_id: str, *,
          worktree: Path | None = None, model: str = "unknown") -> WorkerRecord:
    t = _target(repo_root, node_id)
    wt = _worktree_for(repo_root, str(t.entry["branch"]), str(t.node.get("codename") or node_id), worktree)
    rec = create_record(repo_root, node_id, harness, model, wt, branch=str(t.entry["branch"]), lease="native")
    rec.provider_session_id = session_id
    rec.state = "idle"
    save_record(repo_root, rec)
    take_checkpoint(repo_root, rec)
    append_event(repo_root, rec, "adopted", source="orchestrator", authority="orchestrator",
                 summary=f"adopted native {harness} session {session_id}; observe only")
    return rec


def _changed_since(worktree: Path, since_sha: str | None) -> list[str]:
    if not since_sha:
        return []
    out = git_text(["diff", "--name-only", since_sha], worktree) or ""
    untracked = git_text(["ls-files", "--others", "--exclude-standard"], worktree) or ""
    return sorted({p for p in (out + "\n" + untracked).splitlines() if p.strip()})


def reconcile(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, dict[str, Any]]:
    rec = load_record(repo_root, worker_id)
    t = _target(repo_root, rec.node_id)
    since = (rec.checkpoint or {}).get("git_head") or t.base
    changed = _changed_since(Path(rec.worktree), since)
    zones = t.touch_zones
    outside = [p for p in changed if zones and not any(zone_matches(z, p) for z in zones)]
    text, _p, err = build_prompt(repo_root, rec.node_id, role="executor", model=rec.model)
    contract_changed = bool(rec.contract_hash and not err
                            and hashlib.sha256(text.encode("utf-8")).hexdigest() != rec.contract_hash)
    if outside or contract_changed:
        add_flag(repo_root, rec, FLAG_RECONCILE)
    else:
        clear_flag(repo_root, rec, FLAG_RECONCILE)
    delta = {"since": since, "changed": changed, "outside_touch_zones": outside,
             "contract_changed": contract_changed, "epoch": rec.instruction_epoch,
             "needs_reconcile": FLAG_RECONCILE in rec.flags}
    append_event(repo_root, rec, "reconcile", source="orchestrator", authority="orchestrator",
                 summary=(f"{len(changed)} path(s) changed, {len(outside)} outside touch zones"
                          + ("; contract changed" if contract_changed else "")), detail=delta)
    return rec, delta


# --- sync ------------------------------------------------------------------

def _sync_path(repo_root: Path) -> Path:
    return workers_dir(repo_root) / "sync.yaml"


def sync(repo_root: Path, *, ack: bool = False) -> list[dict[str, Any]]:
    """Per worker, the events after the last acknowledged one; ``ack`` moves the mark."""
    path = _sync_path(repo_root)
    marks: dict[str, int] = {}
    if path.is_file():
        marks = {str(k): int(v) for k, v in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).items()}
    out = []
    for rec in list_records(repo_root):
        evs = events_since(repo_root, rec.worker_id, marks.get(rec.worker_id, 0))
        if not evs:
            continue
        out.append({"worker_id": rec.worker_id, "node_id": rec.node_id, "state": rec.state,
                    "lease": rec.lease.get("holder"), "flags": list(rec.flags), "epoch": rec.instruction_epoch,
                    "events": [{"seq": e.seq, "type": e.type, "source": e.source, "summary": e.summary} for e in evs]})
        if ack:
            marks[rec.worker_id] = evs[-1].seq
    if ack and out:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(marks, sort_keys=True), encoding="utf-8")
    return out


def record_hook_prompt(repo_root: Path, session_id: str, prompt: str) -> WorkerRecord | None:
    """Append a human prompt seen by a harness hook to the matching worker's file."""
    rec = next((r for r in list_records(repo_root) if r.provider_session_id == session_id), None)
    if rec is None:
        return None
    path = interventions_path(repo_root, rec.worker_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": _now(), "session_id": session_id, "prompt": prompt[:2000]}) + "\n")
    return rec
