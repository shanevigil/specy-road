"""M16.1.2: the review-gate decision table, the reviewer-output filing rows and the frozen records.

The rows live in ``cases/`` and ``records/`` beside this file (each file's header says what a row holds); this module
only builds each row's repository and asserts what the table records. The gate is evaluated as finish-this-task,
mark-implementation-reviewed, ``handoff status`` and ``review list`` evaluate it: the node and commit from
``resolve_target(repo, node, "HEAD")``, then ``evaluate_gate`` with the registry's branch.
"""

from __future__ import annotations

import inspect
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.review_repo_helpers import commit_file, git, make_review_repo, review_output
from tests.test_review_defer import bound_ledger

from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts.registration_pickup_commit import registration_commit_message
from specy_road.review_answer import final_answer
from specy_road.review_files import archive_review, load_ready, load_review, render_front_matter, reviews_dir
from specy_road.review_gate import GateResult, evaluate_gate
from specy_road.review_policy_pin import pinned_message
from specy_road.review_record_write import file_review
from specy_road.review_signing import notes_digest, notes_problem, sign
from specy_road.review_target import resolve_target
from specy_road.review_write_check import snapshot
from specy_road.worker_adapters import ADAPTERS

HERE = Path(__file__).resolve().parent
GATE = yaml.safe_load((HERE / "cases" / "gate_rows.yaml").read_text(encoding="utf-8"))
FILING = yaml.safe_load((HERE / "cases" / "filing_rows.yaml").read_text(encoding="utf-8"))
KEYS = yaml.safe_load((HERE / "cases" / "policy_keys.yaml").read_text(encoding="utf-8"))
MANIFEST = yaml.safe_load((HERE / "records" / "MANIFEST.yaml").read_text(encoding="utf-8"))
SCHEMA = HERE.parents[2] / "specy_road" / "templates" / "project" / "schemas" / "orchestration.schema.json"
NODE_ID, BODY = "M1.1", "notes\n"


def orchestration(row: dict[str, Any]) -> str | None:
    """The row's ``roadmap/orchestration.yaml``: raw text, or its roster with its policy; ``None``: no file."""
    if "orchestration" in row:
        return row["orchestration"]
    roster = GATE["rosters"][row["roster"]] if row.get("roster") else None
    if roster is None and not row.get("policy"):
        return None
    return yaml.safe_dump({"version": 1, "roster": roster or GATE["rosters"]["human"],
                           "policy": row.get("policy") or {}}, sort_keys=False)


