"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

TWO_FAMILIES = """version: 1
roster:
  - {id: human, family: human, roles: [reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
  - {id: composer, family: cursor, roles: [executor]}
  - {id: astra, family: openai, roles: [executor]}
policy: {reviewers_required: 2, reviewers_distinct_families: true}
substitutions:
  - {slot: reviewer-openai, use: astra, scope: [M1.1], decided: 2026-01-01, expires: 2026-12-31}
"""
