
from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.models import Document, PIIEntity, ProcessingJob, User
from app.pii_review_service import (
    PIICandidateNotFoundError,
    PIIDocumentAccessError,
    PIIReviewValidationError,
    save_review_decision,
)


def _create_user(session, *, name="PII Review Test User"):
    user = User(
        name=name,
        email=f"pii-review-{uuid4()}@example.com",
        password_hash="test-password-hash",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_document(session, user):
    document = Document(
        user_id=user.id,
        original_filename="pii-review-test.pdf",
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
    session.flush()
    return document


def _create_candidate(session, document):
    candidate = PIIEntity(
        document_id=document.id,
        entity_type="EMAIL",
        detected_text="alex@example.com",
        confidence=1.0,
        page_number=1,
        bounding_boxes=[
            {"x0": 10, "y0": 20, "x1": 100, "y1": 35}
        ],
        source="regex",
        review_status="review_required",
        review_decision=None,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def _cleanup(session, user_ids, document_ids):
    for document_id in document_ids:
        session.query(PIIEntity).filter(
            PIIEntity.document_id == document_id
        ).delete(synchronize_session=False)

        session.query(ProcessingJob).filter(
            ProcessingJob.document_id == document_id
        ).delete(synchronize_session=False)

    for document_id in document_ids:
        session.query(Document).filter(
            Document.id == document_id
        ).delete(synchronize_session=False)

    for user_id in user_ids:
        session.query(User).filter(
            User.id == user_id
        ).delete(synchronize_session=False)

    session.commit()


@pytest.fixture
def review_records():
    session = SessionLocal()
    user = None
    document = None

    try:
        user = _create_user(session)
        document = _create_document(session, user)
        candidate = _create_candidate(session, document)

        yield session, user, document, candidate

    finally:
        try:
            if user is not None and document is not None:
                _cleanup(
                    session,
                    user_ids=[user.id],
                    document_ids=[document.id],
                )
        finally:
            session.close()


def test_save_redact_decision(review_records):
    session, user, document, candidate = review_records

    result = save_review_decision(
        session,
        user_id=user.id,
        document_id=document.id,
        candidate_id=candidate.id,
        decision="REDACT",
    )

    assert result.review_decision == "REDACT"
    assert result.review_status == "approved_for_redaction"

    session.refresh(result)
    assert result.review_decision == "REDACT"


def test_save_keep_decision(review_records):
    session, user, document, candidate = review_records

    result = save_review_decision(
        session,
        user_id=user.id,
        document_id=document.id,
        candidate_id=candidate.id,
        decision="KEEP",
    )

    assert result.review_decision == "KEEP"
    assert result.review_status == "kept"


def test_decision_is_normalized(review_records):
    session, user, document, candidate = review_records

    result = save_review_decision(
        session,
        user_id=user.id,
        document_id=document.id,
        candidate_id=candidate.id,
        decision=" redact ",
    )

    assert result.review_decision == "REDACT"


def test_invalid_decision_is_rejected(review_records):
    session, user, document, candidate = review_records

    with pytest.raises(PIIReviewValidationError):
        save_review_decision(
            session,
            user_id=user.id,
            document_id=document.id,
            candidate_id=candidate.id,
            decision="IGNORE",
        )

    session.refresh(candidate)
    assert candidate.review_decision is None


def test_missing_candidate_is_rejected(review_records):
    session, user, document, _ = review_records

    with pytest.raises(PIICandidateNotFoundError):
        save_review_decision(
            session,
            user_id=user.id,
            document_id=document.id,
            candidate_id=str(uuid4()),
            decision="REDACT",
        )


def test_another_users_document_is_not_accessible(review_records):
    session, _, document, candidate = review_records
    other_user = None

    try:
        other_user = _create_user(
            session,
            name="Different PII Review User",
        )
        session.commit()

        with pytest.raises(PIIDocumentAccessError):
            save_review_decision(
                session,
                user_id=other_user.id,
                document_id=document.id,
                candidate_id=candidate.id,
                decision="REDACT",
            )
    finally:
        if other_user is not None:
            _cleanup(
                session,
                user_ids=[other_user.id],
                document_ids=[],
            )
