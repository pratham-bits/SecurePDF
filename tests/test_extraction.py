import tempfile
import unittest
from pathlib import Path

import pymupdf

from app.extraction import TextExtractionError, extract_text_from_pdf


def create_digital_pdf(path: Path) -> None:
    document = pymupdf.open()

    page1 = document.new_page()
    page1.insert_text((72, 72), "John Doe john@example.com")

    page2 = document.new_page()
    page2.insert_text((72, 72), "Second page with 12345")

    document.save(path)
    document.close()


def create_no_text_pdf(path: Path) -> None:
    """Create a PDF containing a page with no machine-readable text."""
    document = pymupdf.open()

    document.new_page()

    document.save(path)
    document.close()


def create_mixed_pdf(path: Path) -> None:
    """Create a PDF containing text-bearing and non-text pages."""
    document = pymupdf.open()

    text_page = document.new_page()
    text_page.insert_text((72, 72), "Text-bearing page")

    # Page with no machine-readable text.
    document.new_page()

    text_page_2 = document.new_page()
    text_page_2.insert_text((72, 72), "Another text page")

    document.save(path)
    document.close()


def create_whitespace_pdf(path: Path) -> None:
    document = pymupdf.open()

    page = document.new_page()
    page.insert_text(
        (72, 72),
        "   \n\n   John     Doe   \n\n john@example.com   ",
    )

    document.save(path)
    document.close()


def create_empty_pages_pdf(path: Path) -> None:
    document = pymupdf.open()

    document.new_page()
    document.new_page()

    document.save(path)
    document.close()


class TextExtractionTests(unittest.TestCase):

    def test_digital_pdf_multiple_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "digital.pdf"
            create_digital_pdf(pdf_path)

            result = extract_text_from_pdf(pdf_path)

            self.assertEqual(len(result), 2)

            self.assertEqual(result[0]["page_number"], 1)
            self.assertIn("John Doe", result[0]["text"])
            self.assertIn("john@example.com", result[0]["text"])

            self.assertEqual(result[1]["page_number"], 2)
            self.assertIn("Second page", result[1]["text"])

    def test_no_text_page_returns_empty_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "no_text.pdf"
            create_no_text_pdf(pdf_path)

            result = extract_text_from_pdf(pdf_path)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["page_number"], 1)
            self.assertEqual(result[0]["text"], "")

    def test_mixed_pdf_preserves_page_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "mixed.pdf"
            create_mixed_pdf(pdf_path)

            result = extract_text_from_pdf(pdf_path)

            self.assertEqual(len(result), 3)

            self.assertEqual(result[0]["page_number"], 1)
            self.assertIn("Text-bearing page", result[0]["text"])

            self.assertEqual(result[1]["page_number"], 2)
            self.assertEqual(result[1]["text"], "")

            self.assertEqual(result[2]["page_number"], 3)
            self.assertIn("Another text page", result[2]["text"])

    def test_whitespace_is_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "whitespace.pdf"
            create_whitespace_pdf(pdf_path)

            result = extract_text_from_pdf(pdf_path)

            self.assertEqual(
                result[0]["text"],
                "John Doe john@example.com",
            )

    def test_empty_pages_return_empty_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "empty.pdf"
            create_empty_pages_pdf(pdf_path)

            result = extract_text_from_pdf(pdf_path)

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["text"], "")
            self.assertEqual(result[1]["text"], "")
            self.assertEqual(result[0]["page_number"], 1)
            self.assertEqual(result[1]["page_number"], 2)

    def test_missing_file_raises_application_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "missing.pdf"

            with self.assertRaises(TextExtractionError):
                extract_text_from_pdf(pdf_path)

    def test_corrupt_pdf_raises_application_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "corrupt.pdf"
            pdf_path.write_bytes(b"%PDF-this-is-not-a-valid-pdf")

            with self.assertRaises(TextExtractionError):
                extract_text_from_pdf(pdf_path)


if __name__ == "__main__":
    unittest.main()