from pathlib import Path

import pymupdf
import pytest

from app.redaction import RedactionError, redact_pdf


PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "test_data"
    / "coordinate_test.pdf"
)

OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "test_data"
    / "redaction_outputs"
)


PAN_BOX = (
    99.8931655883789,
    130.544921875,
    168.9390106201172,
    142.833984375,
)

PHONE_BOXES = [
    (
        109.89299011230469,
        145.0911865234375,
        128.54158020019531,
        157.3802490234375,
    ),
    (
        131.5928955078125,
        145.0911865234375,
        192.7288818359375,
        157.3802490234375,
    ),
]


@pytest.fixture
def output_pdf(tmp_path):
    return tmp_path / "redacted.pdf"


def extract_pdf_text(path: Path) -> str:
    document = pymupdf.open(path)

    try:
        return "\n".join(
            page.get_text("text")
            for page in document
        )
    finally:
        document.close()


def test_pan_is_permanently_redacted(output_pdf):
    original_text = extract_pdf_text(PDF_PATH)

    assert "ABCDE1234F" in original_text

    redact_pdf(
        PDF_PATH,
        output_pdf,
        {1: [PAN_BOX]},
    )

    assert output_pdf.exists()

    redacted_text = extract_pdf_text(output_pdf)

    assert "ABCDE1234F" not in redacted_text
    assert "Rahul Kumar" in redacted_text
    assert "rahul@example.com" in redacted_text


def test_phone_multiple_boxes_are_redacted(output_pdf):
    original_text = extract_pdf_text(PDF_PATH)

    assert "+91" in original_text
    assert "9876543210" in original_text

    redact_pdf(
        PDF_PATH,
        output_pdf,
        {1: PHONE_BOXES},
    )

    redacted_text = extract_pdf_text(output_pdf)

    assert "+91" not in redacted_text
    assert "9876543210" not in redacted_text

    assert "Rahul Kumar" in redacted_text
    assert "ABCDE1234F" in redacted_text


def test_original_pdf_is_not_modified(output_pdf):
    original_text_before = extract_pdf_text(PDF_PATH)

    redact_pdf(
        PDF_PATH,
        output_pdf,
        {1: [PAN_BOX]},
    )

    original_text_after = extract_pdf_text(PDF_PATH)

    assert original_text_after == original_text_before


def test_redacted_output_is_readable(output_pdf):
    redact_pdf(
        PDF_PATH,
        output_pdf,
        {1: [PAN_BOX]},
    )

    document = pymupdf.open(output_pdf)

    try:
        assert len(document) == 1
        assert document[0].rect.width > 0
        assert document[0].rect.height > 0
    finally:
        document.close()


def test_invalid_bbox_is_rejected(output_pdf):
    invalid_box = (
        100.0,
        100.0,
        50.0,
        120.0,
    )

    with pytest.raises(RedactionError):
        redact_pdf(
            PDF_PATH,
            output_pdf,
            {1: [invalid_box]},
        )


def test_invalid_page_number_is_rejected(output_pdf):
    with pytest.raises(RedactionError):
        redact_pdf(
            PDF_PATH,
            output_pdf,
            {999: [PAN_BOX]},
        )


def test_input_and_output_cannot_be_same_file():
    with pytest.raises(RedactionError):
        redact_pdf(
            PDF_PATH,
            PDF_PATH,
            {1: [PAN_BOX]},
        )