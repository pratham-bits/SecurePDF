
"""Processing-job API endpoints for SecurePDF."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.celery_tasks import process_job_task
from app.database import get_db
from app.dependencies import get_current_user
from app.job_service import JobServiceError, create_job
from app.models import Document, PIIEntity, ProcessingJob, User
from app.pii_review_service import (
    PIICandidateNotFoundError,
    PIIDocumentAccessError,
    PIIReviewError,
    PIIReviewValidationError,
    save_review_decision,
)

from app.pii_finalization_service import (
    PiiFinalizationArtifactError,
    PiiFinalizationError,
    PiiFinalizationValidationError,
    finalize_reviewed_job,
)

router = APIRouter(prefix="/api/v1", tags=["jobs"])

logger = logging.getLogger(__name__)


class CreateJobRequest(BaseModel):
    """Request body for creating a processing job."""

    job_type: str = Field(
        default="PDF_PROCESSING",
        min_length=1,
        max_length=50,
    )


class PIIReviewDecisionRequest(BaseModel):
    """Request body for reviewing a PII candidate."""

    decision: str = Field(
        min_length=1,
        max_length=20,
    )


def _job_response(job: ProcessingJob) -> dict[str, Any]:
    """Convert a ProcessingJob model into an API response."""

    document = job.document

    pii_entities: list[dict[str, Any]] = []

    if document is not None:
        pii_entities = [
            {
                "id": entity.id,
                "entity_type": entity.entity_type,
                "text": entity.detected_text,
                "confidence": entity.confidence,
                "page_number": entity.page_number,
                "bounding_boxes": entity.bounding_boxes,
                "source": entity.source,
                "review_status": entity.review_status,
                "review_decision": entity.review_decision,
            }
            for entity in document.pii_entities
        ]

    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "attempt_count": job.attempt_count,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "started_at": (
            job.started_at.isoformat()
            if job.started_at is not None
            else None
        ),
        "completed_at": (
            job.completed_at.isoformat()
            if job.completed_at is not None
            else None
        ),
        "created_at": (
            job.created_at.isoformat()
            if job.created_at is not None
            else None
        ),
        "pii_entities": pii_entities,
    }


@router.post(
    "/documents/{document_id}/jobs",
    status_code=status.HTTP_201_CREATED,
)
def create_processing_job(
    document_id: str,
    request: CreateJobRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Create a processing job and dispatch it to Celery."""

    document = db.get(Document, document_id)

    if document is None or document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id!r} was not found.",
        )

    try:
        job = create_job(
            db,
            document_id=document_id,
            job_type=request.job_type,
        )
    except JobServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    try:
        process_job_task.delay(job.id)
    except Exception as exc:
        logger.exception(
            "Failed to dispatch processing job %s to Celery.",
            job.id,
        )

        # The database job already exists. A future improvement should
        # provide a safe dispatch-retry or failure-recovery mechanism.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The processing job was created but could not be "
                "queued. Please retry or contact support."
            ),
        ) from exc

    return _job_response(job)


@router.get(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
)
def get_processing_job(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Return a processing job owned by the authenticated user."""

    job = db.get(ProcessingJob, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job {job_id!r} was not found.",
        )

    document = db.get(Document, job.document_id)

    if document is None or document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job {job_id!r} was not found.",
        )

    return _job_response(job)


@router.post(
    "/documents/{document_id}/pii-entities/{candidate_id}/decision",
    status_code=status.HTTP_200_OK,
)
def review_pii_candidate(
    document_id: str,
    candidate_id: str,
    payload: PIIReviewDecisionRequest,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Save an authenticated user's PII review decision."""

    try:
        candidate: PIIEntity = save_review_decision(
            session,
            user_id=current_user.id,
            document_id=document_id,
            candidate_id=candidate_id,
            decision=payload.decision,
        )

        return {
            "id": candidate.id,
            "document_id": candidate.document_id,
            "entity_type": candidate.entity_type,
            "review_decision": candidate.review_decision,
            "review_status": candidate.review_status,
        }

    except (
        PIIDocumentAccessError,
        PIICandidateNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except PIIReviewValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except PIIReviewError as exc:
        logger.exception(
            "Unable to save PII review decision for candidate %s.",
            candidate_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the PII review decision.",
        ) from exc

@router.post(
    "/documents/{document_id}/jobs/{job_id}/finalize",
    status_code=status.HTTP_200_OK,
)
def finalize_processing_job(
    document_id: str,
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Finalize a reviewed PDF and persist the redacted artifact."""

    job = db.get(ProcessingJob, job_id)

    if (
        job is None
        or job.document_id != document_id
        or job.document is None
        or job.document.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing job was not found.",
        )

    try:
        return finalize_reviewed_job(
            db,
            job_id=job_id,
            user_id=current_user.id,
        )

    except PiiFinalizationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except PiiFinalizationArtifactError as exc:
        logger.exception(
            "Artifact finalization failed for job %s.",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    except PiiFinalizationError as exc:
        logger.exception(
            "Finalization failed for job %s.",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc