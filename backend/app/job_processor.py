"""Processing-job orchestration for SecurePDF."""

from __future__ import annotations
import logging
import os
from app.models import PIIEntity
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.artifact_service import (
    ArtifactServiceError,
    DocumentArtifactService,
)
from app.artifact_storage import build_redacted_storage_key
from app.document_processor import (
    DocumentProcessingError,
    ProcessedDocumentResult,
    process_digital_pdf,
    process_mixed_pdf,
    process_scanned_pdf,
)
from app.job_service import (
    JobServiceError,
    complete_job,
    fail_job,
    get_job,
    require_review,
    start_job,
)
from app.storage import LocalStorage

logger = logging.getLogger(__name__)

DocumentType = Literal["digital", "scanned", "mixed"]


class JobProcessingError(Exception):
    """Raised when a processing job cannot be executed."""


class RetryableJobProcessingError(JobProcessingError):
    """Raised when a processing failure may succeed on retry."""


class ArtifactPersistenceError(JobProcessingError):
    """Raised when a completed artifact cannot be persisted."""


def _validate_document_type(document_type: str) -> DocumentType:
    """Validate the document processing type."""

    if document_type not in {"digital", "scanned", "mixed"}:
        raise JobProcessingError(
            f"Unsupported document type: {document_type!r}."
        )

    return document_type  # type: ignore[return-value]


def _run_document_processor(
    *,
    document_type: DocumentType,
    input_path: Path,
    output_path: Path,
) -> ProcessedDocumentResult:
    """Run the appropriate SecurePDF document-processing pipeline."""

    try:
        if document_type == "digital":
            return process_digital_pdf(
                input_path,
                output_path,
            )

        if document_type == "scanned":
            return process_scanned_pdf(
                input_path,
                output_path,
            )

        return process_mixed_pdf(
            input_path,
            output_path,
        )

    except DocumentProcessingError:
        raise

    except Exception as exc:
        raise RetryableJobProcessingError(
            "Unexpected document-processing failure."
        ) from exc


def process_job(
    session: Session,
    *,
    job_id: str,
    input_path: str | Path,
    output_path: str | Path,
    on_completed: Callable[[ProcessedDocumentResult], None] | None = None,
    start_job_if_needed: bool = True,
) -> ProcessedDocumentResult:
    """
    Execute a persisted processing job and synchronize its state.

    Lifecycle:

        PENDING / RETRYING
            -> RUNNING
            -> REVIEW_REQUIRED
            -> or COMPLETED

    Processing failures move the job to FAILED.

    The document processor remains responsible for document processing
    details; this service only coordinates processing with job state.

    ``on_completed`` is called after successful document processing but
    immediately before the job is marked COMPLETED. This allows callers
    to persist final processing artifacts before the completion state is
    committed.
    """

    job = get_job(session, job_id)

    if start_job_if_needed:
        if job.status not in {"PENDING", "RETRYING"}:
            raise JobProcessingError(
                f"Job {job_id!r} cannot be processed from status "
                f"{job.status!r}."
            )
    else:
        if job.status != "RUNNING":
            raise JobProcessingError(
                f"Job {job_id!r} must be RUNNING when "
                "start_job_if_needed=False."
            )
    document_type = _validate_document_type(
        job.document.document_type
    )

    input_file = Path(input_path)
    output_file = Path(output_path)

    try:
        if start_job_if_needed:
            start_job(
                session,
                job_id=job_id,
            )

        if not input_file.exists():
            raise JobProcessingError(
                "Processing input PDF does not exist."
            )

        if not input_file.is_file():
            raise JobProcessingError(
                "Processing input path is not a file."
            )

        result = _run_document_processor(
            document_type=document_type,
            input_path=input_file,
            output_path=output_file,
        )

        if result["review_required"]:
            require_review(
                session,
                job_id=job_id,
            )

            return result

        if on_completed is not None:
            on_completed(result)

        complete_job(
            session,
            job_id=job_id,
        )

        return result

    except ArtifactPersistenceError as exc:
        try:
            fail_job(
                session,
                job_id=job_id,
                error_code="ARTIFACT_PERSISTENCE_FAILED",
                error_message=str(exc),
            )
        except JobServiceError as state_exc:
            raise JobProcessingError(
                "Artifact persistence failed and the job failure "
                "state could not be persisted."
            ) from state_exc

        raise

    except RetryableJobProcessingError as exc:
        try:
            fail_job(
                session,
                job_id=job_id,
                error_code="PROCESSING_FAILED",
                error_message=str(exc),
            )
        except JobServiceError as state_exc:
            raise RetryableJobProcessingError(
                "Unexpected processing failure and the job failure "
                "state could not be persisted."
            ) from state_exc

        raise

    except (DocumentProcessingError, JobProcessingError) as exc:
        try:
            fail_job(
                session,
                job_id=job_id,
                error_code="PROCESSING_FAILED",
                error_message=str(exc),
            )
        except JobServiceError as state_exc:
            raise JobProcessingError(
                "Document processing failed and the job failure "
                "state could not be persisted."
            ) from state_exc

        raise JobProcessingError(
            str(exc)
        ) from exc

    except Exception as exc:
        try:
            fail_job(
                session,
                job_id=job_id,
                error_code="PROCESSING_FAILED",
                error_message="Unexpected document-processing failure.",
            )
        except JobServiceError as state_exc:
            raise RetryableJobProcessingError(
                "Unexpected processing failure and the job failure "
                "state could not be persisted."
            ) from state_exc

        raise RetryableJobProcessingError(
            "Unexpected document-processing failure."
        ) from exc


