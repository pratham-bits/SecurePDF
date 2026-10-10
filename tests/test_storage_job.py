from pathlib import Path
from uuid import uuid4
from app.job_service import complete_job
import pytest

from app.artifact_service import (
    ArtifactServiceError,
    DocumentArtifactService,
)
from app.artifact_storage import (
    build_original_storage_key,
    build_redacted_storage_key,
)
from app.database import SessionLocal
from app.job_processor import (
    ArtifactPersistenceError,
    JobProcessingError,
    process_storage_job,
)
from app.job_service import create_job, retry_job
from app.models import Document, ProcessingJob, User
from app.storage import LocalStorage


def create_storage_service(tmp_path: Path) -> DocumentArtifactService:
    """Create an isolated local storage service for the test."""
    return DocumentArtifactService(
        LocalStorage(tmp_path / "storage")
    )


def create_user_and_document(
    session,
    *,
    document_type: str,
) -> tuple[User, Document]:
    """Create a real database user and document for the test."""
    user_id = str(uuid4())
    document_id = str(uuid4())

    user = User(
        id=user_id,
        name="Storage Job User",
        email=f"storage-job-{uuid4().hex}@example.com",
        password_hash="test-hash",
        is_active=True,
    )

    document = Document(
        id=document_id,
        user_id=user_id,
        original_filename="input.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        page_count=1,
        document_type=document_type,
        status="uploaded",
        original_storage_key=build_original_storage_key(
            document_id
        ),
        redacted_storage_key=None,
        sha256_hash=uuid4().hex + uuid4().hex,
    )

    session.add(user)
    session.add(document)
    session.commit()
    session.refresh(document)

    return user, document


def cleanup_database(
    session,
    user: User | None,
    document: Document | None,
) -> None:
    """Remove test records in foreign-key-safe order."""
    if document is not None:
        session.query(ProcessingJob).filter(
            ProcessingJob.document_id == document.id
        ).delete(synchronize_session=False)

        session.query(Document).filter(
            Document.id == document.id
        ).delete(synchronize_session=False)

    if user is not None:
        session.query(User).filter(
            User.id == user.id
        ).delete(synchronize_session=False)

    session.commit()


@pytest.fixture
def db_document():
    """Provide a real database session and isolated test document."""
    session = SessionLocal()

    user = None
    document = None

    try:
        user, document = create_user_and_document(
            session,
            document_type="digital",
        )

        yield session, document

    finally:
        cleanup_database(
            session,
            user,
            document,
        )
        session.close()


def test_storage_job_review_does_not_create_redacted_artifact(
    db_document,
    tmp_path: Path,
    monkeypatch,
):
    """REVIEW_REQUIRED jobs must not persist a redacted artifact."""
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = create_storage_service(tmp_path)

    original_path = service.storage.get_path(
        document.original_storage_key
    )

    original_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_path.write_bytes(
        b"%PDF-test"
    )

    def fake_process_job(
        session,
        *,
        job_id,
        input_path,
        output_path,
        on_completed=None,
        start_job_if_needed=True,
):
        return {
            "input_path": Path(input_path),
            "output_path": None,
            "pages_processed": 1,
            "detected_entities": 0,
            "redacted_entities": 0,
            "review_entities": 1,
            "kept_entities": 0,
            "review_required": True,
            "detected_candidates": [],
            "redacted_candidates": [],
            "review_candidates": [],
            "kept_candidates": [],
        }

    monkeypatch.setattr(
        "app.job_processor.process_job",
        fake_process_job,
    )

    result = process_storage_job(
        session,
        job_id=job.id,
        artifact_service=service,
    )

    assert result["review_required"] is True

    session.refresh(document)

    assert document.redacted_storage_key is None

    assert not service.storage.exists(
        build_redacted_storage_key(document.id)
    )


def test_storage_job_persists_completed_artifact(
    db_document,
    tmp_path: Path,
    monkeypatch,
):
    """Completed jobs must persist the generated redacted artifact."""
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = create_storage_service(tmp_path)

    original_path = service.storage.get_path(
        document.original_storage_key
    )

    original_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_path.write_bytes(
        b"%PDF-original"
    )

    def fake_process_job(
        session,
        *,
        job_id,
        input_path,
        output_path,
        on_completed=None,
        start_job_if_needed=True,
):
        output_path = Path(output_path)

        output_path.write_bytes(
            b"%PDF-redacted"
        )

        result = {
            "input_path": Path(input_path),
            "output_path": output_path,
            "pages_processed": 1,
            "detected_entities": 1,
            "redacted_entities": 1,
            "review_entities": 0,
            "kept_entities": 0,
            "review_required": False,
            "detected_candidates": [],
            "redacted_candidates": [],
            "review_candidates": [],
            "kept_candidates": [],
        }

        if on_completed is not None:
            on_completed(result)

        complete_job(
            session,
            job_id=job_id,
        )

        return result

    monkeypatch.setattr(
        "app.job_processor.process_job",
        fake_process_job,
    )

    result = process_storage_job(
        session,
        job_id=job.id,
        artifact_service=service,
    )

    assert result["review_required"] is False

    session.refresh(document)

    expected_key = build_redacted_storage_key(
        document.id
    )

    assert document.redacted_storage_key == expected_key

    stored_path = service.storage.get_path(
        expected_key
    )

    assert stored_path.exists()
    assert stored_path.read_bytes() == b"%PDF-redacted"

