from pathlib import Path

import pymupdf
import pytest

from app.final_redaction import (
    FinalRedactionError,
    build_final_redaction_boxes,
    finalize_redaction,
    verify_redacted_pdf,
)


PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "test_data"
    / "coordinate_test.pdf"
)


def extract_text(path: Path) -> str:
    document = pymupdf.open(path)

    try:
        return "\n".join(
            page.get_text("text")
            for page in document
        )
    finally:
        document.close()


def make_candidate(
    candidate_id: str,
    action: str,
    text: str = "ABCDE1234F",
    page_number: int = 1,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "entity_type": "PAN",
        "text": text,
        "confidence": 1.0,
        "source": "regex",
        "start": 0,
        "end": len(text),
        "sensitivity": "HIGH",
        "action": action,
        "reason": "Test candidate.",
        "page_number": page_number,
        "bounding_boxes": [
            (
                99.8931655883789,
                130.544921875,
                168.9390106201172,
                142.833984375,
            )
        ],
    }


def test_build_final_redaction_boxes_uses_only_redact_candidates():
    candidates = [
        make_candidate("c1", "REDACT"),
        make_candidate("c2", "KEEP"),
    ]

    page_boxes = build_final_redaction_boxes(candidates)

    assert 1 in page_boxes
    assert len(page_boxes[1]) == 1


def test_review_candidates_are_rejected():
    candidates = [
        make_candidate("c1", "REVIEW"),
    ]

    with pytest.raises(FinalRedactionError):
        build_final_redaction_boxes(candidates)


def test_keep_candidates_are_not_redacted():
    candidates = [
        make_candidate("c1", "KEEP"),
    ]

    page_boxes = build_final_redaction_boxes(candidates)

    assert page_boxes == {}


def test_invalid_action_is_rejected():
    candidates = [
        make_candidate("c1", "INVALID"),
    ]

    with pytest.raises(FinalRedactionError):
        build_final_redaction_boxes(candidates)


def test_redact_candidate_requires_coordinates():
    candidate = make_candidate("c1", "REDACT")
    candidate["bounding_boxes"] = []

    with pytest.raises(FinalRedactionError):
        build_final_redaction_boxes([candidate])


def test_verify_redacted_pdf_rejects_remaining_text(
    tmp_path,
):
    output_path = tmp_path / "copy.pdf"

    document = pymupdf.open(PDF_PATH)
    document.save(output_path)
    document.close()

    with pytest.raises(FinalRedactionError):
        verify_redacted_pdf(
            output_path,
            ["ABCDE1234F"],
        )


def test_real_pdf_is_permanently_redacted(
    tmp_path,
):
    output_path = tmp_path / "coordinate_test_final_redacted.pdf"

    candidate = make_candidate(
        "pan-1",
        "REDACT",
    )

    result = finalize_redaction(
        PDF_PATH,
        output_path,
        [candidate],
    )

    assert result == output_path
    assert output_path.exists()

    original_text = extract_text(PDF_PATH)
    redacted_text = extract_text(output_path)

    assert "ABCDE1234F" in original_text
    assert "ABCDE1234F" not in redacted_text


def test_real_pdf_is_not_modified(
    tmp_path,
):
    output_path = tmp_path / "coordinate_test_final_redacted.pdf"

    original_text = extract_text(PDF_PATH)

    candidate = make_candidate(
        "pan-1",
        "REDACT",
    )

    finalize_redaction(
        PDF_PATH,
        output_path,
        [candidate],
    )

    assert extract_text(PDF_PATH) == original_text


def test_final_redaction_requires_different_paths(
    tmp_path,
):
    with pytest.raises(FinalRedactionError):
        finalize_redaction(
            PDF_PATH,
            PDF_PATH,
            [
                make_candidate(
                    "pan-1",
                    "REDACT",
                )
            ],
        )