class Leaf:
    """One row's claimed leaf: the repository, its commit labels and the signing keys it generated."""

    def __init__(self, tmp_path: Path, orch: str | None) -> None:
        self.keys_dir, self.keys = tmp_path / "keys", {}
        if orch:
            orch = re.sub(r"@key:(\w+)", lambda m: self.public_key(m[1]), orch)
        self.repo = make_review_repo(tmp_path, orchestration=orch)
        self.labels: dict[str, str] = {}

    def public_key(self, name: str) -> str:
        if name not in self.keys:
            self.keys_dir.mkdir(exist_ok=True)
            key = self.keys_dir / name
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
            self.keys[name] = key
        return (self.keys_dir / f"{name}.pub").read_text(encoding="utf-8").strip()

    def sha(self, label: str = "head") -> str:
        return git(self.repo, "rev-parse", "HEAD") if label == "head" else self.labels[label]

    def reviews(self) -> Path:
        d = reviews_dir(self.repo, NODE_ID)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def gate(self, target: str | None = None) -> GateResult:
        t = resolve_target(self.repo, NODE_ID, "HEAD")
        commit = "0" * 40 if target == "unresolvable" else t.commit
        return evaluate_gate(self.repo, t.node, commit, branch=(t.entry or {}).get("branch"))

    # --- steps (the vocabulary in gate_rows.yaml's header) ---

    def commit(self, path: str, text: str = "x = 1\n", label: str | None = None) -> None:
        sha = commit_file(self.repo, path, text, f"commit {path}")
        if label:
            self.labels[label] = sha

    def dev(self, path: str, text: str) -> None:
        git(self.repo, "checkout", "-q", "dev")
        commit_file(self.repo, path, text, f"dev edits {path}")
        git(self.repo, "checkout", "-q", "feature/rm-thing")

    def claim(self) -> None:
        git(self.repo, "checkout", "-q", "dev")
        message = pinned_message(self.repo, registration_commit_message("thing", include_ci_skip=True))
        git(self.repo, "commit", "-q", "--allow-empty", "-m", message)
        git(self.repo, "checkout", "-q", "feature/rm-thing")
        git(self.repo, "rebase", "-q", "dev")

    def record_data(self, model: str, verdict: str = "approve", at: str = "head", a1: str = "pass",
                    drop: str | None = None, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        data = {"node_id": NODE_ID, "model": model, "date": "2026-10-26", "verdict": verdict, "commit": self.sha(at),
                "acceptance": {"A1": a1, "A2": "pass"},
                "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
                "commands_rerun": [], "required_changes": [] if verdict == "approve" else ["fix"],
                "fresh_session": True, "authored_fix": False, "is_coordinator": False, **(fields or {})}
        if "delta_from" in data:
            data["delta_from"] = self.sha(data["delta_from"])
        if drop:
            del data["acceptance"][drop]
        return data

    def review(self, model: str, history: bool = False, sign_with: str | None = None, **kw: Any) -> None:
        data = self.record_data(model, **kw)
        if sign_with:
            self.public_key(sign_with)
            data["notes_sha256"] = notes_digest(BODY)
            data["signature"] = sign(data, self.keys[sign_with])
        text = render_front_matter(data, BODY)
        (self.reviews() / f"REVIEW-{model}.md").write_text(text, encoding="utf-8")
        if history:
            archive_review(self.repo, NODE_ID, model, text)

    def record(self, model: str, verdict: str, a1: str = "pass", boundary: list[str] | None = None) -> None:
        data = self.record_data(model, verdict, a1=a1)
        data["findings"]["boundary"] = boundary or []
        notes = self.repo.parent / f"notes-{model}.md"
        notes.write_text(render_front_matter(data, BODY), encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            review_cli.main(["review", "record", NODE_ID, "--model", model, "--verdict", verdict,
                             "--file", str(notes), "--repo-root", str(self.repo)])
        assert e.value.code == 0

    def ready(self, agent: str, exit: int = 0, blocked_on: str | None = None) -> None:
        data = {"node_id": NODE_ID, "agent": agent, "branch": "feature/rm-thing", "commit": self.sha(),
                "base": git(self.repo, "rev-parse", "dev"), "changed_paths": ["src/a.py"],
                "verify": [{"cmd": "pytest" if exit == 0 else "false", "exit": exit}]}
        if blocked_on:
            data["blocked_on"] = [{"acceptance": blocked_on, "reason": "cannot meet without weakening tests"}]
        (self.reviews() / f"READY-{agent}.md").write_text(render_front_matter(data), encoding="utf-8")

    def defer(self, **finding: str) -> None:
        """RCA-2 proposing to defer opus's block at HEAD, the decision ``review defer`` closes, and its marker."""
        item = {**finding, "reviewer": "opus", "commit": self.sha()}
        rca = {"node_id": NODE_ID, "model": "sol", "date": "2026-11-04",
               "trigger": {"rule": "forced", "acceptance_ids": [], "round": 2, "reason": "fix-round budget spent"},
               "classification": {"primary": "hard_problem", "confidence": 0.7},
               "evidence": [{"kind": "finding", "ref": "round 2/opus", "note": "a new input class"}],
               "recommended_action": {"type": "defer_findings", "instructions": "defer the new class",
                                      "requires_human_approval": True},
               "deferred_findings": [{**item, "follow_up_title": "Handle it", "follow_up_acceptance": "It works"}]}
        (self.reviews() / "RCA-2.md").write_text(render_front_matter(rca, "reasoning\n"), encoding="utf-8")
        (self.repo / "roadmap" / "decisions.yaml").write_text(yaml.safe_dump(bound_ledger("RCA-2.md", [item])))
        (self.reviews() / "DEFERRAL-2.yaml").write_text(yaml.safe_dump(
            {"node_id": NODE_ID, "rca": "RCA-2.md", "round": 2, "decision": "D9", "deferred": [item]}))

    def run(self, step: dict[str, Any]) -> None:
        (op, arg), = step.items()
        if op == "review":
            arg = {("sign_with" if k == "sign" else k): v for k, v in arg.items()}
        getattr(self, op)(**(arg or {}))


def assert_outcome(gate: GateResult, row: dict[str, Any]) -> None:
    want = row["expect"]
    got = {"passed": gate.passed, "approvals": gate.approval_count, "problems": len(gate.problems()),
           "required": gate.required, "distinct_families": gate.distinct_families, "carry": gate.bookkeeping_carry}
    assert {k: got[k] for k in want} == want, gate.problems()
    for sentence in row.get("says") or {}:
        assert sentence in " ".join(gate.problems())


@pytest.mark.parametrize("row", GATE["rows"], ids=[r["id"] for r in GATE["rows"]])
def test_gate_row(tmp_path: Path, row: dict[str, Any]) -> None:
    leaf = Leaf(tmp_path, orchestration(row))
    for step in row["steps"]:
        leaf.run(step)
    assert_outcome(leaf.gate(row.get("target")), row)


def test_the_branch_list_is_every_field_passed_and_problems_read() -> None:
    source = inspect.getsource(GateResult.passed.fget) + inspect.getsource(GateResult.problems)
    read = set(re.findall(r"self\.(\w+)", source))
    listed = [f for b in GATE["branches"] for f in b["reads"]]
    assert sorted(listed) == sorted(read)


def test_every_branch_has_a_refusal_row_and_an_approval_row_where_it_can_pass() -> None:
    for b in GATE["branches"]:
        outcomes = {r["expect"]["passed"] for r in GATE["rows"] if r["branch"] == b["branch"]}
        assert outcomes == ({False, True} if b["can_pass"] else {False}), b["branch"]


def test_a_row_with_no_approval_is_refused_at_the_default_config() -> None:
    """The table's rows do not run under a configuration that makes the gate trivially pass."""
    assert any(r["roster"] is None and "orchestration" not in r and not r["steps"]
               and r["expect"] == {**r["expect"], "passed": False, "approvals": 0} for r in GATE["rows"])


def test_every_policy_key_is_classified_and_every_gate_input_has_a_row() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    keys = set(schema["$defs"]["policy"]["properties"])
    gate, other = set(KEYS["gate_inputs"]), set(KEYS["non_gate"])
    assert not gate & other
    assert gate | other == keys
    rows_set = {k for r in GATE["rows"] if (text := orchestration(r))
                for k in (yaml.safe_load(text).get("policy") or {})}
    assert gate - rows_set == set()


@pytest.mark.parametrize("row", FILING["rows"], ids=[r["id"] for r in FILING["rows"]])
def test_filing_from_a_final_message(tmp_path: Path, row: dict[str, Any]) -> None:
    leaf = Leaf(tmp_path, orchestration({"roster": "team"}))
    answer = review_output(leaf.sha(), model="opus")
    if "notes" in row:
        answer["notes"] = row["notes"]
    lines = [{"type": "system", "subtype": "init", "session_id": "s"},
             {"type": "result", "subtype": "success", "result": row["message"].replace("{answer}", json.dumps(answer))}]
    parsed = final_answer(ADAPTERS["claude-code"], "\n".join(json.dumps(x) for x in lines))
    reviews = leaf.reviews()
    before = snapshot(leaf.repo, reviews, "opus")
    outcome = file_review(leaf.repo, NODE_ID, "opus", reviews, answer=parsed, before=before,
                          after=snapshot(leaf.repo, reviews, "opus", like=before))
    assert outcome.state == row["expect"]["state"], outcome.reason
    assert (reviews / "REVIEW-opus.md").is_file() == (outcome.state == "recorded")
    assert_outcome(leaf.gate(), {"expect": {k: v for k, v in row["expect"].items() if k != "state"}})


def test_frozen_records_are_read_as_at_pickup() -> None:
    root = HERE / "records"
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.md"))
    assert files == sorted(r["file"] for r in MANIFEST["records"])
    for rec in MANIFEST["records"]:
        path = root / rec["file"]
        r = (load_ready if path.name.startswith("READY-") else load_review)(path)
        got = {"ok": r.ok, **({"keys": sorted(r.data)} if r.ok else {"errors": r.errors})}
        if r.ok and path.name.startswith("REVIEW-"):
            got |= {"verdict": r.data["verdict"], "notes_match": notes_problem(r.data, r.body) is None}
        assert got == {k: v for k, v in rec.items() if k not in ("file", "source")}, rec["file"]
    assert {"READY", "REVIEW"} <= {Path(r["file"]).name.split("-")[0] for r in MANIFEST["records"] if r["ok"]}
