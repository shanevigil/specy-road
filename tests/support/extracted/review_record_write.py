"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

GENERIC = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
           "  - {id: gem, family: google, roles: [reviewer], harness: generic, channels: {cli: '{fake} {prompt}'}}\n")
