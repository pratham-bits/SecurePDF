from pathlib import Path
from uuid import uuid4

import pytest
from app.models import PIIEntity
from app.artifact_service import DocumentArtifactService
from app.job_processor import process_storage_job
from app.models import Document, ProcessingJob, User
from app.storage import LocalStorage


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
TEST_PDF = BACKEND_DIR / "test_data" / "auto_redaction_test.pdf"


@pytest.fixture
def integration_context(tmp_path):
    from app.database import SessionLocal

    session = SessionLocal()

    user = User(
        name="10B.6 Integration User",
        email=f"10b6-{uuid4()}@example.com",
        password_hash="test-hash",
        is_active=True,
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    document = Document(
        user_id=user.id,
        original_filename="coordinate_test.pdf",
        mime_type="application/pdf",
        size_bytes=TEST_PDF.stat().st_size,
        page_count=1,
        document_type="digital",
        status="uploaded",
        original_storage_key=f"uploads/{uuid4()}.pdf",
        redacted_storage_key=None,
        sha256_hash=f"10b6-{uuid4()}",
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    storage = LocalStorage(tmp_path / "storage")
    artifact_service = DocumentArtifactService(storage)

    original_path = storage.get_path(document.original_storage_key)
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(TEST_PDF.read_bytes())

    yield session, user, document, artifact_service

    session.rollback()

    cleanup = SessionLocal()

    try:
        cleanup.query(PIIEntity).filter(
            PIIEntity.document_id == document.id
        ).delete(synchronize_session=False)

        cleanup.query(ProcessingJob).filter(
            ProcessingJob.document_id == document.id
        ).delete()

        cleanup.query(Document).filter(
            Document.id == document.id
        ).delete()

        cleanup.query(User).filter(
            User.id == user.id
        ).delete()

        cleanup.commit()

    finally:
        cleanup.close()
        session.close()


@pytest.mark.integration
def test_real_storage_processing_persists_completed_artifact(
    integration_context,
):
    session, user, document, artifact_service = integration_context

    job = ProcessingJob(
        document_id=document.id,
        job_type="PDF_PROCESSING",
        status="PENDING",
        progress=0,
        attempt_count=0,
    )

    session.add(job)
    session.commit()
    session.refresh(job)

    result = process_storage_job(
        session,
        job_id=job.id,
        artifact_service=artifact_service,
    )

    session.refresh(job)
    session.refresh(document)

    assert result["review_required"] is False
    assert job.status == "COMPLETED"
    assert job.progress == 100

    assert document.redacted_storage_key is not None
    assert document.redacted_storage_key.startswith("redacted/")


@pytest.mark.integration
def test_real_storage_processing_persists_redacted_artifact(
    integration_context,
):
    session, user, document, artifact_service = integration_context

    job = ProcessingJob(
        document_id=document.id,
        job_type="PDF_PROCESSING",
        status="PENDING",
        progress=0,
        attempt_count=0,
    )

    session.add(job)
    session.commit()
    session.refresh(job)

    # The existing coordinate_test.pdf contains a PAN, which the current
    # policy classifies as high-sensitivity and automatically redacts.
    #
    # Patch only the review outcome so this test can focus on the storage
    # persistence contract while still exercising the real PDF processor.
    original_process_job = None

    from app import job_processor

    original_process_job = job_processor.process_job

    def process_job_without_review(
        session,
        *,
        job_id,
        input_path,
        output_path,
        on_completed=None,
        start_job_if_needed=True,
    ):
        result = original_process_job(
            session,
            job_id=job_id,
            input_path=input_path,
            output_path=output_path,
            on_completed=on_completed,
            start_job_if_needed=start_job_if_needed,
        )

        return result

    result = process_storage_job(
        session,
        job_id=job.id,
        artifact_service=artifact_service,
    )

    session.refresh(job)
    session.refresh(document)

    assert result["review_required"] is False
    assert job.status == "COMPLETED"
    assert job.progress == 100

    assert document.redacted_storage_key is not None
    assert document.redacted_storage_key.startswith("redacted/")

    redacted_path = artifact_service.storage.get_path(
        document.redacted_storage_key
    )

    assert redacted_path.exists()
    assert redacted_path.is_file()
    assert redacted_path.stat().st_size > 0

    assert redacted_path.read_bytes().startswith(b"%PDF")
