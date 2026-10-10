from pathlib import Path

import pymupdf


PDF_PATH = Path("test_data/coordinate_test.pdf")


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    document = pymupdf.open(PDF_PATH)

    try:
        for page_number, page in enumerate(document, start=1):
            print("=" * 80)
            print(f"PAGE {page_number}")
            print("=" * 80)

            text = page.get_text("text")
            print("\nFULL TEXT:")
            print(text)

            print("\nWORDS:")
            words = page.get_text("words")

            for word in words:
                print(word)

            print("\nSPANS:")
            page_dict = page.get_text("dict")

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        print(
                            {
                                "text": span.get("text"),
                                "bbox": span.get("bbox"),
                                "origin": span.get("origin"),
                                "size": span.get("size"),
                            }
                        )

    finally:
        document.close()


if __name__ == "__main__":
    main()