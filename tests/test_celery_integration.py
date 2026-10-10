from pathlib import Path
from uuid import uuid4

import pytest
from app.models import PIIEntity
from app.celery_tasks import process_job_task
from app.database import SessionLocal
from app.job_service import create_job
from app.models import Document, ProcessingJob, User
from app.storage import LocalStorage


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
TEST_PDF = BACKEND_DIR / "test_data" / "auto_redaction_test.pdf"
STORAGE_DIR = BACKEND_DIR / "storage"


@pytest.fixture
def real_processing_job():
    session = SessionLocal()
    storage = LocalStorage(STORAGE_DIR)

    user = User(
        name="Celery Integration Test User",
        email=f"celery-{uuid4()}@example.com",
        password_hash="test-hash",
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    user_id = user.id
    storage_key = f"uploads/{uuid4()}.pdf"

    document = Document(
        user_id=user_id,
        original_filename="auto_redaction_test.pdf",
        mime_type="application/pdf",
        size_bytes=TEST_PDF.stat().st_size,
        page_count=1,
        document_type="digital",
        status="uploaded",
        original_storage_key=storage_key,
        redacted_storage_key=None,
        sha256_hash="celery-integration-test",
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    document_id = document.id

    with TEST_PDF.open("rb") as source:
        storage.save(storage_key, source)

    job = create_job(
        session,
        document_id=document_id,
        job_type="PDF_PROCESSING",
    )

    job_id = job.id

    yield session, job

    session.close()

    cleanup = SessionLocal()

    try:
        persisted_document = cleanup.get(Document, document_id)

        redacted_storage_key = (
            persisted_document.redacted_storage_key
            if persisted_document is not None
            else None
        )

        # Remove test-generated persistent artifacts.
        storage.delete(storage_key)

        if redacted_storage_key:
            storage.delete(redacted_storage_key)

        # Remove database records.
        cleanup.query(PIIEntity).filter(
            PIIEntity.document_id == document_id
        ).delete(synchronize_session=False)

        cleanup.query(ProcessingJob).filter(
            ProcessingJob.id == job_id
        ).delete()

        cleanup.query(Document).filter(
            Document.id == document_id
        ).delete()

        cleanup.query(User).filter(
            User.id == user_id
        ).delete()

        cleanup.commit()

    finally:
        cleanup.close()


@pytest.mark.integration
def test_real_celery_processing_job(real_processing_job):
    session, job = real_processing_job

    async_result = process_job_task.delay(job.id)

    result = async_result.get(
        timeout=180,
        propagate=True,
    )

    assert result["job_id"] == job.id
    assert result["review_required"] is False
    assert result["status"] == "COMPLETED"

    verification_session = SessionLocal()

    try:
        persisted_job = verification_session.get(
            ProcessingJob,
            job.id,
        )

        persisted_document = verification_session.get(
            Document,
            job.document_id,
        )

        assert persisted_job is not None
        assert persisted_job.status == "COMPLETED"
        assert persisted_job.progress == 100

        assert persisted_document is not None
        assert persisted_document.redacted_storage_key is not None
        assert persisted_document.redacted_storage_key.startswith(
            "redacted/"
        )

        redacted_path = STORAGE_DIR / persisted_document.redacted_storage_key

        assert redacted_path.exists()
        assert redacted_path.is_file()
        assert redacted_path.stat().st_size > 0

    finally:
        verification_session.close()
