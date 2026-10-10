import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from app.text_pipeline import TextPipelineError, process_pdf_text


def create_digital_pdf(path: Path) -> None:
    document = pymupdf.open()

    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Digital page John Doe john@example.com",
        fontsize=20,
    )

    document.save(path)
    document.close()


def create_mixed_pdf(path: Path) -> None:
    document = pymupdf.open()

    text_page = document.new_page()
    text_page.insert_text(
        (72, 72),
        "Machine readable page",
        fontsize=20,
    )

    image_page = document.new_page()

    image = Image.new("RGB", (1200, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (50, 100),
        "OCR Page",
        fill="black",
    )

    image_path = path.parent / "ocr_page.png"
    image.save(image_path)

    image_page.insert_image(
        image_page.rect,
        filename=str(image_path),
    )

    document.save(path)
    document.close()


def create_empty_pdf(path: Path) -> None:
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()


class TextPipelineTests(unittest.TestCase):

    def test_digital_page_uses_text_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "digital.pdf"
            create_digital_pdf(pdf_path)

            result = process_pdf_text(pdf_path)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["page_number"], 1)
            self.assertEqual(result[0]["source"], "text")
            self.assertIn("Digital page", result[0]["text"])
            self.assertIn("John Doe", result[0]["text"])

    def test_empty_page_is_sent_to_ocr(self):
        class FakeOCREngine:
            def __init__(self):
                self.calls = 0
                self.received_image = None

            def recognize(self, image):
                self.calls += 1
                self.received_image = image
                return "OCR fallback text"
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "empty.pdf"
            create_empty_pdf(pdf_path)

            engine = FakeOCREngine()
            result = process_pdf_text(pdf_path, ocr_engine=engine)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["page_number"], 1)
            self.assertEqual(result[0]["source"], "ocr")
            self.assertEqual(result[0]["text"], "OCR fallback text")
            self.assertEqual(engine.calls, 1)
            self.assertIsInstance(engine.received_image, bytes)

    def test_mixed_pdf_uses_correct_source_per_page(self):
        class FakeOCREngine:
            def recognize(self, image):
                return "OCR extracted page"

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "mixed.pdf"
            create_mixed_pdf(pdf_path)

            result = process_pdf_text(
                pdf_path,
                ocr_engine=FakeOCREngine(),
            )

            self.assertEqual(len(result), 2)

            self.assertEqual(result[0]["page_number"], 1)
            self.assertEqual(result[0]["source"], "text")
            self.assertIn("Machine readable", result[0]["text"])

            self.assertEqual(result[1]["page_number"], 2)
            self.assertEqual(result[1]["source"], "ocr")
            self.assertEqual(result[1]["text"], "OCR extracted page")

    def test_missing_pdf_raises_pipeline_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "missing.pdf"

            with self.assertRaises(TextPipelineError):
                process_pdf_text(pdf_path)

    def test_corrupt_pdf_raises_pipeline_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "corrupt.pdf"
            pdf_path.write_bytes(b"%PDF-invalid")

            with self.assertRaises(TextPipelineError):
                process_pdf_text(pdf_path)


if __name__ == "__main__":
    unittest.main()