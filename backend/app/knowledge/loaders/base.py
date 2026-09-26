from typing import Protocol

from app.knowledge.chunking import TextSection


class DocumentLoader(Protocol):
    def extract(self, data: bytes, filename: str) -> list[TextSection]: ...
