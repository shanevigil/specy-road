"""Put ``SPECY_ROAD_ORCHESTRATION_ROLE`` on a harness process environment (M8.5).

Worker launch (executor via :func:`specy_road.worker_runner.run`, reviewer via
``review delegate``) must export the role so installed hook commands that read
the environment — and do not pin the role in the command string — still deny.
"""

from __future__ import annotations

from collections.abc import Mapping

ROLE_ENV = "SPECY_ROAD_ORCHESTRATION_ROLE"


def harness_env(
    source: Mapping[str, str],
    role: str,
    *,
    harness_pythonpath: str | None = None,
) -> dict[str, str]:
    """Copy ``source`` for a harness child and set the orchestration role.

    Drops ``PYTHONPATH`` (the wrapper's package path must not leak into adopter
    tests) and ``CLAUDE_CODE_EFFORT_LEVEL`` (a caller's setting must not
    override the profile's ``effort_by_role``). Restores ``PYTHONPATH`` from
    ``harness_pythonpath`` when the caller supplied one.
    """
    env = {k: v for k, v in source.items() if k not in ("PYTHONPATH", "CLAUDE_CODE_EFFORT_LEVEL")}
    if harness_pythonpath:
        env["PYTHONPATH"] = harness_pythonpath
    env[ROLE_ENV] = role
    return env
