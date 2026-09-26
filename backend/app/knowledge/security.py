"""Upload checks. The original filename is never used as a filesystem path."""

from app.core.errors import AppError

_ALLOWED = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "csv": "text/csv",
}
_BLOCKED_EXTENSIONS = {
    "exe",
    "dll",
    "py",
    "js",
    "sh",
    "bat",
    "cmd",
    "ps1",
    "msi",
    "jar",
    "com",
    "scr",
    "html",
    "htm",
    "svg",
}
_ACCEPTED_MIME = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    "txt": {"text/plain", "application/octet-stream"},
    "csv": {"text/csv", "application/csv", "text/plain", "application/octet-stream"},
}


def safe_filename(filename: str) -> str:
    cleaned = filename.replace("\x00", "").replace("\\", "/").split("/")[-1].strip()
    if not cleaned or cleaned in {".", ".."}:
        raise AppError("INVALID_FILE", "The file name is not valid.", 400)
    return cleaned[:255]


def validate_upload(
    filename: str, content_type: str | None, data: bytes, max_bytes: int
) -> tuple[str, str, str]:
    """Returns (file_type, mime_type, display filename)."""
    if not data:
        raise AppError("EMPTY_FILE", "This file is empty.", 400)
    if len(data) > max_bytes:
        raise AppError("FILE_TOO_LARGE", "This file is too large.", 413)
    name = safe_filename(filename)
    if "." not in name:
        raise AppError(
            "UNSUPPORTED_FILE",
            "This file type is not supported. Upload a PDF, DOCX, TXT, or CSV.",
            400,
        )
    extension = name.rsplit(".", 1)[-1].lower()
    if extension in _BLOCKED_EXTENSIONS or extension not in _ALLOWED:
        raise AppError(
            "UNSUPPORTED_FILE",
            "This file type is not supported. Upload a PDF, DOCX, TXT, or CSV.",
            400,
        )
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime and mime not in _ACCEPTED_MIME[extension]:
        raise AppError("INVALID_FILE", "The file does not match its type.", 400)
    if not _signature_matches(extension, data):
        raise AppError("INVALID_FILE", "The file does not match its type.", 400)
    return extension, _ALLOWED[extension], name


def _signature_matches(extension: str, data: bytes) -> bool:
    if extension == "pdf":
        return data.startswith(b"%PDF-")
    if extension == "docx":
        return data.startswith(b"PK\x03\x04")
    if b"\x00" in data or data.startswith(b"MZ") or data.startswith(b"\x7fELF"):
        return False
    return True
