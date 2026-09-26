class PermanentIngestionError(Exception):
    """The file itself cannot be processed. Retrying will not help."""

    def __init__(self, message: str) -> None:
        self.safe_message = message
        super().__init__(message)


class TransientIngestionError(Exception):
    """A temporary dependency failure. The worker may retry a bounded number of times."""

    def __init__(self, message: str) -> None:
        self.safe_message = message
        super().__init__(message)
