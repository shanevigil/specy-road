"""A check command that records how it was run: one JSON line per run in ``$CHECKS_PROBE_LOG``.

The line holds the arguments it got, the directory it ran in and every environment variable it
saw; ``test_checks_migration`` compares the variables with its own to find any the caller added.
An argument ``fail`` makes it exit 1, so a row can record what a failing check does.
"""

import json
import os
import sys

with open(os.environ["CHECKS_PROBE_LOG"], "a", encoding="utf-8") as log:
    run = {"argv": sys.argv[1:], "cwd": os.getcwd(), "env": sorted(os.environ)}
    log.write(json.dumps(run) + "\n")
sys.exit(1 if "fail" in sys.argv[1:] else 0)
