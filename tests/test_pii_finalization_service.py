
"""Tests for SecurePDF's reviewed-PII finalization service."""

from io import BytesIO
from uuid import uuid4

import pymupdf
import pytest

from app.artifact_service import DocumentArtifactService
from app.database import SessionLocal
from app.job_service import create_job, require_review, start_job
from app.models import Document, PIIEntity, ProcessingJob, User
from app.pii_finalization_service import (
    PiiFinalizationValidationError,
    finalize_reviewed_job,
)
from app.storage import LocalStorage


def _make_pdf() -> tuple[bytes, dict[str, tuple[float, float, float, float]]]:
    """Create a small real PDF and capture actual text coordinates."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)

    page.insert_text((72, 100), "SECRETPII123", fontsize=12)
    page.insert_text((72, 140), "PUBLICTOKEN", fontsize=12)

    boxes = {}
    for text in ("SECRETPII123", "PUBLICTOKEN"):
        matches = page.search_for(text)
        assert matches, f"Could not locate {text!r} in test PDF"
        rect = matches[0]
        boxes[text] = (
            float(rect.x0),
            float(rect.y0),
            float(rect.x1),
            float(rect.y1),
        )

    pdf_bytes = pdf.tobytes()
    pdf.close()
    return pdf_bytes, boxes


@pytest.fixture
def finalization_context(tmp_path):
    """Create isolated test artifacts and clean database rows afterward."""
    session = SessionLocal()
    storage = LocalStorage(tmp_path / "storage")
    artifact_service = DocumentArtifactService(storage)

    user = User(
        name="PII Finalization Test User",
        email=f"pii-finalization-{uuid4()}@example.com",
        password_hash="test-hash",
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    user_id = user.id
    pdf_bytes, boxes = _make_pdf()
    storage_key = f"uploads/{uuid4()}.pdf"

    document = Document(
        user_id=user.id,
        original_filename="pii-finalization-test.pdf",
        mime_type="application/pdf",
        size_bytes=len(pdf_bytes),
        page_count=1,
        document_type="digital",
        status="uploaded",
        original_storage_key=storage_key,
        redacted_storage_key=None,
        sha256_hash=f"pii-finalization-{uuid4()}",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    document_id = document.id

    storage.save(storage_key, BytesIO(pdf_bytes))

    job = create_job(
        session,
        document_id=document.id,
        job_type="PDF_PROCESSING",
    )
    start_job(session, job_id=job.id)
    require_review(session, job_id=job.id)

    context = {
        "session": session,
        "user": user,
        "document": document,
        "job": job,
        "storage": storage,
        "artifact_service": artifact_service,
        "original_bytes": pdf_bytes,
        "boxes": boxes,
    }

    try:
        yield context
    finally:
        session.rollback()
        session.close()

        cleanup = SessionLocal()
        try:
            # Delete child records before parent records.
            cleanup.query(PIIEntity).filter(
                PIIEntity.document_id == document_id
            ).delete(synchronize_session=False)

            cleanup.query(ProcessingJob).filter(
                ProcessingJob.document_id == document_id
            ).delete(synchronize_session=False)

            cleanup.query(Document).filter(
                Document.id == document_id
            ).delete(synchronize_session=False)

            cleanup.query(User).filter(
                User.id == user_id
            ).delete(synchronize_session=False)

            cleanup.commit()
        except Exception:
            cleanup.rollback()
            raise
        finally:
            cleanup.close()



def _add_candidate(
    context,
    *,
    text: str,
    decision: str | None,
) -> PIIEntity:
    """Persist a candidate with coordinates from the generated PDF."""
    x0, y0, x1, y1 = context["boxes"][text]

    candidate = PIIEntity(
        document_id=context["document"].id,
        entity_type="TEST_PII",
        detected_text=text,
        confidence=0.99,
        page_number=1,
        bounding_boxes=[
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
            }
        ],
        source="test",
        review_status=(
            "approved_for_redaction"
            if decision == "REDACT"
            else "kept"
            if decision == "KEEP"
            else "review_required"
        ),
        review_decision=decision,
    )
    context["session"].add(candidate)
    context["session"].commit()
    context["session"].refresh(candidate)
    return candidate


def test_finalization_uses_saved_redact_and_keep_decisions(
    finalization_context,
):
    context = finalization_context
    _add_candidate(
        context,
        text="SECRETPII123",
        decision="REDACT",
    )
    _add_candidate(
        context,
        text="PUBLICTOKEN",
        decision="KEEP",
    )

    result = finalize_reviewed_job(
        context["session"],
        job_id=context["job"].id,
        user_id=context["user"].id,
        artifact_service=context["artifact_service"],
    )

    assert result["status"] == "COMPLETED"
    assert result["redacted_storage_key"]

    # The original PDF must remain byte-for-byte unchanged.
    original_path = context["artifact_service"].get_original_path(
        context["document"].id,
        context["document"].original_storage_key,
    )
    assert original_path.read_bytes() == context["original_bytes"]

    # Verify the persisted output, not just an intermediate file.
    output_path = context["storage"].get_path(
        result["redacted_storage_key"]
    )
    assert output_path.is_file()

    output_pdf = pymupdf.open(output_path)
    try:
        output_text = "\n".join(
            page.get_text() for page in output_pdf
        )
        assert "SECRETPII123" not in output_text
        assert "PUBLICTOKEN" in output_text
    finally:
        output_pdf.close()

    context["session"].refresh(context["job"])
    context["session"].refresh(context["document"])

    assert context["job"].status == "COMPLETED"
    assert (
        context["document"].redacted_storage_key
        == result["redacted_storage_key"]
    )


def test_finalization_rejects_unreviewed_candidates(
    finalization_context,
):
    context = finalization_context
    _add_candidate(
        context,
        text="SECRETPII123",
        decision=None,
    )

    with pytest.raises(PiiFinalizationValidationError):
        finalize_reviewed_job(
            context["session"],
            job_id=context["job"].id,
            user_id=context["user"].id,
            artifact_service=context["artifact_service"],
        )

    context["session"].refresh(context["job"])
    assert context["job"].status == "REVIEW_REQUIRED"
    assert context["document"].redacted_storage_key is None


def test_finalization_rejects_another_users_job(
    finalization_context,
):
    context = finalization_context

    with pytest.raises(PiiFinalizationValidationError):
        finalize_reviewed_job(
            context["session"],
            job_id=context["job"].id,
            user_id=str(uuid4()),
            artifact_service=context["artifact_service"],
        )

    context["session"].refresh(context["job"])
    assert context["job"].status == "REVIEW_REQUIRED"


def test_finalization_rejects_job_not_waiting_for_review(
    finalization_context,
):
    context = finalization_context

    # Move the job out of REVIEW_REQUIRED.
    from app.job_service import complete_job

    start_job(context["session"], job_id=context["job"].id)
    complete_job(
    context["session"],
    job_id=context["job"].id,
)

    with pytest.raises(PiiFinalizationValidationError):
        finalize_reviewed_job(
            context["session"],
            job_id=context["job"].id,
            user_id=context["user"].id,
            artifact_service=context["artifact_service"],
        )

    context["session"].refresh(context["job"])
    assert context["job"].status == "COMPLETED"
