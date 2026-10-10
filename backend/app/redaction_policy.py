from dataclasses import dataclass, field
from typing import Literal, TypedDict

from app.pii_resolution import UnifiedPIICandidate


PolicyAction = Literal["REDACT", "REVIEW", "KEEP"]
SensitivityLevel = Literal["HIGH", "MEDIUM", "CONTEXTUAL"]


class RedactionDecision(TypedDict):
    entity_type: str
    text: str
    confidence: float
    source: str
    start: int
    end: int
    sensitivity: SensitivityLevel
    action: PolicyAction
    reason: str


@dataclass(frozen=True)
class RedactionPolicy:
    """
    Configurable policy for deciding whether detected PII should be
    redacted automatically, reviewed by a user, or retained.

    Detection and policy are intentionally separated:
    detection identifies potential PII;
    this policy determines the appropriate action.
    """

    high_sensitivity_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "AADHAAR",
                "PAN",
                "SSN",
                "PASSPORT",
                "DRIVER_LICENSE",
                "CREDIT_CARD",
                "BANK_ACCOUNT",
                "TAX_ID",
                "NATIONAL_ID",
                "MEDICAL_RECORD_NUMBER",
                "HEALTH_INSURANCE_ID",
                "INSURANCE_NUMBER",
                "VEHICLE_REGISTRATION",
            }
        )
    )

    medium_sensitivity_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "DATE_OF_BIRTH",
                "EMPLOYEE_ID",
                "IP_ADDRESS",
                "LICENSE_PLATE",
                "DIGITAL_SIGNATURE",
            }
        )
    )

    contextual_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "PERSON",
                "ADDRESS",
                "EMAIL",
                "PHONE",
            }
        )
    )

    # Initial confidence required before automatic redaction.
    # Lower-confidence detections are sent to REVIEW instead.
    auto_redact_confidence: float = 0.50

    # Context words suggesting that a contact detail is intentionally
    # public/organizational rather than a private individual's information.
    public_contact_indicators: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "support",
                "customer support",
                "customer care",
                "helpline",
                "hotline",
                "helpdesk",
                "contact us",
                "contact",
                "sales",
                "info",
                "inquiries",
                "enquiries",
                "office",
                "reception",
                "head office",
                "registered office",
                "corporate office",
                "company",
                "organization",
                "organisation",
                "website",
            }
        )
    )

    private_context_indicators: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "personal",
                "private",
                "registered mobile",
                "registered phone",
                "personal email",
                "personal phone",
                "home address",
                "residential address",
                "residential",
                "applicant",
                "patient",
                "employee",
                "account holder",
                "beneficiary",
                "emergency contact",
                "authentication",
                "two-factor",
                "2fa",
                "verification",
            }
        )
    )


class RedactionPolicyError(Exception):
    """Raised when a redaction policy decision cannot be completed."""


def decide_redaction(
    candidate: UnifiedPIICandidate,
    context: str = "",
    policy: RedactionPolicy | None = None,
) -> RedactionDecision:
    """
    Decide whether a resolved PII candidate should be REDACTED,
    REVIEWED, or KEPT.

    The candidate itself is never modified.
    """

    if policy is None:
        policy = RedactionPolicy()

    _validate_candidate(candidate)

    normalized_context = context.strip().lower()

    entity_type = candidate["entity_type"]
    confidence = candidate["confidence"]

    if entity_type in policy.high_sensitivity_types:
        return _high_sensitivity_decision(
            candidate=candidate,
            policy=policy,
        )

    if entity_type in policy.medium_sensitivity_types:
        return _medium_sensitivity_decision(
            candidate=candidate,
            context=normalized_context,
            policy=policy,
        )

    if entity_type in policy.contextual_types:
        return _contextual_decision(
            candidate=candidate,
            context=normalized_context,
            policy=policy,
        )

    raise RedactionPolicyError(
        f"Unsupported policy entity type: {entity_type}"
    )


def _high_sensitivity_decision(
    candidate: UnifiedPIICandidate,
    policy: RedactionPolicy,
) -> RedactionDecision:
    confidence = candidate["confidence"]

    if confidence >= policy.auto_redact_confidence:
        action: PolicyAction = "REDACT"
        reason = (
            "High-sensitivity PII detected with sufficient confidence "
            "for automatic redaction."
        )
    else:
        action = "REVIEW"
        reason = (
            "High-sensitivity PII was detected, but confidence is below "
            "the automatic-redaction threshold."
        )

    return _build_decision(
        candidate=candidate,
        sensitivity="HIGH",
        action=action,
        reason=reason,
    )


