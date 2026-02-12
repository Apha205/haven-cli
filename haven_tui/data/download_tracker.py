"""Unified Download Progress Interface for Haven TUI.

This module provides a centralized download progress tracking service that normalizes
progress from any source plugin (YouTube, BitTorrent, etc.) into a common format
that gets written to the `downloads` table.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from haven_cli.database.models import Download, Video, PipelineSnapshot
from haven_cli.pipeline.events import EventBus, EventType, Event

logger = logging.getLogger(__name__)


class DownloadStatus(Enum):
    """Download status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"  # No progress for timeout period
    SKIPPED = "skipped"  # Skipped due to size limits or other criteria


def format_bytes(size_bytes: float) -> str:
    """Format bytes to human readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human readable string (e.g., "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f"{size_bytes:.2f} {size_names[i]}"


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable string.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string (e.g., "01:30:45" or "30:45")
    """
    if seconds < 0:
        return "--:--"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


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
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
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
    
    @property
    def formatted_size(self) -> str:
        """Format total size for display."""
        return format_bytes(self.total_size)
    
    @property
    def formatted_downloaded(self) -> str:
        """Format downloaded bytes for display."""
        return format_bytes(self.downloaded)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert progress to dictionary representation."""
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "video_id": self.video_id,
            "title": self.title,
            "uri": self.uri,
            "total_size": self.total_size,
            "downloaded": self.downloaded,
            "progress_pct": self.progress_pct,
            "download_rate": self.download_rate,
            "upload_rate": self.upload_rate,
            "eta_seconds": self.eta_seconds,
            "formatted_speed": self.formatted_speed,
            "formatted_eta": self.formatted_eta,
            "connections": self.connections,
            "seeds": self.seeds,
            "leechers": self.leechers,
            "status": self.status.value,
            "is_active": self.is_active,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


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
    
    def __init__(
        self,
        event_bus: EventBus,
        db_session_factory: Callable,
        enable_events: bool = True
    ):
        """Initialize the download progress tracker.
        
        Args:
            event_bus: Event bus for emitting progress events
            db_session_factory: Factory function that returns a database session
            enable_events: Whether to emit events for progress updates
        """
        self.event_bus = event_bus
        self.db_session_factory = db_session_factory
        self._cache: Dict[str, DownloadProgress] = {}
        self._lock = threading.RLock()
        self._enable_events = enable_events
        
    def report_progress(self, progress: DownloadProgress) -> None:
        """
        Called by plugins to report progress updates.
        Thread-safe - can be called from plugin threads.
        
        Args:
            progress: DownloadProgress object with current state
        """
        with self._lock:
            # Update timestamp
            progress.updated_at = datetime.now(timezone.utc)
            
            # Update cache
            self._cache[progress.source_id] = progress
            
            try:
                # Persist to downloads table
                self._persist_to_downloads_table(progress)
                
                # Update PipelineSnapshot for TUI queries
                if progress.video_id:
                    self._update_pipeline_snapshot(progress)
                
                # Emit event for TUI real-time updates
                if self._enable_events:
                    self._emit_progress_event(progress)
                    
            except Exception as e:
                logger.error(f"Error processing progress report for {progress.source_id}: {e}")
    
    def _persist_to_downloads_table(self, progress: DownloadProgress) -> None:
        """Persist progress to the downloads table.
        
        Args:
            progress: DownloadProgress to persist
        """
        try:
            with self.db_session_factory() as session:
                # Try to find existing download record
                download = None
                if progress.video_id:
                    download = session.query(Download).filter_by(
                        video_id=progress.video_id
                    ).order_by(Download.created_at.desc()).first()
                
                # Check if we need a new record
                if not download or download.status in ["completed", "failed"]:
                    if progress.video_id:
                        # Create new download record for new attempt
                        download = Download(
                            video_id=progress.video_id,
                            source_type=progress.source_type,
                            source_metadata=progress.metadata,
                        )
                        session.add(download)
                        session.commit()  # Commit to get the ID
                    else:
                        # Can't create download without video_id yet
                        logger.debug(f"Skipping download record creation - no video_id for {progress.source_id}")
                        return
                
                if download:
                    # Update download record
                    download.status = progress.status.value
                    download.progress_percent = progress.progress_pct
                    download.bytes_downloaded = int(progress.downloaded)
                    download.bytes_total = int(progress.total_size)
                    download.download_rate = int(progress.download_rate)
                    download.eta_seconds = progress.eta_seconds
                    download.source_metadata = {
                        **(download.source_metadata or {}),
                        **progress.metadata,
                        "connections": progress.connections,
                        "seeds": progress.seeds,
                        "leechers": progress.leechers,
                        "upload_rate": progress.upload_rate,
                    }
                    
                    if progress.started_at and not download.started_at:
                        download.started_at = progress.started_at
                    
                    if progress.status == DownloadStatus.COMPLETED:
                        download.completed_at = datetime.now(timezone.utc)
                    elif progress.status == DownloadStatus.FAILED:
                        download.failed_at = datetime.now(timezone.utc)
                        download.error_message = progress.error_message
                    
                    download.updated_at = datetime.now(timezone.utc)
                    session.commit()
                    
        except Exception as e:
            logger.error(f"Error persisting download progress: {e}")
            raise
    
    def _update_pipeline_snapshot(self, progress: DownloadProgress) -> None:
        """Update PipelineSnapshot for efficient TUI queries.
        
        Args:
            progress: DownloadProgress to update snapshot with
        """
        if not progress.video_id:
            return
        
        try:
            with self.db_session_factory() as session:
                snapshot = session.query(PipelineSnapshot).filter_by(
                    video_id=progress.video_id
                ).first()
                
                if not snapshot:
                    snapshot = PipelineSnapshot(
                        video_id=progress.video_id,
                        current_stage="download",
                        overall_status="active" if progress.is_active else "pending"
                    )
                    session.add(snapshot)
                
                snapshot.current_stage = "download"
                if progress.status == DownloadStatus.DOWNLOADING:
                    snapshot.overall_status = "active"
                elif progress.status == DownloadStatus.COMPLETED:
                    snapshot.overall_status = "pending"  # Ready for next stage
                elif progress.status == DownloadStatus.FAILED:
                    snapshot.overall_status = "failed"
                elif progress.status == DownloadStatus.PAUSED:
                    snapshot.overall_status = "pending"
                
                snapshot.stage_progress_percent = progress.progress_pct
                snapshot.stage_speed = int(progress.download_rate)
                snapshot.stage_eta = progress.eta_seconds
                snapshot.downloaded_bytes = int(progress.downloaded)
                snapshot.total_bytes = int(progress.total_size)
                
                if progress.started_at and not snapshot.stage_started_at:
                    snapshot.stage_started_at = progress.started_at
                
                if progress.status == DownloadStatus.FAILED:
                    snapshot.has_error = True
                    snapshot.error_stage = "download"
                    snapshot.error_message = progress.error_message
                
                snapshot.updated_at = datetime.now(timezone.utc)
                session.commit()
                
        except Exception as e:
            logger.error(f"Error updating pipeline snapshot: {e}")
            raise
    
    def _emit_progress_event(self, progress: DownloadProgress) -> None:
        """Emit DOWNLOAD_PROGRESS event.
        
        For torrents without video_id, uses a negative ID based on the
        torrent's infohash to allow state tracking in the TUI.
        
        Args:
            progress: DownloadProgress to emit event for
        """
        try:
            # Determine video_id for event
            video_id = progress.video_id
            
            # For torrents without video_id, create a synthetic ID from source_id
            # This allows the TUI to track orphaned torrents
            if video_id is None and progress.source_type == "bittorrent":
                # Use a hash of the infohash to create a consistent negative ID
                # This ensures the same torrent always gets the same synthetic ID
                import hashlib
                hash_int = int(hashlib.md5(progress.source_id.encode()).hexdigest()[:8], 16)
                video_id = -(hash_int % 1000000000)  # Negative ID to indicate synthetic
            
            event = Event(
                EventType.DOWNLOAD_PROGRESS,
                payload={
                    "source_id": progress.source_id,
                    "video_id": video_id,
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
            # Use create_task to avoid blocking
            asyncio.create_task(self.event_bus.publish(event))
        except Exception as e:
            logger.error(f"Error emitting progress event: {e}")
    
    def link_video_to_download(self, source_id: str, video_id: int) -> None:
        """Link a download to a video record.
        
        This should be called when a video record is created for a download.
        
        Args:
            source_id: The source ID of the download
            video_id: The video ID to link
        """
        with self._lock:
            progress = self._cache.get(source_id)
            if progress:
                progress.video_id = video_id
                # Trigger an immediate update to persist the link
                self.report_progress(progress)
    
    def get_progress(self, source_id: str) -> Optional[DownloadProgress]:
        """Get current progress for a download (from cache).
        
        Args:
            source_id: The source ID of the download
            
        Returns:
            DownloadProgress if found, None otherwise
        """
        with self._lock:
            return self._cache.get(source_id)
    
    def get_all_active(self) -> List[DownloadProgress]:
        """Get all active downloads (for TUI main view).
        
        Returns:
            List of active DownloadProgress objects
        """
        with self._lock:
            return [
                p for p in self._cache.values()
                if p.status in (DownloadStatus.DOWNLOADING, DownloadStatus.PAUSED)
            ]
    
    def get_all(self) -> List[DownloadProgress]:
        """Get all tracked downloads.
        
        Returns:
            List of all DownloadProgress objects in cache
        """
        with self._lock:
            return list(self._cache.values())
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate stats for dashboard.
        
        Returns:
            Dictionary with aggregate statistics
        """
        active = self.get_all_active()
        all_downloads = self.get_all()
        
        return {
            "total_active": len(active),
            "total_download_speed": sum(p.download_rate for p in active),
            "total_upload_speed": sum(p.upload_rate for p in active),
            "by_type": self._count_by_type(all_downloads),
            "by_status": self._count_by_status(all_downloads),
        }
    
    def _count_by_type(self, progresses: List[DownloadProgress]) -> Dict[str, int]:
        """Count downloads by source type.
        
        Args:
            progresses: List of DownloadProgress objects
            
        Returns:
            Dictionary mapping source type to count
        """
        counts = {}
        for p in progresses:
            counts[p.source_type] = counts.get(p.source_type, 0) + 1
        return counts
    
    def _count_by_status(self, progresses: List[DownloadProgress]) -> Dict[str, int]:
        """Count downloads by status.
        
        Args:
            progresses: List of DownloadProgress objects
            
        Returns:
            Dictionary mapping status to count
        """
        counts = {}
        for p in progresses:
            status = p.status.value
            counts[status] = counts.get(status, 0) + 1
        return counts
    
    def remove_download(self, source_id: str) -> bool:
        """Remove a download from tracking.
        
        Args:
            source_id: The source ID of the download to remove
            
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if source_id in self._cache:
                del self._cache[source_id]
                return True
            return False
    
    def clear_cache(self) -> None:
        """Clear all cached progress data."""
        with self._lock:
            self._cache.clear()


class YouTubeProgressAdapter:
    """Adapter for converting YouTube/yt-dlp progress to DownloadProgress.
    
    Example:
        adapter = YouTubeProgressAdapter(tracker, video_id, source_uri)
        
        # In yt-dlp progress hook:
        def progress_hook(d):
            progress = adapter.from_ytdlp_progress(d)
            tracker.report_progress(progress)
    """
    
    def __init__(
        self,
        tracker: DownloadProgressTracker,
        source_id: str,
        video_id: Optional[int] = None,
        source_uri: str = "",
        title: str = ""
    ):
        """Initialize the YouTube progress adapter.
        
        Args:
            tracker: The DownloadProgressTracker to report to
            source_id: The YouTube video ID
            video_id: The database video ID (if known)
            source_uri: The YouTube URL
            title: Video title
        """
        self.tracker = tracker
        self.source_id = source_id
        self.video_id = video_id
        self.source_uri = source_uri
        self.title = title
    
    def from_ytdlp_progress(self, d: Dict[str, Any]) -> DownloadProgress:
        """Convert yt-dlp progress dict to DownloadProgress.
        
        Args:
            d: yt-dlp progress dictionary
            
        Returns:
            DownloadProgress object
        """
        status = d.get("status", "downloading")
        
        # Map yt-dlp status to DownloadStatus
        status_map = {
            "downloading": DownloadStatus.DOWNLOADING,
            "finished": DownloadStatus.COMPLETED,
            "error": DownloadStatus.FAILED,
        }
        download_status = status_map.get(status, DownloadStatus.DOWNLOADING)
        
        # Calculate progress
        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        progress_pct = 0.0
        if total and total > 0:
            progress_pct = (downloaded / total) * 100
        
        # Get speed and ETA
        speed = d.get("speed", 0) or 0
        eta = d.get("eta")
        
        # Get error message if any
        error_msg = None
        if download_status == DownloadStatus.FAILED:
            error_msg = d.get("error", "Unknown error")
        
        return DownloadProgress(
            source_id=self.source_id,
            source_type="youtube",
            video_id=self.video_id,
            title=self.title,
            uri=self.source_uri,
            total_size=total,
            downloaded=downloaded,
            progress_pct=progress_pct,
            download_rate=float(speed),
            eta_seconds=eta,
            connections=1,  # yt-dlp typically uses single connection per file
            status=download_status,
            error_message=error_msg,
            metadata={
                "filename": d.get("filename"),
                "tmpfilename": d.get("tmpfilename"),
            }
        )
    
    def report(self, d: Dict[str, Any]) -> None:
        """Convert and report progress in one step.
        
        Args:
            d: yt-dlp progress dictionary
        """
        progress = self.from_ytdlp_progress(d)
        self.tracker.report_progress(progress)


class BitTorrentProgressAdapter:
    """Adapter for converting BitTorrent/libtorrent progress to DownloadProgress.
    
    Example:
        adapter = BitTorrentProgressAdapter(tracker, infohash, video_id)
        
        # In download loop:
        status = handle.status()
        progress = adapter.from_libtorrent_status(status)
        tracker.report_progress(progress)
    """
    
    def __init__(
        self,
        tracker: DownloadProgressTracker,
        infohash: str,
        video_id: Optional[int] = None,
        magnet_uri: str = "",
        title: str = ""
    ):
        """Initialize the BitTorrent progress adapter.
        
        Args:
            tracker: The DownloadProgressTracker to report to
            infohash: The torrent infohash
            video_id: The database video ID (if known)
            magnet_uri: The magnet URI
            title: Torrent title
        """
        self.tracker = tracker
        self.infohash = infohash
        self.video_id = video_id
        self.magnet_uri = magnet_uri
        self.title = title
    
    def from_libtorrent_status(self, status: Any) -> DownloadProgress:
        """Convert libtorrent status to DownloadProgress.
        
        Args:
            status: libtorrent torrent_status object
            
        Returns:
            DownloadProgress object
        """
        # Determine status
        if status.is_finished:
            download_status = DownloadStatus.COMPLETED
        elif status.paused:
            download_status = DownloadStatus.PAUSED
        elif status.errc:
            download_status = DownloadStatus.FAILED
        else:
            download_status = DownloadStatus.DOWNLOADING
        
        # Calculate progress (libtorrent gives 0.0-1.0)
        progress_pct = status.progress * 100
        
        # Get sizes
        total = status.total_wanted
        downloaded = status.total_wanted_done
        
        # Calculate ETA
        eta = None
        if status.download_rate > 0 and downloaded < total:
            eta = int((total - downloaded) / status.download_rate)
        
        return DownloadProgress(
            source_id=self.infohash,
            source_type="bittorrent",
            video_id=self.video_id,
            title=self.title,
            uri=self.magnet_uri,
            total_size=total,
            downloaded=downloaded,
            progress_pct=progress_pct,
            download_rate=float(status.download_rate),
            upload_rate=float(status.upload_rate),
            eta_seconds=eta,
            connections=status.num_peers,
            seeds=status.num_seeds,
            leechers=status.num_peers - status.num_seeds,
            status=download_status,
            error_message=str(status.errc) if status.errc else None,
            metadata={
                "num_complete": status.num_complete,
                "num_incomplete": status.num_incomplete,
                "distributed_copies": status.distributed_copies,
                "block_size": status.block_size,
            }
        )
    
    def from_dict(self, data: Dict[str, Any]) -> DownloadProgress:
        """Convert dictionary (from TorrentDownload record) to DownloadProgress.
        
        Args:
            data: Dictionary with torrent download data
            
        Returns:
            DownloadProgress object
        """
        # Map status string to DownloadStatus
        status_map = {
            "downloading": DownloadStatus.DOWNLOADING,
            "paused": DownloadStatus.PAUSED,
            "completed": DownloadStatus.COMPLETED,
            "failed": DownloadStatus.FAILED,
            "stalled": DownloadStatus.STALLED,
        }
        status_str = data.get("status", "downloading")
        download_status = status_map.get(status_str, DownloadStatus.DOWNLOADING)
        
        # Get progress (libtorrent stores as 0.0-1.0)
        progress = data.get("progress", 0.0)
        progress_pct = progress * 100 if progress <= 1.0 else progress
        
        return DownloadProgress(
            source_id=self.infohash,
            source_type="bittorrent",
            video_id=self.video_id,
            title=data.get("title", self.title),
            uri=data.get("magnet_uri", self.magnet_uri),
            total_size=data.get("total_size", 0),
            downloaded=data.get("downloaded_size", 0),
            progress_pct=progress_pct,
            download_rate=float(data.get("download_rate", 0)),
            upload_rate=float(data.get("upload_rate", 0)),
            connections=data.get("peers", 0),
            seeds=data.get("seeds", 0),
            leechers=data.get("peers", 0) - data.get("seeds", 0),
            status=download_status,
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {})
        )
    
    def report_status(self, status: Any) -> None:
        """Convert and report libtorrent status in one step.
        
        Args:
            status: libtorrent torrent_status object
        """
        progress = self.from_libtorrent_status(status)
        self.tracker.report_progress(progress)
    
    def report_dict(self, data: Dict[str, Any]) -> None:
        """Convert and report dictionary in one step.
        
        Args:
            data: Dictionary with torrent download data
        """
        progress = self.from_dict(data)
        self.tracker.report_progress(progress)


# Singleton tracker instance
_default_tracker: Optional[DownloadProgressTracker] = None


def get_download_tracker(
    event_bus: Optional[EventBus] = None,
    db_session_factory: Optional[Callable] = None,
    enable_events: bool = True
) -> DownloadProgressTracker:
    """Get or create the default download progress tracker.
    
    Args:
        event_bus: Event bus for emitting events (required if creating new)
        db_session_factory: Factory for database sessions (required if creating new)
        enable_events: Whether to enable event emission
        
    Returns:
        DownloadProgressTracker instance
    """
    global _default_tracker
    if _default_tracker is None:
        if event_bus is None or db_session_factory is None:
            raise ValueError("event_bus and db_session_factory required for first initialization")
        _default_tracker = DownloadProgressTracker(
            event_bus=event_bus,
            db_session_factory=db_session_factory,
            enable_events=enable_events
        )
    return _default_tracker


def reset_download_tracker() -> None:
    """Reset the default tracker (useful for testing)."""
    global _default_tracker
    if _default_tracker is not None:
        _default_tracker.clear_cache()
    _default_tracker = None
