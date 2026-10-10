from pathlib import Path

import pymupdf
import pytest

from app.ocr import OCREngine
from app.ocr_coordinate_mapping import map_candidate_to_ocr_bboxes
from app.ocr_positioned import extract_positioned_ocr_from_pdf
from app.scanned_redaction import (
    ScannedRedactionError,
    build_scanned_redaction_boxes,
    redact_scanned_pdf,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_PDF = (
    PROJECT_ROOT
    / "backend"
    / "test_data"
    / "coordinate_test.pdf"
)

SCANNED_PDF = (
    PROJECT_ROOT
    / "backend"
    / "test_data"
    / "coordinate_test_scanned.pdf"
)


def _create_scanned_pdf() -> Path:
    """
    Create a genuine image-only PDF from the digital coordinate test PDF.
    """

    SCANNED_PDF.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with pymupdf.open(SOURCE_PDF) as source_document:
        with pymupdf.open() as scanned_document:

            for source_page in source_document:

                pixmap = source_page.get_pixmap(
                    matrix=pymupdf.Matrix(2.0, 2.0)
                )

                page = scanned_document.new_page(
                    width=source_page.rect.width,
                    height=source_page.rect.height,
                )

                page.insert_image(
                    page.rect,
                    pixmap=pixmap,
                )

            scanned_document.save(
                SCANNED_PDF
            )

    return SCANNED_PDF


@pytest.fixture(scope="module")
def scanned_pdf():
    return _create_scanned_pdf()


@pytest.fixture(scope="module")
def positioned_pages(scanned_pdf):
    ocr_engine = OCREngine()

    return extract_positioned_ocr_from_pdf(
        scanned_pdf,
        ocr_engine=ocr_engine,
        scale=2.0,
    )


def test_scanned_source_has_no_native_text(scanned_pdf):
    with pymupdf.open(scanned_pdf) as document:
        extracted = "".join(
            page.get_text("text")
            for page in document
        )

    assert extracted.strip() == ""


def test_real_ocr_contains_known_pii(positioned_pages):
    page = positioned_pages[0]

    assert "rahul@example.com" in page["text"]
    assert "ABCDE1234F" in page["text"]
    assert "9876543210" in page["text"]


def test_candidate_maps_to_real_ocr_bbox(positioned_pages):
    page = positioned_pages[0]

    text = page["text"]

    start = text.index("ABCDE1234F")
    end = start + len("ABCDE1234F")

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": start,
        "end": end,
    }

    boxes = map_candidate_to_ocr_bboxes(
        candidate,
        page,
    )

    assert boxes
    assert all(
        len(box) == 4
        for box in boxes
    )


def test_real_ocr_bbox_transforms_to_pdf_coordinates(
    positioned_pages,
):
    page = positioned_pages[0]

    text = page["text"]

    start = text.index("ABCDE1234F")
    end = start + len("ABCDE1234F")

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": start,
        "end": end,
    }

    boxes = build_scanned_redaction_boxes(
        candidate,
        page,
        scale_x=2.0,
        scale_y=2.0,
    )

    assert boxes

    for x0, y0, x1, y1 in boxes:
        assert x0 >= 0
        assert y0 >= 0
        assert x1 > x0
        assert y1 > y0


def test_real_scanned_pdf_pan_is_redacted(
    scanned_pdf,
    positioned_pages,
    tmp_path,
):
    page = positioned_pages[0]

    text = page["text"]

    start = text.index("ABCDE1234F")
    end = start + len("ABCDE1234F")

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": start,
        "end": end,
    }

    output = (
        tmp_path
        / "scanned_redacted.pdf"
    )

    redact_scanned_pdf(
        scanned_pdf,
        output,
        [
            (
                1,
                candidate,
                page,
            ),
        ],
        scale_x=2.0,
        scale_y=2.0,
    )

    assert output.exists()
    assert output.is_file()

    with pymupdf.open(output) as document:

        assert document.page_count == 1

        extracted = "".join(
            page.get_text("text")
            for page in document
        )

    # The document is still image-only.
    assert extracted.strip() == ""


def test_original_scanned_pdf_is_unchanged(
    scanned_pdf,
    positioned_pages,
    tmp_path,
):
    before = scanned_pdf.read_bytes()

    page = positioned_pages[0]

    text = page["text"]

    start = text.index("ABCDE1234F")
    end = start + len("ABCDE1234F")

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": start,
        "end": end,
    }

    output = (
        tmp_path
        / "scanned_redacted.pdf"
    )

    redact_scanned_pdf(
        scanned_pdf,
        output,
        [
            (
                1,
                candidate,
                page,
            ),
        ],
        scale_x=2.0,
        scale_y=2.0,
    )

    after = scanned_pdf.read_bytes()

    assert before == after


