from pathlib import Path
from app.final_redaction import finalize_redaction
import pymupdf
import pytest

from app.document_processor import (
    DocumentProcessingError,
    process_digital_pdf,
)
from app.pii_gliner import GLiNERPIIDetector
from app.review import apply_review_decisions


PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "test_data"
    / "coordinate_test.pdf"
)

def test_real_review_to_final_redaction_workflow(
    tmp_path,
    gliner_detector,
):
    """
    Validate the complete digital review-to-redaction workflow
    using the real coordinate test PDF.
    """

    initial_output = (
        tmp_path
        / "initial_redacted.pdf"
    )

    final_output = (
        tmp_path
        / "final_redacted.pdf"
    )

    result = process_digital_pdf(
        PDF_PATH,
        initial_output,
        gliner_detector=gliner_detector,
    )

    assert result["review_required"] is True
    assert result["output_path"] is None

    review_candidates = result["review_candidates"]

    assert review_candidates

    selected_candidate = review_candidates[0]

    # Resolve the selected REVIEW candidate.
    updated_candidates = apply_review_decisions(
        result["detected_candidates"],
        [
            {
                "candidate_id": selected_candidate["candidate_id"],
                "action": "REDACT",
            }
        ],
    )

    # Any remaining REVIEW candidates must be explicitly resolved
    # before final redaction.
    remaining_review_candidates = [
        candidate
        for candidate in updated_candidates
        if candidate["action"] == "REVIEW"
    ]

    assert remaining_review_candidates

    # For this integration test, resolve the remaining candidates
    # as KEEP to demonstrate the complete workflow.
    remaining_decisions = [
        {
            "candidate_id": candidate["candidate_id"],
            "action": "KEEP",
        }
        for candidate in remaining_review_candidates
    ]

    final_candidates = apply_review_decisions(
        updated_candidates,
        remaining_decisions,
    )

    assert all(
        candidate["action"] != "REVIEW"
        for candidate in final_candidates
    )

    final_result = finalize_redaction(
        PDF_PATH,
        final_output,
        final_candidates,
    )

    assert final_result == final_output
    assert final_output.exists()

    final_text = extract_text(final_output)

    # The selected candidate must actually disappear from the PDF.
    if selected_candidate["text"]:
        assert selected_candidate["text"] not in final_text

def extract_text(path: Path) -> str:
    """Extract all text from a PDF for verification."""

    document = pymupdf.open(path)

    try:
        return "\n".join(
            page.get_text("text")
            for page in document
        )
    finally:
        document.close()


@pytest.fixture(scope="module")
def gliner_detector():
    """Reuse one real GLiNER model instance across tests."""

    return GLiNERPIIDetector()


def test_end_to_end_digital_pdf_requires_review(
    tmp_path,
    gliner_detector,
):
    """
    Real digital PDF processing should stop before final redaction
    when unresolved REVIEW candidates exist.
    """

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    original_text = extract_text(PDF_PATH)

    assert "ABCDE1234F" in original_text

    result = process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    assert result["pages_processed"] == 1
    assert result["detected_entities"] > 0

    assert result["review_required"] is True

    assert result["redacted_entities"] > 0
    assert result["review_entities"] > 0

    assert result["output_path"] is None

    assert not output_path.exists()

    # The original PDF must remain unchanged.
    assert extract_text(PDF_PATH) == original_text


def test_processing_result_preserves_candidate_details(
    tmp_path,
    gliner_detector,
):
    """
    The initial processing stage should preserve complete structured
    candidate information for the future review UI.
    """

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    result = process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    assert len(result["detected_candidates"]) == 4
    assert len(result["redacted_candidates"]) == 1
    assert len(result["review_candidates"]) == 3

    assert result["kept_entities"] == len(
        result["kept_candidates"]
    )

    assert result["review_required"] is True

    for candidate in result["detected_candidates"]:
        assert candidate["candidate_id"]

        assert candidate["entity_type"]
        assert candidate["text"]

        assert 0.0 <= candidate["confidence"] <= 1.0

        assert candidate["source"]

        assert candidate["start"] >= 0
        assert candidate["end"] > candidate["start"]

        assert candidate["sensitivity"]

        assert candidate["action"] in {
            "REDACT",
            "REVIEW",
            "KEEP",
        }

        assert candidate["reason"]

        assert candidate["page_number"] == 1

        assert candidate["bounding_boxes"]


def test_candidate_ids_are_unique(
    tmp_path,
    gliner_detector,
):
    """Every detected candidate must receive a unique review ID."""

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    result = process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    candidate_ids = [
        candidate["candidate_id"]
        for candidate in result["detected_candidates"]
    ]

    assert len(candidate_ids) == len(set(candidate_ids))


def test_only_redact_candidates_are_approved_automatically(
    tmp_path,
    gliner_detector,
):
    """
    Only candidates whose policy action is REDACT should appear
    in the automatic redaction candidate collection.
    """

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    result = process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    assert all(
        candidate["action"] == "REDACT"
        for candidate in result["redacted_candidates"]
    )

    assert all(
        candidate["action"] == "REVIEW"
        for candidate in result["review_candidates"]
    )

    assert all(
        candidate["action"] != "REDACT"
        for candidate in result["review_candidates"]
    )


def test_review_decision_can_resolve_real_candidate(
    tmp_path,
    gliner_detector,
):
    """
    A real REVIEW candidate produced by the document processor can
    be resolved through the review decision layer.
    """

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    result = process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    assert result["review_required"] is True
    assert result["review_candidates"]

    review_candidate = result["review_candidates"][0]

    updated_candidates = apply_review_decisions(
        result["detected_candidates"],
        [
            {
                "candidate_id": review_candidate["candidate_id"],
                "action": "REDACT",
            }
        ],
    )

    updated_candidate = next(
        candidate
        for candidate in updated_candidates
        if candidate["candidate_id"]
        == review_candidate["candidate_id"]
    )

    assert updated_candidate["action"] == "REDACT"


def test_review_decision_can_keep_real_candidate(
    tmp_path,
    gliner_detector,
):
    """
    A real REVIEW candidate can also be explicitly kept.
    """

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    result = process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    assert result["review_required"] is True
    assert result["review_candidates"]

    review_candidate = result["review_candidates"][0]

    updated_candidates = apply_review_decisions(
        result["detected_candidates"],
        [
            {
                "candidate_id": review_candidate["candidate_id"],
                "action": "KEEP",
            }
        ],
    )

    updated_candidate = next(
        candidate
        for candidate in updated_candidates
        if candidate["candidate_id"]
        == review_candidate["candidate_id"]
    )

    assert updated_candidate["action"] == "KEEP"


def test_missing_input_is_rejected(
    tmp_path,
    gliner_detector,
):
    """Missing input PDFs must still be rejected."""

    missing_pdf = tmp_path / "missing.pdf"
    output_path = tmp_path / "output.pdf"

    with pytest.raises(DocumentProcessingError):
        process_digital_pdf(
            missing_pdf,
            output_path,
            gliner_detector=gliner_detector,
        )


def test_review_processing_does_not_modify_input(
    tmp_path,
    gliner_detector,
):
    """
    Initial processing must never modify the source PDF, even when
    automatic REDACT candidates exist.
    """

    output_path = tmp_path / "coordinate_test_redacted.pdf"

    original_text = extract_text(PDF_PATH)

    process_digital_pdf(
        PDF_PATH,
        output_path,
        gliner_detector=gliner_detector,
    )

    assert extract_text(PDF_PATH) == original_text