from typing import Iterable, TypedDict, TYPE_CHECKING


if TYPE_CHECKING:
    from app.document_processor import ProcessedCandidate


class FinalProcessingResult(TypedDict):
    redaction_candidates: list["ProcessedCandidate"]
    review_candidates: list["ProcessedCandidate"]
    kept_candidates: list["ProcessedCandidate"]
    review_required: bool


class FinalProcessingError(Exception):
    """Raised when final processing decisions are invalid."""


def categorize_final_candidates(
    candidates: Iterable["ProcessedCandidate"],
) -> tuple[
    list["ProcessedCandidate"],
    list["ProcessedCandidate"],
    list["ProcessedCandidate"],
]:
    """
    Categorize candidates according to their final actions.

    Returns:
        redaction_candidates,
        review_candidates,
        kept_candidates
    """

    redaction_candidates: list["ProcessedCandidate"] = []
    review_candidates: list["ProcessedCandidate"] = []
    kept_candidates: list["ProcessedCandidate"] = []

    for candidate in candidates:
        action = candidate["action"]

        if action == "REDACT":
            redaction_candidates.append(candidate)

        elif action == "REVIEW":
            review_candidates.append(candidate)

        elif action == "KEEP":
            kept_candidates.append(candidate)

        else:
            raise FinalProcessingError(
                f"Unsupported final candidate action: {action}"
            )

    return (
        redaction_candidates,
        review_candidates,
        kept_candidates,
    )


def finalize_processing_candidates(
    candidates: Iterable["ProcessedCandidate"],
) -> FinalProcessingResult:
    """
    Determine whether candidates are ready for final PDF processing.

    REVIEW candidates block final PDF generation until the user
    explicitly resolves them.
    """

    (
        redaction_candidates,
        review_candidates,
        kept_candidates,
    ) = categorize_final_candidates(candidates)

    return {
        "redaction_candidates": redaction_candidates,
        "review_candidates": review_candidates,
        "kept_candidates": kept_candidates,
        "review_required": bool(review_candidates),
    }