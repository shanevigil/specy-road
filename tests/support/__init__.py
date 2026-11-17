"""Shared test primitives: repo builders, CLI runners, the fake harness and the shared fixtures.

Test files import helpers from here, never from another test file. The pytest fixtures in
:mod:`tests.support.fixtures` are registered for the whole suite by ``tests/conftest.py``.
"""

from tests.helpers import REPO as REPO
