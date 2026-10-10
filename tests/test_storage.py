from io import BytesIO

import pytest

from app.storage import LocalStorage, StorageError


def test_save_and_read_object(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    key = storage.save(
        "documents/test.pdf",
        BytesIO(b"%PDF-test-content"),
    )

    assert key == "documents/test.pdf"
    assert storage.exists(key)

    with storage.open(key) as source:
        assert source.read() == b"%PDF-test-content"


def test_get_path_returns_storage_path(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    storage.save(
        "documents/test.pdf",
        BytesIO(b"test"),
    )

    path = storage.get_path("documents/test.pdf")

    assert path.is_file()
    assert path.read_bytes() == b"test"


def test_nested_directories_are_created(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    storage.save(
        "users/user-1/documents/document-1/original.pdf",
        BytesIO(b"pdf"),
    )

    assert storage.exists(
        "users/user-1/documents/document-1/original.pdf"
    )


def test_delete_removes_object(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    storage.save(
        "documents/test.pdf",
        BytesIO(b"pdf"),
    )

    storage.delete("documents/test.pdf")

    assert not storage.exists("documents/test.pdf")


def test_delete_missing_object_is_safe(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    storage.delete("documents/missing.pdf")

    assert not storage.exists("documents/missing.pdf")


@pytest.mark.parametrize(
    "key",
    [
        "",
        "   ",
        "/absolute/path.pdf",
        "../outside.pdf",
        "../../outside.pdf",
    ],
)
def test_invalid_storage_keys_are_rejected(
    tmp_path,
    key,
):
    storage = LocalStorage(tmp_path / "storage")

    with pytest.raises(StorageError):
        storage.get_path(key)


def test_storage_key_cannot_escape_root(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    with pytest.raises(StorageError):
        storage.save(
            "../outside.pdf",
            BytesIO(b"malicious"),
        )

def test_create_supports_streamed_writes(tmp_path):
    storage = LocalStorage(tmp_path / "storage")

    with storage.create("documents/streamed.pdf") as destination:
        destination.write(b"%PDF-streamed-content")

    assert storage.exists(
        "documents/streamed.pdf"
    )

    with storage.open("documents/streamed.pdf") as source:
        assert source.read() == b"%PDF-streamed-content"