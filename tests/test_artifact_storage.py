from pathlib import Path

import pytest

from app.artifact_storage import (
    ArtifactStorageError,
    build_original_storage_key,
    build_processing_output_path,
    build_redacted_storage_key,
    get_artifact_path,
)
from app.storage import LocalStorage


def test_build_original_storage_key():
    assert (
        build_original_storage_key("document-123")
        == "uploads/document-123.pdf"
    )


def test_build_redacted_storage_key():
    assert (
        build_redacted_storage_key("document-123")
        == "redacted/document-123.pdf"
    )


@pytest.mark.parametrize(
    "builder",
    [
        build_original_storage_key,
        build_redacted_storage_key,
    ],
)
def test_artifact_key_requires_document_id(builder):
    with pytest.raises(ArtifactStorageError):
        builder("")


def test_get_artifact_path_returns_existing_file(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    key = build_original_storage_key("document-123")

    with storage.create(key) as destination:
        destination.write(b"%PDF-test")

    path = get_artifact_path(
        storage,
        key,
    )

    assert path.is_file()
    assert path.read_bytes() == b"%PDF-test"


def test_get_artifact_path_rejects_missing_file(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    key = build_original_storage_key("missing")

    with pytest.raises(
        ArtifactStorageError,
        match="does not exist",
    ):
        get_artifact_path(
            storage,
            key,
        )


def test_processing_output_path_is_inside_workspace(
    tmp_path,
):
    workspace = tmp_path / "processing"

    output_path = build_processing_output_path(
        workspace
    )

    assert output_path.parent == workspace
    assert output_path.suffix == ".pdf"
    assert workspace.is_dir()


def test_processing_output_paths_are_unique(tmp_path):
    workspace = tmp_path / "processing"

    first = build_processing_output_path(
        workspace
    )

    second = build_processing_output_path(
        workspace
    )

    assert first != second