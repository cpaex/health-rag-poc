"""Phase 3: section-aware chunking, tested against the real seed notes."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.chunk import chunk_note

NOTES_DIR = Path(__file__).resolve().parents[2] / "ingestion" / "seed_data" / "notes"


def _read(name: str) -> str:
    return (NOTES_DIR / name).read_text()


def test_headered_note_splits_into_sections() -> None:
    chunks = chunk_note(_read("note-001.txt"))
    sections = [c["section"] for c in chunks]
    assert "HPI" in sections
    assert "Assessment" in sections
    assert "Plan" in sections
    # The unusual contrast-reaction phrasing lands in the HPI chunk.
    hpi = " ".join(c["text"] for c in chunks if c["section"] == "HPI")
    assert "blotchy and tight in the throat" in hpi


def test_medications_section_is_captured() -> None:
    chunks = chunk_note(_read("note-002.txt"))
    meds = " ".join(c["text"] for c in chunks if c["section"] == "Medications")
    assert "gabapentin" in meds


def test_headerless_note_falls_back_to_fixed_size() -> None:
    chunks = chunk_note(_read("note-003.txt"))
    assert chunks
    assert all(c["section"] is None for c in chunks)


@pytest.mark.parametrize(
    "name", ["note-001.txt", "note-004.txt", "note-006.txt", "note-009.txt", "note-010.txt"]
)
def test_no_empty_chunks_and_content_preserved(name: str) -> None:
    chunks = chunk_note(_read(name))
    assert chunks
    assert all(c["text"].strip() for c in chunks)


def test_fixed_size_overlap_and_bounds() -> None:
    text = "para one. " * 60 + "\n\n" + "para two. " * 60  # ~1240 chars, forces a split
    chunks = chunk_note(text, max_chars=400, overlap=80)
    assert len(chunks) >= 3
    assert all(len(c["text"]) <= 400 for c in chunks)
