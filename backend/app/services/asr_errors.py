"""Small shared error contract for audio acquisition and local transcription."""


class ASRError(RuntimeError):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
