import unittest

from app.pii_resolution import (
    PIIResolutionError,
    normalize_entity_type,
    resolve_pii_candidates,
)


class PIIResolutionTests(unittest.TestCase):

    def test_normalizes_gliner_entity_type(self):
        self.assertEqual(
            normalize_entity_type("person"),
            "PERSON",
        )

    def test_normalizes_regex_entity_type(self):
        self.assertEqual(
            normalize_entity_type("email"),
            "EMAIL",
        )

    def test_normalizes_aadhaar(self):
        self.assertEqual(
            normalize_entity_type("aadhaar"),
            "AADHAAR",
        )

    def test_unknown_entity_type_is_rejected(self):
        with self.assertRaises(PIIResolutionError):
            normalize_entity_type("something_unknown")

    def test_exact_duplicates_are_removed(self):
        candidates = [
            {
                "entity_type": "email",
                "text": "john@example.com",
                "confidence": 1.0,
                "source": "regex",
                "start": 8,
                "end": 24,
            },
            {
                "entity_type": "email",
                "text": "john@example.com",
                "confidence": 0.91,
                "source": "gliner",
                "start": 8,
                "end": 24,
            },
        ]

        result = resolve_pii_candidates(candidates)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "EMAIL")
        self.assertEqual(result[0]["source"], "regex")

    def test_different_non_overlapping_entities_are_preserved(self):
        candidates = [
            {
                "entity_type": "email",
                "text": "john@example.com",
                "confidence": 1.0,
                "source": "regex",
                "start": 8,
                "end": 24,
            },
            {
                "entity_type": "phone",
                "text": "9876543210",
                "confidence": 1.0,
                "source": "regex",
                "start": 30,
                "end": 40,
            },
        ]

        result = resolve_pii_candidates(candidates)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["entity_type"], "EMAIL")
        self.assertEqual(result[1]["entity_type"], "PHONE")

    def test_longer_overlapping_candidate_is_preferred(self):
        candidates = [
            {
                "entity_type": "person",
                "text": "John Doe",
                "confidence": 0.90,
                "source": "gliner",
                "start": 0,
                "end": 8,
            },
            {
                "entity_type": "person",
                "text": "John",
                "confidence": 0.99,
                "source": "gliner",
                "start": 0,
                "end": 4,
            },
        ]

        result = resolve_pii_candidates(candidates)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "John Doe")

    def test_higher_confidence_wins_when_span_length_is_equal(self):
        candidates = [
            {
                "entity_type": "person",
                "text": "John",
                "confidence": 0.75,
                "source": "gliner",
                "start": 0,
                "end": 4,
            },
            {
                "entity_type": "person",
                "text": "John",
                "confidence": 0.95,
                "source": "gliner",
                "start": 0,
                "end": 4,
            },
        ]

        result = resolve_pii_candidates(candidates)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.95)

    def test_invalid_confidence_is_rejected(self):
        candidates = [
            {
                "entity_type": "email",
                "text": "john@example.com",
                "confidence": 1.5,
                "source": "regex",
                "start": 0,
                "end": 16,
            },
        ]

        with self.assertRaises(PIIResolutionError):
            resolve_pii_candidates(candidates)

    def test_invalid_offsets_are_rejected(self):
        candidates = [
            {
                "entity_type": "email",
                "text": "john@example.com",
                "confidence": 1.0,
                "source": "regex",
                "start": 10,
                "end": 5,
            },
        ]

        with self.assertRaises(PIIResolutionError):
            resolve_pii_candidates(candidates)

    def test_result_is_sorted_by_position(self):
        candidates = [
            {
                "entity_type": "phone",
                "text": "9876543210",
                "confidence": 1.0,
                "source": "regex",
                "start": 30,
                "end": 40,
            },
            {
                "entity_type": "email",
                "text": "john@example.com",
                "confidence": 1.0,
                "source": "regex",
                "start": 5,
                "end": 21,
            },
        ]

        result = resolve_pii_candidates(candidates)

        self.assertEqual(result[0]["entity_type"], "EMAIL")
        self.assertEqual(result[1]["entity_type"], "PHONE")


if __name__ == "__main__":
    unittest.main()