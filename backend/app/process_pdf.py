from pathlib import Path
import argparse
import sys

from app.document_processor import (
    DocumentProcessingError,
    process_digital_pdf,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process a digital PDF with SecurePDF."
    )

    parser.add_argument(
        "input_pdf",
        type=Path,
        help="Path to the input PDF.",
    )

    parser.add_argument(
        "output_pdf",
        type=Path,
        help="Path where the redacted PDF will be saved.",
    )

    parser.add_argument(
        "--padding",
        type=float,
        default=0.0,
        help="Optional redaction padding in PDF points.",
    )

    args = parser.parse_args()

    try:
        result = process_digital_pdf(
            args.input_pdf,
            args.output_pdf,
            padding=args.padding,
        )
    except DocumentProcessingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("SecurePDF processing completed.")
    print(f"Input: {result['input_path']}")
    print(f"Output: {result['output_path']}")
    print(f"Pages processed: {result['pages_processed']}")
    print(f"Detected entities: {result['detected_entities']}")
    print(f"Redacted entities: {result['redacted_entities']}")
    print(f"Review entities: {result['review_entities']}")
    print(f"Kept entities: {result['kept_entities']}")

    print("\nDetected candidates:")

    for candidate in result["detected_candidates"]:
        print(
            f"  - {candidate['entity_type']}: "
            f"{candidate['text']!r} "
            f"(confidence={candidate['confidence']:.2f}, "
            f"action={candidate['action']}, "
            f"page={candidate['page_number']})"
        )

        print(f"    reason: {candidate['reason']}")
        print(f"    bounding_boxes: {candidate['bounding_boxes']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())