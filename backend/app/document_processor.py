from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pymupdf

from app.final_processing import finalize_processing_candidates
from app.mixed_positioned_extraction import extract_mixed_positioned_pages
from app.ocr import OCREngine
from app.ocr_positioned import extract_positioned_ocr_from_pdf
from app.pii_gliner import GLiNERPIIDetector
from app.pii_resolution import resolve_pii_candidates
from app.pii_rules import detect_pii_with_rules
from app.positioned_extraction import (
    BBox,
    PositionedPage,
    extract_positioned_text_from_pdf,
)
from app.positioned_page_processing import map_candidate_to_pdf_bboxes
from app.redaction import redact_pdf
from app.redaction_policy import (
    RedactionDecision,
    RedactionPolicy,
    decide_redaction,
)

class DocumentProcessingError(Exception):
    """Raised when end-to-end document processing fails."""


class ProcessedCandidate(TypedDict):
    candidate_id: str
    entity_type: str
    text: str
    confidence: float
    source: str
    start: int
    end: int
    sensitivity: str
    action: str
    reason: str
    page_number: int
    bounding_boxes: list[BBox]


class ProcessedDocumentResult(TypedDict):
    input_path: str
    output_path: str | None
    pages_processed: int

    detected_entities: int
    redacted_entities: int
    review_entities: int
    kept_entities: int

    review_required: bool

    detected_candidates: list[ProcessedCandidate]
    redacted_candidates: list[ProcessedCandidate]
    review_candidates: list[ProcessedCandidate]
    kept_candidates: list[ProcessedCandidate]


def _build_positioned_pages(
    pdf_path: str | Path,
) -> list[PositionedPage]:
    """Extract digital PDF text together with positional information."""

    try:
        return extract_positioned_text_from_pdf(pdf_path)
    except Exception as exc:
        raise DocumentProcessingError(
            "Unable to extract positioned text from PDF."
        ) from exc


def _build_scanned_positioned_pages(
    pdf_path: str | Path,
    *,
    ocr_engine: OCREngine | None = None,
    ocr_scale: float = 2.0,
):
    """Extract scanned PDF text and OCR coordinates."""

    if ocr_scale <= 0:
        raise DocumentProcessingError(
            "OCR scale must be greater than zero."
        )

    try:
        return extract_positioned_ocr_from_pdf(
            pdf_path,
            ocr_engine=ocr_engine,
            scale=ocr_scale,
        )
    except Exception as exc:
        raise DocumentProcessingError(
            "Unable to extract positioned OCR data from scanned PDF."
        ) from exc


def _detect_page_candidates(
    page_number: int,
    text: str,
    gliner_detector: GLiNERPIIDetector,
    policy: RedactionPolicy,
) -> list[RedactionDecision]:
    """Detect, resolve, and classify PII candidates on one page."""

    if not isinstance(page_number, int) or page_number < 1:
        raise DocumentProcessingError(
            "Page number must be a positive integer."
        )

    if not isinstance(text, str):
        raise DocumentProcessingError(
            "Page text must be a string."
        )

    if not text.strip():
        return []

    regex_candidates = detect_pii_with_rules(text)

    gliner_candidates = gliner_detector.detect(text)

    resolved_candidates = resolve_pii_candidates(
        regex_candidates + gliner_candidates
    )

    return [
        decide_redaction(
            candidate,
            context=text,
            policy=policy,
        )
        for candidate in resolved_candidates
    ]


