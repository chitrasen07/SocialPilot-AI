import csv
from io import StringIO

from app.knowledge.chunking import TextSection
from app.knowledge.errors import PermanentIngestionError
from app.knowledge.loaders.text import extract_text


def extract_csv(data: bytes, filename: str) -> list[TextSection]:
    raw = extract_text(data, filename)[0].text
    try:
        rows = list(csv.reader(StringIO(raw)))
    except csv.Error as exc:
        raise PermanentIngestionError("This CSV could not be read.") from exc
    header: list[str] | None = None
    blocks: list[str] = []
    for row in rows:
        cells = [cell.strip() for cell in row]
        if not any(cells):
            continue
        if header is None:
            header = cells
            continue
        pairs = []
        for index, cell in enumerate(cells):
            if not cell:
                continue
            # Spreadsheet formulas are stored as text. Nothing here is evaluated.
            label = (
                header[index] if index < len(header) and header[index] else f"Column {index + 1}"
            )
            pairs.append(f"{label}: {cell}")
        if pairs:
            blocks.append("\n".join(pairs))
    if not blocks:
        raise PermanentIngestionError("This CSV has no data rows.")
    return [TextSection("\n\n".join(blocks), {"source": filename, "section": "rows"})]
