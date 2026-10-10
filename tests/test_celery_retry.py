from unittest.mock import MagicMock, patch

import pytest

from app.celery_tasks import process_job_task
from app.job_processor import (
    JobProcessingError,
    RetryableJobProcessingError,
)


def test_retryable_failure_schedules_retry():
    task = process_job_task

    fake_session = MagicMock()
    retry_error = RuntimeError("celery retry")

    with (
        patch(
            "app.celery_tasks.SessionLocal",
            return_value=fake_session,
        ),
        patch(
            "app.celery_tasks.process_storage_job",
            side_effect=RetryableJobProcessingError(
                "temporary processing failure"
            ),
        ),
        patch(
            "app.celery_tasks.retry_job",
        ) as mock_retry_job,
    ):
        task.retry = MagicMock(side_effect=retry_error)

        task.push_request(retries=0)

        try:
            with pytest.raises(
                RuntimeError,
                match="celery retry",
            ):
                task.run("job-1")

            mock_retry_job.assert_called_once_with(
                fake_session,
                job_id="job-1",
            )

            task.retry.assert_called_once()

            retry_kwargs = task.retry.call_args.kwargs

            assert retry_kwargs["countdown"] == 10
            assert isinstance(
                retry_kwargs["exc"],
                RetryableJobProcessingError,
            )

        finally:
            task.pop_request()

    fake_session.close.assert_called_once()


def test_retryable_failure_is_not_rescheduled_after_retry_limit():
    task = process_job_task

    fake_session = MagicMock()

    with (
        patch(
            "app.celery_tasks.SessionLocal",
            return_value=fake_session,
        ),
        patch(
            "app.celery_tasks.process_storage_job",
            side_effect=RetryableJobProcessingError(
                "temporary processing failure"
            ),
        ),
        patch(
            "app.celery_tasks.retry_job",
        ) as mock_retry_job,
    ):
        task.retry = MagicMock()

        task.push_request(retries=2)

        try:
            with pytest.raises(
                RetryableJobProcessingError,
                match="temporary processing failure",
            ):
                task.run("job-1")

            mock_retry_job.assert_not_called()
            task.retry.assert_not_called()

        finally:
            task.pop_request()

    fake_session.close.assert_called_once()


def test_permanent_processing_failure_is_not_retried():
    task = process_job_task

    fake_session = MagicMock()

    with (
        patch(
            "app.celery_tasks.SessionLocal",
            return_value=fake_session,
        ),
        patch(
            "app.celery_tasks.process_storage_job",
            side_effect=JobProcessingError(
                "input PDF does not exist"
            ),
        ),
        patch(
            "app.celery_tasks.retry_job",
        ) as mock_retry_job,
    ):
        task.retry = MagicMock()

        task.push_request(retries=0)

        try:
            with pytest.raises(
                JobProcessingError,
                match="input PDF does not exist",
            ):
                task.run("job-1")

            mock_retry_job.assert_not_called()
            task.retry.assert_not_called()

        finally:
            task.pop_request()

    fake_session.close.assert_called_once()


def test_successful_processing_does_not_retry():
    task = process_job_task

    fake_session = MagicMock()

    result = {
        "review_required": True,
    }

    with (
        patch(
            "app.celery_tasks.SessionLocal",
            return_value=fake_session,
        ),
        patch(
            "app.celery_tasks.process_storage_job",
            return_value=result,
        ),
        patch(
            "app.celery_tasks.retry_job",
        ) as mock_retry_job,
    ):
        task.retry = MagicMock()

        task.push_request(retries=0)

        try:
            response = task.run("job-1")

            assert response == {
                "job_id": "job-1",
                "status": "REVIEW_REQUIRED",
                "review_required": True,
            }

            mock_retry_job.assert_not_called()
            task.retry.assert_not_called()

        finally:
            task.pop_request()

    fake_session.close.assert_called_once()