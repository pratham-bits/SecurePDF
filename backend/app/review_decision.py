from typing import Literal, TypedDict


ReviewAction = Literal["REDACT", "KEEP"]


class ReviewDecisionError(Exception):
    """Raised when a review decision is invalid."""


class ReviewDecision(TypedDict):
    candidate_id: str
    action: ReviewAction


def validate_review_action(action: str) -> ReviewAction:
    """Validate and normalize a user-provided review action."""

    if action not in {"REDACT", "KEEP"}:
        raise ReviewDecisionError(
            "Review action must be REDACT or KEEP."
        )

    return action  # type: ignore[return-value]