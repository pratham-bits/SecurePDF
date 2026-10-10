from pathlib import Path

import pymupdf

from app.document_processor import process_mixed_pdf
from app.ocr import OCREngine


TEST_DATA = Path("backend/test_data")

DIGITAL_PDF = TEST_DATA / "coordinate_test.pdf"
SCANNED_PDF = TEST_DATA / "coordinate_test_scanned.pdf"


def _create_mixed_pdf(output_path: Path) -> None:
    """
    Create a genuine two-page mixed PDF.

    Page 1:
        Native machine-readable PDF.

    Page 2:
        Image-only scanned PDF.
    """

    digital_document = pymupdf.open(DIGITAL_PDF)

    try:
        scanned_document = pymupdf.open(SCANNED_PDF)

        try:
            scanned_page = scanned_document[0]

            scanned_pixmap = scanned_page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2)
            )

            scanned_image = scanned_pixmap.tobytes("png")

            output = pymupdf.open()

            try:
                # ---------------------------------------------------
                # Page 1: native digital PDF
                # ---------------------------------------------------

                output.insert_pdf(
                    digital_document,
                    from_page=0,
                    to_page=0,
                )

                # ---------------------------------------------------
                # Page 2: image-only scanned page
                # ---------------------------------------------------

                new_page = output.new_page(
                    width=scanned_page.rect.width,
                    height=scanned_page.rect.height,
                )

                new_page.insert_image(
                    new_page.rect,
                    stream=scanned_image,
                )

                output.save(output_path)

            finally:
                output.close()

        finally:
            scanned_document.close()

    finally:
        digital_document.close()


def test_mixed_pdf_runs_real_pii_pipeline_on_both_page_types(
    tmp_path,
):
    """
    Verify that both digital and OCR pages reach the common PII
    processing pipeline.
    """

    mixed_pdf = tmp_path / "mixed_test.pdf"
    output_pdf = tmp_path / "mixed_output.pdf"

    _create_mixed_pdf(mixed_pdf)

    ocr_engine = OCREngine()

    result = process_mixed_pdf(
        mixed_pdf,
        output_pdf,
        ocr_engine=ocr_engine,
        ocr_scale=2.0,
    )

    # ---------------------------------------------------------------
    # Document-level evidence
    # ---------------------------------------------------------------

    assert result["pages_processed"] == 2
    assert result["detected_entities"] > 0

    # ---------------------------------------------------------------
    # Candidates must exist on BOTH pages.
    # ---------------------------------------------------------------

    page_numbers = {
        candidate["page_number"]
        for candidate in result["detected_candidates"]
    }

    assert 1 in page_numbers
    assert 2 in page_numbers

    # ---------------------------------------------------------------
    # PAN should be detected on both pages.
    # ---------------------------------------------------------------

    pan_candidates = [
        candidate
        for candidate in result["detected_candidates"]
        if candidate["entity_type"] == "PAN"
    ]

    assert len(pan_candidates) >= 2

    pan_page_numbers = {
        candidate["page_number"]
        for candidate in pan_candidates
    }

    assert 1 in pan_page_numbers
    assert 2 in pan_page_numbers

    for candidate in pan_candidates:
        assert candidate["text"] == "ABCDE1234F"
        assert candidate["action"] == "REDACT"
        assert candidate["bounding_boxes"]

        for bbox in candidate["bounding_boxes"]:
            assert len(bbox) == 4
            assert bbox[2] > bbox[0]
            assert bbox[3] > bbox[1]

    # ---------------------------------------------------------------
    # Since contextual candidates can require review, the processor
    # must not generate the final PDF until review is resolved.
    # ---------------------------------------------------------------

    if result["review_required"]:
        assert result["output_path"] is None
        assert not output_pdf.exists()