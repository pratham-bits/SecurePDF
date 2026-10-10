import unittest

from app.pii_rules import PIIRuleError, detect_pii_with_rules


class PIIRuleDetectionTests(unittest.TestCase):

    def test_email_detection(self):
        text = "Contact John at john.doe@example.com for details."

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "EMAIL")
        self.assertEqual(result[0]["text"], "john.doe@example.com")
        self.assertEqual(result[0]["confidence"], 1.0)
        self.assertEqual(result[0]["source"], "regex")

    def test_indian_phone_detection(self):
        text = "Mobile: 9876543210"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "PHONE")
        self.assertEqual(result[0]["text"], "9876543210")

    def test_phone_with_country_code(self):
        text = "Mobile: +91 9876543210"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "PHONE")
        self.assertEqual(result[0]["text"], "+91 9876543210")

    def test_phone_with_separators(self):
        text = "Mobile: 98765-43210"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "PHONE")
        self.assertEqual(result[0]["text"], "98765-43210")

    def test_aadhaar_detection(self):
        text = "Aadhaar: 1234 5678 9012"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "AADHAAR")
        self.assertEqual(result[0]["text"], "1234 5678 9012")

    def test_aadhaar_with_hyphens(self):
        text = "Aadhaar: 1234-5678-9012"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "AADHAAR")
        self.assertEqual(result[0]["text"], "1234-5678-9012")

    def test_pan_detection(self):
        text = "PAN: ABCDE1234F"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "PAN")
        self.assertEqual(result[0]["text"], "ABCDE1234F")

    def test_multiple_pii_types(self):
        text = (
            "John Doe, john@example.com, "
            "9876543210, 1234 5678 9012, ABCDE1234F"
        )

        result = detect_pii_with_rules(text)

        entity_types = [candidate["entity_type"] for candidate in result]

        self.assertIn("EMAIL", entity_types)
        self.assertIn("PHONE", entity_types)
        self.assertIn("AADHAAR", entity_types)
        self.assertIn("PAN", entity_types)
        self.assertEqual(len(result), 4)

    def test_character_positions(self):
        text = "Email: john@example.com"

        result = detect_pii_with_rules(text)

        candidate = result[0]

        self.assertEqual(
            text[candidate["start"]:candidate["end"]],
            "john@example.com",
        )

    def test_non_matching_text(self):
        text = "This document contains no identifiable patterns."

        result = detect_pii_with_rules(text)

        self.assertEqual(result, [])

    def test_invalid_input_type(self):
        with self.assertRaises(PIIRuleError):
            detect_pii_with_rules(None)  # type: ignore[arg-type]

    def test_email_case(self):
        text = "Email: JOHN.DOE@EXAMPLE.COM"

        result = detect_pii_with_rules(text)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["entity_type"], "EMAIL")


if __name__ == "__main__":
    unittest.main()