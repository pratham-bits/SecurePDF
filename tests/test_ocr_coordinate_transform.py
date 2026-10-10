import pytest

from app.ocr_coordinate_transform import (
    OCRCoordinateTransformError,
    transform_ocr_bbox_to_pdf,
    transform_ocr_bboxes_to_pdf,
)


def test_transforms_bbox_using_uniform_scale():
    result = transform_ocr_bbox_to_pdf(
        (200.0, 300.0, 400.0, 500.0),
        scale_x=2.0,
        scale_y=2.0,
    )

    assert result == (
        100.0,
        150.0,
        200.0,
        250.0,
    )


def test_transforms_bbox_using_non_uniform_scale():
    result = transform_ocr_bbox_to_pdf(
        (200.0, 300.0, 600.0, 900.0),
        scale_x=2.0,
        scale_y=3.0,
    )

    assert result == (
        100.0,
        100.0,
        300.0,
        300.0,
    )


def test_transforms_multiple_bboxes():
    result = transform_ocr_bboxes_to_pdf(
        [
            (20.0, 40.0, 60.0, 80.0),
            (100.0, 120.0, 200.0, 240.0),
        ],
        scale_x=2.0,
        scale_y=2.0,
    )

    assert result == [
        (10.0, 20.0, 30.0, 40.0),
        (50.0, 60.0, 100.0, 120.0),
    ]


@pytest.mark.parametrize(
    "scale_x,scale_y",
    [
        (0, 2.0),
        (-1, 2.0),
        (2.0, 0),
        (2.0, -1),
    ],
)
def test_rejects_non_positive_scale(scale_x, scale_y):
    with pytest.raises(OCRCoordinateTransformError):
        transform_ocr_bbox_to_pdf(
            (10.0, 10.0, 20.0, 20.0),
            scale_x=scale_x,
            scale_y=scale_y,
        )


def test_rejects_non_finite_scale():
    with pytest.raises(OCRCoordinateTransformError):
        transform_ocr_bbox_to_pdf(
            (10.0, 10.0, 20.0, 20.0),
            scale_x=float("inf"),
            scale_y=2.0,
        )


@pytest.mark.parametrize(
    "bbox",
    [
        (10.0, 10.0, 10.0, 20.0),
        (10.0, 20.0, 20.0, 20.0),
        (20.0, 20.0, 10.0, 30.0),
        (10.0, 20.0, 30.0, 10.0),
    ],
)
def test_rejects_invalid_bbox(bbox):
    with pytest.raises(OCRCoordinateTransformError):
        transform_ocr_bbox_to_pdf(
            bbox,
            scale_x=2.0,
            scale_y=2.0,
        )


def test_transformed_bbox_preserves_order_and_positive_dimensions():
    result = transform_ocr_bbox_to_pdf(
        (101.0, 201.0, 301.0, 401.0),
        scale_x=2.0,
        scale_y=2.0,
    )

    assert result[0] < result[2]
    assert result[1] < result[3]


def test_scale_one_preserves_coordinates():
    bbox = (10.0, 20.0, 30.0, 40.0)

    result = transform_ocr_bbox_to_pdf(
        bbox,
        scale_x=1.0,
        scale_y=1.0,
    )

    assert result == bbox