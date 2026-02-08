# Task 4.1: Unified Download Progress Interface

**Priority:** P0 (Critical)  
**Owner:** Backend Engineer  
**Effort:** 3 days

**Description:**
Both YouTube and BitTorrent plugins download content, but they report progress differently. Create a unified interface that writes to the `downloads` table in the database, which the TUI can query regardless of source.

**Current State Analysis:**

**YouTube Plugin:**
- Uses yt-dlp with `progress_hook` callback
- Reports: `downloaded_bytes`, `total_bytes`, `speed`, `eta`
- No persistent storage during download (needs to write to `downloads` table)

**BitTorrent Plugin:**
- Uses `TorrentDownload` table (legacy)
- Reports: `progress` (0.0-1.0), `download_rate`, `peers`, `seeds`
- Should write unified progress to `downloads` table alongside TorrentDownload

**Implementation:**

### 4.1.1 Create DownloadProgress dataclass

```python
# src/haven_tui/data/download_tracker.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

class DownloadStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"  # No progress for timeout period

@dataclass
class DownloadProgress:
    """
    Universal download progress representation.
    
    Normalizes progress from any source plugin into a common format
    that gets written to the `downloads` table.
    """
    # Identification
    source_id: str                    # Correlates to video_id or torrent hash
    source_type: str                  # "youtube", "bittorrent", "direct", etc.
    video_id: Optional[int] = None    # Link to Video record once known
    
    # Content info
    title: str = ""
    uri: str = ""                     # Source URI (YouTube URL, magnet link, etc.)
    
    # Progress metrics
    total_size: int = 0               # Total bytes expected
    downloaded: int = 0               # Bytes downloaded
    progress_pct: float = 0.0         # 0.0 - 100.0
    
    # Speed metrics
    download_rate: float = 0.0        # bytes/sec (instantaneous)
    download_rate_avg: float = 0.0    # bytes/sec (averaged over window)
    upload_rate: float = 0.0          # bytes/sec (BitTorrent seeding)
    
    # Time estimates
    eta_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = field(default_factory=datetime.utcnow)
    
    # Connection metrics (plugin-specific)
    connections: int = 0              # HTTP connections (YouTube) or peers (BitTorrent)
    seeds: int = 0                    # Only meaningful for BitTorrent
    leechers: int = 0                 # Only meaningful for BitTorrent
    
    # State
    status: DownloadStatus = DownloadStatus.PENDING
    error_message: Optional[str] = None
    
    # Plugin-specific metadata stored as JSON
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_active(self) -> bool:
        """Check if download is currently active."""
        return self.status == DownloadStatus.DOWNLOADING
    
    @property
    def formatted_speed(self) -> str:
        """Format download speed for display."""
        return format_bytes(self.download_rate) + "/s"
    
    @property
    def formatted_eta(self) -> str:
        """Format ETA for display."""
        if self.eta_seconds is None:
            return "--:--"
        return format_duration(self.eta_seconds)
```

### 4.1.2 Create DownloadProgressTracker service

