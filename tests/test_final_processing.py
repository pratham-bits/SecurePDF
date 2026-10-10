import pytest

from app.final_processing import (
    FinalProcessingError,
    categorize_final_candidates,
    finalize_processing_candidates,
)


def make_candidate(candidate_id: str, action: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "entity_type": "EMAIL",
        "text": "test@example.com",
        "confidence": 0.95,
        "source": "regex",
        "start": 0,
        "end": 16,
        "sensitivity": "CONTEXTUAL",
        "action": action,
        "reason": "Test candidate.",
        "page_number": 1,
        "bounding_boxes": [
            (72.0, 100.0, 150.0, 112.0)
        ],
    }


def test_candidates_are_categorized():
    candidates = [
        make_candidate("c1", "REDACT"),
        make_candidate("c2", "REVIEW"),
        make_candidate("c3", "KEEP"),
    ]

    redacted, review, kept = categorize_final_candidates(candidates)

    assert [c["candidate_id"] for c in redacted] == ["c1"]
    assert [c["candidate_id"] for c in review] == ["c2"]
    assert [c["candidate_id"] for c in kept] == ["c3"]


def test_review_required_when_review_candidates_exist():
    candidates = [
        make_candidate("c1", "REDACT"),
        make_candidate("c2", "REVIEW"),
    ]

    result = finalize_processing_candidates(candidates)

    assert result["review_required"] is True
    assert len(result["review_candidates"]) == 1
    assert len(result["redaction_candidates"]) == 1


def test_no_review_required_when_all_candidates_are_final():
    candidates = [
        make_candidate("c1", "REDACT"),
        make_candidate("c2", "KEEP"),
    ]

    result = finalize_processing_candidates(candidates)

    assert result["review_required"] is False
    assert len(result["review_candidates"]) == 0


def test_all_keep_is_valid():
    candidates = [
        make_candidate("c1", "KEEP"),
        make_candidate("c2", "KEEP"),
    ]

    result = finalize_processing_candidates(candidates)

    assert result["review_required"] is False
    assert len(result["redaction_candidates"]) == 0
    assert len(result["kept_candidates"]) == 2


def test_all_review_requires_user_action():
    candidates = [
        make_candidate("c1", "REVIEW"),
        make_candidate("c2", "REVIEW"),
    ]

    result = finalize_processing_candidates(candidates)

    assert result["review_required"] is True
    assert len(result["review_candidates"]) == 2


def test_invalid_final_action_is_rejected():
    candidates = [
        make_candidate("c1", "INVALID"),
    ]

    with pytest.raises(FinalProcessingError):
        categorize_final_candidates(candidates)


def test_empty_candidate_list_is_valid():
    result = finalize_processing_candidates([])

    assert result["review_required"] is False
    assert result["redaction_candidates"] == []
    assert result["review_candidates"] == []
    assert result["kept_candidates"] == []