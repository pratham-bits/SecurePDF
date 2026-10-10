from pathlib import Path
from typing import TypedDict

import numpy as np
import pymupdf

from app.ocr import OCREngine, OCRError


BBox = tuple[
    float,
    float,
    float,
    float,
]


class OCRTextFragment(TypedDict):
    text: str
    start: int
    end: int
    bbox: BBox


class OCRPositionedPage(TypedDict):
    page_number: int
    text: str
    source: str
    fragments: list[OCRTextFragment]


class OCRPositionedExtractionError(Exception):
    """Raised when positional OCR extraction fails."""


def _build_positioned_page(
    page_number: int,
    fragments: list[dict],
) -> OCRPositionedPage:
    """
    Build canonical page text and assign offsets to OCR fragments.

    Fragments are joined with exactly one space, making the offsets
    deterministic and compatible with PII candidate spans.
    """

    text_parts: list[str] = []

    current_offset = 0

    positioned_fragments: list[OCRTextFragment] = []

    for fragment in fragments:
        fragment_text = fragment["text"]

        if text_parts:
            text_parts.append(" ")
            current_offset += 1

        start = current_offset
        end = start + len(fragment_text)

        positioned_fragments.append(
            {
                "text": fragment_text,
                "start": start,
                "end": end,
                "bbox": fragment["bbox"],
            }
        )

        text_parts.append(
            fragment_text
        )

        current_offset = end

    return {
        "page_number": page_number,
        "text": "".join(text_parts),
        "source": "ocr",
        "fragments": positioned_fragments,
    }


def extract_positioned_ocr_from_image(
    image: bytes | np.ndarray,
    *,
    ocr_engine: OCREngine | None = None,
) -> OCRPositionedPage:
    """
    Run positional OCR on one image.

    The public OCREngine.recognize_positioned() API is used so this
    module does not access PaddleOCR internals.
    """

    engine = ocr_engine or OCREngine()

    try:
        results = engine.recognize_positioned(
            image
        )
    except OCRError as exc:
        raise OCRPositionedExtractionError(
            "Unable to perform positional OCR."
        ) from exc
    except Exception as exc:
        raise OCRPositionedExtractionError(
            "Unexpected positional OCR failure."
        ) from exc

    return _build_positioned_page(
        page_number=1,
        fragments=results,
    )


def extract_positioned_ocr_from_pdf(
    pdf_path: str | Path,
    *,
    ocr_engine: OCREngine | None = None,
    scale: float = 2.0,
) -> list[OCRPositionedPage]:
    """
    Render each PDF page and perform positional OCR.

    This is intended for scanned/image-based PDFs where native PDF
    text extraction does not provide usable text.
    """

    path = Path(pdf_path)

    if not path.exists():
        raise OCRPositionedExtractionError(
            "PDF file not found."
        )

    if not path.is_file():
        raise OCRPositionedExtractionError(
            "PDF source is not a file."
        )

    if scale <= 0:
        raise OCRPositionedExtractionError(
            "OCR rendering scale must be greater than zero."
        )

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise OCRPositionedExtractionError(
            "Unable to open PDF for positional OCR."
        ) from exc

    engine = ocr_engine

    positioned_pages: list[
        OCRPositionedPage
    ] = []

    try:
        for page_index, page in enumerate(
            document
        ):
            try:
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(
                        scale,
                        scale,
                    )
                )

                image_bytes = pixmap.tobytes(
                    "png"
                )

                page_result = (
                    extract_positioned_ocr_from_image(
                        image_bytes,
                        ocr_engine=engine,
                    )
                )

                page_result["page_number"] = (
                    page_index + 1
                )

                positioned_pages.append(
                    page_result
                )

            except OCRPositionedExtractionError:
                raise

            except Exception as exc:
                raise OCRPositionedExtractionError(
                    f"Unable to perform positional OCR "
                    f"on PDF page {page_index + 1}."
                ) from exc

    finally:
        document.close()

    return positioned_pages