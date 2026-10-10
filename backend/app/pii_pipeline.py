from typing import TypedDict

from app.pii_gliner import GLiNERPIIDetector
from app.pii_resolution import (
    UnifiedPIICandidate,
    resolve_pii_candidates,
)
from app.pii_rules import detect_pii_with_rules
from app.redaction_policy import (
    RedactionDecision,
    RedactionPolicy,
    decide_redaction,
)


class PagePIIResult(TypedDict):
    page_number: int
    text: str
    candidates: list[RedactionDecision]
    redaction_candidates: list[RedactionDecision]
    review_candidates: list[RedactionDecision]


class PIIPipelineError(Exception):
    """Raised when the PII detection and policy pipeline fails."""


def process_page_pii(
    page_number: int,
    text: str,
    gliner_detector: GLiNERPIIDetector,
    policy: RedactionPolicy | None = None,
) -> PagePIIResult:
    """
    Detect, resolve, and apply policy to PII on a single page.

    The function does not modify the source text or PDF.
    """

    if not isinstance(page_number, int) or page_number < 1:
        raise PIIPipelineError("Page number must be a positive integer.")

    if not isinstance(text, str):
        raise PIIPipelineError("Page text must be a string.")

    if gliner_detector is None:
        raise PIIPipelineError("A GLiNER detector is required.")

    if not text.strip():
        return {
            "page_number": page_number,
            "text": text,
            "candidates": [],
            "redaction_candidates": [],
            "review_candidates": [],
        }

    try:
        regex_candidates = detect_pii_with_rules(text)

        gliner_candidates = gliner_detector.detect(text)

        resolved_candidates = resolve_pii_candidates(
            regex_candidates + gliner_candidates
        )
    except Exception as exc:
        raise PIIPipelineError(
            "Unable to detect or resolve PII candidates."
        ) from exc

    decisions: list[RedactionDecision] = []

    for candidate in resolved_candidates:
        try:
            decision = decide_redaction(
                candidate,
                context=text,
                policy=policy,
            )
        except Exception as exc:
            raise PIIPipelineError(
                "Unable to apply PII redaction policy."
            ) from exc

        decisions.append(decision)

    redaction_candidates = [
        decision
        for decision in decisions
        if decision["action"] == "REDACT"
    ]

    review_candidates = [
        decision
        for decision in decisions
        if decision["action"] == "REVIEW"
    ]

    return {
        "page_number": page_number,
        "text": text,
        "candidates": decisions,
        "redaction_candidates": redaction_candidates,
        "review_candidates": review_candidates,
    }