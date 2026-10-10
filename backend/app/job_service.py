"""Database-backed processing job service for SecurePDF."""

from datetime import UTC, datetime
from typing import Final

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.job_state import (
    COMPLETED,
    FAILED,
    PENDING,
    REVIEW_REQUIRED,
    RETRYING,
    RUNNING,
    JobStateError,
    transition_job_status,
)
from app.models import Document, ProcessingJob


DEFAULT_JOB_TYPE: Final[str] = "PDF_PROCESSING"


class JobServiceError(Exception):
    """Base exception for processing-job service errors."""


class JobNotFoundError(JobServiceError):
    """Raised when the requested processing job does not exist."""


class DocumentNotFoundError(JobServiceError):
    """Raised when the requested document does not exist."""


class JobValidationError(JobServiceError):
    """Raised when processing-job input is invalid."""


def _utc_now() -> datetime:
    """Return a naive UTC datetime compatible with SQLAlchemy DateTime."""
    return datetime.now(UTC).replace(tzinfo=None)

def get_job(
    session: Session,
    job_id: str,
) -> ProcessingJob:
    """Load a processing job or raise a domain-specific error."""

    if not isinstance(job_id, str) or not job_id.strip():
        raise JobValidationError("job_id must be a non-empty string.")

    job = session.get(ProcessingJob, job_id)

    if job is None:
        raise JobNotFoundError(
            f"Processing job {job_id!r} was not found."
        )

    return job


def _validate_progress(progress: int) -> int:
    """Validate processing progress as an integer percentage."""

    if isinstance(progress, bool) or not isinstance(progress, int):
        raise JobValidationError(
            "progress must be an integer between 0 and 100."
        )

    if not 0 <= progress <= 100:
        raise JobValidationError(
            "progress must be between 0 and 100."
        )

    return progress


def _commit(
    session: Session,
) -> None:
    """Commit the current transaction and translate database failures."""

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise JobServiceError(
            "Unable to persist processing-job changes."
        ) from exc


def create_job(
    session: Session,
    *,
    document_id: str,
    job_type: str = DEFAULT_JOB_TYPE,
) -> ProcessingJob:
    """
    Create a new processing job in the PENDING state.

    The referenced document must exist before the job is created.
    """

    if not isinstance(document_id, str) or not document_id.strip():
        raise JobValidationError(
            "document_id must be a non-empty string."
        )

    if not isinstance(job_type, str) or not job_type.strip():
        raise JobValidationError(
            "job_type must be a non-empty string."
        )

    document = session.get(Document, document_id)

    if document is None:
        raise DocumentNotFoundError(
            f"Document {document_id!r} was not found."
        )

    job = ProcessingJob(
        document_id=document.id,
        job_type=job_type.strip(),
        status=PENDING,
        progress=0,
        attempt_count=0,
        error_code=None,
        error_message=None,
        started_at=None,
        completed_at=None,
    )

    session.add(job)
    _commit(session)
    session.refresh(job)

    return job


def start_job(
    session: Session,
    *,
    job_id: str,
) -> ProcessingJob:
    """
    Start a pending or retrying processing job.

    Each transition into RUNNING increments attempt_count.
    """

    job = get_job(session, job_id)

    try:
        next_status = transition_job_status(
            job.status,
            RUNNING,
        )
    except JobStateError as exc:
        raise JobServiceError(str(exc)) from exc

    job.status = next_status
    job.started_at = _utc_now()
    job.completed_at = None
    job.error_code = None
    job.error_message = None
    job.attempt_count += 1

    _commit(session)
    session.refresh(job)

    return job


def update_progress(
    session: Session,
    *,
    job_id: str,
    progress: int,
) -> ProcessingJob:
    """
    Update processing progress for a currently running job.
    """

    progress = _validate_progress(progress)
    job = get_job(session, job_id)

    if job.status != RUNNING:
        raise JobServiceError(
            "Progress can only be updated while a job is RUNNING."
        )

    job.progress = progress

    _commit(session)
    session.refresh(job)

    return job


def require_review(
    session: Session,
    *,
    job_id: str,
) -> ProcessingJob:
    """
    Move a running job into the human-review state.

    Processing is considered complete from the automated-processing
    perspective, so progress is set to 100 while the job waits for
    user decisions.
    """

    job = get_job(session, job_id)

    try:
        next_status = transition_job_status(
            job.status,
            REVIEW_REQUIRED,
        )
    except JobStateError as exc:
        raise JobServiceError(str(exc)) from exc

    job.status = next_status
    job.progress = 100

    _commit(session)
    session.refresh(job)

    return job


def complete_job(
    session: Session,
    *,
    job_id: str,
) -> ProcessingJob:
    """
    Mark a running job as successfully completed.
    """

    job = get_job(session, job_id)

    try:
        next_status = transition_job_status(
            job.status,
            COMPLETED,
        )
    except JobStateError as exc:
        raise JobServiceError(str(exc)) from exc

    job.status = next_status
    job.progress = 100
    job.completed_at = _utc_now()
    job.error_code = None
    job.error_message = None

    _commit(session)
    session.refresh(job)

    return job


def fail_job(
    session: Session,
    *,
    job_id: str,
    error_code: str,
    error_message: str,
) -> ProcessingJob:
    """
    Mark a running or retrying job as failed.

    Error details are persisted for operational diagnostics.
    """

    if not isinstance(error_code, str) or not error_code.strip():
        raise JobValidationError(
            "error_code must be a non-empty string."
        )

    if not isinstance(error_message, str) or not error_message.strip():
        raise JobValidationError(
            "error_message must be a non-empty string."
        )

    job = get_job(session, job_id)

    try:
        next_status = transition_job_status(
            job.status,
            FAILED,
        )
    except JobStateError as exc:
        raise JobServiceError(str(exc)) from exc

    job.status = next_status
    job.error_code = error_code.strip()
    job.error_message = error_message.strip()
    job.completed_at = None

    _commit(session)
    session.refresh(job)

    return job


def retry_job(
    session: Session,
    *,
    job_id: str,
) -> ProcessingJob:
    """
    Mark a failed job as ready for another processing attempt.

    attempt_count is incremented when the retry actually starts, not here.
    """

    job = get_job(session, job_id)

    try:
        next_status = transition_job_status(
            job.status,
            RETRYING,
        )
    except JobStateError as exc:
        raise JobServiceError(str(exc)) from exc

    job.status = next_status
    job.progress = 0
    job.started_at = None
    job.completed_at = None
    job.error_code = None
    job.error_message = None

    _commit(session)
    session.refresh(job)

    return job