from app.knowledge.chunking import TextSection
from app.knowledge.errors import PermanentIngestionError
from app.knowledge.loaders.csv import extract_csv
from app.knowledge.loaders.docx import extract_docx
from app.knowledge.loaders.pdf import extract_pdf
from app.knowledge.loaders.text import extract_text

_LOADERS = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "txt": extract_text,
    "csv": extract_csv,
}


def extract_document(file_type: str, data: bytes, filename: str) -> list[TextSection]:
    loader = _LOADERS.get(file_type)
    if loader is None:
        raise PermanentIngestionError(
            "This file type is not supported. Upload a PDF, DOCX, TXT, or CSV."
        )
    return loader(data, filename)
