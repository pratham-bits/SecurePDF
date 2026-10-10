"""Simple text-based PDF document classification."""

from pathlib import Path

import pymupdf


def classify_pdf(storage_path: Path) -> str:
    """Classify a readable PDF by whether its pages contain extracted text."""
    try:
        with pymupdf.open(storage_path) as pdf:
            text_page_count = sum(
                bool(" ".join(page.get_text("text").split())) for page in pdf
            )
            if text_page_count == pdf.page_count:
                return "digital"
            if text_page_count == 0:
                return "scanned"
            return "mixed"
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError("PDF could not be classified.") from exc
