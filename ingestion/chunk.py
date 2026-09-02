"""Section-aware chunking (SPEC.md §6 step 4).

Split clinical notes on common section headers (HPI, Assessment, Plan,
Medications, ...). If fewer than two headers are found, fall back to fixed-size
character chunks with overlap.

Each chunk is ``{"section": str | None, "text": str}``.
"""

from __future__ import annotations

import re

# Header label -> canonical section name. Matched case-insensitively as a line
# that is (optionally) followed by a colon and nothing else of substance.
_SECTION_HEADERS: dict[str, str] = {
    "hpi": "HPI",
    "history of present illness": "HPI",
    "assessment": "Assessment",
    "assessment and plan": "Assessment/Plan",
    "impression": "Assessment",
    "plan": "Plan",
    "medications": "Medications",
    "discharge medications": "Medications",
    "hospital course": "Hospital Course",
}

_HEADER_RE = re.compile(
    r"^[ \t]*(" + "|".join(re.escape(h) for h in _SECTION_HEADERS) + r")[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def chunk_note(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[dict]:
    text = text.strip("\n")
    matches = list(_HEADER_RE.finditer(text))

    if len(matches) < 2:
        return [
            {"section": None, "text": piece}
            for piece in _fixed_size(text, max_chars=max_chars, overlap=overlap)
        ]

    chunks: list[dict] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        chunks.append({"section": None, "text": preamble})

    for i, m in enumerate(matches):
        canonical = _SECTION_HEADERS[m.group(1).lower()]
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if not body:
            continue
        for piece in _fixed_size(body, max_chars=max_chars, overlap=overlap):
            chunks.append({"section": canonical, "text": piece})
    return chunks


def _fixed_size(text: str, *, max_chars: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        # Prefer to break on a paragraph / sentence boundary past the midpoint.
        if end < len(text):
            window = text[start:end]
            for sep in ("\n\n", "\n", ". "):
                idx = window.rfind(sep)
                if idx > max_chars // 2:
                    end = start + idx + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = end - overlap if end - overlap > start else end
    return out
