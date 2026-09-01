"""Guards that apply to the whole test suite.

Kept deliberately small: anything here is invisible at the call site, so it
should only ever prevent a test from damaging the checkout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import REPO


@pytest.fixture(autouse=True)
def repo_root_env_never_leaks_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's own ``SPECY_ROAD_REPO_ROOT`` must not steer the suite.

    The CLI honours that variable now, and ``tests.helpers.script_subprocess_env``
    copies ``os.environ`` wholesale into every subprocess test — so anyone who
    exports it in their shell would silently point the whole suite at one repo.
    Tests that want it set it themselves with ``monkeypatch.setenv``.
    """
    monkeypatch.delenv("SPECY_ROAD_REPO_ROOT", raising=False)


@pytest.fixture(autouse=True)
def history_cache_stays_out_of_the_source_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never write the derived history cache inside this checkout.

    ``render_brief`` builds the history index for whatever repo root it is
    given, and several tests pass the dogfood fixture *in place*. Left alone
    that writes ``tests/fixtures/specy_road_dogfood/.specyrd/cache/``, which
    then gets copied into every ``shutil.copytree`` fixture — seeding tmp repos
    with a foreign cache and making test outcomes depend on what ran before.

    Tests that exercise caching use ``tmp_path`` repos, which are outside the
    checkout and so still hit the real writer.
    """
    import specy_road.history_index as history_index

    real_save = history_index.save_cache

    def guarded(root: Path, doc: dict) -> bool:
        try:
            Path(root).resolve().relative_to(REPO)
        except ValueError:
            return real_save(root, doc)
        return False  # inside the checkout: behave like an unwritable cache

    monkeypatch.setattr(history_index, "save_cache", guarded)
