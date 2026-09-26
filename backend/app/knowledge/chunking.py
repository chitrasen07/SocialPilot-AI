from dataclasses import dataclass
from typing import Any

from app.knowledge.cleaning import clean_text

_MIN_TAIL = 40


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    content: str
    metadata: dict[str, Any]
    token_count: int


@dataclass(frozen=True)
class TextSection:
    text: str
    metadata: dict[str, Any]


def chunk_sections(
    sections: list[TextSection], *, size: int, overlap: int, max_chunks: int
) -> list[ChunkDraft]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    words: list[str] = []
    marks: list[dict[str, Any]] = []
    for section in sections:
        cleaned = clean_text(section.text)
        section_words = cleaned.split()
        if not section_words:
            continue
        words.extend(section_words)
        marks.extend([section.metadata] * len(section_words))
    if not words:
        return []

    drafts: list[ChunkDraft] = []
    start = 0
    step = size - overlap
    seen: set[str] = set()
    while start < len(words):
        end = min(start + size, len(words))
        if drafts and end - start < _MIN_TAIL:
            previous = drafts[-1]
            merged = f"{previous.content} {' '.join(words[start:end])}".strip()
            drafts[-1] = ChunkDraft(previous.index, merged, previous.metadata, len(merged.split()))
            break
        content = " ".join(words[start:end]).strip()
        key = content.casefold()
        if content and key not in seen:
            seen.add(key)
            drafts.append(
                ChunkDraft(len(drafts), content, dict(marks[start]), len(words[start:end]))
            )
        if end >= len(words):
            break
        start += step
        if len(drafts) > max_chunks:
            break
    if len(drafts) > max_chunks:
        raise ValueError("too many chunks")
    return drafts
