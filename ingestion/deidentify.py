"""Comprehend Medical DetectPHI wrapper (SPEC.md §6 step 2).

Runs for real against `comprehendmedical:DetectPHI` even on synthetic seed data so
the code path is exercised. All AWS access goes through an injectable client so
unit tests can pass a fake (Comprehend Medical is not covered by moto).
"""

from __future__ import annotations

from typing import Any

_MAX_BYTES = 20000  # Comprehend Medical DetectPHI hard limit per request


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("comprehendmedical", region_name=region)


def detect_phi(text: str, *, client: Any = None, region: str | None = None) -> list[dict]:
    """Return the list of PHI entities Comprehend Medical finds in ``text``.

    Each entity is the raw API shape: ``Type``, ``Text``, ``BeginOffset``,
    ``EndOffset``, ``Score``, ``Category`` (== "PROTECTED_HEALTH_INFORMATION").
    Long inputs are split on UTF-8 byte size and offsets are rebased to the
    original string.
    """
    client = client or _client(region)
    entities: list[dict] = []
    for chunk_start, chunk in _byte_chunks(text, _MAX_BYTES):
        resp = client.detect_phi(Text=chunk)
        for ent in resp.get("Entities", []):
            ent = dict(ent)
            ent["BeginOffset"] += chunk_start
            ent["EndOffset"] += chunk_start
            entities.append(ent)
    return entities


def redact(text: str, entities: list[dict], *, mask: str = "[{type}]") -> str:
    """Replace each detected PHI span with a typed placeholder, e.g. ``[NAME]``.

    Non-overlapping, applied right-to-left so offsets stay valid.
    """
    spans = sorted(
        ((e["BeginOffset"], e["EndOffset"], e.get("Type", "PHI")) for e in entities),
        key=lambda s: s[0],
        reverse=True,
    )
    out = text
    prev_start = len(text) + 1
    for start, end, etype in spans:
        if end > prev_start:  # overlaps a span we already replaced; skip
            continue
        out = out[:start] + mask.format(type=etype) + out[end:]
        prev_start = start
    return out


def _byte_chunks(text: str, max_bytes: int):
    """Yield ``(char_offset, substring)`` pieces each <= ``max_bytes`` UTF-8 bytes."""
    if len(text.encode("utf-8")) <= max_bytes:
        yield 0, text
        return
    start = 0
    while start < len(text):
        end = start
        size = 0
        while end < len(text):
            ch = text[end].encode("utf-8")
            if size + len(ch) > max_bytes:
                break
            size += len(ch)
            end += 1
        if end == start:  # single char larger than limit — shouldn't happen for text
            end = start + 1
        yield start, text[start:end]
        start = end
