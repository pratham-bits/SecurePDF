"""PII candidate review operations for SecurePDF."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Document, PIIEntity


class PIIReviewError(Exception):
    """Base exception for PII review failures."""


class PIICandidateNotFoundError(PIIReviewError):
    """Raised when a candidate does not exist."""


class PIIDocumentAccessError(PIIReviewError):
    """Raised when the document does not belong to the user."""


class PIIReviewValidationError(PIIReviewError):
    """Raised when a review decision is invalid."""


def save_review_decision(
    session: Session,
    *,
    user_id: str,
    document_id: str,
    candidate_id: str,
    decision: str,
) -> PIIEntity:
    """Save an explicit REDACT or KEEP decision."""

    normalized_decision = decision.strip().upper()

    if normalized_decision not in {"REDACT", "KEEP"}:
        raise PIIReviewValidationError(
            "Decision must be REDACT or KEEP."
        )

    document = (
        session.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .first()
    )

    if document is None:
        raise PIIDocumentAccessError(
            "Document not found or access denied."
        )

    candidate = (
        session.query(PIIEntity)
        .filter(
            PIIEntity.id == candidate_id,
            PIIEntity.document_id == document_id,
        )
        .with_for_update()
        .first()
    )

    if candidate is None:
        raise PIICandidateNotFoundError(
            "PII candidate not found."
        )

    candidate.review_decision = normalized_decision
    candidate.review_status = (
        "approved_for_redaction"
        if normalized_decision == "REDACT"
        else "kept"
    )

    try:
        session.commit()
        session.refresh(candidate)
    except SQLAlchemyError as exc:
        session.rollback()
        raise PIIReviewError(
            "Unable to save the PII review decision."
        ) from exc

    return candidate
