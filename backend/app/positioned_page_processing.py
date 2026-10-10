from typing import Any, Mapping

from app.coordinate_mapping import map_candidate_to_bboxes
from app.ocr_coordinate_mapping import map_candidate_to_ocr_bboxes
from app.ocr_coordinate_transform import transform_ocr_bboxes_to_pdf
from app.positioned_extraction import PositionedPage


class PositionedPageProcessingError(Exception):
    """Raised when positioned-page candidate processing fails."""


def map_candidate_to_pdf_bboxes(
    candidate: Mapping[str, Any],
    page: Mapping[str, Any],
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> list[tuple[float, float, float, float]]:
    """
    Map a PII candidate to PDF-coordinate bounding boxes.

    Digital pages already contain PDF-coordinate bounding boxes.

    OCR pages contain image-coordinate bounding boxes, which are converted
    into PDF coordinates using the supplied rendering scale.
    """

    source = page.get("source")

    if source == "text":
        try:
            return map_candidate_to_bboxes(
                candidate,
                page,  # type: ignore[arg-type]
            )
        except Exception as exc:
            raise PositionedPageProcessingError(
                "Unable to map digital candidate to PDF coordinates."
            ) from exc

    if source == "ocr":
        try:
            ocr_boxes = map_candidate_to_ocr_bboxes(
                candidate,
                page,
            )

            return transform_ocr_bboxes_to_pdf(
                ocr_boxes,
                scale_x=scale_x,
                scale_y=scale_y,
            )

        except Exception as exc:
            raise PositionedPageProcessingError(
                "Unable to map OCR candidate to PDF coordinates."
            ) from exc

    raise PositionedPageProcessingError(
        f"Unsupported positioned page source: {source!r}"
    )