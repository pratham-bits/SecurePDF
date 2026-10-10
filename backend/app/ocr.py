from io import BytesIO
from typing import Any, TypedDict

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR


class OCRError(Exception):
    """Raised when OCR processing fails."""


class OCRPositionedResult(TypedDict):
    text: str
    bbox: tuple[float, float, float, float]


class OCREngine:
    """
    PaddleOCR-based OCR engine.

    The PaddleOCR implementation is intentionally encapsulated inside
    this class so callers do not need to access the underlying private
    PaddleOCR object.
    """

    def __init__(self):
        self._ocr = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )

    def recognize(
        self,
        image: bytes | np.ndarray,
    ) -> str:
        """
        Recognize text from an image.

        Returns normalized text only.
        """

        image_input = _prepare_image(image)

        try:
            results = self._ocr.predict(
                image_input,
            )
        except Exception as exc:
            raise OCRError(
                "PaddleOCR text recognition failed."
            ) from exc

        return _extract_text(results)

    def recognize_positioned(
        self,
        image: bytes | np.ndarray,
    ) -> list[OCRPositionedResult]:
        """
        Recognize text together with OCR bounding boxes.

        Each returned item contains the recognized text and its
        corresponding bounding box.

        This method provides the public positional OCR API used by
        SecurePDF's scanned-document processing pipeline.
        """

        image_input = _prepare_image(image)

        try:
            results = self._ocr.predict(
                image_input,
            )
        except Exception as exc:
            raise OCRError(
                "PaddleOCR positional recognition failed."
            ) from exc

        return _extract_positioned_results(results)


def _prepare_image(
    image: bytes | np.ndarray,
) -> bytes | np.ndarray:
    """
    Convert supported image inputs into PaddleOCR-compatible input.

    Bytes are decoded through Pillow and converted into an RGB
    NumPy array.
    """

    if isinstance(image, bytes):
        try:
            pil_image = Image.open(
                BytesIO(image)
            ).convert("RGB")
        except Exception as exc:
            raise OCRError(
                "Unable to decode OCR image."
            ) from exc

        return np.array(pil_image)

    if isinstance(image, np.ndarray):
        return image

    raise OCRError(
        "OCR image must be bytes or a NumPy array."
    )


def _extract_result_data(
    result: Any,
) -> dict[str, Any]:
    """
    Extract the JSON-like result dictionary returned by PaddleOCR.
    """

    try:
        result_data = result.json

        if callable(result_data):
            result_data = result_data()

    except Exception as exc:
        raise OCRError(
            "Unable to read PaddleOCR result."
        ) from exc

    if not isinstance(result_data, dict):
        raise OCRError(
            "PaddleOCR returned an unexpected result structure."
        )

    data = result_data.get(
        "res",
        result_data,
    )

    if not isinstance(data, dict):
        raise OCRError(
            "PaddleOCR result data is not a dictionary."
        )

    return data


def _extract_text(
    results: Any,
) -> str:
    """
    Extract recognized text from PaddleOCR results.
    """

    text_parts: list[str] = []

    for result in results:
        data = _extract_result_data(result)

        recognized_texts = data.get(
            "rec_texts",
            [],
        )

        for text in recognized_texts:
            if not isinstance(text, str):
                continue

            normalized_text = " ".join(
                text.split()
            )

            if normalized_text:
                text_parts.append(
                    normalized_text
                )

    return _normalize_text(
        " ".join(text_parts)
    )


def _extract_positioned_results(
    results: Any,
) -> list[OCRPositionedResult]:
    """
    Extract recognized text and bounding boxes from PaddleOCR.

    The PaddleOCR result is converted into a stable application-level
    representation so the rest of SecurePDF does not depend on the
    exact PaddleOCR response object.
    """

    positioned_results: list[OCRPositionedResult] = []

    for result in results:
        data = _extract_result_data(result)

        recognized_texts = data.get(
            "rec_texts",
            [],
        )

        recognized_boxes = data.get(
            "rec_boxes",
            [],
        )

        if not recognized_texts:
            continue

        if len(recognized_texts) != len(
            recognized_boxes
        ):
            raise OCRError(
                "OCR text and bounding-box counts do not match."
            )

        for text, bbox in zip(
            recognized_texts,
            recognized_boxes,
        ):
            if not isinstance(text, str):
                continue

            normalized_text = " ".join(
                text.split()
            )

            if not normalized_text:
                continue

            normalized_bbox = _normalize_bbox(
                bbox
            )

            positioned_results.append(
                {
                    "text": normalized_text,
                    "bbox": normalized_bbox,
                }
            )

    return positioned_results


def _normalize_bbox(
    bbox: Any,
) -> tuple[float, float, float, float]:
    """
    Validate and normalize an OCR bounding box.
    """

    try:
        values = [
            float(value)
            for value in bbox
        ]
    except (TypeError, ValueError) as exc:
        raise OCRError(
            "OCR returned an invalid bounding box."
        ) from exc

    if len(values) != 4:
        raise OCRError(
            "OCR bounding box must contain four coordinates."
        )

    x0, y0, x1, y1 = values

    if x1 <= x0 or y1 <= y0:
        raise OCRError(
            "OCR returned invalid bounding box geometry."
        )

    return (
        x0,
        y0,
        x1,
        y1,
    )


def _normalize_text(
    text: str,
) -> str:
    """Normalize basic whitespace without changing meaningful text."""

    return " ".join(
        text.split()
    )