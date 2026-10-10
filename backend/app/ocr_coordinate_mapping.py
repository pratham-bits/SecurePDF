from collections.abc import Mapping
from typing import Any

from app.positioned_extraction import BBox


class OCRCoordinateMappingError(Exception):
    """Raised when an OCR candidate cannot be mapped to OCR fragments."""


def _validate_candidate(candidate: Mapping[str, Any]) -> tuple[int, int]:
    try:
        start = candidate["start"]
        end = candidate["end"]
    except KeyError as exc:
        raise OCRCoordinateMappingError(
            "Candidate must contain start and end offsets."
        ) from exc

    if not isinstance(start, int) or isinstance(start, bool):
        raise OCRCoordinateMappingError("Candidate start must be an integer.")

    if not isinstance(end, int) or isinstance(end, bool):
        raise OCRCoordinateMappingError("Candidate end must be an integer.")

    if start < 0:
        raise OCRCoordinateMappingError("Candidate start cannot be negative.")

    if end <= start:
        raise OCRCoordinateMappingError(
            "Candidate end must be greater than start."
        )

    return start, end


def _validate_page(page: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    try:
        text = page["text"]
        fragments = page["fragments"]
    except KeyError as exc:
        raise OCRCoordinateMappingError(
            "OCR page must contain text and fragments."
        ) from exc

    if not isinstance(text, str):
        raise OCRCoordinateMappingError("OCR page text must be a string.")

    if not isinstance(fragments, list):
        raise OCRCoordinateMappingError("OCR page fragments must be a list.")

    return text, fragments


def _validate_fragment(
    fragment: Mapping[str, Any],
    page_text_length: int,
) -> tuple[int, int, BBox]:
    required_fields = ("text", "start", "end", "bbox")

    for field in required_fields:
        if field not in fragment:
            raise OCRCoordinateMappingError(
                f"OCR fragment is missing required field: {field}."
            )

    text = fragment["text"]
    start = fragment["start"]
    end = fragment["end"]
    bbox = fragment["bbox"]

    if not isinstance(text, str) or not text:
        raise OCRCoordinateMappingError(
            "OCR fragment text must be a non-empty string."
        )

    if not isinstance(start, int) or isinstance(start, bool):
        raise OCRCoordinateMappingError(
            "OCR fragment start must be an integer."
        )

    if not isinstance(end, int) or isinstance(end, bool):
        raise OCRCoordinateMappingError(
            "OCR fragment end must be an integer."
        )

    if start < 0 or end <= start:
        raise OCRCoordinateMappingError(
            "OCR fragment offsets are invalid."
        )

    if end > page_text_length:
        raise OCRCoordinateMappingError(
            "OCR fragment end exceeds page text length."
        )

    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise OCRCoordinateMappingError(
            "OCR fragment bbox must contain four coordinates."
        )

    normalized_bbox: BBox = tuple(float(value) for value in bbox)  # type: ignore[assignment]

    return start, end, normalized_bbox


def map_candidate_to_ocr_bboxes(
    candidate: Mapping[str, Any],
    positioned_page: Mapping[str, Any],
) -> list[BBox]:
    """
    Map a PII candidate's character span to OCR fragment bounding boxes.

    The returned coordinates remain in OCR/image coordinate space.

    They are intentionally NOT converted to PDF coordinates here. That
    transformation belongs to the OCR coordinate transformation layer.
    """
    candidate_start, candidate_end = _validate_candidate(candidate)
    page_text, fragments = _validate_page(positioned_page)

    if candidate_end > len(page_text):
        raise OCRCoordinateMappingError(
            "Candidate end exceeds OCR page text length."
        )

    matched_boxes: list[BBox] = []

    for fragment in fragments:
        fragment_start, fragment_end, bbox = _validate_fragment(
            fragment,
            len(page_text),
        )

        overlaps = (
            candidate_start < fragment_end
            and candidate_end > fragment_start
        )

        if overlaps:
            matched_boxes.append(bbox)

    if not matched_boxes:
        raise OCRCoordinateMappingError(
            "Candidate span could not be mapped to OCR fragments."
        )

    return matched_boxes