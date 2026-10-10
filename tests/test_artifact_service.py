from pathlib import Path

import pytest

from app.artifact_service import (
    ArtifactServiceError,
    DocumentArtifactService,
)
from app.storage import LocalStorage


def create_service(tmp_path: Path) -> DocumentArtifactService:
    storage = LocalStorage(tmp_path / "storage")
    return DocumentArtifactService(storage)


def test_get_original_path(tmp_path: Path):
    service = create_service(tmp_path)

    document_id = "doc-123"
    storage_key = "uploads/doc-123.pdf"

    source = service.storage.get_path(storage_key)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"%PDF-test")

    result = service.get_original_path(document_id, storage_key)

    assert result == source
    assert result.exists()


def test_get_original_path_missing_artifact(tmp_path: Path):
    service = create_service(tmp_path)

    with pytest.raises(ArtifactServiceError):
        service.get_original_path("missing-document")


def test_save_redacted_artifact(tmp_path: Path):
    service = create_service(tmp_path)

    source = tmp_path / "processed.pdf"
    source.write_bytes(b"%PDF-redacted")

    storage_key = service.save_redacted_artifact(
        "doc-123",
        source,
    )

    assert storage_key == "redacted/doc-123.pdf"
    assert service.storage.exists(storage_key)

    stored = service.storage.get_path(storage_key)
    assert stored.read_bytes() == b"%PDF-redacted"


def test_save_redacted_artifact_missing_source(tmp_path: Path):
    service = create_service(tmp_path)

    with pytest.raises(ArtifactServiceError):
        service.save_redacted_artifact(
            "doc-123",
            tmp_path / "missing.pdf",
        )


def test_get_redacted_path(tmp_path: Path):
    service = create_service(tmp_path)

    source = tmp_path / "processed.pdf"
    source.write_bytes(b"%PDF-redacted")

    service.save_redacted_artifact("doc-123", source)

    result = service.get_redacted_path("doc-123")

    assert result.exists()
    assert result.read_bytes() == b"%PDF-redacted"


def test_get_redacted_path_missing(tmp_path: Path):
    service = create_service(tmp_path)

    with pytest.raises(ArtifactServiceError):
        service.get_redacted_path("missing-document")


def test_processing_workspace_isolated(tmp_path: Path):
    service = create_service(tmp_path)

    with service.processing_workspace() as workspace:
        assert workspace.exists()
        assert workspace.is_dir()

        output = workspace / "processed.pdf"
        output.write_bytes(b"%PDF-test")

        assert output.exists()

    assert not workspace.exists()


def test_processing_workspaces_are_unique(tmp_path: Path):
    service = create_service(tmp_path)

    with service.processing_workspace() as first:
        first_path = first

        with service.processing_workspace() as second:
            second_path = second

            assert first_path != second_path
            assert first_path.exists()
            assert second_path.exists()