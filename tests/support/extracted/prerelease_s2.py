"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: rev, family: openai, roles: [reviewer]}
policy: {reviewers_required: 1}
"""
