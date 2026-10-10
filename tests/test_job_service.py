from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.job_service import (
    DocumentNotFoundError,
    JobServiceError,
    JobValidationError,
    complete_job,
    create_job,
    fail_job,
    require_review,
    retry_job,
    start_job,
    update_progress,
)
from app.models import Document, ProcessingJob, User


def _create_test_document(session):
    """Create a real database user and document for service tests."""

    user = User(
        name="Job Service Test User",
        email=f"job-service-{uuid4()}@example.com",
        password_hash="test-password-hash",
        is_active=True,
    )

    session.add(user)
    session.flush()

    document = Document(
        user_id=user.id,
        original_filename="job-service-test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        page_count=1,
        document_type="digital",
        status="uploaded",
        original_storage_key=f"uploads/{uuid4()}.pdf",
        redacted_storage_key=None,
        sha256_hash=uuid4().hex + uuid4().hex,
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    return user, document


def _cleanup(session, user, document):
    """Remove test records from the real database."""

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
def db_session():
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


def test_create_job_persists_pending_job(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )

    assert job.id is not None
    assert job.document_id == document.id
    assert job.job_type == "PDF_PROCESSING"
    assert job.status == "PENDING"
    assert job.progress == 0
    assert job.attempt_count == 0
    assert job.started_at is None
    assert job.completed_at is None


def test_create_job_rejects_missing_document(db_session):
    session, _ = db_session

    with pytest.raises(DocumentNotFoundError):
        create_job(
            session,
            document_id=str(uuid4()),
        )


def test_create_job_rejects_invalid_input(db_session):
    session, _ = db_session

    with pytest.raises(JobValidationError):
        create_job(
            session,
            document_id="",
        )

    with pytest.raises(JobValidationError):
        create_job(
            session,
            document_id=str(uuid4()),
            job_type="",
        )


def test_start_job_changes_status_and_increments_attempt(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    started = start_job(
        session,
        job_id=job.id,
    )

    assert started.status == "RUNNING"
    assert started.attempt_count == 1
    assert started.started_at is not None
    assert started.completed_at is None


def test_progress_updates_for_running_job(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    updated = update_progress(
        session,
        job_id=job.id,
        progress=50,
    )

    assert updated.status == "RUNNING"
    assert updated.progress == 50


@pytest.mark.parametrize(
    "progress",
    [-1, 101, 1.5, True, False],
)
def test_invalid_progress_is_rejected(db_session, progress):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    with pytest.raises(JobValidationError):
        update_progress(
            session,
            job_id=job.id,
            progress=progress,
        )


def test_progress_cannot_be_updated_before_job_starts(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    with pytest.raises(JobServiceError):
        update_progress(
            session,
            job_id=job.id,
            progress=20,
        )


def test_running_job_can_require_review(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    updated = require_review(
        session,
        job_id=job.id,
    )

    assert updated.status == "REVIEW_REQUIRED"
    assert updated.progress == 100


def test_review_job_can_resume(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    require_review(
        session,
        job_id=job.id,
    )

    resumed = start_job(
        session,
        job_id=job.id,
    )

    assert resumed.status == "RUNNING"
    assert resumed.attempt_count == 2
    assert resumed.started_at is not None


def test_running_job_can_complete(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    completed = complete_job(
        session,
        job_id=job.id,
    )

    assert completed.status == "COMPLETED"
    assert completed.progress == 100
    assert completed.completed_at is not None
    assert completed.error_code is None
    assert completed.error_message is None


def test_running_job_can_fail(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    failed = fail_job(
        session,
        job_id=job.id,
        error_code="OCR_FAILED",
        error_message="OCR processing failed.",
    )

    assert failed.status == "FAILED"
    assert failed.error_code == "OCR_FAILED"
    assert failed.error_message == "OCR processing failed."
    assert failed.completed_at is None


def test_failed_job_can_retry_and_start_again(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    fail_job(
        session,
        job_id=job.id,
        error_code="PROCESSING_FAILED",
        error_message="Processing failed.",
    )

    retrying = retry_job(
        session,
        job_id=job.id,
    )

    assert retrying.status == "RETRYING"
    assert retrying.progress == 0
    assert retrying.error_code is None
    assert retrying.error_message is None

    restarted = start_job(
        session,
        job_id=job.id,
    )

    assert restarted.status == "RUNNING"
    assert restarted.attempt_count == 2


def test_completed_job_cannot_be_modified(db_session):
    session, document = db_session

    job = create_job(
        session,
        document_id=document.id,
    )

    start_job(
        session,
        job_id=job.id,
    )

    complete_job(
        session,
        job_id=job.id,
    )

    with pytest.raises(JobServiceError):
        start_job(
            session,
            job_id=job.id,
        )

    with pytest.raises(JobServiceError):
        fail_job(
            session,
            job_id=job.id,
            error_code="TEST",
            error_message="Should fail.",
        )


def test_missing_job_is_rejected(db_session):
    session, _ = db_session

    with pytest.raises(JobServiceError):
        start_job(
            session,
            job_id=str(uuid4()),
        )