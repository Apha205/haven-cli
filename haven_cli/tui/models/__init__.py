"""TUI view models.

This package contains data models specific to the TUI views,
separate from the database models in haven_cli.database.models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class VideoViewModel:
    """View model for video display in TUI.
    
    Attributes:
        id: Video ID.
        title: Video title.
        status: Current status (pending, downloading, encrypting, uploading, completed, failed).
        progress: Overall progress percentage (0-100).
        stage: Current pipeline stage.
        speed: Current speed in bytes/sec.
        eta: Estimated time remaining in seconds.
        size: Total file size in bytes.
        error: Error message if failed.
        updated_at: Last update timestamp.
    """
    
    id: int
    title: str
    status: str
    progress: float = 0.0
    stage: str = "unknown"
    speed: Optional[int] = None
    eta: Optional[int] = None
    size: Optional[int] = None
    error: Optional[str] = None
    updated_at: Optional[datetime] = None
    
    @property
    def speed_human(self) -> str:
        """Get human-readable speed string."""
        if self.speed is None or self.speed <= 0:
            return "-"
        
        for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
            if self.speed < 1024:
                return f"{self.speed:.1f} {unit}"
            self.speed /= 1024
        return f"{self.speed:.1f} TB/s"
    
    @property
    def size_human(self) -> str:
        """Get human-readable size string."""
        if self.size is None or self.size <= 0:
            return "-"
        
        size = float(self.size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    @property
    def eta_human(self) -> str:
        """Get human-readable ETA string."""
        if self.eta is None or self.eta <= 0:
            return "-"
        
        seconds = self.eta
        if seconds < 60:
            return f"{seconds}s"
        
        minutes = seconds // 60
        seconds %= 60
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        
        hours = minutes // 60
        minutes %= 60
        if hours < 24:
            return f"{hours}h {minutes}m"
        
        days = hours // 24
        hours %= 24
        return f"{days}d {hours}h"


__all__ = ["VideoViewModel"]