def _build_processed_candidate(
    decision: RedactionDecision,
    page: Any,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> ProcessedCandidate:
    """Convert a policy decision into a coordinate-aware candidate."""

    try:
        bounding_boxes = map_candidate_to_pdf_bboxes(
            decision,
            page,
            scale_x=scale_x,
            scale_y=scale_y,
        )
    except Exception as exc:
        raise DocumentProcessingError(
            f"Unable to map candidate coordinates for page "
            f"{page['page_number']}."
        ) from exc

    return {
        "candidate_id": str(uuid4()),
        "entity_type": decision["entity_type"],
        "text": decision["text"],
        "confidence": decision["confidence"],
        "source": decision["source"],
        "start": decision["start"],
        "end": decision["end"],
        "sensitivity": decision["sensitivity"],
        "action": decision["action"],
        "reason": decision["reason"],
        "page_number": page["page_number"],
        "bounding_boxes": bounding_boxes,
    }


def _verify_output_pdf(
    output_file: Path,
) -> None:
    """Verify that the generated PDF exists and can be opened."""

    if not output_file.exists():
        raise DocumentProcessingError(
            "Redacted PDF was not created."
        )

    if not output_file.is_file():
        raise DocumentProcessingError(
            "Redacted PDF output path is not a file."
        )

    try:
        document = pymupdf.open(output_file)

        try:
            if document.page_count <= 0:
                raise DocumentProcessingError(
                    "Generated redacted PDF contains no pages."
                )
        finally:
            document.close()

    except DocumentProcessingError:
        raise

    except Exception as exc:
        raise DocumentProcessingError(
            "Generated redacted PDF is not readable."
        ) from exc


def _validate_processing_paths(
    input_path: str | Path,
    output_path: str | Path,
) -> tuple[Path, Path]:
    """Validate common input/output PDF path requirements."""

    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        raise DocumentProcessingError(
            "Input PDF file not found."
        )

    if not input_file.is_file():
        raise DocumentProcessingError(
            "Input PDF path is not a file."
        )

    if input_file.resolve() == output_file.resolve():
        raise DocumentProcessingError(
            "Input and output paths must be different."
        )

    return input_file, output_file


def _process_positioned_pdf(
    input_file: Path,
    output_file: Path,
    positioned_pages,
    *,
    gliner_detector: GLiNERPIIDetector,
    policy: RedactionPolicy,
    padding: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> ProcessedDocumentResult:
    """
    Run the common PII processing workflow for positioned PDF pages.

    The input pages may originate from either:
    - digital text extraction, or
    - OCR extraction.

    Coordinates are normalized to PDF space before redaction.
    """

    detected_candidates: list[ProcessedCandidate] = []

    for page in positioned_pages:
        decisions = _detect_page_candidates(
            page["page_number"],
            page["text"],
            gliner_detector,
            policy,
        )

        for decision in decisions:
            processed_candidate = _build_processed_candidate(
                decision,
                page,
                scale_x=scale_x,
                scale_y=scale_y,
            )

            detected_candidates.append(
                processed_candidate
            )

    finalized = finalize_processing_candidates(
        detected_candidates
    )

    redaction_candidates = finalized["redaction_candidates"]
    review_candidates = finalized["review_candidates"]
    kept_candidates = finalized["kept_candidates"]

    # ---------------------------------------------------------------
    # Review is required.
    #
    # Do not modify or generate the PDF until the user has resolved
    # every REVIEW candidate.
    # ---------------------------------------------------------------

    if finalized["review_required"]:
        return {
            "input_path": str(input_file),
            "output_path": None,
            "pages_processed": len(positioned_pages),
            "detected_entities": len(detected_candidates),
            "redacted_entities": len(redaction_candidates),
            "review_entities": len(review_candidates),
            "kept_entities": len(kept_candidates),
            "review_required": True,
            "detected_candidates": detected_candidates,
            "redacted_candidates": redaction_candidates,
            "review_candidates": review_candidates,
            "kept_candidates": kept_candidates,
        }

    # ---------------------------------------------------------------
    # Build PDF redaction geometry.
    # ---------------------------------------------------------------

    page_boxes: dict[int, list[BBox]] = {}

    for candidate in redaction_candidates:
        page_boxes.setdefault(
            candidate["page_number"],
            [],
        ).extend(
            candidate["bounding_boxes"]
        )

    # ---------------------------------------------------------------
    # Nothing requires redaction.
    # ---------------------------------------------------------------

    if not page_boxes:
        return {
            "input_path": str(input_file),
            "output_path": None,
            "pages_processed": len(positioned_pages),
            "detected_entities": len(detected_candidates),
            "redacted_entities": 0,
            "review_entities": 0,
            "kept_entities": len(kept_candidates),
            "review_required": False,
            "detected_candidates": detected_candidates,
            "redacted_candidates": [],
            "review_candidates": [],
            "kept_candidates": kept_candidates,
        }

    # ---------------------------------------------------------------
    # Create final redacted PDF.
    # ---------------------------------------------------------------

    try:
        redact_pdf(
            input_file,
            output_file,
            page_boxes,
            padding=padding,
        )
    except Exception as exc:
        raise DocumentProcessingError(
            "Unable to create redacted PDF."
        ) from exc

    # ---------------------------------------------------------------
    # Verify generated PDF.
    # ---------------------------------------------------------------

    _verify_output_pdf(output_file)

    return {
        "input_path": str(input_file),
        "output_path": str(output_file),
        "pages_processed": len(positioned_pages),
        "detected_entities": len(detected_candidates),
        "redacted_entities": len(redaction_candidates),
        "review_entities": 0,
        "kept_entities": len(kept_candidates),
        "review_required": False,
        "detected_candidates": detected_candidates,
        "redacted_candidates": redaction_candidates,
        "review_candidates": [],
        "kept_candidates": kept_candidates,
    }


def process_digital_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    gliner_detector: GLiNERPIIDetector | None = None,
    policy: RedactionPolicy | None = None,
    padding: float = 0.0,
) -> ProcessedDocumentResult:
    """
    Run the digital-PDF PII detection and processing workflow.

    Workflow:

    1. Extract positioned machine-readable text.
    2. Detect PII using Regex/Rules and GLiNER.
    3. Resolve duplicate and overlapping candidates.
    4. Apply the redaction policy.
    5. Map candidates to PDF coordinates.
    6. Determine whether user review is required.
    7. Create a redacted PDF only when no REVIEW candidates remain.

    The input PDF is never modified.

    If one or more candidates require review, no output PDF is created.
    The complete candidate set is returned for the later review workflow.
    """

    input_file, output_file = _validate_processing_paths(
        input_path,
        output_path,
    )

    detector = gliner_detector or GLiNERPIIDetector()
    active_policy = policy or RedactionPolicy()

    positioned_pages = _build_positioned_pages(
        input_file
    )

    return _process_positioned_pdf(
        input_file,
        output_file,
        positioned_pages,
        gliner_detector=detector,
        policy=active_policy,
        padding=padding,
        scale_x=1.0,
        scale_y=1.0,
    )


def process_scanned_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    gliner_detector: GLiNERPIIDetector | None = None,
    policy: RedactionPolicy | None = None,
    ocr_engine: OCREngine | None = None,
    ocr_scale: float = 2.0,
    padding: float = 0.0,
) -> ProcessedDocumentResult:
    """
    Run the scanned-PDF PII detection and processing workflow.

    Workflow:

    1. Render scanned PDF pages.
    2. Run positioned PaddleOCR.
    3. Detect PII using Regex/Rules and GLiNER.
    4. Resolve duplicate and overlapping candidates.
    5. Apply the redaction policy.
    6. Map OCR coordinates into PDF coordinates.
    7. Determine whether user review is required.
    8. Create a redacted PDF only when no REVIEW candidates remain.

    OCR coordinates are converted to PDF coordinates using the same
    rendering scale used during OCR.

    The input PDF is never modified.

    If one or more candidates require review, no output PDF is created.
    The complete candidate set is returned for the later review workflow.
    """

    input_file, output_file = _validate_processing_paths(
        input_path,
        output_path,
    )

    if ocr_scale <= 0:
        raise DocumentProcessingError(
            "OCR scale must be greater than zero."
        )

    detector = gliner_detector or GLiNERPIIDetector()
    active_policy = policy or RedactionPolicy()
    engine = ocr_engine or OCREngine()

    positioned_pages = _build_scanned_positioned_pages(
        input_file,
        ocr_engine=engine,
        ocr_scale=ocr_scale,
    )

    return _process_positioned_pdf(
        input_file,
        output_file,
        positioned_pages,
        gliner_detector=detector,
        policy=active_policy,
        padding=padding,
        scale_x=ocr_scale,
        scale_y=ocr_scale,
    )

