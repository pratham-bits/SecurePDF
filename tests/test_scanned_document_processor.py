from pathlib import Path

import pymupdf

from app.document_processor import process_scanned_pdf
from app.final_redaction import finalize_redaction
from app.ocr import OCREngine
from app.review import apply_review_decisions


TEST_DATA = Path("backend/test_data")

INPUT_PDF = TEST_DATA / "coordinate_test_scanned.pdf"


def _render_region_mean(
    pdf_path: Path,
    bbox: tuple[float, float, float, float],
) -> float:
    """
    Calculate the mean pixel intensity inside a PDF-coordinate region.

    The PDF is rendered at 2x so that the PDF coordinates can be mapped
    back to the rendered image coordinates using the same scale.
    """

    document = pymupdf.open(pdf_path)

    try:
        page = document[0]

        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2)
        )

        samples = pixmap.samples
        width = pixmap.width
        height = pixmap.height
        channels = pixmap.n

        x0, y0, x1, y1 = bbox

        px0 = max(0, int(x0 * 2))
        py0 = max(0, int(y0 * 2))
        px1 = min(width, int(x1 * 2))
        py1 = min(height, int(y1 * 2))

        values: list[int] = []

        for y in range(py0, py1):
            for x in range(px0, px1):
                offset = (y * width + x) * channels

                pixel = samples[
                    offset : offset + min(3, channels)
                ]

                values.extend(pixel)

        if not values:
            raise AssertionError(
                "No pixels were found inside the verification region."
            )

        return sum(values) / len(values)

    finally:
        document.close()


def test_scanned_pdf_full_e2e_with_real_ocr_and_pii_pipeline(
    tmp_path,
):
    """
    Full scanned-PDF E2E acceptance test.

    Evidence path:

    scanned PDF
        -> real PaddleOCR
        -> positioned OCR
        -> Regex/Rules + real GLiNER
        -> candidate resolution
        -> redaction policy
        -> OCR-to-PDF coordinate transformation
        -> review decision
        -> permanent PDF redaction
        -> pixel-level verification
    """

    assert INPUT_PDF.exists()
    assert INPUT_PDF.is_file()

    output_pdf = tmp_path / "scanned_redacted.pdf"

    # Reuse one OCR engine instance across the document.
    ocr_engine = OCREngine()

    result = process_scanned_pdf(
        INPUT_PDF,
        output_pdf,
        ocr_engine=ocr_engine,
        ocr_scale=2.0,
    )

    # ---------------------------------------------------------------
    # Basic processing evidence
    # ---------------------------------------------------------------

    assert result["pages_processed"] == 1
    assert result["detected_entities"] > 0

    # ---------------------------------------------------------------
    # Locate the real PAN candidate.
    #
    # PAN is detected by the real Regex/Rules engine and should be
    # classified as HIGH sensitivity -> REDACT.
    # ---------------------------------------------------------------

    pan_candidates = [
        candidate
        for candidate in result["detected_candidates"]
        if candidate["entity_type"] == "PAN"
    ]

    assert pan_candidates

    pan_candidate = pan_candidates[0]

    assert pan_candidate["text"] == "ABCDE1234F"
    assert pan_candidate["action"] == "REDACT"
    assert pan_candidate["page_number"] == 1
    assert pan_candidate["bounding_boxes"]

    pan_bbox = pan_candidate["bounding_boxes"][0]

    assert len(pan_bbox) == 4

    x0, y0, x1, y1 = pan_bbox

    assert x1 > x0
    assert y1 > y0

    # ---------------------------------------------------------------
    # Resolve contextual REVIEW candidates.
    #
    # This represents explicit user review decisions.
    # The test keeps contextual candidates and preserves the automatic
    # PAN REDACT decision.
    # ---------------------------------------------------------------

    review_decisions = [
        {
            "candidate_id": candidate["candidate_id"],
            "action": "KEEP",
        }
        for candidate in result["review_candidates"]
    ]

    updated_candidates = apply_review_decisions(
        result["detected_candidates"],
        review_decisions,
    )

    assert all(
        candidate["action"] != "REVIEW"
        for candidate in updated_candidates
    )

    # ---------------------------------------------------------------
    # Final permanent redaction.
    # ---------------------------------------------------------------

    finalize_result = finalize_redaction(
        INPUT_PDF,
        output_pdf,
        updated_candidates,
    )

    assert finalize_result == output_pdf
    assert output_pdf.exists()
    assert output_pdf.is_file()

    # ---------------------------------------------------------------
    # Verify the scanned redaction at pixel level.
    #
    # Image-only PDFs have no text layer, so text extraction cannot
    # prove that the redaction happened. Pixel-level evidence is
    # therefore required.
    # ---------------------------------------------------------------

    original_mean = _render_region_mean(
        INPUT_PDF,
        pan_bbox,
    )

    redacted_mean = _render_region_mean(
        output_pdf,
        pan_bbox,
    )

    assert redacted_mean < original_mean * 0.35