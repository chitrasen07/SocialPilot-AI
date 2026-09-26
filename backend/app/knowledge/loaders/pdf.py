from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.knowledge.chunking import TextSection
from app.knowledge.errors import PermanentIngestionError


def extract_pdf(data: bytes, filename: str) -> list[TextSection]:
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        pages = list(reader.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise PermanentIngestionError("This PDF could not be read.") from exc
    sections: list[TextSection] = []
    for number, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except (PdfReadError, OSError, ValueError) as exc:
            raise PermanentIngestionError("This PDF could not be read.") from exc
        if text.strip():
            sections.append(
                TextSection(text, {"page": number, "source": filename, "section": f"page {number}"})
            )
    if not sections:
        raise PermanentIngestionError(
            "This PDF has no extractable text. Scanned documents are not supported."
        )
    return sections
