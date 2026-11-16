"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
  - {id: haiku, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
  - {id: astra, family: openai, roles: [reviewer]}
  - {id: gem, family: google, roles: [reviewer]}
  - {id: grok, family: xai, roles: [reviewer]}
  - {id: composer, family: cursor, roles: [executor]}
policy: {reviewers_required: 1}
"""

STRONG = ROSTER.replace("policy: {reviewers_required: 1}", "policy:\n  reviewers_required: 1\n"
                        "  strong_review:\n    - {zones: [src], require_one_of: [sonnet]}")
