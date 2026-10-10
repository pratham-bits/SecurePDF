from pathlib import Path

import pytest

from app.coordinate_mapping import (
    CoordinateMappingError,
    map_candidate_to_bboxes,
)
from app.positioned_extraction import extract_positioned_text_from_pdf


PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "test_data"
    / "coordinate_test.pdf"
)


@pytest.fixture(scope="module")
def positioned_page():
    pages = extract_positioned_text_from_pdf(PDF_PATH)

    assert len(pages) == 1

    return pages[0]


def candidate_from_text(text: str, value: str) -> dict:
    start = text.index(value)

    return {
        "text": value,
        "start": start,
        "end": start + len(value),
    }


def test_pan_maps_to_one_bbox(positioned_page):
    candidate = candidate_from_text(
        positioned_page["text"],
        "ABCDE1234F",
    )

    boxes = map_candidate_to_bboxes(candidate, positioned_page)

    assert len(boxes) == 1

    assert boxes[0] == (
        99.8931655883789,
        130.544921875,
        168.9390106201172,
        142.833984375,
    )


def test_phone_maps_to_two_bboxes(positioned_page):
    candidate = candidate_from_text(
        positioned_page["text"],
        "+91 9876543210",
    )

    boxes = map_candidate_to_bboxes(candidate, positioned_page)

    assert len(boxes) == 2

    assert boxes[0] == (
        109.89299011230469,
        145.0911865234375,
        128.5415802001953,
        157.3802490234375,
    )

    assert boxes[1] == (
        131.5928955078125,
        145.0911865234375,
        192.7288818359375,
        157.3802490234375,
    )


def test_full_name_maps_to_two_bboxes(positioned_page):
    candidate = candidate_from_text(
        positioned_page["text"],
        "Rahul Kumar",
    )

    boxes = map_candidate_to_bboxes(candidate, positioned_page)

    assert len(boxes) == 2


def test_email_maps_to_one_bbox(positioned_page):
    candidate = candidate_from_text(
        positioned_page["text"],
        "rahul@example.com",
    )

    boxes = map_candidate_to_bboxes(candidate, positioned_page)

    assert len(boxes) == 1


def test_invalid_negative_span_is_rejected(positioned_page):
    candidate = {
        "text": "ABCDE1234F",
        "start": -1,
        "end": 9,
    }

    with pytest.raises(CoordinateMappingError):
        map_candidate_to_bboxes(candidate, positioned_page)


def test_out_of_range_span_is_rejected(positioned_page):
    candidate = {
        "text": "ABCDE1234F",
        "start": 0,
        "end": len(positioned_page["text"]) + 1,
    }

    with pytest.raises(CoordinateMappingError):
        map_candidate_to_bboxes(candidate, positioned_page)


def test_unmapped_span_is_rejected(positioned_page):
    candidate = {
        "text": "not-present",
        "start": len(positioned_page["text"]) + 1,
        "end": len(positioned_page["text"]) + 12,
    }

    with pytest.raises(CoordinateMappingError):
        map_candidate_to_bboxes(candidate, positioned_page)