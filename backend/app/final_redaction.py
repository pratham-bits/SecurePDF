from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import pymupdf

from app.redaction import redact_pdf


if TYPE_CHECKING:
    from app.document_processor import ProcessedCandidate


class FinalRedactionError(Exception):
    """Raised when final PDF redaction cannot be completed."""


def build_final_redaction_boxes(
    candidates: Iterable["ProcessedCandidate"],
) -> dict[
    int,
    list[tuple[float, float, float, float]],
]:
    """
    Build page-level redaction geometry from final REDACT candidates.

    Only candidates whose final action is REDACT are included.

    REVIEW candidates are rejected because final processing must
    happen only after all review decisions have been resolved.
    """

    page_boxes: dict[
        int,
        list[tuple[float, float, float, float]],
    ] = {}

    for candidate in candidates:
        action = candidate["action"]

        if action == "REVIEW":
            raise FinalRedactionError(
                "Cannot perform final redaction while REVIEW "
                "candidates remain unresolved."
            )

        if action == "KEEP":
            continue

        if action != "REDACT":
            raise FinalRedactionError(
                f"Unsupported final candidate action: {action}"
            )

        page_number = candidate["page_number"]
        bounding_boxes = candidate["bounding_boxes"]

        if not bounding_boxes:
            raise FinalRedactionError(
                "REDACT candidate contains no bounding boxes."
            )

        page_boxes.setdefault(
            page_number,
            [],
        ).extend(bounding_boxes)

    return page_boxes


def verify_redacted_pdf(
    output_path: str | Path,
    redacted_texts: Iterable[str],
) -> None:
    """
    Verify that the generated PDF exists, is readable, and no longer
    contains the text values that were approved for redaction.

    This verifies extracted PDF text. It is an application-level
    verification and not a complete forensic guarantee against every
    possible embedded-data recovery technique.
    """

    output_file = Path(output_path)

    if not output_file.exists():
        raise FinalRedactionError(
            "Redacted PDF was not created."
        )

    if not output_file.is_file():
        raise FinalRedactionError(
            "Redacted PDF output path is not a file."
        )

    try:
        document = pymupdf.open(output_file)

        try:
            if document.page_count <= 0:
                raise FinalRedactionError(
                    "Redacted PDF contains no pages."
                )

            extracted_text = "\n".join(
                page.get_text("text")
                for page in document
            )

        finally:
            document.close()

    except FinalRedactionError:
        raise

    except Exception as exc:
        raise FinalRedactionError(
            "Unable to read generated redacted PDF."
        ) from exc

    for text in redacted_texts:
        if text and text in extracted_text:
            raise FinalRedactionError(
                "Redacted text was still found in the generated PDF."
            )


def finalize_redaction(
    input_path: str | Path,
    output_path: str | Path,
    candidates: Iterable["ProcessedCandidate"],
    *,
    padding: float = 0.0,
) -> Path:
    """
    Apply final candidate decisions to the input PDF and verify output.

    All candidates must already have final actions:

        REDACT
        KEEP

    REVIEW candidates are rejected.
    """

    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.exists():
        raise FinalRedactionError(
            "Input PDF file not found."
        )

    if not input_file.is_file():
        raise FinalRedactionError(
            "Input PDF path is not a file."
        )

    if input_file.resolve() == output_file.resolve():
        raise FinalRedactionError(
            "Input and output paths must be different."
        )

    candidate_list = list(candidates)

    page_boxes = build_final_redaction_boxes(
        candidate_list
    )

    redacted_texts = [
        candidate["text"]
        for candidate in candidate_list
        if candidate["action"] == "REDACT"
    ]

    # No REDACT candidates is a valid final state.
    #
    # For example:
    #
    #     KEEP
    #     KEEP
    #
    # means there is simply nothing to redact.
    if not page_boxes:
        return input_file

    try:
        redact_pdf(
            input_file,
            output_file,
            page_boxes,
            padding=padding,
        )
    except Exception as exc:
        raise FinalRedactionError(
            "Unable to create final redacted PDF."
        ) from exc

    verify_redacted_pdf(
        output_file,
        redacted_texts,
    )

    return output_file