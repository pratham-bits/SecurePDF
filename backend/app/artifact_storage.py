"""Document artifact storage helpers for SecurePDF."""

from pathlib import Path
from uuid import uuid4

from app.storage import LocalStorage, StorageError


class ArtifactStorageError(Exception):
    """Raised when a document artifact cannot be stored or retrieved."""


ORIGINALS_PREFIX = "uploads"
REDACTED_PREFIX = "redacted"


def build_original_storage_key(
    document_id: str,
) -> str:
    """Build the storage key for an original uploaded PDF."""

    if not document_id or not document_id.strip():
        raise ArtifactStorageError(
            "document_id must be a non-empty string."
        )

    return f"{ORIGINALS_PREFIX}/{document_id}.pdf"


def build_redacted_storage_key(
    document_id: str,
) -> str:
    """Build the storage key for a final redacted PDF."""

    if not document_id or not document_id.strip():
        raise ArtifactStorageError(
            "document_id must be a non-empty string."
        )

    return f"{REDACTED_PREFIX}/{document_id}.pdf"


def get_artifact_path(
    storage: LocalStorage,
    storage_key: str,
) -> Path:
    """Resolve a stored artifact to a local processing path."""

    try:
        path = storage.get_path(storage_key)
    except StorageError as exc:
        raise ArtifactStorageError(
            f"Unable to resolve storage artifact {storage_key!r}."
        ) from exc

    if not path.exists():
        raise ArtifactStorageError(
            f"Storage artifact {storage_key!r} does not exist."
        )

    if not path.is_file():
        raise ArtifactStorageError(
            f"Storage artifact {storage_key!r} is not a file."
        )

    return path


def build_processing_output_path(
    workspace: str | Path,
) -> Path:
    """
    Build a unique temporary output path inside a processing workspace.
    """

    workspace_path = Path(workspace)
    workspace_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return workspace_path / f"{uuid4()}.pdf"