def process_mixed_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    gliner_detector: GLiNERPIIDetector | None = None,
    policy: RedactionPolicy | None = None,
    ocr_engine: OCREngine | None = None,
    ocr_scale: float = 2.0,
    padding: float = 0.0,
) -> ProcessedDocumentResult:
    """
    Run the PII detection and processing workflow for a mixed PDF.

    Each page is processed independently:

    - machine-readable pages use PyMuPDF
    - image-only pages use PaddleOCR

    Both extraction paths produce positioned pages which then enter
    the same PII detection, resolution, policy, review, coordinate,
    and redaction pipeline.

    OCR coordinates are converted to PDF coordinates using the same
    scale used during OCR rendering.

    The input PDF is never modified.

    If one or more candidates require review, no output PDF is created.
    The complete candidate set is returned for the later review workflow.
    """

    input_file, output_file = _validate_processing_paths(
        input_path,
        output_path,
    )

    if ocr_scale <= 0:
        raise DocumentProcessingError(
            "OCR scale must be greater than zero."
        )

    detector = gliner_detector or GLiNERPIIDetector()
    active_policy = policy or RedactionPolicy()
    engine = ocr_engine or OCREngine()

    try:
        positioned_pages = extract_mixed_positioned_pages(
            input_file,
            ocr_engine=engine,
            ocr_scale=ocr_scale,
        )
    except Exception as exc:
        raise DocumentProcessingError(
            "Unable to extract positioned content from mixed PDF."
        ) from exc

    return _process_positioned_pdf(
        input_file,
        output_file,
        positioned_pages,
        gliner_detector=detector,
        policy=active_policy,
        padding=padding,
        scale_x=ocr_scale,
        scale_y=ocr_scale,
    )