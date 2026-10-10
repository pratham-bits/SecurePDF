from math import isfinite
from typing import Sequence

from app.positioned_extraction import BBox
from app.redaction_geometry import validate_bbox


class OCRCoordinateTransformError(Exception):
    """Raised when OCR coordinates cannot be transformed safely."""


def transform_ocr_bbox_to_pdf(
    bbox: Sequence[float],
    *,
    scale_x: float,
    scale_y: float,
) -> BBox:
    """
    Convert an OCR/image-space bounding box into PDF/page coordinates.

    OCR coordinates are assumed to be measured in pixels produced by a
    PyMuPDF render. PDF coordinates are measured in page points.

    The transformation is intentionally limited to scaling. Translation,
    rotation, and crop-box handling belong to the page-rendering layer and
    should be added only when the renderer requires them.
    """
    try:
        validate_bbox(bbox)
    except Exception as exc:
        raise OCRCoordinateTransformError(
            "Invalid OCR bounding box."
        ) from exc

    if not isinstance(scale_x, (int, float)) or isinstance(scale_x, bool):
        raise OCRCoordinateTransformError("scale_x must be numeric.")

    if not isinstance(scale_y, (int, float)) or isinstance(scale_y, bool):
        raise OCRCoordinateTransformError("scale_y must be numeric.")

    if not isfinite(float(scale_x)) or scale_x <= 0:
        raise OCRCoordinateTransformError(
            "scale_x must be finite and greater than zero."
        )

    if not isfinite(float(scale_y)) or scale_y <= 0:
        raise OCRCoordinateTransformError(
            "scale_y must be finite and greater than zero."
        )

    x0, y0, x1, y1 = (float(value) for value in bbox)

    transformed: BBox = (
        x0 / float(scale_x),
        y0 / float(scale_y),
        x1 / float(scale_x),
        y1 / float(scale_y),
    )

    try:
        validate_bbox(transformed)
    except Exception as exc:
        raise OCRCoordinateTransformError(
            "Transformed OCR bounding box is invalid."
        ) from exc

    return transformed


def transform_ocr_bboxes_to_pdf(
    bboxes: Sequence[Sequence[float]],
    *,
    scale_x: float,
    scale_y: float,
) -> list[BBox]:
    """Transform multiple OCR bounding boxes into PDF coordinates."""
    return [
        transform_ocr_bbox_to_pdf(
            bbox,
            scale_x=scale_x,
            scale_y=scale_y,
        )
        for bbox in bboxes
    ]