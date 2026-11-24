"""Helpers shared by tests that folded into more than one module."""

from __future__ import annotations


PROFILE_REL = "model-profiles/anthropic-claude/claude-opus-5-5.md"
ROSTER = f"""version: 1
roster:
  - {{id: human, family: human, roles: [coordinator, reviewer]}}
  - id: opus
    family: anthropic
    profile: {PROFILE_REL}
    roles: [coordinator, executor, reviewer]
policy: {{reviewers_required: 1}}
"""
