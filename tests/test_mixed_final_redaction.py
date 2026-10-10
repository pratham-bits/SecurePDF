from pathlib import Path

import pymupdf

from app.document_processor import process_mixed_pdf
from app.final_redaction import finalize_redaction
from app.ocr import OCREngine
from app.review import apply_review_decisions


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
                output.insert_pdf(
                    digital_document,
                    from_page=0,
                    to_page=0,
                )

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


def _render_region_mean(
    pdf_path: Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
    *,
    scale: float = 2.0,
) -> float:
    """
    Calculate mean pixel intensity inside a PDF-coordinate region.
    """

    document = pymupdf.open(pdf_path)

    try:
        page = document[page_number - 1]

        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale)
        )

        samples = pixmap.samples
        width = pixmap.width
        height = pixmap.height
        channels = pixmap.n

        x0, y0, x1, y1 = bbox

        px0 = max(0, int(x0 * scale))
        py0 = max(0, int(y0 * scale))
        px1 = min(width, int(x1 * scale))
        py1 = min(height, int(y1 * scale))

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
                "No pixels found inside verification region."
            )

        return sum(values) / len(values)

    finally:
        document.close()


def test_mixed_pdf_final_redaction_verifies_digital_and_scanned_pages(
    tmp_path,
):
    """
    Full mixed-PDF final redaction acceptance test.

    Digital page:
        PAN is permanently removed from the PDF text layer.

    Scanned page:
        PAN region is permanently covered in the rendered image.
    """

    mixed_pdf = tmp_path / "mixed_input.pdf"
    output_pdf = tmp_path / "mixed_redacted.pdf"

    _create_mixed_pdf(mixed_pdf)

    ocr_engine = OCREngine()

    result = process_mixed_pdf(
        mixed_pdf,
        output_pdf,
        ocr_engine=ocr_engine,
        ocr_scale=2.0,
    )

    assert result["pages_processed"] == 2
    assert result["detected_entities"] > 0

    # ---------------------------------------------------------------
    # Find PAN candidates on both page types.
    # ---------------------------------------------------------------

    pan_candidates = [
        candidate
        for candidate in result["detected_candidates"]
        if candidate["entity_type"] == "PAN"
    ]

    assert len(pan_candidates) >= 2

    pan_by_page = {
        candidate["page_number"]: candidate
        for candidate in pan_candidates
    }

    assert 1 in pan_by_page
    assert 2 in pan_by_page

    digital_pan = pan_by_page[1]
    scanned_pan = pan_by_page[2]

    assert digital_pan["text"] == "ABCDE1234F"
    assert scanned_pan["text"] == "ABCDE1234F"

    assert digital_pan["action"] == "REDACT"
    assert scanned_pan["action"] == "REDACT"

    assert digital_pan["bounding_boxes"]
    assert scanned_pan["bounding_boxes"]

    digital_bbox = digital_pan["bounding_boxes"][0]
    scanned_bbox = scanned_pan["bounding_boxes"][0]

    # ---------------------------------------------------------------
    # Resolve every REVIEW candidate explicitly.
    #
    # PAN candidates retain their automatic REDACT decision.
    # Contextual candidates are explicitly kept for this test.
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

    final_output = finalize_redaction(
        mixed_pdf,
        output_pdf,
        updated_candidates,
    )

    assert final_output == output_pdf
    assert output_pdf.exists()
    assert output_pdf.is_file()

    # ---------------------------------------------------------------
    # DIGITAL PAGE VERIFICATION
    #
    # The digital page has a real text layer. Permanent redaction
    # must remove the original PAN text.
    # ---------------------------------------------------------------

    document = pymupdf.open(output_pdf)

    try:
        digital_text = document[0].get_text("text")

        assert "ABCDE1234F" not in digital_text

    finally:
        document.close()

    # ---------------------------------------------------------------
    # SCANNED PAGE VERIFICATION
    #
    # The scanned page has no text layer, so verify the rendered
    # pixels instead.
    # ---------------------------------------------------------------

    original_mean = _render_region_mean(
        mixed_pdf,
        page_number=2,
        bbox=scanned_bbox,
    )

    redacted_mean = _render_region_mean(
        output_pdf,
        page_number=2,
        bbox=scanned_bbox,
    )

    assert redacted_mean < original_mean * 0.35

    # ---------------------------------------------------------------
    # INPUT MUST REMAIN UNCHANGED
    # ---------------------------------------------------------------

    original_document = pymupdf.open(mixed_pdf)

    try:
        original_digital_text = (
            original_document[0].get_text("text")
        )

        assert "ABCDE1234F" in original_digital_text

    finally:
        original_document.close()