import math

import pytest

from app.redaction_geometry import (
    RedactionGeometryError,
    expand_bbox,
    validate_bbox,
    validate_bbox_within_page,
    validate_page_geometry,
)


PAGE = {
    "width": 595.0,
    "height": 842.0,
}


def test_valid_bbox_is_accepted():
    bbox = (100.0, 100.0, 200.0, 120.0)

    assert validate_bbox(bbox) == bbox


def test_invalid_bbox_length_is_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_bbox((100.0, 100.0, 200.0))


def test_non_numeric_bbox_is_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_bbox(("a", 100.0, 200.0, 120.0))


def test_nan_bbox_is_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_bbox((100.0, math.nan, 200.0, 120.0))


def test_infinite_bbox_is_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_bbox((100.0, 100.0, math.inf, 120.0))


def test_zero_width_bbox_is_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_bbox((100.0, 100.0, 100.0, 120.0))


def test_zero_height_bbox_is_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_bbox((100.0, 100.0, 200.0, 100.0))


def test_page_geometry_is_validated():
    assert validate_page_geometry(PAGE) == PAGE


def test_invalid_page_dimensions_are_rejected():
    with pytest.raises(RedactionGeometryError):
        validate_page_geometry({
            "width": 0,
            "height": 842,
        })


def test_bbox_inside_page_is_accepted():
    bbox = (100.0, 100.0, 200.0, 120.0)

    assert validate_bbox_within_page(bbox, PAGE) == bbox


def test_bbox_outside_page_is_rejected():
    bbox = (100.0, 100.0, 700.0, 120.0)

    with pytest.raises(RedactionGeometryError):
        validate_bbox_within_page(bbox, PAGE)


def test_padding_expands_bbox():
    bbox = (100.0, 100.0, 200.0, 120.0)

    assert expand_bbox(bbox, 5.0, PAGE) == (
        95.0,
        95.0,
        205.0,
        125.0,
    )


def test_padding_is_clipped_to_page_boundaries():
    bbox = (2.0, 3.0, 20.0, 25.0)

    assert expand_bbox(bbox, 10.0, PAGE) == (
        0.0,
        0.0,
        30.0,
        35.0,
    )


def test_negative_padding_is_rejected():
    bbox = (100.0, 100.0, 200.0, 120.0)

    with pytest.raises(RedactionGeometryError):
        expand_bbox(bbox, -1.0, PAGE)


def test_non_numeric_padding_is_rejected():
    bbox = (100.0, 100.0, 200.0, 120.0)

    with pytest.raises(RedactionGeometryError):
        expand_bbox(bbox, "invalid", PAGE)