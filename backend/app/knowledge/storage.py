from pathlib import Path
from typing import Protocol
from uuid import UUID


class KnowledgeStorage(Protocol):
    def save(self, organization_id: UUID, document_id: UUID, data: bytes) -> str: ...

    def read(self, storage_path: str) -> bytes: ...

    def delete(self, storage_path: str) -> None: ...


class LocalKnowledgeStorage:
    """Files live under a configured directory, named by ids, never by the upload name."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def save(self, organization_id: UUID, document_id: UUID, data: bytes) -> str:
        relative = f"{organization_id}/{document_id}"
        path = self._resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return relative

    def read(self, storage_path: str) -> bytes:
        return self._resolve(storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        path = self._resolve(storage_path)
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent != self.root.resolve() and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def _resolve(self, relative: str) -> Path:
        if not relative or "\x00" in relative or relative.startswith(("/", "\\")):
            raise ValueError("invalid storage path")
        if ".." in Path(relative).parts:
            raise ValueError("invalid storage path")
        root = self.root.resolve()
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError("invalid storage path")
        return path