def _medium_sensitivity_decision(
    candidate: UnifiedPIICandidate,
    context: str,
    policy: RedactionPolicy,
) -> RedactionDecision:
    confidence = candidate["confidence"]

    if _contains_indicator(
        context,
        policy.private_context_indicators,
    ):
        if confidence >= policy.auto_redact_confidence:
            return _build_decision(
                candidate=candidate,
                sensitivity="MEDIUM",
                action="REDACT",
                reason=(
                    "Context indicates that the information is associated "
                    "with a private or sensitive record."
                ),
            )

        return _build_decision(
            candidate=candidate,
            sensitivity="MEDIUM",
            action="REVIEW",
            reason=(
                "Context indicates potentially private information, "
                "but detection confidence is below the automatic threshold."
            ),
        )

    return _build_decision(
        candidate=candidate,
        sensitivity="MEDIUM",
        action="REVIEW",
        reason=(
            "Information may be personally identifying, but its sensitivity "
            "depends on document context."
        ),
    )


def _contextual_decision(
    candidate: UnifiedPIICandidate,
    context: str,
    policy: RedactionPolicy,
) -> RedactionDecision:
    confidence = candidate["confidence"]

    if _contains_indicator(
        context,
        policy.private_context_indicators,
    ):
        if confidence >= policy.auto_redact_confidence:
            return _build_decision(
                candidate=candidate,
                sensitivity="CONTEXTUAL",
                action="REDACT",
                reason=(
                    "Context indicates that this potentially identifying "
                    "information is being used in a private or sensitive context."
                ),
            )

        return _build_decision(
            candidate=candidate,
            sensitivity="CONTEXTUAL",
            action="REVIEW",
            reason=(
                "Private-context indicators were found, but detection "
                "confidence is below the automatic-redaction threshold."
            ),
        )

    if candidate["entity_type"] in {"EMAIL", "PHONE", "ADDRESS"}:
        if _contains_indicator(
            context,
            policy.public_contact_indicators,
        ):
            return _build_decision(
                candidate=candidate,
                sensitivity="CONTEXTUAL",
                action="KEEP",
                reason=(
                    "Context indicates that the contact information is "
                    "intended for public or organizational use."
                ),
            )

    return _build_decision(
        candidate=candidate,
        sensitivity="CONTEXTUAL",
        action="REVIEW",
        reason=(
            "The information may be PII, but the available context does not "
            "establish whether it should be automatically redacted."
        ),
    )


def _contains_indicator(
    context: str,
    indicators: frozenset[str],
) -> bool:
    return any(indicator in context for indicator in indicators)


def _build_decision(
    candidate: UnifiedPIICandidate,
    sensitivity: SensitivityLevel,
    action: PolicyAction,
    reason: str,
) -> RedactionDecision:
    return {
        "entity_type": candidate["entity_type"],
        "text": candidate["text"],
        "confidence": candidate["confidence"],
        "source": candidate["source"],
        "start": candidate["start"],
        "end": candidate["end"],
        "sensitivity": sensitivity,
        "action": action,
        "reason": reason,
    }


def _validate_candidate(candidate: UnifiedPIICandidate) -> None:
    required_fields = {
        "entity_type",
        "text",
        "confidence",
        "source",
        "start",
        "end",
    }

    missing_fields = required_fields - candidate.keys()

    if missing_fields:
        raise RedactionPolicyError(
            f"Candidate is missing required fields: {sorted(missing_fields)}"
        )

    if not isinstance(candidate["entity_type"], str):
        raise RedactionPolicyError("Entity type must be a string.")

    if not isinstance(candidate["text"], str) or not candidate["text"].strip():
        raise RedactionPolicyError("Candidate text must be non-empty.")

    confidence = candidate["confidence"]

    if not isinstance(confidence, (int, float)):
        raise RedactionPolicyError("Candidate confidence must be numeric.")

    if not 0.0 <= confidence <= 1.0:
        raise RedactionPolicyError(
            "Candidate confidence must be between 0 and 1."
        )

    start = candidate["start"]
    end = candidate["end"]

    if not isinstance(start, int) or not isinstance(end, int):
        raise RedactionPolicyError("Candidate offsets must be integers.")

    if start < 0 or end <= start:
        raise RedactionPolicyError("Candidate offsets are invalid.")