import re
from typing import Pattern, TypedDict


class PIICandidate(TypedDict):
    entity_type: str
    text: str
    confidence: float
    source: str
    start: int
    end: int


class PIIRuleError(Exception):
    """Raised when rule-based PII detection cannot be completed."""


class PIIRule:
    """Definition of a deterministic PII detection rule."""

    def __init__(
        self,
        entity_type: str,
        pattern: Pattern[str],
        confidence: float = 1.0,
    ) -> None:
        self.entity_type = entity_type
        self.pattern = pattern
        self.confidence = confidence


# Email addresses.
EMAIL_RULE = PIIRule(
    entity_type="EMAIL",
    pattern=re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
)

# Indian mobile numbers.
#
# Supports common forms such as:
#   9876543210
#   +91 9876543210
#   +91-9876543210
#   98765 43210
PHONE_RULE = PIIRule(
    entity_type="PHONE",
    pattern=re.compile(
        r"(?<!\d)"
        r"(?:\+91[\s-]?)?"
        r"[6-9]\d{4}[\s-]?\d{5}"
        r"(?!\d)"
    ),
)

# Indian Aadhaar number.
#
# Aadhaar is represented as 12 digits, commonly written as:
#   123456789012
#   1234 5678 9012
#   1234-5678-9012
AADHAAR_RULE = PIIRule(
    entity_type="AADHAAR",
    pattern=re.compile(
        r"(?<!\d)"
        r"\d{4}[\s-]?\d{4}[\s-]?\d{4}"
        r"(?!\d)"
    ),
)

# Indian PAN format.
#
# Example:
#   ABCDE1234F
PAN_RULE = PIIRule(
    entity_type="PAN",
    pattern=re.compile(
        r"(?<![A-Za-z0-9])"
        r"[A-Z]{5}\d{4}[A-Z]"
        r"(?![A-Za-z0-9])"
    ),
)


DEFAULT_PII_RULES = (
    EMAIL_RULE,
    PHONE_RULE,
    AADHAAR_RULE,
    PAN_RULE,
)


def detect_pii_with_rules(
    text: str,
    rules: tuple[PIIRule, ...] = DEFAULT_PII_RULES,
) -> list[PIICandidate]:
    """
    Detect deterministic PII patterns in a text string.

    Returns all matching PII candidates with their character
    positions in the supplied text.
    """
    if not isinstance(text, str):
        raise PIIRuleError("PII detection input must be text.")

    candidates: list[PIICandidate] = []

    for rule in rules:
        for match in rule.pattern.finditer(text):
            candidates.append(
                {
                    "entity_type": rule.entity_type,
                    "text": match.group(0),
                    "confidence": rule.confidence,
                    "source": "regex",
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    candidates.sort(key=lambda candidate: (candidate["start"], candidate["end"]))

    return candidates