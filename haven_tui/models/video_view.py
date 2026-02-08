"""Video view models for Haven TUI.

Aggregated view of video for TUI display from PipelineSnapshot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class PipelineStage(Enum):
    """Pipeline stages for video processing."""
    PENDING = "pending"
    DOWNLOAD = "download"
    INGEST = "ingest"
    ANALYSIS = "analysis"
    ENCRYPT = "encrypt"
    UPLOAD = "upload"
    SYNC = "sync"
    COMPLETE = "complete"


class StageStatus(Enum):
    """Status for individual pipeline stages."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageInfo:
    """Information about a specific pipeline stage."""
    stage: PipelineStage
    status: StageStatus
    progress: float = 0.0  # 0.0 - 100.0
    speed: int = 0  # bytes/sec
    eta: Optional[int] = None  # seconds remaining
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def is_active(self) -> bool:
        """Check if stage is currently active."""
        return self.status == StageStatus.ACTIVE
    
    @property
    def is_complete(self) -> bool:
        """Check if stage is completed."""
        return self.status == StageStatus.COMPLETED
    
    @property
    def has_failed(self) -> bool:
        """Check if stage has failed."""
        return self.status == StageStatus.FAILED


@dataclass
class VideoView:
    """Aggregated view of video for TUI display from PipelineSnapshot."""
    id: int
    title: str
    source_path: str
    current_stage: PipelineStage
    stage_progress: float = 0.0  # 0.0 - 100.0
    stage_speed: int = 0  # bytes/sec (if applicable)
    stage_eta: Optional[int] = None  # seconds remaining
    overall_status: str = "pending"  # "active", "pending", "completed", "failed"
    has_error: bool = False
    error_message: Optional[str] = None
    file_size: int = 0
    plugin: str = "unknown"
    
    # Optional detailed stage info for expanded view
    stage_details: Optional[List[StageInfo]] = None
    
    @property
    def is_complete(self) -> bool:
        """Check if video completed all pipeline stages."""
        return self.current_stage == PipelineStage.COMPLETE
    
    @property
    def is_active(self) -> bool:
        """Check if video is actively processing."""
        return self.overall_status == "active"
    
    @property
    def is_pending(self) -> bool:
        """Check if video is pending."""
        return self.overall_status == "pending"
    
    @property
    def has_failed(self) -> bool:
        """Check if video has failed."""
        return self.overall_status == "failed" or self.has_error
    
    @property
    def formatted_speed(self) -> str:
        """Format speed for display."""
        if self.stage_speed == 0:
            return "-"
        return self._human_readable_bytes(self.stage_speed) + "/s"
    
    @property
    def formatted_eta(self) -> str:
        """Format ETA for display."""
        if self.stage_eta is None:
            return "--:--"
        minutes, seconds = divmod(self.stage_eta, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h{minutes:02d}m"
        return f"{minutes}:{seconds:02d}"
    
    @property
    def formatted_file_size(self) -> str:
        """Format file size for display."""
        if self.file_size == 0:
            return "-"
        return self._human_readable_bytes(self.file_size)
    
    @property
    def formatted_progress(self) -> str:
        """Format progress percentage for display."""
        return f"{self.stage_progress:.1f}%"
    
    @property
    def display_title(self) -> str:
        """Get display title (truncated if needed)."""
        max_len = 50
        if len(self.title) > max_len:
            return self.title[:max_len - 3] + "..."
        return self.title
    
    def _human_readable_bytes(self, size: int) -> str:
        """Convert bytes to human readable format."""
        if size < 1024:
            return f"{size}B"
        size = size / 1024
        if size < 1024:
            return f"{size:.1f}KB"
        size = size / 1024
        if size < 1024:
            return f"{size:.1f}MB"
        size = size / 1024
        return f"{size:.1f}GB"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert view to dictionary representation."""
        return {
            "id": self.id,
            "title": self.title,
            "source_path": self.source_path,
            "current_stage": self.current_stage.value,
            "stage_progress": self.stage_progress,
            "stage_speed": self.stage_speed,
            "stage_eta": self.stage_eta,
            "overall_status": self.overall_status,
            "has_error": self.has_error,
            "error_message": self.error_message,
            "file_size": self.file_size,
            "plugin": self.plugin,
            "formatted_speed": self.formatted_speed,
            "formatted_eta": self.formatted_eta,
            "is_complete": self.is_complete,
            "is_active": self.is_active,
        }
