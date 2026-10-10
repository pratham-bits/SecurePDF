from typing import TypedDict


class UnifiedPIICandidate(TypedDict):
    entity_type: str
    text: str
    confidence: float
    source: str
    start: int
    end: int


ENTITY_TYPE_MAP = {
    # GLiNER labels
    "person": "PERSON",
    "address": "ADDRESS",
    "email": "EMAIL",
    "phone number": "PHONE",
    "passport number": "PASSPORT",
    "driver's license number": "DRIVER_LICENSE",
    "credit card number": "CREDIT_CARD",
    "bank account number": "BANK_ACCOUNT",
    "social security number": "SSN",
    "tax identification number": "TAX_ID",
    "national id number": "NATIONAL_ID",
    "date of birth": "DATE_OF_BIRTH",
    "health insurance id number": "HEALTH_INSURANCE_ID",
    "medical record number": "MEDICAL_RECORD_NUMBER",
    "employee id number": "EMPLOYEE_ID",
    "insurance number": "INSURANCE_NUMBER",
    "ip address": "IP_ADDRESS",
    "vehicle registration number": "VEHICLE_REGISTRATION",
    "license plate number": "LICENSE_PLATE",
    "digital signature": "DIGITAL_SIGNATURE",

    # Regex labels
    "pan": "PAN",
    "aadhaar": "AADHAAR",
    "phone": "PHONE",
}


class PIIResolutionError(Exception):
    """Raised when PII candidates cannot be normalized or resolved."""


def normalize_entity_type(entity_type: str) -> str:
    """
    Convert detector-specific labels into SecurePDF canonical types.
    """
    if not isinstance(entity_type, str):
        raise PIIResolutionError("Entity type must be a string.")

    normalized = ENTITY_TYPE_MAP.get(
        entity_type.strip().lower()
    )

    if normalized is None:
        raise PIIResolutionError(
            f"Unsupported PII entity type: {entity_type}"
        )

    return normalized


def normalize_candidate(candidate: dict) -> UnifiedPIICandidate:
    """Convert a detector result into the SecurePDF candidate format."""

    required_fields = (
        "entity_type",
        "text",
        "confidence",
        "source",
        "start",
        "end",
    )

    for field in required_fields:
        if field not in candidate:
            raise PIIResolutionError(
                f"PII candidate is missing field: {field}"
            )

    entity_type = normalize_entity_type(candidate["entity_type"])

    text = candidate["text"]

    if not isinstance(text, str) or not text.strip():
        raise PIIResolutionError("PII candidate text must be non-empty.")

    confidence = float(candidate["confidence"])
    start = int(candidate["start"])
    end = int(candidate["end"])

    if not 0.0 <= confidence <= 1.0:
        raise PIIResolutionError(
            "PII candidate confidence must be between 0 and 1."
        )

    if start < 0 or end <= start:
        raise PIIResolutionError(
            "PII candidate offsets are invalid."
        )

    return {
        "entity_type": entity_type,
        "text": text,
        "confidence": confidence,
        "source": str(candidate["source"]),
        "start": start,
        "end": end,
    }


def _overlaps(
    first: UnifiedPIICandidate,
    second: UnifiedPIICandidate,
) -> bool:
    """Return whether two character spans overlap."""
    return (
        first["start"] < second["end"]
        and second["start"] < first["end"]
    )


def _candidate_priority(candidate: UnifiedPIICandidate) -> tuple:
    """
    Rank candidates for overlap resolution.

    Longer spans are preferred because they usually carry more
    contextual information. Confidence is used as the secondary
    criterion.
    """
    span_length = candidate["end"] - candidate["start"]

    return (
        span_length,
        candidate["confidence"],
    )


def resolve_pii_candidates(
    candidates: list[dict],
) -> list[UnifiedPIICandidate]:
    """
    Normalize and resolve duplicate/overlapping PII candidates.

    The function does not decide whether candidates should be
    redacted.
    """
    normalized = [
        normalize_candidate(candidate)
        for candidate in candidates
    ]

    # Remove exact duplicates.
    unique: dict[tuple, UnifiedPIICandidate] = {}

    for candidate in normalized:
        key = (
            candidate["start"],
            candidate["end"],
            candidate["entity_type"],
            candidate["text"],
        )

        existing = unique.get(key)

        if existing is None or candidate["confidence"] > existing["confidence"]:
            unique[key] = candidate

    candidates_to_resolve = list(unique.values())

    # Prefer stronger candidates when spans overlap.
    candidates_to_resolve.sort(
        key=lambda candidate: (
            candidate["start"],
            candidate["end"],
        )
    )

    resolved: list[UnifiedPIICandidate] = []

    for candidate in candidates_to_resolve:
        overlapping = [
            existing
            for existing in resolved
            if _overlaps(candidate, existing)
        ]

        if not overlapping:
            resolved.append(candidate)
            continue

        strongest = max(
            [candidate, *overlapping],
            key=_candidate_priority,
        )

        if strongest is candidate:
            resolved = [
                existing
                for existing in resolved
                if existing not in overlapping
            ]
            resolved.append(candidate)

    resolved.sort(
        key=lambda candidate: (
            candidate["start"],
            candidate["end"],
        )
    )

    return resolved