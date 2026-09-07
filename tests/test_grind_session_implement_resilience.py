"""A hook killed from outside is not a failed implementation.

``classify_limit("")`` is NONE, so a Claude process whose tree was killed
before it printed anything used to return its raw exit code as an ordinary
task failure -- indistinguishable from a real one, and the end of an
unattended run. That shape now has its own bounded retry, and the bounds that
were hardcoded module constants are tunable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import specy_road.bundled_scripts.grind_session_implement as gsi
from specy_road.bundled_scripts.grind_session_limits import resolve_implement_limits
from tests.test_grind_session_implement import (  # noqa: F401 - autouse fixture
    CLAUDE,
    LIMIT,
    _Emitter,
    _empty_claude_home,
    _limit_text,
    _runs,
)


def _events(emitter: _Emitter, name: str) -> list[dict]:
    return [f for e, f in emitter.events if e == name]


# ---------------------------------------------------------------------------
# The vanish category


def test_a_vanished_implementer_is_retried_with_a_fresh_run(monkeypatch) -> None:
    slept: list[float] = []
    emitter = _Emitter()
    seen = _runs(monkeypatch, [(137, ""), (0, "done")])
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), emitter=emitter, node_id="M9.1",
        sleep=slept.append,
    )
    assert code == 0
    assert len(seen) == 2
    # A fresh run, never a guessed --resume: there is no session id to trust.
    assert seen[1] == CLAUDE
    assert slept == [gsi.EMPTY_RETRY_SECONDS]
    (event,) = _events(emitter, "implementer_vanished")
    assert event["rc"] == 137
    assert event["attempt"] == 1
    assert event["max_retries"] == gsi.MAX_EMPTY_RETRIES


def test_a_negative_return_code_counts_as_vanished(monkeypatch) -> None:
    """The shell execs a simple command directly, so a kill arrives negative."""
    seen = _runs(monkeypatch, [(-9, ""), (0, "")])
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), sleep=lambda _s: None
    )
    assert code == 0
    assert len(seen) == 2


def test_repeated_vanishing_stops_after_the_bound(monkeypatch, capsys) -> None:
    attempts = gsi.MAX_EMPTY_RETRIES + 1
    seen = _runs(monkeypatch, [(137, "")] * attempts)
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), sleep=lambda _s: None
    )
    assert code == 1
    assert len(seen) == attempts
    assert "without printing anything" in capsys.readouterr().err


def test_a_quiet_ordinary_failure_is_not_retried(monkeypatch) -> None:
    """The guard against this category widening: exit 1 with no output."""
    seen = _runs(monkeypatch, [(1, "")])
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("must not sleep")
    )
    assert code == 1
    assert len(seen) == 1


def test_a_signal_death_that_printed_something_is_not_a_vanish(monkeypatch) -> None:
    seen = _runs(monkeypatch, [(137, "Traceback: boom")])
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("must not sleep")
    )
    assert code == 137
    assert len(seen) == 1


def test_a_vanish_does_not_consume_the_limit_wait_budget(monkeypatch) -> None:
    """The two categories are counted separately."""
    emitter = _Emitter()
    seen = _runs(monkeypatch, [(137, ""), (1, LIMIT), (0, "done")])
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), emitter=emitter, sleep=lambda _s: None
    )
    assert code == 0
    assert len(seen) == 3
    (limited,) = _events(emitter, "usage_limited")
    assert limited["attempt"] == 1


def test_the_vanish_backoff_grows_with_each_attempt(monkeypatch) -> None:
    slept: list[float] = []
    _runs(monkeypatch, [(137, ""), (137, ""), (0, "")])
    gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=slept.append)
    assert slept == [gsi.EMPTY_RETRY_SECONDS, gsi.EMPTY_RETRY_SECONDS * 2]


# ---------------------------------------------------------------------------
# The knobs


def _yaml(repo: Path, **extra) -> Path:
    (repo / "roadmap").mkdir(parents=True, exist_ok=True)
    (repo / "roadmap" / "git-workflow.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "integration_branch": "dev",
                "remote": "origin",
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return repo


def test_the_module_constants_are_the_defaults() -> None:
    """Guards the decision to read them at call time, not bind them as fields."""
    cfg = gsi.ImplementLimits.defaults()
    assert cfg.max_resumes == gsi.MAX_RESUMES
    assert cfg.max_wait_seconds == gsi.MAX_WAIT_SECONDS
    assert cfg.grace_seconds == gsi.GRACE_SECONDS
    assert cfg.max_empty_retries == gsi.MAX_EMPTY_RETRIES


def test_the_yaml_supplies_the_bounds_when_no_flag_does(tmp_path: Path) -> None:
    _yaml(tmp_path, grind_session_max_limit_wait_hours=8)
    cfg = resolve_implement_limits(tmp_path)
    assert cfg.max_wait_seconds == 8 * 3600
    assert cfg.max_resumes == gsi.MAX_RESUMES  # the rest fall back


def test_a_cli_flag_beats_the_yaml(tmp_path: Path) -> None:
    _yaml(tmp_path, grind_session_max_limit_wait_hours=8)
    cfg = resolve_implement_limits(tmp_path, max_limit_wait_hours=12)
    assert cfg.max_wait_seconds == 12 * 3600


def test_a_missing_or_invalid_config_falls_back_to_the_defaults(
    tmp_path: Path,
) -> None:
    assert resolve_implement_limits(tmp_path) == gsi.ImplementLimits.defaults()
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "this: [is not, a valid config", encoding="utf-8"
    )
    assert resolve_implement_limits(tmp_path) == gsi.ImplementLimits.defaults()


def test_negative_values_are_clamped(tmp_path: Path) -> None:
    cfg = resolve_implement_limits(tmp_path, limit_wait_grace_seconds=0)
    assert cfg.grace_seconds == 0


def test_an_eight_hour_reset_is_waited_out_when_the_ceiling_is_raised(
    monkeypatch,
) -> None:
    """The reporter's own case: a plan that resets on an 8-hour cadence."""
    seen = _runs(monkeypatch, [(1, _limit_text(minutes_ahead=7 * 60)), (0, "done")])
    code = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"),
        sleep=lambda _s: None,
        limits=gsi.ImplementLimits(3, 8 * 3600, 120, 2),
    )
    assert code == 0
    assert len(seen) == 2


def test_the_default_ceiling_still_refuses_that_reset(monkeypatch, capsys) -> None:
    seen = _runs(monkeypatch, [(1, _limit_text(minutes_ahead=7 * 60))])
    code = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: None)
    assert code == 1
    assert len(seen) == 1
    err = capsys.readouterr().err
    assert "beyond the 6h this loop waits unattended" in err
    assert "--max-limit-wait-hours" in err
