"""The recorded old selections are what the cleanup commands select on the fixture today."""

from __future__ import annotations

import json

import pytest

from tests.parity.cleanup import record

pytestmark = pytest.mark.parity


def test_the_recorded_selections_are_todays() -> None:
    assert record.selections() == json.loads(record.GOLDEN.read_text(encoding="utf-8"))
