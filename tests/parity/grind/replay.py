"""Replay the grind table on another commit's package.

``python -m tests.parity.grind.replay REF``: the goldens must be what the code before the grind
modules moved printed. This lays this checkout's ``tests/parity/grind/`` (rows, fixture, test and
goldens) over ``REF``'s tree with :func:`tests.parity.orchestration_state.replay.replay`'s
extraction, and runs the table there without regeneration. Exit status is pytest's.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.parity.orchestration_state.replay import replay

ROWS_DIR = Path(__file__).resolve().parent
#: Laid over ``REF``'s tree with the goldens.
OVERLAY = ("__init__.py", "fixture.py", "rows.py", "test_grind_rows.py")


if __name__ == "__main__":
    sys.exit(replay(sys.argv[1], rows_dir=ROWS_DIR, overlay=OVERLAY, test="test_grind_rows.py"))