def test_missing_input_is_rejected(tmp_path):
    with pytest.raises(
        ScannedRedactionError
    ):
        redact_scanned_pdf(
            tmp_path / "missing.pdf",
            tmp_path / "output.pdf",
            [],
        )


def test_same_input_and_output_is_rejected(
    scanned_pdf,
    positioned_pages,
):
    page = positioned_pages[0]

    text = page["text"]

    start = text.index("ABCDE1234F")
    end = start + len("ABCDE1234F")

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": start,
        "end": end,
    }

    with pytest.raises(
        ScannedRedactionError
    ):
        redact_scanned_pdf(
            scanned_pdf,
            scanned_pdf,
            [
                (
                    1,
                    candidate,
                    page,
                ),
            ],
        )


def test_real_scanned_pdf_redaction_changes_pan_pixels(
    scanned_pdf,
    positioned_pages,
    tmp_path,
):
    """
    Verify the scanned-PDF redaction visually at the pixel level.

    The source PDF is image-only, so text extraction cannot prove that
    redaction occurred. This test renders the original and redacted PDFs
    and compares the actual pixels inside the transformed PAN bbox.
    """

    page = positioned_pages[0]

    text = page["text"]

    start = text.index("ABCDE1234F")
    end = start + len("ABCDE1234F")

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": start,
        "end": end,
    }

    output = (
        tmp_path
        / "scanned_redacted_visual.pdf"
    )

    redact_scanned_pdf(
        scanned_pdf,
        output,
        [
            (
                1,
                candidate,
                page,
            ),
        ],
        scale_x=2.0,
        scale_y=2.0,
    )

    ocr_bbox = build_scanned_redaction_boxes(
        candidate,
        page,
        scale_x=2.0,
        scale_y=2.0,
    )[0]

    with pymupdf.open(scanned_pdf) as original_document:
        original_page = original_document[0]

        original_pixmap = original_page.get_pixmap(
            matrix=pymupdf.Matrix(2.0, 2.0),
            alpha=False,
        )

    with pymupdf.open(output) as redacted_document:
        redacted_page = redacted_document[0]

        redacted_pixmap = redacted_page.get_pixmap(
            matrix=pymupdf.Matrix(2.0, 2.0),
            alpha=False,
        )

    # Convert PDF coordinates back into the 2x rendered pixel coordinates.
    x0, y0, x1, y1 = ocr_bbox

    pixel_x0 = max(0, int(x0 * 2.0))
    pixel_y0 = max(0, int(y0 * 2.0))
    pixel_x1 = min(
        original_pixmap.width,
        int(x1 * 2.0),
    )
    pixel_y1 = min(
        original_pixmap.height,
        int(y1 * 2.0),
    )

    assert pixel_x1 > pixel_x0
    assert pixel_y1 > pixel_y0

    original_samples = []
    redacted_samples = []

    original_stride = original_pixmap.stride
    redacted_stride = redacted_pixmap.stride

    original_channels = original_pixmap.n
    redacted_channels = redacted_pixmap.n

    original_samples_data = original_pixmap.samples
    redacted_samples_data = redacted_pixmap.samples

    for y in range(pixel_y0, pixel_y1):
        original_row_start = y * original_stride
        redacted_row_start = y * redacted_stride

        for x in range(pixel_x0, pixel_x1):
            original_offset = (
                original_row_start
                + x * original_channels
            )

            redacted_offset = (
                redacted_row_start
                + x * redacted_channels
            )

            original_pixel = original_samples_data[
                original_offset:
                original_offset + 3
            ]

            redacted_pixel = redacted_samples_data[
                redacted_offset:
                redacted_offset + 3
            ]

            original_samples.append(
                sum(original_pixel) / 3
            )

            redacted_samples.append(
                sum(redacted_pixel) / 3
            )

    assert original_samples
    assert redacted_samples

    original_mean = (
        sum(original_samples)
        / len(original_samples)
    )

    redacted_mean = (
        sum(redacted_samples)
        / len(redacted_samples)
    )

    # The original PAN region contains dark text on a light background.
    # After redaction, the region should become substantially darker.
    assert redacted_mean < original_mean * 0.35