def test_storage_job_persistence_failure_leaves_no_redacted_artifact(
    db_document,
    tmp_path: Path,
    monkeypatch,
):
    """Persistence failure must not leave a redacted artifact behind."""
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = create_storage_service(tmp_path)

    original_path = service.storage.get_path(
        document.original_storage_key
    )

    original_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_path.write_bytes(
        b"%PDF-original"
    )

    def fake_process_job(
        session,
        *,
        job_id,
        input_path,
        output_path,
        on_completed=None,
        start_job_if_needed=True,
    ):
        output_path = Path(output_path)
        output_path.write_bytes(b"%PDF-redacted")

        result = {
            "input_path": Path(input_path),
            "output_path": output_path,
            "pages_processed": 1,
            "detected_entities": 1,
            "redacted_entities": 1,
            "review_entities": 0,
            "kept_entities": 0,
            "review_required": False,
            "detected_candidates": [],
            "redacted_candidates": [],
            "review_candidates": [],
            "kept_candidates": [],
        }

        if on_completed is not None:
            on_completed(result)

        return result

    monkeypatch.setattr(
        "app.job_processor.process_job",
        fake_process_job,
    )

    def fail_persistence(*args, **kwargs):
        raise ArtifactServiceError(
            "Simulated artifact persistence failure."
    )

    monkeypatch.setattr(
        service,
        "save_redacted_artifact",
        fail_persistence,
    )

    with pytest.raises(ArtifactPersistenceError):
        process_storage_job(
            session,
            job_id=job.id,
            artifact_service=service,
        )

    session.refresh(job)
    session.refresh(document)

    assert job.status == "FAILED"
    assert job.error_code == "ARTIFACT_PERSISTENCE_FAILED"
    assert document.redacted_storage_key is None

    assert not service.storage.exists(
        build_redacted_storage_key(document.id)
    )

def test_storage_job_retry_after_persistence_failure_can_complete(
    db_document,
    tmp_path: Path,
    monkeypatch,
):
    """A failed artifact persistence attempt can be retried successfully."""
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = create_storage_service(tmp_path)

    original_path = service.storage.get_path(
        document.original_storage_key
    )

    original_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_path.write_bytes(
        b"%PDF-original"
    )

    def fake_process_job(
        session,
        *,
        job_id,
        input_path,
        output_path,
        on_completed=None,
        start_job_if_needed=True,
    ):
        output_path = Path(output_path)
        output_path.write_bytes(b"%PDF-redacted")

        result = {
            "input_path": Path(input_path),
            "output_path": output_path,
            "pages_processed": 1,
            "detected_entities": 1,
            "redacted_entities": 1,
            "review_entities": 0,
            "kept_entities": 0,
            "review_required": False,
            "detected_candidates": [],
            "redacted_candidates": [],
            "review_candidates": [],
            "kept_candidates": [],
        }

        if on_completed is not None:
            on_completed(result)

        complete_job(
            session,
            job_id=job_id,
        )

        return result

    monkeypatch.setattr(
        "app.job_processor.process_job",
        fake_process_job,
    )

    original_save = service.save_redacted_artifact
    attempts = {"count": 0}

    def flaky_save(document_id, source_path):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise ArtifactPersistenceError(
                "Simulated first persistence failure."
            )

        return original_save(
            document_id,
            source_path,
        )

    monkeypatch.setattr(
        service,
        "save_redacted_artifact",
        flaky_save,
    )

    # First attempt must fail.
    with pytest.raises(ArtifactPersistenceError):
        process_storage_job(
            session,
            job_id=job.id,
            artifact_service=service,
        )

    session.refresh(job)

    assert job.status == "FAILED"

    # Move the failed job into RETRYING.
    retry_job(
        session,
        job_id=job.id,
    )

    session.refresh(job)

    assert job.status == "RETRYING"

    # Second attempt should succeed.
    result = process_storage_job(
        session,
        job_id=job.id,
        artifact_service=service,
    )

    session.refresh(job)
    session.refresh(document)

    assert result["review_required"] is False
    assert job.status == "COMPLETED"
    assert job.progress == 100

    expected_key = build_redacted_storage_key(
        document.id
    )

    assert document.redacted_storage_key == expected_key
    assert service.storage.exists(expected_key)

    stored_path = service.storage.get_path(expected_key)

    assert stored_path.read_bytes() == b"%PDF-redacted"
    assert attempts["count"] == 2

def test_storage_job_missing_original_fails(
    db_document,
    tmp_path: Path,
):
    """A missing original artifact must fail the processing operation."""
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = create_storage_service(tmp_path)

    with pytest.raises(JobProcessingError):
        process_storage_job(
            session,
            job_id=job.id,
            artifact_service=service,
        )