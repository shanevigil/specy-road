"""Tests for advisory review_node script."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road import llm_client
from specy_road.bundled_scripts import review_node
from specy_road.roadmap_chunk_utils import write_json_chunk
from tests.helpers import REPO, SCHEMAS, use_fake_llm


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    shutil.copytree(SCHEMAS, tmp_path / "schemas")
    shutil.copytree(REPO / "constraints", tmp_path / "constraints")
    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "shared").mkdir(parents=True)
    (tmp_path / "shared" / "README.md").write_text("# S\n", encoding="utf-8")
    (tmp_path / "shared" / "nested").mkdir(parents=True)
    (tmp_path / "shared" / "nested" / "note.md").write_text(
        "## Deep title\n\nbody\n",
        encoding="utf-8",
    )
    (tmp_path / "shared" / "asset.bin").write_bytes(b"\x00\x01\xff")
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (tmp_path / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    nodes = [
        {
            "id": "M99",
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "codename": None,
            "execution_milestone": "Human-led",
            "status": "Complete",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
        {
            "id": "M99.1",
            "parent_id": "M99",
            "type": "task",
            "title": "One",
            "codename": "one",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
    ]
    write_json_chunk(tmp_path / "roadmap" / "phases" / "T.json", nodes)
    return tmp_path


def test_review_node_mock_llm(tiny_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SPECY_ROAD_OPENAI_MODEL", raising=False)
    captured: list[str] = []
    requests: list[dict] = []

    def reply(request: dict) -> str:
        requests.append(request)
        captured.append(request["messages"][-1]["content"])
        return "## Review\nok"

    use_fake_llm(monkeypatch, reply)
    review_node.main(["M99.1", "--repo-root", str(tiny_repo)])
    assert len(captured) == 1
    # One system turn (the feature-sheet prompt), then the context as one user turn.
    assert requests[0]["model"] == "gpt-4o-mini"
    assert [m["role"] for m in requests[0]["messages"]] == ["system", "user"]
    assert requests[0]["messages"][0]["content"] == review_node.SYSTEM_PROMPT
    msg = captured[0]
    assert "Brief" in msg
    assert "## shared/ index (possible references)" in msg
    assert msg.index("## Brief") < msg.index("## shared/ index (possible references)")
    assert msg.index("## shared/ index (possible references)") < msg.index(
        "## constraints/README.md",
    )
    assert "Deep title" in msg
    # Sort order is a property of the catalog block, so measure inside it: the
    # brief above now lists un-inlined shared/*.md paths of its own, and a
    # whole-message index() would compare positions across the two blocks.
    catalog = msg[
        msg.index("## shared/ index (possible references)") : msg.index(
            "## constraints/README.md",
        )
    ]
    assert "`shared/README.md`" in catalog
    assert "`shared/asset.bin`" in catalog
    assert "`shared/nested/note.md`" in catalog
    assert catalog.index("`shared/README.md`") < catalog.index("`shared/asset.bin`")
    assert catalog.index("`shared/asset.bin`") < catalog.index(
        "`shared/nested/note.md`",
    )
    assert "constraints/README.md" in msg
    assert "shared/README.md" in msg
    assert "Current planning sheet" in msg
    assert "Expected shape" in msg
    assert "scaffold-planning" in msg
    assert "deterministic index" in review_node.SYSTEM_PROMPT


def test_normalize_azure_endpoint_strips_path_and_query() -> None:
    raw = (
        "https://myresource.openai.azure.com/openai/responses?api-version=2024-08-01"
    )
    assert llm_client.normalize_azure_endpoint(raw) == (
        "https://myresource.openai.azure.com"
    )


def test_normalize_azure_endpoint_adds_https() -> None:
    assert (
        llm_client.normalize_azure_endpoint("myresource.openai.azure.com")
        == "https://myresource.openai.azure.com"
    )


def test_azure_settings_prefers_specy_over_azure_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://azure-only.example.com")
    monkeypatch.setenv("SPECY_ROAD_AZURE_OPENAI_ENDPOINT", "https://specy.example.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k-azure")
    monkeypatch.setenv("SPECY_ROAD_AZURE_OPENAI_API_KEY", "k-specy")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "dep-azure")
    monkeypatch.setenv("SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT", "dep-specy")
    monkeypatch.delenv("SPECY_ROAD_OPENAI_API_VERSION", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    ep, key, dep, ver = llm_client.azure_openai_settings_from_env()
    assert ep == "https://specy.example.com"
    assert key == "k-specy"
    assert dep == "dep-specy"
    assert ver == "2024-08-01-preview"


def test_anthropic_max_tokens_requires_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_MAX_TOKENS", raising=False)
    with pytest.raises(llm_client.ReviewError, match="SPECY_ROAD_ANTHROPIC_MAX_TOKENS"):
        llm_client.anthropic_max_completion_tokens()


def test_anthropic_provider_errors_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider failure is a ReviewError with the key redacted, as on the OpenAI path."""
    monkeypatch.setenv("SPECY_ROAD_ANTHROPIC_MAX_TOKENS", "100")
    sent: list[dict] = []

    class Messages:
        def create(self, **request: object) -> object:
            sent.append(request)
            raise RuntimeError("401: api_key=sk-ant-secret0123456789 rejected")

    client_type = type("Anthropic", (), {"__module__": "anthropic.fake", "messages": Messages()})
    monkeypatch.setattr(llm_client, "make_client", client_type)
    with pytest.raises(llm_client.ReviewError) as caught:
        llm_client.complete([{"role": "user", "content": "hi"}], system_prompt="S")
    assert "secret0123456789" not in str(caught.value)
    assert sent[0]["system"] == "S"
    assert sent[0]["max_tokens"] == 100


