from math import isfinite
from typing import TypedDict

from app.positioned_extraction import BBox


class RedactionGeometryError(Exception):
    """Raised when redaction geometry is invalid."""


class PageGeometry(TypedDict):
    width: float
    height: float


class RedactionRegion(TypedDict):
    page_number: int
    bbox: BBox


def validate_bbox(bbox: BBox) -> BBox:
    """
    Validate a PyMuPDF-style bounding box.

    Coordinates use:
        (x0, y0, x1, y1)

    where x1 > x0 and y1 > y0.
    """
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise RedactionGeometryError(
            "Bounding box must contain exactly four coordinates."
        )

    try:
        x0, y0, x1, y1 = (float(value) for value in bbox)
    except (TypeError, ValueError) as exc:
        raise RedactionGeometryError(
            "Bounding box coordinates must be numeric."
        ) from exc

    if not all(isfinite(value) for value in (x0, y0, x1, y1)):
        raise RedactionGeometryError(
            "Bounding box coordinates must be finite."
        )

    if x1 <= x0 or y1 <= y0:
        raise RedactionGeometryError(
            "Bounding box must have positive width and height."
        )

    return (x0, y0, x1, y1)


def validate_page_geometry(page: PageGeometry) -> PageGeometry:
    """Validate PDF page dimensions."""
    try:
        width = float(page["width"])
        height = float(page["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RedactionGeometryError(
            "Page geometry must contain numeric width and height."
        ) from exc

    if not isfinite(width) or not isfinite(height):
        raise RedactionGeometryError(
            "Page dimensions must be finite."
        )

    if width <= 0 or height <= 0:
        raise RedactionGeometryError(
            "Page dimensions must be positive."
        )

    return {
        "width": width,
        "height": height,
    }


def validate_bbox_within_page(
    bbox: BBox,
    page: PageGeometry,
) -> BBox:
    """Validate that a bounding box lies completely inside a PDF page."""
    validated_bbox = validate_bbox(bbox)
    validated_page = validate_page_geometry(page)

    x0, y0, x1, y1 = validated_bbox
    width = validated_page["width"]
    height = validated_page["height"]

    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        raise RedactionGeometryError(
            "Bounding box lies outside the page boundaries."
        )

    return validated_bbox


def expand_bbox(
    bbox: BBox,
    padding: float,
    page: PageGeometry,
) -> BBox:
    """
    Expand a bounding box by the supplied padding.

    Expansion is clipped to the page boundaries.
    """
    validated_bbox = validate_bbox(bbox)
    validated_page = validate_page_geometry(page)

    try:
        padding = float(padding)
    except (TypeError, ValueError) as exc:
        raise RedactionGeometryError(
            "Padding must be numeric."
        ) from exc

    if not isfinite(padding) or padding < 0:
        raise RedactionGeometryError(
            "Padding must be a finite non-negative value."
        )

    x0, y0, x1, y1 = validated_bbox
    width = validated_page["width"]
    height = validated_page["height"]

    expanded = (
        max(0.0, x0 - padding),
        max(0.0, y0 - padding),
        min(width, x1 + padding),
        min(height, y1 + padding),
    )

    return validate_bbox(expanded)