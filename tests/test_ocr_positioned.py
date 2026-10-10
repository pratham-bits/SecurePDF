from pathlib import Path

import pymupdf
import pytest

from app.ocr import OCREngine
from app.ocr_positioned import (
    OCRPositionedExtractionError,
    extract_positioned_ocr_from_pdf,
)


PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "test_data"
    / "coordinate_test.pdf"
)


def create_scanned_test_pdf(
    output_path: Path,
) -> None:
    """
    Create a genuine image-only PDF from the existing coordinate
    test PDF.

    The resulting PDF contains rendered page images and no native
    text layer.
    """

    source = pymupdf.open(PDF_PATH)

    try:
        output = pymupdf.open()

        try:
            for page in source:
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(2, 2)
                )

                image_bytes = pixmap.tobytes("png")

                new_page = output.new_page(
                    width=page.rect.width,
                    height=page.rect.height,
                )

                new_page.insert_image(
                    new_page.rect,
                    stream=image_bytes,
                )

            output.save(output_path)

        finally:
            output.close()

    finally:
        source.close()


@pytest.fixture(scope="module")
def ocr_engine():
    return OCREngine()


@pytest.fixture(scope="module")
def scanned_pdf(tmp_path_factory):
    directory = tmp_path_factory.mktemp(
        "ocr_positioned"
    )

    output_path = directory / "scanned_coordinate_test.pdf"

    create_scanned_test_pdf(output_path)

    return output_path


def test_scanned_test_pdf_contains_no_native_text(
    scanned_pdf,
):
    document = pymupdf.open(scanned_pdf)

    try:
        extracted_text = "\n".join(
            page.get_text("text")
            for page in document
        )
    finally:
        document.close()

    assert extracted_text.strip() == ""


def test_positioned_ocr_returns_page_data(
    scanned_pdf,
    ocr_engine,
):
    pages = extract_positioned_ocr_from_pdf(
        scanned_pdf,
        ocr_engine=ocr_engine,
    )

    assert len(pages) == 1

    page = pages[0]

    assert page["page_number"] == 1
    assert page["source"] == "ocr"

    assert page["text"]

    assert page["fragments"]


def test_positioned_ocr_preserves_expected_pii_text(
    scanned_pdf,
    ocr_engine,
):
    pages = extract_positioned_ocr_from_pdf(
        scanned_pdf,
        ocr_engine=ocr_engine,
    )

    text = pages[0]["text"]

    assert "Rahul" in text
    assert "Kumar" in text
    assert "rahul@example.com" in text
    assert "ABCDE1234F" in text
    assert "9876543210" in text


def test_positioned_ocr_fragments_have_valid_offsets(
    scanned_pdf,
    ocr_engine,
):
    pages = extract_positioned_ocr_from_pdf(
        scanned_pdf,
        ocr_engine=ocr_engine,
    )

    page = pages[0]

    for fragment in page["fragments"]:
        assert fragment["text"]

        assert fragment["start"] >= 0

        assert fragment["end"] > fragment["start"]

        assert fragment["end"] <= len(page["text"])

        assert (
            page["text"][
                fragment["start"]:fragment["end"]
            ]
            == fragment["text"]
        )


def test_positioned_ocr_fragments_have_valid_bboxes(
    scanned_pdf,
    ocr_engine,
):
    pages = extract_positioned_ocr_from_pdf(
        scanned_pdf,
        ocr_engine=ocr_engine,
    )

    page = pages[0]

    for fragment in page["fragments"]:
        x0, y0, x1, y1 = fragment["bbox"]

        assert x1 > x0
        assert y1 > y0

        assert all(
            value >= 0
            for value in (
                x0,
                y0,
                x1,
                y1,
            )
        )


def test_positioned_ocr_page_text_matches_fragments(
    scanned_pdf,
    ocr_engine,
):
    pages = extract_positioned_ocr_from_pdf(
        scanned_pdf,
        ocr_engine=ocr_engine,
    )

    page = pages[0]

    reconstructed = " ".join(
        fragment["text"]
        for fragment in page["fragments"]
    )

    assert reconstructed == page["text"]


def test_missing_pdf_is_rejected(
    tmp_path,
    ocr_engine,
):
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(OCRPositionedExtractionError):
        extract_positioned_ocr_from_pdf(
            missing_pdf,
            ocr_engine=ocr_engine,
        )