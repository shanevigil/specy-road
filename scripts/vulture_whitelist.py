"""Names vulture reports as unused that are used or kept on purpose.

Read by the advisory dead-code step in CI (``.github/workflows/validate.yml``):

    vulture specy_road scripts --min-confidence 60

This file sits under ``scripts/``, so that run reads it. vulture matches names,
not objects: reading ``_.name`` below marks every definition called ``name`` as
used. Nothing imports this module; running it only builds the tuple.

Add a name only when nothing in ``specy_road`` or ``scripts`` reads it by name
and it is still used (a route, a hook, a callback parameter) or kept by a
recorded decision. A name used only by tests is a finding, not an entry here.
"""


class _Names:
    """An attribute read returns the attribute's name."""

    def __getattr__(self, name: str) -> str:
        return name


_ = _Names()

__all__ = ["USED"]

USED = (
    # FastAPI routes, middleware and handlers: registered by decorator, called by the framework.
    _.refuse_writes,
    _.api_not_found,
    _.spa_fallback,
    _.health,
    _.api_repo,
    _.api_roadmap,
    _.api_roadmap_fingerprint,
    _.api_governance_completion,
    _.api_git_workflow_status,
    _.api_add_node,
    _.api_publish_status,
    _.api_publish,
    _.api_settings_get,
    _.api_settings_put,
    _.api_llm_test,
    _.api_llm_review,
    _.api_git_test,
    # pytest plugin hook in scripts/lean_metrics.py, loaded with ``-p`` by ``--contexts``.
    _.pytest_runtest_logstart,
    # Callback parameters the caller passes: PyYAML passes ``indentless`` by keyword to
    # registry_yaml's _IndentedDumper.increase_indent; argparse passes ``option_string``
    # positionally to worker_cli_args' FixRound.__call__.
    _.indentless,
    _.option_string,
    # behaviour_changes.py: the catalogue of behaviour changes, kept for a planned report
    # though no command reads it yet.
    _.CATALOGUE,
    _.contradicted_by,
    # Kept: a consistency test checks shipped text against these labels.
    _.upgrade_help_step_labels,
    _.readme_upgrade_step_labels,
    # Kept: test set-up and cache reset.
    _.set_lease,
    _.clear_memo,
    # Kept: test-isolation resets for module-level state.
    _.reset_openai_chat_throughput_gate_for_tests,
    _._shared_catalog_cache_clear,
)
