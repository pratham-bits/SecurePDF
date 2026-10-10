"""Celery tasks for SecurePDF background processing."""

from app.celery_app import celery_app
from app.database import SessionLocal
from app.job_processor import (
    JobProcessingError,
    RetryableJobProcessingError,
    process_storage_job,
)
from app.job_service import retry_job


MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 10


@celery_app.task(
    bind=True,
    name="securepdf.process_job",
    max_retries=MAX_RETRIES,
)
def process_job_task(
    self,
    job_id: str,
) -> dict:
    """Execute a SecurePDF processing job in a Celery worker."""

    session = SessionLocal()

    try:
        result = process_storage_job(
            session,
            job_id=job_id,
        )

        return {
            "job_id": job_id,
            "status": (
                "REVIEW_REQUIRED"
                if result["review_required"]
                else "COMPLETED"
            ),
            "review_required": result["review_required"],
        }

    except RetryableJobProcessingError as exc:
        if self.request.retries >= MAX_RETRIES:
            raise

        retry_job(
            session,
            job_id=job_id,
        )

        raise self.retry(
            exc=exc,
            countdown=RETRY_DELAY_SECONDS,
        )

    except JobProcessingError:
        raise

    finally:
        session.close()