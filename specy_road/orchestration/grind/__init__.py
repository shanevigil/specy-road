"""The grind-session loop and its plan: the loop with its implement bounds and ``--step`` phases,
its events and exit codes, the implement hook, in-flight claims, the end-of-session cleanup, and
the read-only session plan with its git enrichment and its rendering.

The ``grind-session`` command entry (``specy_road.bundled_scripts.grind_session``) takes
:func:`~specy_road.orchestration.grind.grind_session.run_session` from
:mod:`specy_road.orchestration`; other callers import these modules by their path in this package.
"""
