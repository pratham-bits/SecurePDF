from pathlib import Path
from typing import Iterable

import pymupdf

from app.positioned_extraction import BBox
from app.redaction_geometry import (
    PageGeometry,
    RedactionGeometryError,
    expand_bbox,
    validate_bbox_within_page,
)


class RedactionError(Exception):
    """Raised when PDF redaction cannot be completed."""


def redact_pdf(
    input_path: str | Path,
    output_path: str | Path,
    page_boxes: dict[int, Iterable[BBox]],
    *,
    padding: float = 0.0,
) -> None:
    """
    Permanently redact supplied bounding boxes from a PDF.

    page_boxes uses 1-based page numbers:
        {
            1: [
                (x0, y0, x1, y1),
                ...
            ]
        }

    The input PDF is never modified in place.
    """
    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        raise RedactionError("Input PDF file not found.")

    if not input_file.is_file():
        raise RedactionError("Input PDF path is not a file.")

    if input_file.resolve() == output_file.resolve():
        raise RedactionError(
            "Input and output PDF paths must be different."
        )

    try:
        document = pymupdf.open(input_file)
    except Exception as exc:
        raise RedactionError("Unable to open input PDF.") from exc

    try:
        for page_number, boxes in page_boxes.items():
            if not isinstance(page_number, int):
                raise RedactionError("Page numbers must be integers.")

            if page_number < 1 or page_number > len(document):
                raise RedactionError(
                    f"Page number {page_number} is outside the PDF."
                )

            page = document[page_number - 1]

            page_geometry: PageGeometry = {
                "width": float(page.rect.width),
                "height": float(page.rect.height),
            }

            for bbox in boxes:
                try:
                    validated_bbox = validate_bbox_within_page(
                        bbox,
                        page_geometry,
                    )

                    final_bbox = expand_bbox(
                        validated_bbox,
                        padding,
                        page_geometry,
                    )
                except RedactionGeometryError as exc:
                    raise RedactionError(
                        f"Invalid redaction geometry on page "
                        f"{page_number}: {exc}"
                    ) from exc

                page.add_redact_annot(
                    pymupdf.Rect(final_bbox),
                    fill=(0, 0, 0),
                )

        for page_number in page_boxes:
            page = document[page_number - 1]
            page.apply_redactions()

        output_file.parent.mkdir(parents=True, exist_ok=True)

        document.save(
            output_file,
            garbage=4,
            deflate=True,
        )

    except RedactionError:
        raise
    except Exception as exc:
        raise RedactionError("Unable to redact PDF.") from exc
    finally:
        document.close()