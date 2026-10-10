from typing import TypedDict

from app.positioned_extraction import BBox, PositionedPage, TextFragment


class CoordinateMappingError(Exception):
    """Raised when a PII candidate cannot be mapped safely to coordinates."""


class CandidateSpan(TypedDict):
    text: str
    start: int
    end: int


def map_candidate_to_bboxes(
    candidate: CandidateSpan,
    positioned_page: PositionedPage,
) -> list[BBox]:
    """
    Map a candidate's character span to one or more PDF bounding boxes.

    The candidate offsets and fragment offsets must refer to the same
    canonical page text.
    """
    start = candidate["start"]
    end = candidate["end"]

    if not isinstance(start, int) or not isinstance(end, int):
        raise CoordinateMappingError("Candidate offsets must be integers.")

    if start < 0 or end < 0 or start >= end:
        raise CoordinateMappingError("Candidate span is invalid.")

    page_text = positioned_page["text"]

    if end > len(page_text):
        raise CoordinateMappingError(
            "Candidate span falls outside the positioned page text."
        )

    matched_fragments: list[TextFragment] = []

    for fragment in positioned_page["fragments"]:
        fragment_start = fragment["start"]
        fragment_end = fragment["end"]

        # Character-span intersection:
        # candidate: [start, end)
        # fragment:  [fragment_start, fragment_end)
        overlaps = start < fragment_end and end > fragment_start

        if overlaps:
            matched_fragments.append(fragment)

    if not matched_fragments:
        raise CoordinateMappingError(
            "Candidate span does not overlap any positioned text fragment."
        )

    return [fragment["bbox"] for fragment in matched_fragments]