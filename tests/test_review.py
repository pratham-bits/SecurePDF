import pytest

from app.review import apply_review_decisions
from app.review_decision import ReviewDecisionError


def make_candidate(
    candidate_id: str,
    action: str,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "entity_type": "EMAIL",
        "text": "rahul@example.com",
        "confidence": 0.90,
        "source": "regex",
        "start": 0,
        "end": 18,
        "sensitivity": "CONTEXTUAL",
        "action": action,
        "reason": "Context requires review.",
        "page_number": 1,
        "bounding_boxes": [
            (72.0, 100.0, 150.0, 112.0)
        ],
    }


def test_review_candidate_can_be_redacted():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "REDACT",
        }
    ]

    result = apply_review_decisions(candidates, decisions)

    assert result[0]["action"] == "REDACT"
    assert result[0]["candidate_id"] == "c1"


def test_review_candidate_can_be_kept():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "KEEP",
        }
    ]

    result = apply_review_decisions(candidates, decisions)

    assert result[0]["action"] == "KEEP"


def test_invalid_review_action_is_rejected():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "DELETE",
        }
    ]

    with pytest.raises(ReviewDecisionError):
        apply_review_decisions(candidates, decisions)


def test_unknown_candidate_id_is_rejected():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    decisions = [
        {
            "candidate_id": "unknown",
            "action": "REDACT",
        }
    ]

    with pytest.raises(ReviewDecisionError):
        apply_review_decisions(candidates, decisions)


def test_automatic_redact_cannot_be_overridden():
    candidates = [
        make_candidate("c1", "REDACT"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "KEEP",
        }
    ]

    with pytest.raises(ReviewDecisionError):
        apply_review_decisions(candidates, decisions)


def test_automatic_keep_cannot_be_overridden():
    candidates = [
        make_candidate("c1", "KEEP"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "REDACT",
        }
    ]

    with pytest.raises(ReviewDecisionError):
        apply_review_decisions(candidates, decisions)


def test_multiple_review_decisions_are_applied():
    candidates = [
        make_candidate("c1", "REVIEW"),
        make_candidate("c2", "REVIEW"),
        make_candidate("c3", "KEEP"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "REDACT",
        },
        {
            "candidate_id": "c2",
            "action": "KEEP",
        },
    ]

    result = apply_review_decisions(candidates, decisions)

    result_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in result
    }

    assert result_by_id["c1"]["action"] == "REDACT"
    assert result_by_id["c2"]["action"] == "KEEP"
    assert result_by_id["c3"]["action"] == "KEEP"


def test_duplicate_review_decision_is_rejected():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "REDACT",
        },
        {
            "candidate_id": "c1",
            "action": "KEEP",
        },
    ]

    with pytest.raises(ReviewDecisionError):
        apply_review_decisions(candidates, decisions)


def test_original_candidates_are_not_mutated():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    decisions = [
        {
            "candidate_id": "c1",
            "action": "REDACT",
        }
    ]

    result = apply_review_decisions(candidates, decisions)

    assert candidates[0]["action"] == "REVIEW"
    assert result[0]["action"] == "REDACT"