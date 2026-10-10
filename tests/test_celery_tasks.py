from unittest.mock import MagicMock, patch

import pytest

from app.celery_app import celery_app
from app.celery_tasks import process_job_task
from app.job_processor import JobProcessingError


def test_celery_app_is_configured():
    assert celery_app.main == "securepdf"


def test_process_job_task_has_expected_name():
    assert process_job_task.name == "securepdf.process_job"


@patch("app.celery_tasks.SessionLocal")
@patch("app.celery_tasks.process_storage_job")
def test_process_job_task_delegates_to_process_storage_job(
    mock_process_storage_job,
    mock_session_local,
):
    session = MagicMock()
    mock_session_local.return_value = session

    mock_process_storage_job.return_value = {
        "review_required": False,
    }

    result = process_job_task.run("job-123")

    mock_process_storage_job.assert_called_once_with(
        session,
        job_id="job-123",
    )

    assert result == {
        "job_id": "job-123",
        "status": "COMPLETED",
        "review_required": False,
    }

    session.close.assert_called_once()


@patch("app.celery_tasks.SessionLocal")
@patch("app.celery_tasks.process_storage_job")
def test_process_job_task_reports_review_required(
    mock_process_storage_job,
    mock_session_local,
):
    session = MagicMock()
    mock_session_local.return_value = session

    mock_process_storage_job.return_value = {
        "review_required": True,
    }

    result = process_job_task.run("job-456")

    mock_process_storage_job.assert_called_once_with(
        session,
        job_id="job-456",
    )

    assert result == {
        "job_id": "job-456",
        "status": "REVIEW_REQUIRED",
        "review_required": True,
    }

    session.close.assert_called_once()


@patch("app.celery_tasks.SessionLocal")
@patch("app.celery_tasks.process_storage_job")
def test_process_job_task_propagates_processing_error(
    mock_process_storage_job,
    mock_session_local,
):
    session = MagicMock()
    mock_session_local.return_value = session

    mock_process_storage_job.side_effect = JobProcessingError(
        "Processing failed."
    )

    with pytest.raises(
        JobProcessingError,
        match="Processing failed.",
    ):
        process_job_task.run("job-789")

    mock_process_storage_job.assert_called_once_with(
        session,
        job_id="job-789",
    )

    session.close.assert_called_once()