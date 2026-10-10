import unittest
from pathlib import Path

from app.positioned_extraction import (
    PositionedExtractionError,
    extract_positioned_text_from_pdf,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_PDF = PROJECT_ROOT / "backend" / "test_data" / "coordinate_test.pdf"


class PositionedExtractionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not TEST_PDF.exists():
            raise unittest.SkipTest(
                f"Real evidence PDF not found: {TEST_PDF}"
            )

    def test_real_pdf_produces_positioned_page(self):
        pages = extract_positioned_text_from_pdf(TEST_PDF)

        self.assertEqual(len(pages), 1)

        page = pages[0]

        self.assertEqual(page["page_number"], 1)
        self.assertEqual(page["source"], "text")
        self.assertTrue(page["text"])
        self.assertTrue(page["fragments"])

    def test_real_pdf_contains_expected_pii_text(self):
        pages = extract_positioned_text_from_pdf(TEST_PDF)

        text = pages[0]["text"]

        self.assertIn("rahul@example.com", text)
        self.assertIn("ABCDE1234F", text)
        self.assertIn("+91", text)
        self.assertIn("9876543210", text)

    def test_real_pdf_pii_fragments_have_coordinates(self):
        pages = extract_positioned_text_from_pdf(TEST_PDF)

        fragments = pages[0]["fragments"]

        pan_fragment = next(
            fragment
            for fragment in fragments
            if fragment["text"] == "ABCDE1234F"
        )

        self.assertEqual(
            pan_fragment["bbox"],
            (
                99.8931655883789,
                130.544921875,
                168.9390106201172,
                142.833984375,
            ),
        )

    def test_real_pdf_phone_is_split_into_positioned_words(self):
        pages = extract_positioned_text_from_pdf(TEST_PDF)

        fragments = pages[0]["fragments"]

        phone_parts = [
            fragment
            for fragment in fragments
            if fragment["text"] in {"+91", "9876543210"}
        ]

        self.assertEqual(len(phone_parts), 2)

        self.assertEqual(
            phone_parts[0]["text"],
            "+91",
        )

        self.assertEqual(
            phone_parts[1]["text"],
            "9876543210",
        )

    def test_fragment_offsets_match_page_text(self):
        pages = extract_positioned_text_from_pdf(TEST_PDF)

        page = pages[0]

        for fragment in page["fragments"]:
            self.assertEqual(
                page["text"][fragment["start"]:fragment["end"]],
                fragment["text"],
            )

    def test_fragments_are_positioned_in_text_order(self):
        pages = extract_positioned_text_from_pdf(TEST_PDF)

        fragments = pages[0]["fragments"]

        for previous, current in zip(
            fragments,
            fragments[1:],
        ):
            self.assertLessEqual(
                previous["end"],
                current["start"],
            )

    def test_missing_pdf_is_rejected(self):
        missing_path = TEST_PDF.parent / "does_not_exist.pdf"

        with self.assertRaises(PositionedExtractionError):
            extract_positioned_text_from_pdf(missing_path)


if __name__ == "__main__":
    unittest.main()