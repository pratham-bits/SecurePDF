from copy import deepcopy
from typing import Iterable

from app.document_processor import ProcessedCandidate
from app.review_decision import (
    ReviewDecision,
    ReviewDecisionError,
    validate_review_action,
)


def apply_review_decisions(
    candidates: Iterable[ProcessedCandidate],
    decisions: Iterable[ReviewDecision],
) -> list[ProcessedCandidate]:
    """
    Apply user review decisions to candidates currently marked REVIEW.

    Only REVIEW candidates may be changed.

    Automatic REDACT and KEEP decisions are immutable through
    the review mechanism.
    """

    candidate_list = list(candidates)

    candidate_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in candidate_list
    }

    decision_list = list(decisions)

    seen_ids: set[str] = set()

    for decision in decision_list:
        candidate_id = decision.get("candidate_id")

        if not candidate_id:
            raise ReviewDecisionError(
                "Review decision must contain candidate_id."
            )

        if candidate_id in seen_ids:
            raise ReviewDecisionError(
                f"Duplicate review decision for candidate: {candidate_id}"
            )

        seen_ids.add(candidate_id)

        if candidate_id not in candidate_by_id:
            raise ReviewDecisionError(
                f"Unknown candidate ID: {candidate_id}"
            )

        validate_review_action(decision.get("action"))

    updated_candidates = deepcopy(candidate_list)

    updated_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in updated_candidates
    }

    for decision in decision_list:
        candidate = updated_by_id[decision["candidate_id"]]

        if candidate["action"] != "REVIEW":
            raise ReviewDecisionError(
                "Only candidates with action REVIEW can receive "
                "a user review decision."
            )

        candidate["action"] = validate_review_action(
            decision["action"]
        )

        candidate["reason"] = (
            f"User review decision: {candidate['action']}"
        )

    return updated_candidates