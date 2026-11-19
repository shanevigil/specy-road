"""API tests for ``GET/PUT /api/workspace/file`` (``shared/`` text files)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD
from tests.support.same.mutation_headers_1fdfef6b66c9 import mutation_headers








def test_api_workspace_file_get_reads_shared_md(api_client: TestClient) -> None:
    r = api_client.get(
        "/api/workspace/file",
        params={"path": "shared/README.md"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "shared/README.md"
    assert "content" in body
    assert len(body["content"]) > 0


@pytest.mark.parametrize(
    "path",
    ["planning/README.md", "work/note.md"],
)
def test_api_workspace_file_get_rejects_non_shared(
    api_client: TestClient,
    path: str,
) -> None:
    """Paths outside ``shared/`` are refused, and the detail says to use that prefix."""
    r = api_client.get(
        "/api/workspace/file",
        params={"path": path},
    )
    assert r.status_code == 400
    assert "path must start with shared/" in r.json().get("detail", "")


def test_api_workspace_file_get_rejects_path_traversal(
    api_client: TestClient,
) -> None:
    r = api_client.get(
        "/api/workspace/file",
        params={"path": "shared/../constitution/purpose.md"},
    )
    assert r.status_code == 400


def test_api_workspace_file_put_roundtrip(
    api_client: TestClient,
    dogfood_copy: Path,
) -> None:
    path = "shared/pytest-workspace-text.md"
    content = "# hello\n\ngui workspace file put.\n"
    r = api_client.put(
        "/api/workspace/file",
        params={"path": path},
        headers={
            **mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={"content": content},
    )
    assert r.status_code == 200
    out = dogfood_copy / "shared" / "pytest-workspace-text.md"
    assert out.read_text(encoding="utf-8") == content
    r2 = api_client.get(
        "/api/workspace/file",
        params={"path": path},
    )
    assert r2.status_code == 200
    assert r2.json()["content"] == content


def test_api_workspace_file_put_requires_mutation_header(
    api_client: TestClient,
) -> None:
    r = api_client.put(
        "/api/workspace/file",
        params={"path": "shared/x.md"},
        headers={"Content-Type": "application/json"},
        json={"content": "x"},
    )
    assert r.status_code == 428


def test_api_workspace_file_put_rejects_non_shared(
    api_client: TestClient,
) -> None:
    r = api_client.put(
        "/api/workspace/file",
        params={"path": "work/x.md"},
        headers={
            **mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={"content": "x"},
    )
    assert r.status_code == 400
