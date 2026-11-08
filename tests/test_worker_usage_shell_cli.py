"""M22.13 (D8): a shell ``channels.cli`` is priced from the literal ``-m`` in its command string."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_cursor_usage_cost import CODEX_ROSTER, priced_repo
from tests.test_worker_adapters import CODEX_TURN

from specy_road import worker_adapters as wa
from specy_road.model_names import roster_match
from specy_road.worker_adapter_parsers import estimate_usage_cost, mtok_rates, usage_text

SIMPLE = "codex exec --json -m gpt-6.1-sol -c sandbox_mode=workspace-write -c approval_policy=never - < {prompt}"
#: rc4's git-roots grant: the quoted $(...) makes it more than one simple command to command_model, so unpriced.
GIT_ROOTS = ('codex exec --json -m gpt-6.1-sol -c sandbox_mode=workspace-write -c approval_policy=never '
             '-c "sandbox_workspace_write.writable_roots=[\\"$(git rev-parse --absolute-git-dir)\\"]" - < {prompt}')


@pytest.mark.parametrize("cli, priced", [
    (SIMPLE, True),
    ("codex exec --json --model=gpt-6.1-sol - < {prompt}", True),
    (SIMPLE + " | tee out.log", False),                                    # a pipeline
    ('codex exec --json -m "$MODEL" - < {prompt}', False),                 # a non-literal -m
    (GIT_ROOTS, False),
    ("codex exec --json -m 'gpt-6.1-sol - < {prompt}", False),             # unsplittable: as before
])
def test_a_shell_channels_cli_is_priced_from_its_literal_model(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli: str, priced: bool) -> None:
    repo = priced_repo(tmp_path, CODEX_ROSTER, ("openai-gpt/gpt-6.1-sol.md",))
    monkeypatch.chdir(repo)   # the runner starts a channels.cli in the worktree
    prompt = tmp_path / "prompt.md"
    prompt.write_text("ok")
    launch = wa.Launch(["sh", "-c", cli.replace("{prompt}", str(prompt))])   # the argv the runner builds
    usage = wa.adapter_for("codex").parse_events(json.dumps(CODEX_TURN), launch)[0].usage
    if not priced:
        assert usage["cost_usd"] is None and usage_text(usage).endswith("$?")
        return
    want = estimate_usage_cost(usage, mtok_rates(roster_match(repo, "gpt-6.1-sol")[1].data))
    assert want is not None and usage["cost_usd"] == want and usage["cost_is_estimate"] is True
    assert usage_text(usage).endswith(" est.")
