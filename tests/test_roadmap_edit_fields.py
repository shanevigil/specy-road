"""Tests for roadmap_edit_fields helpers."""

from __future__ import annotations

from roadmap_edit_fields import title_to_codename


def test_title_to_codename_basic() -> None:
    assert title_to_codename("Hello World") == "hello-world"
    assert title_to_codename("  Foo   Bar  ") == "foo-bar"


def test_title_to_codename_empty() -> None:
    assert title_to_codename("") == ""
    assert title_to_codename("   ") == ""
    assert title_to_codename("!!!") == ""


def test_title_to_codename_valid_pattern() -> None:
    assert title_to_codename("BI - Occupancy Mgt. v.3.0") == "bi-occupancy-mgt-v-3-0"
