import pytest

from app.ocr_coordinate_mapping import (
    OCRCoordinateMappingError,
    map_candidate_to_ocr_bboxes,
)


def _page():
    return {
        "page_number": 1,
        "text": "Name Rahul Kumar Email rahul@example.com",
        "source": "ocr",
        "fragments": [
            {
                "text": "Name",
                "start": 0,
                "end": 4,
                "bbox": (10.0, 10.0, 40.0, 20.0),
            },
            {
                "text": "Rahul",
                "start": 5,
                "end": 10,
                "bbox": (45.0, 10.0, 80.0, 20.0),
            },
            {
                "text": "Kumar",
                "start": 11,
                "end": 16,
                "bbox": (85.0, 10.0, 120.0, 20.0),
            },
            {
                "text": "Email",
                "start": 17,
                "end": 22,
                "bbox": (10.0, 30.0, 40.0, 40.0),
            },
            {
                "text": "rahul@example.com",
                "start": 23,
                "end": 39,
                "bbox": (45.0, 30.0, 180.0, 40.0),
            },
        ],
    }


def test_maps_single_fragment_candidate():
    page = _page()

    candidate = {
        "entity_type": "EMAIL",
        "text": "rahul@example.com",
        "start": 23,
        "end": 39,
    }

    result = map_candidate_to_ocr_bboxes(candidate, page)

    assert result == [
        (45.0, 30.0, 180.0, 40.0),
    ]


def test_maps_multi_fragment_candidate():
    page = _page()

    candidate = {
        "entity_type": "PERSON",
        "text": "Rahul Kumar",
        "start": 5,
        "end": 16,
    }

    result = map_candidate_to_ocr_bboxes(candidate, page)

    assert result == [
        (45.0, 10.0, 80.0, 20.0),
        (85.0, 10.0, 120.0, 20.0),
    ]


def test_partial_fragment_overlap_maps_fragment():
    page = _page()

    candidate = {
        "entity_type": "PERSON",
        "text": "Rahul",
        "start": 7,
        "end": 9,
    }

    result = map_candidate_to_ocr_bboxes(candidate, page)

    assert result == [
        (45.0, 10.0, 80.0, 20.0),
    ]


def test_candidate_span_must_be_within_page_text():
    page = _page()

    candidate = {
        "entity_type": "EMAIL",
        "text": "something",
        "start": 23,
        "end": 1000,
    }

    with pytest.raises(OCRCoordinateMappingError):
        map_candidate_to_ocr_bboxes(candidate, page)


def test_unmapped_candidate_is_rejected():
    page = _page()

    candidate = {
        "entity_type": "PASSPORT",
        "text": "AB123456",
        "start": 100,
        "end": 108,
    }

    with pytest.raises(OCRCoordinateMappingError):
        map_candidate_to_ocr_bboxes(candidate, page)


def test_invalid_candidate_offsets_are_rejected():
    page = _page()

    candidate = {
        "entity_type": "EMAIL",
        "text": "rahul@example.com",
        "start": 20,
        "end": 20,
    }

    with pytest.raises(OCRCoordinateMappingError):
        map_candidate_to_ocr_bboxes(candidate, page)


def test_missing_candidate_offsets_are_rejected():
    page = _page()

    candidate = {
        "entity_type": "EMAIL",
        "text": "rahul@example.com",
    }

    with pytest.raises(OCRCoordinateMappingError):
        map_candidate_to_ocr_bboxes(candidate, page)


def test_invalid_fragment_bbox_is_rejected():
    page = _page()
    page["fragments"][1]["bbox"] = (45.0, 10.0, 80.0)

    candidate = {
        "entity_type": "PERSON",
        "text": "Rahul",
        "start": 5,
        "end": 10,
    }

    with pytest.raises(OCRCoordinateMappingError):
        map_candidate_to_ocr_bboxes(candidate, page)


def test_fragment_outside_page_text_is_rejected():
    page = _page()
    page["fragments"][1]["end"] = 999

    candidate = {
        "entity_type": "PERSON",
        "text": "Rahul",
        "start": 5,
        "end": 10,
    }

    with pytest.raises(OCRCoordinateMappingError):
        map_candidate_to_ocr_bboxes(candidate, page)