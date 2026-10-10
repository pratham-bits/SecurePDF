import tempfile
import unittest
from pathlib import Path

import pymupdf

from app.ocr import OCREngine


def create_ocr_test_pdf(path: Path) -> None:
    document = pymupdf.open()

    page = document.new_page()
    page.insert_text(
        (72, 72),
        "SecurePDF OCR Test\nJohn Doe\njohn@example.com",
        fontsize=20,
    )

    document.save(path)
    document.close()


class OCRTests(unittest.TestCase):

    def test_ocr_engine_initializes(self):
        engine = OCREngine()

        self.assertIsNotNone(engine)

    def test_ocr_recognizes_rendered_pdf_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "ocr_test.pdf"
            create_ocr_test_pdf(pdf_path)

            document = pymupdf.open(pdf_path)

            try:
                page = document[0]

                # Render PDF page to an image.
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))

                image_bytes = pixmap.tobytes("png")

            finally:
                document.close()

            engine = OCREngine()
            text = engine.recognize(image_bytes)

            self.assertIn("SecurePDF", text)
            self.assertIn("John Doe", text)
            self.assertIn("john@example.com", text)


if __name__ == "__main__":
    unittest.main()