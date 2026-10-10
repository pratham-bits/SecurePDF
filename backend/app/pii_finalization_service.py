"""Finalize reviewed PII candidates and persist the resulting PDF."""

from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.artifact_service import (
    ArtifactServiceError,
    DocumentArtifactService,
)
from app.document_processor import ProcessedCandidate
from app.final_redaction import (
    FinalRedactionError,
    finalize_redaction,
)
from app.job_service import (
    JobServiceError,
    complete_job,
    fail_job,
    get_job,
    start_job,
)
from app.models import PIIEntity

logger = logging.getLogger(__name__)


class PiiFinalizationError(Exception):
    """Base error for PII finalization."""


class PiiFinalizationValidationError(PiiFinalizationError):
    """Raised when a job or candidate is not ready for finalization."""


class PiiFinalizationArtifactError(PiiFinalizationError):
    """Raised when the final PDF cannot be persisted."""


def _parse_bounding_box(
    raw_box: Any,
    *,
    candidate_id: str,
    box_index: int,
) -> tuple[float, float, float, float]:
    """Parse a supported bounding-box shape and validate its geometry.

    Supported persisted shapes:
      - {"x0": ..., "y0": ..., "x1": ..., "y1": ...}
      - [x0, y0, x1, y1] (or an equivalent tuple)

    Coordinates are interpreted as PDF page coordinates. We deliberately do
    not guess at other schemas or silently repair invalid geometry.
    """

    if isinstance(raw_box, dict):
        try:
            values = (
                raw_box["x0"],
                raw_box["y0"],
                raw_box["x1"],
                raw_box["y1"],
            )
        except KeyError as exc:
            logger.error(
                "Invalid PII bounding box: candidate_id=%s box_index=%s "
                "reason=missing_coordinate_key box=%r",
                candidate_id,
                box_index,
                raw_box,
            )
            raise PiiFinalizationValidationError(
                f"Candidate {candidate_id} bounding box {box_index} "
                "is missing x0, y0, x1, or y1."
            ) from exc
    elif isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
        values = tuple(raw_box)
    else:
        logger.error(
            "Invalid PII bounding box: candidate_id=%s box_index=%s "
            "reason=unsupported_shape type=%s box=%r",
            candidate_id,
            box_index,
            type(raw_box).__name__,
            raw_box,
        )
        raise PiiFinalizationValidationError(
            f"Candidate {candidate_id} bounding box {box_index} "
            "has an unsupported format. Expected x0/y0/x1/y1 coordinates."
        )

    try:
        coordinates = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        logger.error(
            "Invalid PII bounding box: candidate_id=%s box_index=%s "
            "reason=non_numeric_coordinates box=%r",
            candidate_id,
            box_index,
            raw_box,
        )
        raise PiiFinalizationValidationError(
            f"Candidate {candidate_id} bounding box {box_index} "
            "contains non-numeric coordinates."
        ) from exc

    if len(coordinates) != 4 or not all(math.isfinite(value) for value in coordinates):
        logger.error(
            "Invalid PII bounding box: candidate_id=%s box_index=%s "
            "reason=non_finite_coordinates coordinates=%r",
            candidate_id,
            box_index,
            coordinates,
        )
        raise PiiFinalizationValidationError(
            f"Candidate {candidate_id} bounding box {box_index} "
            "contains non-finite coordinates."
        )

    x0, y0, x1, y1 = coordinates
    if x1 <= x0 or y1 <= y0:
        logger.error(
            "Invalid PII bounding box: candidate_id=%s box_index=%s "
            "reason=non_positive_area coordinates=%r",
            candidate_id,
            box_index,
            coordinates,
        )
        raise PiiFinalizationValidationError(
            f"Candidate {candidate_id} bounding box {box_index} "
            "has invalid geometry (x1 must exceed x0 and y1 must exceed y0)."
        )

    return (x0, y0, x1, y1)


def _build_final_candidates(
    entities: list[PIIEntity],
) -> list[ProcessedCandidate]:
    """Convert persisted PII records into validated final-redaction candidates."""

    candidates: list[ProcessedCandidate] = []

    if not entities:
        raise PiiFinalizationValidationError(
            "No PII candidates were found for this review job."
        )

    for entity in entities:
        decision = entity.review_decision

        if decision not in {"REDACT", "KEEP"}:
            raise PiiFinalizationValidationError(
                "Every detected PII candidate must have a REDACT "
                "or KEEP decision before finalization."
            )

        raw_boxes = entity.bounding_boxes
        logger.info(
            "PII bounding boxes: candidate_id=%s entity_type=%s "
            "page_number=%s container_type=%s boxes=%r",
            entity.id,
            entity.entity_type,
            entity.page_number,
            type(raw_boxes).__name__,
            raw_boxes,
        )

        if not isinstance(raw_boxes, list):
            logger.error(
                "Invalid PII bounding-box collection: candidate_id=%s "
                "type=%s value=%r",
                entity.id,
                type(raw_boxes).__name__,
                raw_boxes,
            )
            raise PiiFinalizationValidationError(
                f"Candidate {entity.id} has invalid bounding-box data."
            )

        boxes = [
            _parse_bounding_box(
                raw_box,
                candidate_id=str(entity.id),
                box_index=index,
            )
            for index, raw_box in enumerate(raw_boxes)
        ]

        if decision == "REDACT" and not boxes:
            logger.error(
                "Candidate approved for redaction has no bounding boxes: "
                "candidate_id=%s entity_type=%s page_number=%s",
                entity.id,
                entity.entity_type,
                entity.page_number,
            )
            raise PiiFinalizationValidationError(
                f"Candidate {entity.id} is approved for redaction "
                "but has no bounding boxes."
            )

        candidates.append(
            {
                "candidate_id": entity.id,
                "entity_type": entity.entity_type,
                "text": entity.detected_text,
                "confidence": entity.confidence,
                "source": entity.source,
                "start": 0,
                "end": 0,
                "sensitivity": "PII",
                "action": decision,
                "reason": "User review decision",
                "page_number": entity.page_number,
                "bounding_boxes": boxes,
            }
        )

    return candidates


