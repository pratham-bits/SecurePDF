from pathlib import Path
from typing import TypedDict

import pymupdf


BBox = tuple[float, float, float, float]


class TextFragment(TypedDict):
    text: str
    start: int
    end: int
    bbox: BBox


class PositionedPage(TypedDict):
    page_number: int
    text: str
    source: str
    fragments: list[TextFragment]


class PositionedExtractionError(Exception):
    """Raised when positioned PDF text extraction cannot be completed."""


def extract_positioned_text_from_pdf(
    pdf_path: str | Path,
) -> list[PositionedPage]:
    """
    Extract digital PDF text together with character offsets and
    PyMuPDF word bounding boxes.

    The returned page text is constructed from the same ordered
    word fragments used to calculate character offsets, ensuring
    that offsets and coordinates remain aligned.

    OCR is intentionally not performed here.
    """

    path = Path(pdf_path)

    if not path.exists():
        raise PositionedExtractionError("PDF file not found.")

    if not path.is_file():
        raise PositionedExtractionError("PDF source is not a file.")

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise PositionedExtractionError(
            "Unable to open PDF for positioned text extraction."
        ) from exc

    positioned_pages: list[PositionedPage] = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1

            try:
                words = page.get_text("words")
            except Exception as exc:
                raise PositionedExtractionError(
                    f"Unable to extract positioned text from "
                    f"PDF page {page_number}."
                ) from exc

            fragments: list[TextFragment] = []
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

            positioned_pages.append(
                {
                    "page_number": page_number,
                    "text": "".join(text_parts),
                    "source": "text",
                    "fragments": fragments,
                }
            )

    finally:
        document.close()

    return positioned_pages