def test_normalize_review_strips_markdown_fence() -> None:
    raw = "```markdown\n## Intent\n\nx\n```"
    assert review_node._normalize_review_markdown_output(raw) == "## Intent\n\nx"


def test_system_prompt_for_planning_review_gate() -> None:
    sp = review_node.system_prompt_for_planning_review("gate")
    assert "roadmap **gate**" in sp
    assert "Why this gate exists" in sp
    assert sp != review_node.system_prompt_for_planning_review("task")


def test_feature_sheet_prompt_references_brief_dependency_section() -> None:
    """Feature-sheet prompt must steer the model to brief section 6 and
    forbid duplicating dep-intent prose in the revised sheet."""
    sp = review_node.system_prompt_for_planning_review("task")
    # Names the new brief section explicitly so the model has a landmark.
    assert "## 6. Dependency context" in sp
    assert "intent of upstream work" in sp
    # Tells the model to scan it before paraphrasing a dep.
    assert "scan brief section 6" in sp
    # Allows a one-line clarification only when something is missing.
    assert "one-line clarification" in sp
    assert "`## Approach`" in sp


def test_gate_planning_prompt_references_brief_dependency_section() -> None:
    """Gate-sheet prompt has the same dep-context discipline."""
    sp = review_node.system_prompt_for_planning_review("gate")
    assert "## 6. Dependency context" in sp
    assert "one-line clarification" in sp
    # Gate sheets put clarifications under Decisions and notes.
    assert "`## Decisions and notes`" in sp


def test_run_review_planning_body_override(
    tiny_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    captured: list[str] = []

    def reply(request: dict) -> str:
        captured.append(request["messages"][-1]["content"])
        return "## OK\n"

    use_fake_llm(monkeypatch, reply)
    review_node.run_review("M99.1", tiny_repo, planning_body="EDITOR_ONLY")
    assert "EDITOR_ONLY" in captured[0]


def test_run_review_returns_markdown(tiny_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    use_fake_llm(monkeypatch, lambda _request: "## OK\n")
    out = review_node.run_review("M99.1", tiny_repo)
    assert out.startswith("## OK")


def test_shared_catalog_sorts_lexicographically(
    tiny_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paths are sorted by string, not filesystem creation order."""
    (tiny_repo / "shared" / "b.md").write_text("# B\n", encoding="utf-8")
    (tiny_repo / "shared" / "a.md").write_text("# A\n", encoding="utf-8")
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    captured: list[str] = []

    def reply(request: dict) -> str:
        captured.append(request["messages"][-1]["content"])
        return "## OK\n"

    use_fake_llm(monkeypatch, reply)
    review_node.run_review("M99.1", tiny_repo)
    msg = captured[0]
    assert msg.index("`shared/a.md`") < msg.index("`shared/b.md`")


def test_shared_catalog_max_files_footer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_node, "_SHARED_CATALOG_MAX_FILES", 2)
    (tmp_path / "shared").mkdir()
    for i in range(4):
        (tmp_path / "shared" / f"z{i}.md").write_text("# t\n", encoding="utf-8")
    out = review_node._shared_catalog(tmp_path)
    assert "`shared/z0.md`" in out
    assert "`shared/z1.md`" in out
    assert "`shared/z2.md`" not in out
    assert "2 more path(s)" in out


def test_shared_catalog_no_shared_directory(tmp_path: Path) -> None:
    out = review_node._shared_catalog(tmp_path)
    assert "not present" in out


def test_shared_catalog_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    out = review_node._shared_catalog(tmp_path)
    assert "empty" in out.lower()


def test_shared_catalog_memoizes_when_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_node._shared_catalog_cache_clear()
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "x.md").write_text("# X\n", encoding="utf-8")
    calls = {"n": 0}
    real_build = review_node._shared_catalog_build

    def counting_build(r: Path) -> str:
        calls["n"] += 1
        return real_build(r)

    monkeypatch.setattr(review_node, "_shared_catalog_build", counting_build)
    assert review_node._shared_catalog(tmp_path) == review_node._shared_catalog(tmp_path)
    assert calls["n"] == 1


def test_shared_catalog_cache_invalidates_after_file_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_node._shared_catalog_cache_clear()
    (tmp_path / "shared").mkdir()
    p = tmp_path / "shared" / "x.md"
    p.write_text("# X\n", encoding="utf-8")
    calls = {"n": 0}
    real_build = review_node._shared_catalog_build

    def counting_build(r: Path) -> str:
        calls["n"] += 1
        return real_build(r)

    monkeypatch.setattr(review_node, "_shared_catalog_build", counting_build)
    review_node._shared_catalog(tmp_path)
    # _stat_fingerprint_shared_paths keys on (mtime_ns, size). On fast tmpfs
    # both writes can land in the same nanosecond; rewrite with a different
    # size so the size component alone forces a cache miss even when mtime
    # collides.
    p.write_text("# Y (longer content to force size change)\n", encoding="utf-8")
    review_node._shared_catalog(tmp_path)
    assert calls["n"] == 2


def test_shared_catalog_memoizes_with_git_head_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_node._shared_catalog_cache_clear()
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "a.md").write_text("# Git doc\n", encoding="utf-8")
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "shared/a.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    calls = {"n": 0}
    real_build = review_node._shared_catalog_build

    def counting_build(r: Path) -> str:
        calls["n"] += 1
        return real_build(r)

    monkeypatch.setattr(review_node, "_shared_catalog_build", counting_build)
    assert review_node._shared_catalog(tmp_path) == review_node._shared_catalog(tmp_path)
    assert calls["n"] == 1
    key = review_node._shared_catalog_cache_key(tmp_path.resolve())
    assert "\0git:" in key