def finalize_reviewed_job(
    session: Session,
    *,
    job_id: str,
    user_id: str,
    artifact_service: DocumentArtifactService | None = None,
) -> dict[str, Any]:
    """Finalize a review-required job using saved candidate decisions."""

    if artifact_service is None:
        from os import getenv

        from app.storage import LocalStorage

        storage_dir = Path(
            getenv(
                "STORAGE_DIR",
                Path(__file__).resolve().parents[1] / "storage",
            )
        )
        artifact_service = DocumentArtifactService(LocalStorage(storage_dir))

    try:
        job = get_job(session, job_id)
    except JobServiceError as exc:
        raise PiiFinalizationValidationError(
            "The requested processing job was not found."
        ) from exc

    document = job.document

    if document is None or document.user_id != user_id:
        # Do not reveal whether another user's job exists.
        raise PiiFinalizationValidationError(
            "The requested processing job was not found."
        )

    if job.status != "REVIEW_REQUIRED":
        raise PiiFinalizationValidationError(
            "Only jobs awaiting review can be finalized."
        )

    entities = (
        session.query(PIIEntity)
        .filter(PIIEntity.document_id == document.id)
        .order_by(PIIEntity.created_at, PIIEntity.id)
        .all()
    )

    # Validate every saved decision and box before changing job state or
    # generating output. Invalid coordinates must never be silently ignored.
    candidates = _build_final_candidates(entities)

    try:
        original_path = artifact_service.get_original_path(
            document.id,
            document.original_storage_key,
        )
    except ArtifactServiceError as exc:
        raise PiiFinalizationArtifactError(
            "The original PDF is unavailable."
        ) from exc

    try:
        with artifact_service.processing_workspace() as workspace:
            output_path = workspace / "finalized.pdf"

            try:
                # REVIEW_REQUIRED -> RUNNING is handled by the existing state machine.
                start_job(session, job_id=job_id)

                final_path = finalize_redaction(
                    original_path,
                    output_path,
                    candidates,
                )

                # An all-KEEP decision set may return the original path. Persist
                # a separate copy so the original uploaded artifact is untouched.
                if final_path.resolve() == original_path.resolve():
                    shutil.copyfile(original_path, output_path)
                    final_path = output_path

                redacted_storage_key = artifact_service.save_redacted_artifact(
                    document.id,
                    final_path,
                )
                document.redacted_storage_key = redacted_storage_key

                # Persist the artifact reference and completion state together.
                complete_job(session, job_id=job_id)

            except Exception:
                session.rollback()

                # Best effort: record failure if the job reached RUNNING.
                try:
                    current_job = get_job(session, job_id)
                    if current_job.status == "RUNNING":
                        fail_job(
                            session,
                            job_id=job_id,
                            error_code="FINALIZATION_FAILED",
                            error_message=(
                                "Final redaction or artifact persistence failed."
                            ),
                        )
                except Exception:
                    logger.exception(
                        "Could not record finalization failure for job %s.",
                        job_id,
                    )

                raise

    except PiiFinalizationValidationError:
        raise
    except (ArtifactServiceError, FinalRedactionError) as exc:
        raise PiiFinalizationArtifactError(
            "Final redaction could not be completed."
        ) from exc
    except JobServiceError as exc:
        raise PiiFinalizationError(
            "The processing job could not be finalized."
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise PiiFinalizationError(
            "The finalization database transaction failed."
        ) from exc
    except PiiFinalizationError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected finalization failure for job %s.",
            job_id,
        )
        raise PiiFinalizationError(
            "Unexpected finalization failure."
        ) from exc

    session.refresh(job)
    session.refresh(document)

    return {
        "job_id": job.id,
        "document_id": document.id,
        "status": job.status,
        "progress": job.progress,
        "redacted_storage_key": document.redacted_storage_key,
        "candidates_processed": len(candidates),
        "redacted_candidates": sum(
            candidate["action"] == "REDACT"
            for candidate in candidates
        ),
        "kept_candidates": sum(
            candidate["action"] == "KEEP"
            for candidate in candidates
        ),
    }
