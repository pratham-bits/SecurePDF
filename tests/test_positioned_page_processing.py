import pytest

from app.positioned_page_processing import (
    PositionedPageProcessingError,
    map_candidate_to_pdf_bboxes,
)


def test_maps_digital_page_directly_to_pdf_coordinates():
    page = {
        "page_number": 1,
        "text": "PAN ABCDE1234F",
        "source": "text",
        "fragments": [
            {
                "text": "PAN",
                "start": 0,
                "end": 3,
                "bbox": (10.0, 10.0, 30.0, 20.0),
            },
            {
                "text": "ABCDE1234F",
                "start": 4,
                "end": 14,
                "bbox": (35.0, 10.0, 100.0, 20.0),
            },
        ],
    }

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": 4,
        "end": 14,
    }

    result = map_candidate_to_pdf_bboxes(
        candidate,
        page,
    )

    assert result == [
        (35.0, 10.0, 100.0, 20.0),
    ]


def test_maps_ocr_page_and_transforms_to_pdf_coordinates():
    page = {
        "page_number": 1,
        "text": "PAN ABCDE1234F",
        "source": "ocr",
        "fragments": [
            {
                "text": "PAN",
                "start": 0,
                "end": 3,
                "bbox": (20.0, 20.0, 60.0, 40.0),
            },
            {
                "text": "ABCDE1234F",
                "start": 4,
                "end": 14,
                "bbox": (70.0, 20.0, 200.0, 40.0),
            },
        ],
    }

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": 4,
        "end": 14,
    }

    result = map_candidate_to_pdf_bboxes(
        candidate,
        page,
        scale_x=2.0,
        scale_y=2.0,
    )

    assert result == [
        (35.0, 10.0, 100.0, 20.0),
    ]


def test_maps_multi_fragment_ocr_candidate():
    page = {
        "page_number": 1,
        "text": "Name Rahul Kumar",
        "source": "ocr",
        "fragments": [
            {
                "text": "Name",
                "start": 0,
                "end": 4,
                "bbox": (20.0, 20.0, 60.0, 40.0),
            },
            {
                "text": "Rahul",
                "start": 5,
                "end": 10,
                "bbox": (70.0, 20.0, 140.0, 40.0),
            },
            {
                "text": "Kumar",
                "start": 11,
                "end": 16,
                "bbox": (150.0, 20.0, 220.0, 40.0),
            },
        ],
    }

    candidate = {
        "entity_type": "PERSON",
        "text": "Rahul Kumar",
        "start": 5,
        "end": 16,
    }

    result = map_candidate_to_pdf_bboxes(
        candidate,
        page,
        scale_x=2.0,
        scale_y=2.0,
    )

    assert result == [
        (35.0, 10.0, 70.0, 20.0),
        (75.0, 10.0, 110.0, 20.0),
    ]


def test_rejects_unsupported_page_source():
    page = {
        "page_number": 1,
        "text": "PAN ABCDE1234F",
        "source": "unknown",
        "fragments": [],
    }

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": 4,
        "end": 14,
    }

    with pytest.raises(PositionedPageProcessingError):
        map_candidate_to_pdf_bboxes(
            candidate,
            page,
        )


def test_ocr_mapping_requires_valid_scale():
    page = {
        "page_number": 1,
        "text": "PAN ABCDE1234F",
        "source": "ocr",
        "fragments": [
            {
                "text": "ABCDE1234F",
                "start": 4,
                "end": 14,
                "bbox": (70.0, 20.0, 200.0, 40.0),
            },
        ],
    }

    candidate = {
        "entity_type": "PAN",
        "text": "ABCDE1234F",
        "start": 4,
        "end": 14,
    }

    with pytest.raises(PositionedPageProcessingError):
        map_candidate_to_pdf_bboxes(
            candidate,
            page,
            scale_x=0,
            scale_y=2.0,
        )