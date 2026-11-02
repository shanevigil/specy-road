"""M4.3: add-idea / revise --from-file as one write, merge, --from-gap, cluster objects."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_session import BrainstormError, read_session, session_path
from tests.helpers import DOGFOOD

SLUG = "how-do-we-expand-payments"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main(["brainstorm", *args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _start(repo: Path, *titles: str) -> None:
    assert _cli(repo, "start", "--topic", "How do we expand payments?")[0] == 0
    for title in titles:
        assert _cli(repo, "add-idea", "--title", title)[0] == 0


def _session(repo: Path):
    return read_session(repo, SLUG)


def _file(tmp_path: Path, name: str, data) -> str:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")
    return str(path)


def test_add_idea_from_file_records_every_idea_with_flag_names_as_keys(repo: Path, tmp_path: Path) -> None:
    _start(repo)
    path = _file(tmp_path, "ideas.yaml", [
        {"title": "Vault", "rationale": "PCI scope", "kind": "risk", "effort": "M",
         "evidence": ["https://a.example", "https://b.example"], "origin": "claude-code/opus/SCAMPER/1",
         "hypothesis": "If we do this, audit cost drops", "assumption": ["SMBs pay by card"]},
        {"title": "Pay by link", "from-gap": True},
        {"title": "Retry", "effort": 3},
    ])
    code, out, _err = _cli(repo, "add-idea", "--from-file", path)
    assert code == 0 and "recorded 3 idea(s)" in out
    s = _session(repo)
    vault, link, retry = (s.by_id(i) for i in ("B1", "B2", "B3"))
    assert (vault.kind, vault.effort, vault.evidence) == ("risk", "M", ["https://a.example", "https://b.example"])
    assert vault.origin == {"harness": "claude-code", "model": "opus", "lens": "SCAMPER", "round": "1"}
    assert vault.assumptions == ["SMBs pay by card"] and vault.raised_in is None
    assert link.raised_in == "converge" and retry.effort == "3"


@pytest.mark.parametrize("bad, message", [
    ({"title": "Bad", "kind": "nope"}, "invalid choice"),
    ({"title": "Bad", "bogus": "x"}, "unrecognized arguments"),
    ({"tit": "Abbreviated"}, "unrecognized arguments"),
    ({"title": ["One", "Two"]}, "takes one value"),
    ({"title": "Bad", "slug": "other"}, "not allowed"),
    ({"title": "Bad", "id": "B9"}, "not allowed"),
    ({"rationale": "no title"}, "missing a title"),
    ("just text", "expected a mapping"),
])
def test_add_idea_from_file_writes_nothing_when_any_record_is_bad(repo: Path, tmp_path: Path, bad, message) -> None:
    _start(repo, "Existing")
    before = session_path(repo, SLUG).read_text(encoding="utf-8")
    path = _file(tmp_path, "ideas.yaml", {"ideas": [{"title": "Good one"}, {"title": "Good two"}, bad]})
    code, out, err = _cli(repo, "add-idea", "--from-file", path)
    assert code == 1 and not out.strip()
    assert message in err and "record 3" in err and "nothing was written" in err
    assert session_path(repo, SLUG).read_text(encoding="utf-8") == before


def test_add_idea_reads_jsonl_on_stdin(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _start(repo)
    lines = "\n".join(json.dumps(r) for r in ({"title": "One", "kind": "research"}, {"title": "-dash first"}))
    monkeypatch.setattr("sys.stdin", io.StringIO(lines + "\n"))
    code, out, _err = _cli(repo, "add-idea", "--from-file", "-")
    assert code == 0, out
    s = _session(repo)
    assert [(i.title, i.kind) for i in s.ideas] == [("One", "research"), ("-dash first", "feature")]


def test_add_idea_from_file_refuses_flags_and_needs_a_title_without_one(repo: Path, tmp_path: Path) -> None:
    _start(repo)
    path = _file(tmp_path, "ideas.yaml", [{"title": "One"}])
    code, _out, err = _cli(repo, "add-idea", "--from-file", path, "--title", "Two")
    assert code == 1 and "drop --title" in err
    code, _out, err = _cli(repo, "add-idea")
    assert code == 1 and "needs --title" in err
    code, _out, err = _cli(repo, "add-idea", "--from-file", _file(tmp_path, "empty.yaml", "[]\n"))
    assert code == 1 and "non-empty" in err
    assert not _session(repo).ideas


def test_revise_from_file_applies_every_verdict(repo: Path, tmp_path: Path) -> None:
    _start(repo, "One", "Two")
    path = _file(tmp_path, "verdicts.yaml", {"verdicts": [
        {"id": "B1", "recommendation": "strong", "why": "Principle 3", "cluster": "C1",
         "critic": ["feasibility: needs billing", "value: SMBs"], "overlap": ["M1:adjacent"]},
        {"id": "b2", "recommendation": "park", "append_why": "duplicates B1"},
    ]})
    code, out, _err = _cli(repo, "revise", "--from-file", path)
    assert code == 0 and "applied 2 verdict record(s)" in out
    s = _session(repo)
    one, two = s.by_id("B1"), s.by_id("B2")
    assert (one.recommendation, one.verdict_why, one.cluster_id) == ("strong", "Principle 3", "C1")
    assert one.critic == {"feasibility": "needs billing", "value": "SMBs"}
    assert one.overlap == [{"node_id": "M1", "relation": "adjacent"}]
    assert (two.recommendation, two.verdict_why, two.status) == ("park", "duplicates B1", "proposed")


@pytest.mark.parametrize("bad, message", [
    ({"id": "B9", "recommendation": "strong"}, "no idea 'B9'"),
    ({"id": "B2", "recommendation": "maybe"}, "invalid choice"),
    ({"recommendation": "strong"}, "needs `id`"),
    ({"id": "B2", "overlap": ["M1:sideways"]}, "overlap relation"),
])
def test_revise_from_file_applies_nothing_when_any_record_is_bad(repo: Path, tmp_path: Path, bad, message) -> None:
    _start(repo, "One", "Two")
    before = session_path(repo, SLUG).read_text(encoding="utf-8")
    path = _file(tmp_path, "verdicts.yaml", [{"id": "B1", "recommendation": "strong"}, bad])
    code, out, err = _cli(repo, "revise", "--from-file", path)
    assert code == 1 and not out.strip() and message in err
    assert session_path(repo, SLUG).read_text(encoding="utf-8") == before


def test_revise_needs_an_id_or_a_file_but_not_both(repo: Path, tmp_path: Path) -> None:
    _start(repo, "One")
    assert "needs IDEA_ID" in _cli(repo, "revise", "--recommendation", "strong")[2]
    path = _file(tmp_path, "verdicts.yaml", [{"id": "B1", "recommendation": "strong"}])
    code, _out, err = _cli(repo, "revise", "B1", "--from-file", path)
    assert code == 1 and "drop B1" in err
    assert _cli(repo, "revise", "B1", "--recommendation", "consider")[0] == 0
    assert _session(repo).by_id("B1").recommendation == "consider"


def test_merge_sets_status_and_reverse_links_and_promote_skips_it(repo: Path) -> None:
    _start(repo, "Vault", "Card vault", "Tokenise cards")
    code, out, _err = _cli(repo, "merge", "B2", "--into", "B1", "b3")
    assert code == 0 and "B2 merged into B1, B3" in out
    s = _session(repo)
    assert s.by_id("B2").status == "merged" and s.by_id("B2").merged_into == ["B1", "B3"]
    assert s.by_id("B2").decision["into"] == "B1, B3"
    assert s.by_id("B1").merged_from == ["B2"] and s.by_id("B3").merged_from == ["B2"]
    assert "=> B1, B3" in _cli(repo, "list")[1]
    code, _out, err = _cli(repo, "accept", "B1", "B2")
    assert code == 1 and "merged into B1, B3" in err
    assert _cli(repo, "accept", "B1")[0] == 0
    code, out, _err = _cli(repo, "promote", "--dry-run", "--under", "M1")
    assert code == 0 and "(from B1)" in out and "B2" not in out


def test_merge_refuses_self_chains_and_repeats(repo: Path) -> None:
    _start(repo, "One", "Two", "Three")
    assert "other than B1" in _cli(repo, "merge", "B1", "--into", "B1")[2]
    assert _cli(repo, "merge", "B2", "--into", "B1")[0] == 0
    assert "itself merged into B1" in _cli(repo, "merge", "B3", "--into", "B2")[2]
    assert "is merged into B1" in _cli(repo, "merge", "B2", "--into", "B3")[2]
    assert _session(repo).by_id("B3").status == "proposed"


def test_from_gap_marks_the_idea_and_recommend_lists_it_for_a_verdict(repo: Path) -> None:
    _start(repo, "One")
    assert _cli(repo, "recommend")[0] == 0
    assert _cli(repo, "add-idea", "--title", "Nobody serves refunds", "--from-gap")[0] == 0
    assert _session(repo).by_id("B2").raised_in == "converge"
    assert "[gap]" in _cli(repo, "list")[1]
    code, out, _err = _cli(repo, "recommend")
    assert code == 0 and "gap idea B2 (raised in the converge pass) needs a verdict" in out
    code, out, _err = _cli(repo, "recommend", "--check")
    assert code == 1 and "Nobody serves refunds [gap]" in out
    assert _cli(repo, "revise", "B2", "--recommendation", "consider")[0] == 0
    assert "gap idea" not in _cli(repo, "recommend")[1]


def test_recommend_check_does_not_ask_a_merged_idea_for_a_verdict(repo: Path) -> None:
    _start(repo, "One", "Two")
    assert _cli(repo, "revise", "B1", "--cluster", "C1", "--recommendation", "strong")[0] == 0
    assert _cli(repo, "merge", "B2", "--into", "B1")[0] == 0
    assert _cli(repo, "recommend", "--check")[0] == 0


def test_cluster_records_an_object_shown_by_list_by_cluster(repo: Path) -> None:
    _start(repo, "Vault", "Card vault", "Unrelated")
    for ident in ("B1", "B2"):
        assert _cli(repo, "revise", ident, "--cluster", "C1")[0] == 0
    code, out, _err = _cli(repo, "cluster", "C1", "--name", "Stored cards", "--best", "b2",
                           "--critic", "feasibility: PCI audit first")
    assert code == 0 and "best B2, 2 member(s)" in out
    assert _cli(repo, "cluster", "C2", "--name", "Empty for now")[0] == 0
    s = _session(repo)
    assert s.clusters["C1"] == {"name": "Stored cards", "best": "B2", "critic": {"feasibility": "PCI audit first"}}
    listing = _cli(repo, "list", "--by", "cluster")[1]
    assert "C1  Stored cards  (2)  best: B2" in listing and "C2  Empty for now  (0)" in listing
    assert "PCI audit first" not in listing
    assert "feasibility: PCI audit first" in _cli(repo, "list", "--by", "cluster", "--show-verdicts")[1]
    assert json.loads(_cli(repo, "list", "--json")[1])["clusters"]["C1"]["best"] == "B2"


def test_cluster_best_must_be_a_member_and_empty_clears(repo: Path) -> None:
    _start(repo, "Vault", "Unrelated")
    assert _cli(repo, "revise", "B1", "--cluster", "C1")[0] == 0
    code, _out, err = _cli(repo, "cluster", "C1", "--best", "B2")
    assert code == 1 and "B2 is in cluster (none), not C1" in err
    assert _cli(repo, "cluster", "C1", "--name", "Cards", "--best", "B1")[0] == 0
    assert _cli(repo, "cluster", "C1", "--best", "")[0] == 0
    assert _session(repo).clusters["C1"] == {"name": "Cards"}


def test_session_round_trips_links_and_clusters_and_rejects_bad_links(repo: Path) -> None:
    _start(repo, "One", "Two")
    assert _cli(repo, "merge", "B2", "--into", "B1")[0] == 0
    assert _cli(repo, "cluster", "C1", "--name", "Cards")[0] == 0
    raw = yaml.safe_load(session_path(repo, SLUG).read_text(encoding="utf-8"))
    assert raw["clusters"] == {"C1": {"name": "Cards"}}
    assert raw["ideas"][0]["merged_from"] == ["B2"] and "merged_into" not in raw["ideas"][0]
    raw["ideas"][1]["merged_into"] = "B1"
    session_path(repo, SLUG).write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(BrainstormError, match="merged_into must be a list"):
        read_session(repo, SLUG)
