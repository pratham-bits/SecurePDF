from pathlib import Path
from typing import Iterable, Mapping, Any

import pymupdf

from app.ocr_coordinate_mapping import map_candidate_to_ocr_bboxes
from app.ocr_coordinate_transform import transform_ocr_bboxes_to_pdf
from app.redaction import redact_pdf


class ScannedRedactionError(Exception):
    """Raised when scanned-PDF redaction cannot be completed."""


DEFAULT_OCR_SCALE_X = 2.0
DEFAULT_OCR_SCALE_Y = 2.0


def build_scanned_redaction_boxes(
    candidate: Mapping[str, Any],
    positioned_page: Mapping[str, Any],
    *,
    scale_x: float = DEFAULT_OCR_SCALE_X,
    scale_y: float = DEFAULT_OCR_SCALE_Y,
) -> list[tuple[float, float, float, float]]:
    """
    Convert a scanned-PDF PII candidate into PDF-coordinate redaction boxes.

    OCR fragments are in rendered-image coordinates. The returned boxes are
    in PDF page coordinates and can therefore be passed to redact_pdf().
    """
    try:
        ocr_bboxes = map_candidate_to_ocr_bboxes(
            candidate,
            positioned_page,
        )
    except Exception as exc:
        raise ScannedRedactionError(
            "Unable to map candidate to OCR coordinates."
        ) from exc

    try:
        return transform_ocr_bboxes_to_pdf(
            ocr_bboxes,
            scale_x=scale_x,
            scale_y=scale_y,
        )
    except Exception as exc:
        raise ScannedRedactionError(
            "Unable to transform OCR coordinates to PDF coordinates."
        ) from exc


def redact_scanned_pdf(
    input_path: str | Path,
    output_path: str | Path,
    page_candidates: Iterable[
        tuple[int, Mapping[str, Any], Mapping[str, Any]]
    ],
    *,
    scale_x: float = DEFAULT_OCR_SCALE_X,
    scale_y: float = DEFAULT_OCR_SCALE_Y,
    padding: float = 0.0,
) -> Path:
    """
    Permanently redact selected candidates from a scanned PDF.

    Each page candidate tuple contains:

        (page_number, candidate, positioned_page)

    Candidate coordinates are derived from OCR fragments and transformed
    into PDF page coordinates before using the existing redaction engine.
    """
    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        raise ScannedRedactionError("Input PDF does not exist.")

    if not input_file.is_file():
        raise ScannedRedactionError("Input PDF is not a file.")

    if input_file.resolve() == output_file.resolve():
        raise ScannedRedactionError(
            "Input and output PDF paths must be different."
        )

    page_boxes: dict[int, list[tuple[float, float, float, float]]] = {}

    for page_number, candidate, positioned_page in page_candidates:
        if not isinstance(page_number, int) or page_number < 1:
            raise ScannedRedactionError("Invalid page number.")

        boxes = build_scanned_redaction_boxes(
            candidate,
            positioned_page,
            scale_x=scale_x,
            scale_y=scale_y,
        )

        page_boxes.setdefault(page_number, []).extend(boxes)

    if not page_boxes:
        raise ScannedRedactionError(
            "No scanned-PDF redaction candidates were supplied."
        )

    try:
        redact_pdf(
            input_file,
            output_file,
            page_boxes,
            padding=padding,
        )
    except Exception as exc:
        raise ScannedRedactionError(
            "Scanned PDF redaction failed."
        ) from exc

    if not output_file.exists() or not output_file.is_file():
        raise ScannedRedactionError(
            "Redacted output PDF was not created."
        )

    try:
        with pymupdf.open(output_file) as document:
            if document.page_count == 0:
                raise ScannedRedactionError(
                    "Redacted output PDF contains no pages."
                )
    except ScannedRedactionError:
        raise
    except Exception as exc:
        raise ScannedRedactionError(
            "Redacted output PDF cannot be opened."
        ) from exc

    return output_file