def process_storage_job(
    session: Session,
    *,
    job_id: str,
    artifact_service: DocumentArtifactService | None = None,
) -> ProcessedDocumentResult:
    """
    Execute a processing job using persistent storage artifacts.

    The original PDF is resolved from its storage key, copied into an
    isolated temporary workspace, processed by the existing document
    pipeline, and a successfully completed redacted PDF is persisted
    through the storage abstraction.

    Review-required jobs do not create or update a redacted artifact.
    """

    if artifact_service is None:
        storage_dir = Path(
            os.getenv(
                "STORAGE_DIR",
                Path(__file__).resolve().parents[1] / "storage",
            )
        )

        artifact_service = DocumentArtifactService(
            LocalStorage(storage_dir),
        )
        logger.info(
            "SecurePDF worker storage root: %s",
            artifact_service.storage.root,
        )

    job = get_job(
        session,
        job_id,
    )

    if job.document is None:
        raise JobProcessingError(
            f"Job {job_id!r} is not associated with a document."
        )

    document = job.document

    # Start the persisted job before accessing the storage artifact.
    # This guarantees that preparation failures can transition the job
    # from PENDING/RETRYING to FAILED.
    try:
        start_job(session, job_id=job_id)
    except JobServiceError as exc:
        raise JobProcessingError(
            "Processing job could not be started."
        ) from exc

    try:
        original_path = artifact_service.get_original_path(
            document.id,
            document.original_storage_key,
        )

    except ArtifactServiceError as exc:
        try:
            fail_job(
                session,
                job_id=job_id,
                error_code="ARTIFACT_UNAVAILABLE",
                error_message="Original document artifact is unavailable.",
            )
        except JobServiceError as state_exc:
            raise JobProcessingError(
                "Original document artifact is unavailable and the "
                "job failure state could not be persisted."
            ) from state_exc

        raise JobProcessingError(
            "Original document artifact is unavailable."
        ) from exc

    redacted_storage_key = build_redacted_storage_key(
        document.id
    )

    artifact_saved = False

    with artifact_service.processing_workspace() as workspace:
        input_path = workspace / "input.pdf"
        output_path = workspace / "redacted.pdf"

        # Copy the persistent artifact into the isolated workspace
        # without loading the entire PDF into memory.
        try:
            with original_path.open("rb") as source:
                with input_path.open("wb") as destination:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)

        except OSError as exc:
            try:
                fail_job(
                    session,
                    job_id=job_id,
                    error_code="ARTIFACT_PREPARATION_FAILED",
                    error_message=(
                        "Unable to prepare the document for processing."
                    ),
                )
            except JobServiceError as state_exc:
                raise JobProcessingError(
                    "Document preparation failed and the job failure "
                    "state could not be persisted."
                ) from state_exc

            raise JobProcessingError(
                "Unable to prepare the document for processing."
            ) from exc

        def persist_completed_artifact(
            result: ProcessedDocumentResult,
        ) -> None:
            nonlocal artifact_saved

            result_output = result["output_path"]

            if result_output is None:
                raise ArtifactPersistenceError(
                    "Completed processing did not produce an output PDF."
                )

            try:
                artifact_service.save_redacted_artifact(
                    document.id,
                    Path(result_output),
                )
            except ArtifactServiceError as exc:
                raise ArtifactPersistenceError(
                    "Redacted document artifact could not be persisted."
                ) from exc

            artifact_saved = True

            document.redacted_storage_key = redacted_storage_key

            session.flush()

        try:
            result = process_job(
                session,
                job_id=job_id,
                input_path=input_path,
                output_path=output_path,
                on_completed=persist_completed_artifact,
                start_job_if_needed=False,
            )
        except ArtifactPersistenceError as exc:
            if artifact_saved:
                artifact_service.storage.delete(redacted_storage_key)

            document.redacted_storage_key = None
            session.flush()

            current_job = get_job(session, job_id)

            if current_job.status == "RUNNING":
                fail_job(
                    session,
                    job_id=job_id,
                    error_code="ARTIFACT_PERSISTENCE_FAILED",
                    error_message="Unable to persist redacted document artifact.",
                )

            raise
        
        # Persist detected PII candidates for review in the database.
        candidates = result.get("detected_candidates", [])

        logger.info(
            "SecurePDF job %s: review_required=%s, detected_candidates=%d",
            job_id,
            result.get("review_required"),
            len(candidates),
        )

        for candidate in candidates:
            logger.info(
                "PII candidate: type=%s, source=%s, confidence=%s, action=%s",
                candidate.get("entity_type"),
                candidate.get("source"),
                candidate.get("confidence"),
                candidate.get("action"),
            )

        for candidate in candidates:
            action = candidate.get("action", "REVIEW").upper()
            review_status = (
                "review_required"
                if action == "REVIEW"
                else "detected"
            )

            session.add(
                PIIEntity(
                    document_id=document.id,
                    entity_type=candidate["entity_type"],
                    detected_text=candidate["text"],
                    confidence=candidate.get("confidence"),
                    page_number=candidate["page_number"],
                    bounding_boxes=candidate.get("bounding_boxes", []),
                    source=candidate.get("source", "unknown"),
                    review_status=review_status,
                )
            )

        session.flush()
        session.commit()

        return result