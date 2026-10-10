"""Storage abstraction for SecurePDF document artifacts."""

from pathlib import Path
from typing import BinaryIO, Protocol


class StorageError(Exception):
    """Raised when a storage operation fails."""


class StorageBackend(Protocol):
    """Interface implemented by SecurePDF storage backends."""

    def save(
        self,
        key: str,
        source: BinaryIO,
    ) -> str:
        """Persist an object and return its storage key."""
        ...

    def create(
        self,
        key: str,
    ) -> BinaryIO:
        """Create a storage object for streamed binary writes."""
        ...

    def open(
        self,
        key: str,
    ) -> BinaryIO:
        """Open a stored object for binary reading."""
        ...

    def exists(
        self,
        key: str,
    ) -> bool:
        """Return whether an object exists."""
        ...

    def delete(
        self,
        key: str,
    ) -> None:
        """Delete an object if it exists."""
        ...

    def get_path(
        self,
        key: str,
    ) -> Path:
        """
        Return the local filesystem path for a stored object.

        Backends that do not expose local paths may raise StorageError.
        """
        ...


class LocalStorage:
    """Filesystem-backed storage implementation."""

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _resolve_key(
        self,
        key: str,
    ) -> Path:
        """Resolve a storage key safely inside the storage root."""

        if not isinstance(key, str) or not key.strip():
            raise StorageError(
                "Storage key must be a non-empty string."
            )

        relative_key = Path(key)

        if relative_key.is_absolute():
            raise StorageError(
                "Storage key must be relative."
            )

        resolved = (
            self.root / relative_key
        ).resolve()

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise StorageError(
                "Storage key escapes the storage root."
            ) from exc

        return resolved

    def create(
        self,
        key: str,
    ) -> BinaryIO:
        """Create a storage object for streamed binary writes."""

        path = self._resolve_key(key)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            return path.open("xb")
        except OSError as exc:
            raise StorageError(
                f"Unable to create storage object {key!r}."
            ) from exc

    def save(
        self,
        key: str,
        source: BinaryIO,
    ) -> str:
        """Save a binary stream under the supplied storage key."""

        destination = self._resolve_key(key)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            with destination.open("wb") as target:
                while True:
                    chunk = source.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    target.write(chunk)

        except OSError as exc:
            raise StorageError(
                f"Unable to save storage object {key!r}."
            ) from exc

        return key

    def open(
        self,
        key: str,
    ) -> BinaryIO:
        """Open a stored object for binary reading."""

        path = self._resolve_key(key)

        try:
            return path.open("rb")
        except OSError as exc:
            raise StorageError(
                f"Unable to open storage object {key!r}."
            ) from exc

    def exists(
        self,
        key: str,
    ) -> bool:
        """Return whether the storage object exists."""

        return self._resolve_key(key).is_file()

    def delete(
        self,
        key: str,
    ) -> None:
        """Delete a storage object if it exists."""

        path = self._resolve_key(key)

        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            raise StorageError(
                f"Unable to delete storage object {key!r}."
            ) from exc

    def get_path(
        self,
        key: str,
    ) -> Path:
        """Return the local filesystem path for a stored object."""

        return self._resolve_key(key)