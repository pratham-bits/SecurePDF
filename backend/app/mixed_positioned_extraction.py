from pathlib import Path
from typing import Any

import pymupdf

from app.extraction import _normalize_text
from app.ocr import OCREngine
from app.ocr_positioned import extract_positioned_ocr_from_image


class MixedPositionedExtractionError(Exception):
    """Raised when mixed PDF positioned extraction fails."""


def _extract_digital_page(
    page: pymupdf.Page,
) -> dict[str, Any]:
    """
    Extract machine-readable text and word-level coordinates
    from a digital PDF page.
    """

    words = page.get_text("words")

    fragments: list[dict[str, Any]] = []
    text_parts: list[str] = []

    current_offset = 0

    for word in words:
        if len(word) < 5:
            continue

        x0, y0, x1, y1, word_text = word[:5]

        if not isinstance(word_text, str):
            continue

        word_text = word_text.strip()

        if not word_text:
            continue

        if text_parts:
            text_parts.append(" ")
            current_offset += 1

        start = current_offset
        end = start + len(word_text)

        fragments.append(
            {
                "text": word_text,
                "start": start,
                "end": end,
                "bbox": (
                    float(x0),
                    float(y0),
                    float(x1),
                    float(y1),
                ),
            }
        )

        text_parts.append(word_text)
        current_offset = end

    return {
        "text": "".join(text_parts),
        "fragments": fragments,
    }


def extract_mixed_positioned_pages(
    pdf_path: str | Path,
    *,
    ocr_engine: OCREngine | None = None,
    ocr_scale: float = 2.0,
) -> list[dict[str, Any]]:
    """
    Extract positioned text from every page of a mixed PDF.

    Pages with machine-readable text use PyMuPDF.
    Pages without machine-readable text use PaddleOCR.

    Each returned page contains:

    - page_number
    - text
    - source: "text" or "ocr"
    - fragments
    """

    path = Path(pdf_path)

    if not path.exists():
        raise MixedPositionedExtractionError(
            "PDF file not found."
        )

    if not path.is_file():
        raise MixedPositionedExtractionError(
            "PDF source is not a file."
        )

    if ocr_scale <= 0:
        raise MixedPositionedExtractionError(
            "OCR scale must be greater than zero."
        )

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise MixedPositionedExtractionError(
            "Unable to open PDF."
        ) from exc

    engine = ocr_engine
    positioned_pages: list[dict[str, Any]] = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1

            raw_text = page.get_text("text")
            normalized_text = _normalize_text(raw_text)

            # -------------------------------------------------------
            # Digital page
            # -------------------------------------------------------

            if normalized_text:
                digital = _extract_digital_page(page)

                positioned_pages.append(
                    {
                        "page_number": page_number,
                        "text": digital["text"],
                        "source": "text",
                        "fragments": digital["fragments"],
                    }
                )

                continue

            # -------------------------------------------------------
            # Scanned page
            # -------------------------------------------------------

            if engine is None:
                engine = OCREngine()

            try:
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(
                        ocr_scale,
                        ocr_scale,
                    )
                )

                image_bytes = pixmap.tobytes("png")

                ocr_page = extract_positioned_ocr_from_image(
                    image_bytes,
                    ocr_engine=engine,
                )

            except Exception as exc:
                raise MixedPositionedExtractionError(
                    f"Unable to OCR PDF page {page_number}."
                ) from exc

            positioned_pages.append(
                {
                    "page_number": page_number,
                    "text": ocr_page["text"],
                    "source": "ocr",
                    "fragments": ocr_page["fragments"],
                }
            )

    finally:
        document.close()

    return positioned_pages