import unittest

from app.redaction_policy import (
    RedactionPolicy,
    RedactionPolicyError,
    decide_redaction,
)


def make_candidate(
    entity_type: str,
    text: str,
    confidence: float = 0.95,
    source: str = "gliner",
    start: int = 0,
) -> dict:
    return {
        "entity_type": entity_type,
        "text": text,
        "confidence": confidence,
        "source": source,
        "start": start,
        "end": start + len(text),
    }


class RedactionPolicyTests(unittest.TestCase):

    def test_high_sensitivity_pii_is_redacted(self):
        candidate = make_candidate(
            "PASSPORT",
            "P1234567",
        )

        decision = decide_redaction(candidate)

        self.assertEqual(decision["action"], "REDACT")
        self.assertEqual(decision["sensitivity"], "HIGH")

    def test_high_sensitivity_low_confidence_requires_review(self):
        candidate = make_candidate(
            "SSN",
            "123-45-6789",
            confidence=0.40,
        )

        decision = decide_redaction(candidate)

        self.assertEqual(decision["action"], "REVIEW")
        self.assertEqual(decision["sensitivity"], "HIGH")

    def test_private_phone_context_is_redacted(self):
        candidate = make_candidate(
            "PHONE",
            "+91 9876543210",
        )

        decision = decide_redaction(
            candidate,
            context="Registered mobile number of the applicant",
        )

        self.assertEqual(decision["action"], "REDACT")

    def test_public_support_phone_is_kept(self):
        candidate = make_candidate(
            "PHONE",
            "1800-123-456",
        )

        decision = decide_redaction(
            candidate,
            context="Customer Support Helpline",
        )

        self.assertEqual(decision["action"], "KEEP")

    def test_public_company_email_is_kept(self):
        candidate = make_candidate(
            "EMAIL",
            "support@example.com",
        )

        decision = decide_redaction(
            candidate,
            context="For technical support, contact us at",
        )

        self.assertEqual(decision["action"], "KEEP")

    def test_person_name_requires_review(self):
        candidate = make_candidate(
            "PERSON",
            "Rahul Kumar",
        )

        decision = decide_redaction(candidate)

        self.assertEqual(decision["action"], "REVIEW")
        self.assertEqual(decision["sensitivity"], "CONTEXTUAL")

    def test_person_name_in_private_context_is_redacted(self):
        candidate = make_candidate(
            "PERSON",
            "Rahul Kumar",
        )

        decision = decide_redaction(
            candidate,
            context="Applicant Name",
        )

        self.assertEqual(decision["action"], "REDACT")

    def test_home_address_is_redacted(self):
        candidate = make_candidate(
            "ADDRESS",
            "12 Park Street, Kolkata",
        )

        decision = decide_redaction(
            candidate,
            context="Home Address",
        )

        self.assertEqual(decision["action"], "REDACT")

    def test_ambiguous_address_requires_review(self):
        candidate = make_candidate(
            "ADDRESS",
            "12 Park Street, Kolkata",
        )

        decision = decide_redaction(candidate)

        self.assertEqual(decision["action"], "REVIEW")

    def test_medium_sensitivity_without_context_requires_review(self):
        candidate = make_candidate(
            "DATE_OF_BIRTH",
            "12/03/2005",
        )

        decision = decide_redaction(candidate)

        self.assertEqual(decision["action"], "REVIEW")
        self.assertEqual(decision["sensitivity"], "MEDIUM")

    def test_medium_sensitivity_private_context_is_redacted(self):
        candidate = make_candidate(
            "DATE_OF_BIRTH",
            "12/03/2005",
        )

        decision = decide_redaction(
            candidate,
            context="Applicant date of birth",
        )

        self.assertEqual(decision["action"], "REDACT")

    def test_decision_preserves_candidate_information(self):
        candidate = make_candidate(
            "PAN",
            "ABCDE1234F",
            confidence=0.97,
            source="regex",
            start=15,
        )

        decision = decide_redaction(candidate)

        self.assertEqual(decision["entity_type"], "PAN")
        self.assertEqual(decision["text"], "ABCDE1234F")
        self.assertEqual(decision["confidence"], 0.97)
        self.assertEqual(decision["source"], "regex")
        self.assertEqual(decision["start"], 15)
        self.assertEqual(decision["end"], 25)

    def test_decision_contains_explanation(self):
        candidate = make_candidate(
            "AADHAAR",
            "1234 5678 9012",
        )

        decision = decide_redaction(candidate)

        self.assertTrue(decision["reason"])
        self.assertIsInstance(decision["reason"], str)

    def test_unknown_entity_type_is_rejected(self):
        candidate = make_candidate(
            "UNKNOWN_ENTITY",
            "something",
        )

        with self.assertRaises(RedactionPolicyError):
            decide_redaction(candidate)

    def test_invalid_confidence_is_rejected(self):
        candidate = make_candidate(
            "PASSPORT",
            "P1234567",
            confidence=1.5,
        )

        with self.assertRaises(RedactionPolicyError):
            decide_redaction(candidate)

    def test_custom_policy_can_change_threshold(self):
        policy = RedactionPolicy(
            auto_redact_confidence=0.90,
        )

        candidate = make_candidate(
            "PAN",
            "ABCDE1234F",
            confidence=0.80,
        )

        decision = decide_redaction(
            candidate,
            policy=policy,
        )

        self.assertEqual(decision["action"], "REVIEW")


if __name__ == "__main__":
    unittest.main()