from pathlib import Path
from uuid import uuid4
from app.job_service import complete_job
import pytest
from app.models import PIIEntity

from app.artifact_service import DocumentArtifactService
from app.artifact_storage import (
    build_original_storage_key,
    build_redacted_storage_key,
)
from app.database import SessionLocal
from app.job_processor import (
    JobProcessingError,
    process_storage_job,
)
from app.job_service import create_job
from app.models import Document, ProcessingJob, User
from app.storage import LocalStorage


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
TEST_PDF = BACKEND_DIR / "test_data" / "coordinate_test.pdf"


def _create_test_document(session):
    """Create a real database document for the storage-job tests."""

    user = User(
        name="Storage Job Test User",
        email=f"storage-job-{uuid4()}@example.com",
        password_hash="test-password-hash",
        is_active=True,
    )

    session.add(user)
    session.flush()

    document_id = str(uuid4())

    document = Document(
        id=document_id,
        user_id=user.id,
        original_filename="coordinate_test.pdf",
        mime_type="application/pdf",
        size_bytes=TEST_PDF.stat().st_size,
        page_count=1,
        document_type="digital",
        status="uploaded",
        original_storage_key=build_original_storage_key(
            document_id
        ),
        redacted_storage_key=None,
        sha256_hash=uuid4().hex + uuid4().hex,
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    return user, document



def _cleanup(session, user, document):
    """Remove integration-test database records."""

    # Delete child records before deleting their parent document.
    session.query(PIIEntity).filter(
        PIIEntity.document_id == document.id
    ).delete(synchronize_session=False)

    session.query(ProcessingJob).filter(
        ProcessingJob.document_id == document.id
    ).delete(synchronize_session=False)

    session.query(Document).filter(
        Document.id == document.id
    ).delete(synchronize_session=False)

    session.query(User).filter(
        User.id == user.id
    ).delete(synchronize_session=False)

    session.commit()



@pytest.fixture
def db_document():
    session = SessionLocal()
    user = None
    document = None

    try:
        user, document = _create_test_document(session)
        yield session, document
    finally:
        try:
            if user is not None and document is not None:
                _cleanup(session, user, document)
        finally:
            session.close()


def _create_storage_service(tmp_path: Path):
    """Create an isolated local storage backend for the test."""

    return DocumentArtifactService(
        LocalStorage(tmp_path / "storage")
    )


def _store_original_pdf(
    service: DocumentArtifactService,
    document: Document,
):
    """Store the real test PDF under the document's storage key."""

    with TEST_PDF.open("rb") as source:
        service.storage.save(
            document.original_storage_key,
            source,
        )


def test_storage_job_review_does_not_create_redacted_artifact(
    db_document,
    tmp_path,
):
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = _create_storage_service(tmp_path)

    _store_original_pdf(
        service,
        document,
    )

    result = process_storage_job(
        session,
        job_id=job.id,
        artifact_service=service,
    )

    session.refresh(job)
    session.refresh(document)

    assert result["review_required"] is True

    assert job.status == "REVIEW_REQUIRED"
    assert job.progress == 100

    assert document.redacted_storage_key is None

    assert not service.storage.exists(
        build_redacted_storage_key(document.id)
    )


def test_storage_job_persists_completed_artifact(
    db_document,
    tmp_path,
    monkeypatch,
):
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = _create_storage_service(tmp_path)

    _store_original_pdf(
        service,
        document,
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

    session.refresh(job)
    session.refresh(document)

    assert result["review_required"] is False

    assert job.status == "COMPLETED"
    assert job.progress == 100

    assert (
        document.redacted_storage_key
        == build_redacted_storage_key(document.id)
    )

    stored_path = service.storage.get_path(
        document.redacted_storage_key
    )

    assert stored_path.exists()
    assert stored_path.read_bytes() == b"%PDF-redacted"


def test_storage_job_missing_original_fails(
    db_document,
    tmp_path,
):
    session, document = db_document

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    service = _create_storage_service(tmp_path)

    with pytest.raises(JobProcessingError):
        process_storage_job(
            session,
            job_id=job.id,
            artifact_service=service,
        )

    session.refresh(job)
    session.refresh(document)

    assert job.status == "FAILED"
    assert job.error_code == "ARTIFACT_UNAVAILABLE"
    assert job.error_message is not None
    assert document.redacted_storage_key is None