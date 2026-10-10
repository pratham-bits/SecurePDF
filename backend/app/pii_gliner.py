from typing import Any, TypedDict

from gliner import GLiNER


MODEL_NAME = "urchade/gliner_multi_pii-v1"


DEFAULT_LABELS = (
    "person",
    "address",
    "email",
    "phone number",
    "passport number",
    "driver's license number",
    "credit card number",
    "bank account number",
    "social security number",
    "tax identification number",
    "national id number",
    "date of birth",
    "health insurance id number",
    "medical record number",
    "employee id number",
    "insurance number",
    "ip address",
    "vehicle registration number",
    "license plate number",
    "digital signature",
)


class ContextualPIICandidate(TypedDict):
    entity_type: str
    text: str
    confidence: float
    source: str
    start: int
    end: int


class GLiNERError(Exception):
    """Raised when contextual PII detection cannot be completed."""


class GLiNERPIIDetector:
    """Contextual PII detector backed by GLiNER Multi-PII."""

    def __init__(
        self,
        model_name: str = MODEL_NAME,
    ) -> None:
        try:
            self._model = GLiNER.from_pretrained(model_name)
        except Exception as exc:
            raise GLiNERError(
                "Unable to initialize contextual PII detector."
            ) from exc

    def detect(
        self,
        text: str,
        labels: tuple[str, ...] = DEFAULT_LABELS,
        threshold: float = 0.5,
    ) -> list[ContextualPIICandidate]:
        """
        Detect contextual PII entities in text.

        Returns candidates with character offsets and confidence.
        This method does not make a redaction decision.
        """
        if not isinstance(text, str):
            raise GLiNERError("PII detection input must be text.")

        if not text.strip():
            return []

        if not labels:
            raise GLiNERError("At least one entity label is required.")

        if not 0.0 <= threshold <= 1.0:
            raise GLiNERError("Detection threshold must be between 0 and 1.")

        try:
            entities = self._model.predict_entities(
                text,
                list(labels),
                threshold=threshold,
            )
        except Exception as exc:
            raise GLiNERError(
                "Unable to perform contextual PII detection."
            ) from exc

        candidates: list[ContextualPIICandidate] = []

        for entity in entities:
            try:
                entity_text = entity["text"]
                label = entity["label"]
                score = float(entity["score"])
                start = int(entity["start"])
                end = int(entity["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise GLiNERError(
                    "Unable to parse contextual PII result."
                ) from exc

            if not isinstance(entity_text, str) or not entity_text.strip():
                continue

            candidates.append(
                {
                    "entity_type": label,
                    "text": entity_text,
                    "confidence": score,
                    "source": "gliner",
                    "start": start,
                    "end": end,
                }
            )

        candidates.sort(
            key=lambda candidate: (
                candidate["start"],
                candidate["end"],
            )
        )

        return candidates