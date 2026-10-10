from pathlib import Path
from typing import TypedDict

import pymupdf


class ExtractedPage(TypedDict):
    page_number: int
    text: str


class TextExtractionError(Exception):
    """Raised when PDF text extraction cannot be completed."""


def _normalize_text(text: str) -> str:
    """Normalize basic whitespace without changing meaningful content."""
    return " ".join(text.split())


def extract_text_from_pdf(pdf_path: str | Path) -> list[ExtractedPage]:
    """
    Extract machine-readable text from a PDF page by page.

    Pages without machine-readable text are returned with an empty
    string. OCR is intentionally not performed here.
    """
    path = Path(pdf_path)

    if not path.exists():
        raise TextExtractionError("PDF file not found.")

    if not path.is_file():
        raise TextExtractionError("PDF source is not a file.")

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise TextExtractionError(
            "Unable to open PDF for text extraction."
        ) from exc

    extracted_pages: list[ExtractedPage] = []

    try:
        for page_index, page in enumerate(document):
            try:
                raw_text = page.get_text("text")
            except Exception as exc:
                raise TextExtractionError(
                    f"Unable to extract text from PDF page {page_index + 1}."
                ) from exc

            extracted_pages.append(
                {
                    "page_number": page_index + 1,
                    "text": _normalize_text(raw_text),
                }
            )
    finally:
        document.close()

    return extracted_pages