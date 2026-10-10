import unittest

from app.pii_gliner import (
    DEFAULT_LABELS,
    GLiNERPIIDetector,
)


class GLiNERPIITests(unittest.TestCase):

    def test_detector_initializes(self):
        detector = GLiNERPIIDetector()

        self.assertIsNotNone(detector)

    def test_detects_contextual_pii(self):
        detector = GLiNERPIIDetector()

        text = (
            "John Doe lives at 25 King's Road. "
            "His email is john.doe@example.com."
        )

        result = detector.detect(
            text,
            labels=(
                "person",
                "address",
                "email",
            ),
            threshold=0.5,
        )

        self.assertGreater(len(result), 0)

        entity_types = {
            candidate["entity_type"].lower()
            for candidate in result
        }

        self.assertTrue(
            "person" in entity_types
            or "address" in entity_types
            or "email" in entity_types
        )

        for candidate in result:
            self.assertGreaterEqual(candidate["confidence"], 0.5)
            self.assertEqual(candidate["source"], "gliner")
            self.assertEqual(
                text[candidate["start"]:candidate["end"]],
                candidate["text"],
            )


if __name__ == "__main__":
    unittest.main()