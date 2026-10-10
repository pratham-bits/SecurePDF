from pathlib import Path
from typing import TypedDict

import pymupdf

from app.extraction import _normalize_text
from app.ocr import OCREngine, OCRError


class ProcessedPage(TypedDict):
    page_number: int
    text: str
    source: str


class TextPipelineError(Exception):
    """Raised when unified PDF text processing cannot be completed."""


def process_pdf_text(
    pdf_path: str | Path,
    ocr_engine: OCREngine | None = None,
) -> list[ProcessedPage]:
    """
    Extract text from a PDF using direct extraction or OCR per page.

    Pages containing machine-readable text use PyMuPDF extraction.
    Pages without machine-readable text are rendered and processed
    using the supplied OCR engine.

    Returns page-level text while preserving page boundaries and
    identifying the source as either 'text' or 'ocr'.
    """
    path = Path(pdf_path)

    if not path.exists():
        raise TextPipelineError("PDF file not found.")

    if not path.is_file():
        raise TextPipelineError("PDF source is not a file.")

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise TextPipelineError("Unable to open PDF for text processing.") from exc

    engine = ocr_engine
    results: list[ProcessedPage] = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1

            try:
                extracted_text = _normalize_text(page.get_text("text"))
            except Exception as exc:
                raise TextPipelineError(
                    f"Unable to extract text from PDF page {page_number}."
                ) from exc

            if extracted_text:
                results.append(
                    {
                        "page_number": page_number,
                        "text": extracted_text,
                        "source": "text",
                    }
                )
                continue

            if engine is None:
                engine = OCREngine()

            try:
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                image_bytes = pixmap.tobytes("png")
                ocr_text = engine.recognize(image_bytes)
            except OCRError as exc:
                raise TextPipelineError(
                    f"Unable to OCR PDF page {page_number}."
                ) from exc
            except Exception as exc:
                raise TextPipelineError(
                    f"Unable to render PDF page {page_number} for OCR."
                ) from exc

            results.append(
                {
                    "page_number": page_number,
                    "text": ocr_text,
                    "source": "ocr",
                }
            )

    finally:
        document.close()

    return results