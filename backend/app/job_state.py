from typing import Final, Literal


JobStatus = Literal[
    "PENDING",
    "RUNNING",
    "REVIEW_REQUIRED",
    "COMPLETED",
    "FAILED",
    "RETRYING",
]


PENDING: Final = "PENDING"
RUNNING: Final = "RUNNING"
REVIEW_REQUIRED: Final = "REVIEW_REQUIRED"
COMPLETED: Final = "COMPLETED"
FAILED: Final = "FAILED"
RETRYING: Final = "RETRYING"


ALL_JOB_STATUSES: Final[frozenset[str]] = frozenset(
    {
        PENDING,
        RUNNING,
        REVIEW_REQUIRED,
        COMPLETED,
        FAILED,
        RETRYING,
    }
)


class JobStateError(Exception):
    """Raised when an invalid processing-job state transition occurs."""


# Explicit state-transition table.
#
# Keeping this centralized prevents different parts of the application
# from inventing their own job lifecycle rules.
_ALLOWED_TRANSITIONS: Final[
    dict[str, frozenset[str]]
] = {
    PENDING: frozenset(
        {
            RUNNING,
            FAILED,
        }
    ),
    RUNNING: frozenset(
        {
            REVIEW_REQUIRED,
            COMPLETED,
            FAILED,
        }
    ),
    REVIEW_REQUIRED: frozenset(
        {
            RUNNING,
            FAILED,
        }
    ),
    FAILED: frozenset(
        {
            RETRYING,
        }
    ),
    RETRYING: frozenset(
        {
            RUNNING,
            FAILED,
        }
    ),
    COMPLETED: frozenset(),
}


def validate_job_status(
    status: str,
) -> JobStatus:
    """Validate and return a supported job status."""

    if status not in ALL_JOB_STATUSES:
        raise JobStateError(
            f"Unsupported processing job status: {status!r}."
        )

    return status  # type: ignore[return-value]


def can_transition(
    current_status: str,
    next_status: str,
) -> bool:
    """
    Return whether a processing job may transition between two states.
    """

    validate_job_status(current_status)
    validate_job_status(next_status)

    return next_status in _ALLOWED_TRANSITIONS[current_status]


def transition_job_status(
    current_status: str,
    next_status: str,
) -> JobStatus:
    """
    Validate and perform a processing-job state transition.

    The function is intentionally side-effect free. Database persistence
    will be handled by the processing-job service in the next task.
    """

    validate_job_status(current_status)
    validate_job_status(next_status)

    if not can_transition(
        current_status,
        next_status,
    ):
        raise JobStateError(
            f"Invalid processing job transition: "
            f"{current_status} -> {next_status}."
        )

    return next_status  # type: ignore[return-value]