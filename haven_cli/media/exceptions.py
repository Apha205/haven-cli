"""Exceptions for media processing operations."""


class MediaError(Exception):
    """Base exception for media processing errors."""
    
    def __init__(self, message: str, path: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
    
    def __str__(self) -> str:
        if self.path:
            return f"{self.message} (path: {self.path})"
        return self.message


class VideoMetadataError(MediaError):
    """Raised when video metadata extraction fails."""
    pass


class ThumbnailError(MediaError):
    """Raised when thumbnail generation fails."""
    pass


class FFmpegError(MediaError):
    """Raised when FFmpeg/ffprobe operation fails."""
    
    def __init__(
        self,
        message: str,
        path: str | None = None,
        returncode: int | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message, path)
        self.returncode = returncode
        self.stderr = stderr
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.path:
            parts.append(f"(path: {self.path})")
        if self.returncode is not None:
            parts.append(f"(returncode: {self.returncode})")
        if self.stderr:
            # Include full stderr for debugging (truncated to 2000 chars to avoid log spam)
            stderr_display = self.stderr[:2000] if len(self.stderr) > 2000 else self.stderr
            parts.append(f"(stderr: {stderr_display!r})")
        return " ".join(parts)


class MimeTypeError(MediaError):
    """Raised when MIME type detection fails."""
    pass
