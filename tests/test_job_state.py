import pytest

from app.job_state import (
    COMPLETED,
    FAILED,
    JobStateError,
    PENDING,
    REVIEW_REQUIRED,
    RETRYING,
    RUNNING,
    can_transition,
    transition_job_status,
    validate_job_status,
)


def test_all_supported_statuses_are_valid():
    statuses = [
        PENDING,
        RUNNING,
        REVIEW_REQUIRED,
        COMPLETED,
        FAILED,
        RETRYING,
    ]

    for status in statuses:
        assert validate_job_status(status) == status


def test_pending_can_start():
    assert can_transition(
        PENDING,
        RUNNING,
    )

    assert transition_job_status(
        PENDING,
        RUNNING,
    ) == RUNNING


def test_running_can_require_review():
    assert can_transition(
        RUNNING,
        REVIEW_REQUIRED,
    )

    assert transition_job_status(
        RUNNING,
        REVIEW_REQUIRED,
    ) == REVIEW_REQUIRED


def test_review_can_resume_processing():
    assert can_transition(
        REVIEW_REQUIRED,
        RUNNING,
    )

    assert transition_job_status(
        REVIEW_REQUIRED,
        RUNNING,
    ) == RUNNING


def test_running_can_complete():
    assert can_transition(
        RUNNING,
        COMPLETED,
    )

    assert transition_job_status(
        RUNNING,
        COMPLETED,
    ) == COMPLETED


def test_running_can_fail():
    assert can_transition(
        RUNNING,
        FAILED,
    )

    assert transition_job_status(
        RUNNING,
        FAILED,
    ) == FAILED


def test_failed_can_retry():
    assert can_transition(
        FAILED,
        RETRYING,
    )

    assert transition_job_status(
        FAILED,
        RETRYING,
    ) == RETRYING


def test_retrying_can_run_again():
    assert can_transition(
        RETRYING,
        RUNNING,
    )

    assert transition_job_status(
        RETRYING,
        RUNNING,
    ) == RUNNING


def test_retrying_can_fail_again():
    assert can_transition(
        RETRYING,
        FAILED,
    )


@pytest.mark.parametrize(
    "current_status,next_status",
    [
        (PENDING, COMPLETED),
        (PENDING, REVIEW_REQUIRED),
        (COMPLETED, RUNNING),
        (COMPLETED, FAILED),
        (COMPLETED, RETRYING),
        (FAILED, COMPLETED),
        (FAILED, RUNNING),
        (REVIEW_REQUIRED, COMPLETED),
        (REVIEW_REQUIRED, RETRYING),
    ],
)
def test_invalid_transitions_are_rejected(
    current_status,
    next_status,
):
    assert not can_transition(
        current_status,
        next_status,
    )

    with pytest.raises(JobStateError):
        transition_job_status(
            current_status,
            next_status,
        )


def test_invalid_status_is_rejected():
    with pytest.raises(JobStateError):
        validate_job_status("UNKNOWN")


def test_invalid_next_status_is_rejected():
    with pytest.raises(JobStateError):
        transition_job_status(
            PENDING,
            "UNKNOWN",
        )


def test_completed_is_terminal():
    assert not can_transition(
        COMPLETED,
        COMPLETED,
    )

    with pytest.raises(JobStateError):
        transition_job_status(
            COMPLETED,
            COMPLETED,
        )