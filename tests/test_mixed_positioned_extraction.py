from pathlib import Path

import pymupdf

from app.mixed_positioned_extraction import (
    extract_mixed_positioned_pages,
)


TEST_DATA = Path("backend/test_data")

DIGITAL_PDF = TEST_DATA / "coordinate_test.pdf"
SCANNED_PDF = TEST_DATA / "coordinate_test_scanned.pdf"


def _create_mixed_pdf(output_path: Path) -> None:
    """
    Create a genuine mixed PDF:

    Page 1 -> machine-readable digital content.
    Page 2 -> image-only scanned content.
    """

    digital_document = pymupdf.open(DIGITAL_PDF)

    try:
        digital_page = digital_document[0]

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
                # Page 1: genuine digital page
                # ---------------------------------------------------

                output.insert_pdf(
                    digital_document,
                    from_page=0,
                    to_page=0,
                )

                # ---------------------------------------------------
                # Page 2: genuine image-only page
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


def test_mixed_pdf_selects_digital_and_ocr_paths(
    tmp_path,
):
    mixed_pdf = tmp_path / "mixed_test.pdf"

    _create_mixed_pdf(mixed_pdf)

    pages = extract_mixed_positioned_pages(
        mixed_pdf,
        ocr_scale=2.0,
    )

    assert len(pages) == 2

    assert pages[0]["page_number"] == 1
    assert pages[0]["source"] == "text"

    assert "Rahul" in pages[0]["text"]
    assert "ABCDE1234F" in pages[0]["text"]

    assert pages[1]["page_number"] == 2
    assert pages[1]["source"] == "ocr"

    assert "Rahul" in pages[1]["text"]
    assert "ABCDE1234F" in pages[1]["text"]


def test_mixed_pdf_preserves_page_boundaries(
    tmp_path,
):
    mixed_pdf = tmp_path / "mixed_test.pdf"

    _create_mixed_pdf(mixed_pdf)

    pages = extract_mixed_positioned_pages(
        mixed_pdf,
        ocr_scale=2.0,
    )

    assert pages[0]["page_number"] == 1
    assert pages[1]["page_number"] == 2

    assert pages[0]["source"] == "text"
    assert pages[1]["source"] == "ocr"


def test_digital_page_contains_pdf_coordinates(
    tmp_path,
):
    mixed_pdf = tmp_path / "mixed_test.pdf"

    _create_mixed_pdf(mixed_pdf)

    pages = extract_mixed_positioned_pages(
        mixed_pdf,
        ocr_scale=2.0,
    )

    digital_page = pages[0]

    assert digital_page["fragments"]

    for fragment in digital_page["fragments"]:
        bbox = fragment["bbox"]

        assert len(bbox) == 4
        assert bbox[2] > bbox[0]
        assert bbox[3] > bbox[1]


def test_scanned_page_contains_ocr_coordinates(
    tmp_path,
):
    mixed_pdf = tmp_path / "mixed_test.pdf"

    _create_mixed_pdf(mixed_pdf)

    pages = extract_mixed_positioned_pages(
        mixed_pdf,
        ocr_scale=2.0,
    )

    scanned_page = pages[1]

    assert scanned_page["fragments"]

    for fragment in scanned_page["fragments"]:
        bbox = fragment["bbox"]

        assert len(bbox) == 4
        assert bbox[2] > bbox[0]
        assert bbox[3] > bbox[1]


def test_missing_mixed_pdf_is_rejected(
    tmp_path,
):
    missing_pdf = tmp_path / "does_not_exist.pdf"

    try:
        extract_mixed_positioned_pages(
            missing_pdf,
        )
    except Exception as exc:
        assert "not found" in str(exc).lower()
    else:
        raise AssertionError(
            "Expected missing PDF to be rejected."
        )