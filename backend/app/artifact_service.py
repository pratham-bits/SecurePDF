"""Document artifact persistence and processing workspace management."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from app.artifact_storage import (
    ArtifactStorageError,
    build_original_storage_key,
    build_redacted_storage_key,
    get_artifact_path,
)
from app.storage import LocalStorage, StorageError


class ArtifactServiceError(Exception):
    """Raised when document artifact operations fail."""


class DocumentArtifactService:
    """Coordinates persistent artifacts and temporary processing files."""

    def __init__(self, storage: LocalStorage) -> None:
        self.storage = storage

    def get_original_path(
        self,
        document_id: str,
        storage_key: str | None = None,
    ) -> Path:
        """Resolve the original PDF to a local filesystem path."""
        key = storage_key or build_original_storage_key(document_id)

        try:
            return get_artifact_path(self.storage, key)
        except ArtifactStorageError as exc:
            raise ArtifactServiceError(
                "Original document artifact is unavailable."
            ) from exc

    def save_redacted_artifact(
    self,
    document_id: str,
    source_path: Path,
) -> str:
        """Persist a processed PDF and return its storage key."""
        source = Path(source_path)

        if not source.exists() or not source.is_file():
            raise ArtifactServiceError(
                "Redacted source artifact does not exist."
            )

        storage_key = build_redacted_storage_key(document_id)

        try:
            with source.open("rb") as source_stream:
                self.storage.save(storage_key, source_stream)
        except (StorageError, OSError) as exc:
            raise ArtifactServiceError(
                "Unable to persist redacted document artifact."
            ) from exc

        return storage_key

    def get_redacted_path(self, document_id: str) -> Path:
        """Resolve a previously stored redacted PDF."""
        storage_key = build_redacted_storage_key(document_id)

        try:
            return get_artifact_path(self.storage, storage_key)
        except ArtifactStorageError as exc:
            raise ArtifactServiceError(
                "Redacted document artifact is unavailable."
            ) from exc

    def processing_workspace(self) -> Iterator[Path]:
        """Create an isolated temporary workspace."""
        return _ProcessingWorkspace()


class _ProcessingWorkspace:
    """Context manager for an isolated temporary processing directory."""

    def __init__(self) -> None:
        self._directory: TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        self._directory = TemporaryDirectory(prefix="securepdf-")
        return Path(self._directory.name)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None