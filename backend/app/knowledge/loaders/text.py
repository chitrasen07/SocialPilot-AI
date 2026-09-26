from app.knowledge.chunking import TextSection
from app.knowledge.cleaning import clean_text
from app.knowledge.errors import PermanentIngestionError


def extract_text(data: bytes, filename: str) -> list[TextSection]:
    text = clean_text(_decode(data))
    if not text:
        raise PermanentIngestionError("This file has no extractable text.")
    return [TextSection(text, {"source": filename, "section": "document"})]


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PermanentIngestionError("This file's text encoding is not supported.")