```python
# src/haven_tui/data/download_tracker.py

class DownloadProgressTracker:
    """
    Centralized download progress tracking service.
    
    Plugins report progress to this service, which:
    1. Normalizes plugin-specific formats to DownloadProgress
    2. Persists to the `downloads` table
    3. Maintains in-memory cache for hot queries
    4. Emits events for real-time TUI updates
    5. Updates PipelineSnapshot for TUI efficiency
    """
    
    def __init__(self, event_bus: EventBus, db_session_factory):
        self.event_bus = event_bus
        self.db_session_factory = db_session_factory
        self._cache: Dict[str, DownloadProgress] = {}
        self._lock = threading.RLock()
        
    def report_progress(self, progress: DownloadProgress) -> None:
        """
        Called by plugins to report progress updates.
        Thread-safe - can be called from plugin threads.
        """
        with self._lock:
            # Update cache
            self._cache[progress.source_id] = progress
            
            # Persist to downloads table
            self._persist_to_downloads_table(progress)
            
            # Update PipelineSnapshot for TUI queries
            self._update_pipeline_snapshot(progress)
            
            # Emit event for TUI real-time updates
            self._emit_progress_event(progress)
    
    def _persist_to_downloads_table(self, progress: DownloadProgress) -> None:
        """Persist progress to the downloads table."""
        with self.db_session_factory() as session:
            # Find existing download record or create new
            download = session.query(Download).filter_by(
                video_id=progress.video_id
            ).order_by(Download.created_at.desc()).first()
            
            if not download or download.status in ["completed", "failed"]:
                # Create new download record for new attempt
                download = Download(
                    video_id=progress.video_id,
                    source_type=progress.source_type,
                    source_metadata=progress.metadata,
                )
                session.add(download)
            
            # Update download record
            download.status = progress.status.value
            download.progress_percent = progress.progress_pct
            download.bytes_downloaded = int(progress.downloaded)
            download.bytes_total = int(progress.total_size)
            download.download_rate = int(progress.download_rate)
            download.eta_seconds = progress.eta_seconds
            
            if progress.started_at and not download.started_at:
                download.started_at = progress.started_at
            
            if progress.status == DownloadStatus.COMPLETED:
                download.completed_at = datetime.now()
            elif progress.status == DownloadStatus.FAILED:
                download.failed_at = datetime.now()
                download.error_message = progress.error_message
            
            download.updated_at = datetime.now()
            session.commit()
            
            # Store the download ID for future updates
            if not progress.video_id:
                # Try to link to video if we can find it
                video = self._find_video_by_source(session, progress.uri)
                if video:
                    download.video_id = video.id
                    progress.video_id = video.id
                    session.commit()
    
    def _update_pipeline_snapshot(self, progress: DownloadProgress) -> None:
        """Update PipelineSnapshot for efficient TUI queries."""
        if not progress.video_id:
            return
        
        with self.db_session_factory() as session:
            snapshot = session.query(PipelineSnapshot).filter_by(
                video_id=progress.video_id
            ).first()
            
            if not snapshot:
                snapshot = PipelineSnapshot(video_id=progress.video_id)
                session.add(snapshot)
            
            snapshot.current_stage = "download"
            snapshot.overall_status = "active" if progress.is_active else "pending"
            snapshot.stage_progress_percent = progress.progress_pct
            snapshot.stage_speed = int(progress.download_rate)
            snapshot.stage_eta = progress.eta_seconds
            snapshot.downloaded_bytes = int(progress.downloaded)
            snapshot.total_bytes = int(progress.total_size)
            snapshot.stage_started_at = progress.started_at
            snapshot.updated_at = datetime.now()
            
            if progress.status == DownloadStatus.FAILED:
                snapshot.has_error = True
                snapshot.error_stage = "download"
                snapshot.error_message = progress.error_message
            
            session.commit()
    
    def _emit_progress_event(self, progress: DownloadProgress) -> None:
        """Emit DOWNLOAD_PROGRESS event."""
        event = Event(
            EventType.DOWNLOAD_PROGRESS,
            payload={
                "source_id": progress.source_id,
                "video_id": progress.video_id,
                "video_path": progress.title,
                "source_type": progress.source_type,
                "progress_percent": progress.progress_pct,
                "download_rate": progress.download_rate,
                "eta_seconds": progress.eta_seconds,
                "total_bytes": progress.total_size,
                "downloaded_bytes": progress.downloaded,
                "connections": progress.connections,
                "seeds": progress.seeds,
            }
        )
        asyncio.create_task(self.event_bus.publish(event))
    
    def _find_video_by_source(self, session, source_uri: str) -> Optional[Video]:
        """Find video by source URI to link download record."""
        return session.query(Video).filter(
            Video.source_uri == source_uri
        ).first()
    
    def get_progress(self, source_id: str) -> Optional[DownloadProgress]:
        """Get current progress for a download (from cache)."""
        with self._lock:
            return self._cache.get(source_id)
    
    def get_all_active(self) -> List[DownloadProgress]:
        """Get all active downloads (for TUI main view)."""
        with self._lock:
            return [
                p for p in self._cache.values()
                if p.status in (DownloadStatus.DOWNLOADING, DownloadStatus.PAUSED)
            ]
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate stats for dashboard."""
        active = self.get_all_active()
        
        return {
            "total_active": len(active),
            "total_download_speed": sum(p.download_rate for p in active),
            "total_upload_speed": sum(p.upload_rate for p in active),
            "by_type": self._count_by_type(active),
            "by_status": self._count_by_status(active),
        }
    
    def _count_by_type(self, progresses: List[DownloadProgress]) -> Dict[str, int]:
        """Count downloads by source type."""
        counts = {}
        for p in progresses:
            counts[p.source_type] = counts.get(p.source_type, 0) + 1
        return counts
```

**Acceptance Criteria:**
- [ ] YouTube downloads create records in `downloads` table
- [ ] BitTorrent downloads create records in `downloads` table
- [ ] Both appear identical when querying `downloads` table
- [ ] `PipelineSnapshot` updated for TUI queries
- [ ] Events emitted for each progress update
- [ ] Aggregate stats calculated correctly
