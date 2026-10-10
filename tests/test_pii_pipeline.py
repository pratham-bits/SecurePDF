import unittest

from app.pii_pipeline import PIIPipelineError, process_page_pii
from app.redaction_policy import RedactionPolicy


class FakeGLiNERDetector:
    def __init__(self, candidates=None):
        self.candidates = candidates or []
        self.received_text = None

    def detect(self, text):
        self.received_text = text
        return self.candidates


def candidate(
    entity_type,
    text,
    confidence=0.95,
    source="gliner",
    start=0,
):
    return {
        "entity_type": entity_type,
        "text": text,
        "confidence": confidence,
        "source": source,
        "start": start,
        "end": start + len(text),
    }


class PIIPipelineTests(unittest.TestCase):

    def test_empty_page_returns_no_candidates(self):
        detector = FakeGLiNERDetector()

        result = process_page_pii(
            page_number=1,
            text="",
            gliner_detector=detector,
        )

        self.assertEqual(result["page_number"], 1)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["redaction_candidates"], [])
        self.assertEqual(result["review_candidates"], [])

    def test_gliner_detector_receives_page_text(self):
        detector = FakeGLiNERDetector()

        result = process_page_pii(
            page_number=2,
            text="Applicant information",
            gliner_detector=detector,
        )

        self.assertEqual(
            detector.received_text,
            "Applicant information",
        )
        self.assertEqual(result["page_number"], 2)

    def test_high_sensitivity_candidate_becomes_redaction_candidate(self):
        passport = candidate(
        "passport number",
        "P1234567",
    )

        detector = FakeGLiNERDetector(
            candidates=[passport],
        )

        result = process_page_pii(
            page_number=1,
            text="Passport Number: P1234567",
            gliner_detector=detector,
        )

        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(len(result["redaction_candidates"]), 1)
        self.assertEqual(result["candidates"][0]["action"], "REDACT")

    def test_person_candidate_requires_review(self):
        person = candidate(
            "PERSON",
            "Rahul Kumar",
        )

        detector = FakeGLiNERDetector(
            candidates=[person],
        )

        result = process_page_pii(
            page_number=1,
            text="Rahul Kumar",
            gliner_detector=detector,
        )

        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(len(result["review_candidates"]), 1)
        self.assertEqual(
            result["review_candidates"][0]["action"],
            "REVIEW",
        )

    def test_public_support_phone_is_kept(self):
        phone = candidate(
            "PHONE",
            "1800-123-456",
        )

        detector = FakeGLiNERDetector(
            candidates=[phone],
        )

        result = process_page_pii(
            page_number=1,
            text="Customer Support Helpline: 1800-123-456",
            gliner_detector=detector,
        )

        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["action"], "KEEP")
        self.assertEqual(result["redaction_candidates"], [])
        self.assertEqual(result["review_candidates"], [])

    def test_private_phone_is_redacted(self):
        text = "Registered mobile number: +91 9876543210"

        phone_start = text.index("+91 9876543210")

        phone = candidate(
            "PHONE",
            "+91 9876543210",
            start=phone_start,
        )

        detector = FakeGLiNERDetector(
            candidates=[phone],
        )

        result = process_page_pii(
            page_number=1,
            text=text,
            gliner_detector=detector,
        )

        # print("\nDEBUG PIPELINE RESULT:")
        # print(result)

        self.assertEqual(len(result["redaction_candidates"]), 1)
        self.assertEqual(
            result["redaction_candidates"][0]["action"],
            "REDACT",
        )

    def test_regex_and_gliner_duplicates_are_resolved(self):
        text = "Email: user@example.com"

        gliner_email = candidate(
            "EMAIL",
            "user@example.com",
            confidence=0.90,
            source="gliner",
            start=7,
        )

        detector = FakeGLiNERDetector(
            candidates=[gliner_email],
        )

        result = process_page_pii(
            page_number=1,
            text=text,
            gliner_detector=detector,
        )

        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(
            result["candidates"][0]["text"],
            "user@example.com",
        )

    def test_custom_policy_is_used(self):
        policy = RedactionPolicy(
            auto_redact_confidence=0.99,
        )

        passport = candidate(
        "passport number",
        "P1234567",
        confidence=0.90,
)

        detector = FakeGLiNERDetector(
            candidates=[passport],
        )

        result = process_page_pii(
            page_number=1,
            text="Passport: P1234567",
            gliner_detector=detector,
            policy=policy,
        )

        self.assertEqual(
            result["candidates"][0]["action"],
            "REVIEW",
        )

    def test_invalid_page_number_is_rejected(self):
        detector = FakeGLiNERDetector()

        with self.assertRaises(PIIPipelineError):
            process_page_pii(
                page_number=0,
                text="Some text",
                gliner_detector=detector,
            )

    def test_invalid_text_type_is_rejected(self):
        detector = FakeGLiNERDetector()

        with self.assertRaises(PIIPipelineError):
            process_page_pii(
                page_number=1,
                text=None,
                gliner_detector=detector,
            )

    def test_missing_gliner_detector_is_rejected(self):
        with self.assertRaises(PIIPipelineError):
            process_page_pii(
                page_number=1,
                text="Some text",
                gliner_detector=None,
            )


if __name__ == "__main__":
    unittest.main()