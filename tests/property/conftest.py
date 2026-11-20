"""The one Hypothesis settings profile every property under ``tests/property/`` runs with.

``derandomize`` removes the random seed, ``database=None`` keeps Hypothesis from saving failing
examples, and ``deadline=None`` keeps a slow machine from failing an example on time alone.
Hypothesis also draws constants from the source of project modules already loaded, so the
examples can still differ between runs: each property must hold for any draw. It caches Unicode
tables and those constants on disk whatever the database says, so its home directory is moved out
of the checkout into the system temporary directory: a run leaves no ``.hypothesis`` directory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import settings
from hypothesis.configuration import set_hypothesis_home_dir

set_hypothesis_home_dir(Path(tempfile.gettempdir()) / "specy-road-hypothesis")
settings.register_profile(
    "specy-road", derandomize=True, database=None, deadline=None, max_examples=100
)
settings.load_profile("specy-road")
