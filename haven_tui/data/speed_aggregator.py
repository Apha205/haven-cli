"""Download Speed Aggregator for Haven TUI.

This module provides a service that aggregates download speeds from the
`downloads` table and `speed_history` table for TUI display.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple, Any

from sqlalchemy import func

from haven_cli.database.models import Download, SpeedHistory


@dataclass
class SpeedSample:
    """Single speed measurement.
    
    Attributes:
        timestamp: Unix timestamp of the sample
        video_id: Video ID associated with this sample
        stage: Pipeline stage (e.g., "download", "encrypt", "upload")
        download_rate: Download speed in bytes/sec
        upload_rate: Upload speed in bytes/sec (for BitTorrent seeding)
    """
    timestamp: float
    video_id: int
    stage: str
    download_rate: float
    upload_rate: float


@dataclass
class SpeedAggregate:
    """Aggregated speed statistics.
    
    Attributes:
        current_download: Current download speed in bytes/sec
        current_upload: Current upload speed in bytes/sec
        average_download: Average download speed in bytes/sec
        average_upload: Average upload speed in bytes/sec
        peak_download: Peak download speed in bytes/sec
        peak_upload: Peak upload speed in bytes/sec
        sample_count: Number of samples in the aggregation window
    """
    current_download: float = 0.0
    current_upload: float = 0.0
    average_download: float = 0.0
    average_upload: float = 0.0
    peak_download: float = 0.0
    peak_upload: float = 0.0
    sample_count: int = 0


class SpeedAggregator:
    """Aggregates download/upload speeds from downloads and speed_history tables.
    
    Maintains rolling window of samples for graphing and averaging.
    Thread-safe for concurrent updates.
    
    Attributes:
        db_session_factory: Factory function that returns a database session
        window_seconds: Rolling window duration in seconds
    
    Example:
        >>> aggregator = SpeedAggregator(db_session_factory, window_seconds=60)
        >>> aggregator.sample_from_downloads_table()
        >>> speeds = aggregator.get_current_speeds()
        >>> history = aggregator.get_speed_history(video_id=1)
    """
    
    def __init__(
        self,
        db_session_factory: Callable,
        window_seconds: int = 60
    ):
        """Initialize the speed aggregator.
        
        Args:
            db_session_factory: Factory function that returns a database session
            window_seconds: Rolling window duration in seconds (default: 60)
        """
        self.db_session_factory = db_session_factory
        self.window_seconds = window_seconds
        self._samples: deque[SpeedSample] = deque()
        self._lock = threading.RLock()
        self._last_aggregate_time: float = 0.0
    
    def sample_from_downloads_table(self) -> int:
        """Sample current speeds from downloads table.
        
        Queries active downloads and adds samples to the rolling window.
        Also records samples to the speed_history table for persistence.
        
        Returns:
            Number of samples added
        """
        count = 0
        with self.db_session_factory() as session:
            # Query active downloads
            active = session.query(Download).filter(
                Download.status == "downloading"
            ).all()
            
            for download in active:
                # Get upload rate from source_metadata if available
                upload_rate = 0.0
                if download.source_metadata and isinstance(download.source_metadata, dict):
                    upload_rate = float(download.source_metadata.get("upload_rate", 0))
                
                self.add_sample(
                    video_id=download.video_id,
                    stage="download",
                    download_rate=float(download.download_rate or 0),
                    upload_rate=upload_rate
                )
                count += 1
                
                # Also record to speed_history for persistence
                self._record_to_speed_history(
                    video_id=download.video_id,
                    stage="download",
                    speed=download.download_rate or 0,
                    progress=download.progress_percent or 0.0,
                    bytes_processed=download.bytes_downloaded or 0,
                    session=session
                )
        
        return count
    
    def add_sample(
        self,
        video_id: int,
        stage: str,
        download_rate: float,
        upload_rate: float = 0.0
    ) -> None:
        """Add a speed sample from a source.
        
        Thread-safe - can be called from any thread.
        
        Args:
            video_id: Video ID associated with this sample
            stage: Pipeline stage (e.g., "download", "encrypt", "upload")
            download_rate: Download speed in bytes/sec
            upload_rate: Upload speed in bytes/sec
        """
        with self._lock:
            sample = SpeedSample(
                timestamp=time.time(),
                video_id=video_id,
                stage=stage,
                download_rate=download_rate,
                upload_rate=upload_rate
            )
            
            self._samples.append(sample)
            self._cleanup_old_samples()
    
    def _cleanup_old_samples(self) -> None:
        """Remove samples older than the rolling window.
        
        This is called internally and should only be called while holding _lock.
        """
        cutoff = time.time() - self.window_seconds
        while self._samples and self._samples[0].timestamp < cutoff:
            self._samples.popleft()
    
    def _record_to_speed_history(
        self,
        video_id: int,
        stage: str,
        speed: int,
        progress: float,
        bytes_processed: int,
        session: Any
    ) -> Optional[SpeedHistory]:
        """Record a speed sample to the speed_history table.
        
        Args:
            video_id: Video ID
            stage: Pipeline stage
            speed: Speed in bytes/sec
            progress: Progress percentage (0-100)
            bytes_processed: Bytes processed so far
            session: Database session
            
        Returns:
            Created SpeedHistory entry, or None if recording failed
        """
        try:
            entry = SpeedHistory(
                video_id=video_id,
                stage=stage,
                speed=speed,
                progress=progress,
                bytes_processed=bytes_processed,
            )
            session.add(entry)
            session.commit()
            return entry
        except Exception:
            # If commit fails, rollback and continue
            try:
                session.rollback()
            except Exception:
                pass
            return None
    
    def get_current_speeds(self) -> Tuple[float, float]:
        """Get current aggregate download and upload speeds.
        
        Queries the downloads table for the most recent active downloads
        and sums their download/upload rates.
        
        Returns:
            Tuple of (total_download_rate, total_upload_rate) in bytes/sec
        """
        with self.db_session_factory() as session:
            result = session.query(
                func.sum(Download.download_rate),
                func.sum(Download.download_rate)  # Download table doesn't have upload_rate column
            ).filter(
                Download.status == "downloading"
            ).first()
            
            download_rate = float(result[0] or 0.0)
            
            # For upload rate, check source_metadata in Download records
            # This is where BitTorrent upload rate is stored
            upload_rate = 0.0
            active_downloads = session.query(Download).filter(
                Download.status == "downloading"
            ).all()
            
            for download in active_downloads:
                if download.source_metadata and isinstance(download.source_metadata, dict):
                    upload_rate += float(download.source_metadata.get("upload_rate", 0))
            
            return (download_rate, upload_rate)
    
    def get_average_speeds(
        self,
        window_seconds: Optional[int] = None
    ) -> Tuple[float, float]:
        """Get average speeds from speed_history table.
        
        Args:
            window_seconds: Time window for averaging (default: self.window_seconds)
            
        Returns:
            Tuple of (average_download_speed, average_upload_speed) in bytes/sec
        """
        since = datetime.now(timezone.utc) - timedelta(
            seconds=window_seconds or self.window_seconds
        )
        
        with self.db_session_factory() as session:
            # Get average download speed
            download_avg = session.query(
                func.avg(SpeedHistory.speed)
            ).filter(
                SpeedHistory.timestamp >= since,
                SpeedHistory.stage == "download"
            ).scalar()
            
            # Note: Upload speeds in speed_history are recorded with stage="upload"
            upload_avg = session.query(
                func.avg(SpeedHistory.speed)
            ).filter(
                SpeedHistory.timestamp >= since,
                SpeedHistory.stage == "upload"
            ).scalar()
            
            return (
                float(download_avg or 0.0),
                float(upload_avg or 0.0)
            )
    
    def get_speed_history(
        self,
        video_id: Optional[int] = None,
        stage: Optional[str] = None,
        resolution_seconds: int = 1
    ) -> List[Tuple[float, float, float]]:
        """Get speed history for graphing from speed_history table.
        
        Args:
            video_id: Optional video ID to filter by (default: all videos)
            stage: Optional stage to filter by (e.g., "download", "encrypt", "upload")
            resolution_seconds: Time bucket resolution in seconds (currently unused)
            
        Returns:
            List of (timestamp, download_rate, upload_rate) tuples.
            For download stage, upload_rate will be 0.
            For upload stage, download_rate will be the upload speed.
        """
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        
        with self.db_session_factory() as session:
            query = session.query(SpeedHistory).filter(
                SpeedHistory.timestamp >= since
            )
            
            if video_id is not None:
                query = query.filter(SpeedHistory.video_id == video_id)
            
            if stage is not None:
                query = query.filter(SpeedHistory.stage == stage)
            
            samples = query.order_by(SpeedHistory.timestamp).all()
            
            # Transform to (timestamp, speed_for_stage, 0) format
            # For upload stage, treat speed as "upload rate" in the third position
            result = []
            for s in samples:
                ts = s.timestamp.timestamp() if s.timestamp else time.time()
                if s.stage == "upload":
                    # For upload stage, put speed in upload position
                    result.append((ts, 0.0, float(s.speed)))
                else:
                    # For download and other stages, put speed in download position
                    result.append((ts, float(s.speed), 0.0))
            
            return result
    
    def get_speed_history_for_graphing(
        self,
        video_id: int,
        stage: str = "download"
    ) -> List[Tuple[float, float]]:
        """Get speed history formatted for graphing components.
        
        Args:
            video_id: Video ID to get history for
            stage: Pipeline stage (default: "download")
            
        Returns:
            List of (timestamp, speed) tuples where timestamp is Unix timestamp
        """
        since = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        
        with self.db_session_factory() as session:
            samples = session.query(SpeedHistory).filter(
                SpeedHistory.video_id == video_id,
                SpeedHistory.stage == stage,
                SpeedHistory.timestamp >= since
            ).order_by(SpeedHistory.timestamp).all()
            
            return [
                (s.timestamp.timestamp(), float(s.speed))
                for s in samples if s.timestamp
            ]
    
    def get_aggregate_stats(self) -> SpeedAggregate:
        """Get comprehensive speed statistics from current samples.
        
        Calculates current, average, and peak speeds from the rolling window.
        
        Returns:
            SpeedAggregate with computed statistics
        """
        with self._lock:
            if not self._samples:
                return SpeedAggregate()
            
            download_rates = [s.download_rate for s in self._samples]
            upload_rates = [s.upload_rate for s in self._samples]
            
            return SpeedAggregate(
                current_download=download_rates[-1] if download_rates else 0.0,
                current_upload=upload_rates[-1] if upload_rates else 0.0,
                average_download=sum(download_rates) / len(download_rates) if download_rates else 0.0,
                average_upload=sum(upload_rates) / len(upload_rates) if upload_rates else 0.0,
                peak_download=max(download_rates) if download_rates else 0.0,
                peak_upload=max(upload_rates) if upload_rates else 0.0,
                sample_count=len(self._samples)
            )
    
    def get_samples_by_video(
        self,
        video_id: int
    ) -> List[SpeedSample]:
        """Get all samples for a specific video.
        
        Args:
            video_id: Video ID to filter by
            
        Returns:
            List of SpeedSample objects for the video
        """
        with self._lock:
            return [s for s in self._samples if s.video_id == video_id]
    
    def get_samples_by_stage(
        self,
        stage: str
    ) -> List[SpeedSample]:
        """Get all samples for a specific stage.
        
        Args:
            stage: Pipeline stage to filter by
            
        Returns:
            List of SpeedSample objects for the stage
        """
        with self._lock:
            return [s for s in self._samples if s.stage == stage]
    
    def clear_samples(self) -> None:
        """Clear all in-memory samples.
        
        Note: This does not affect the speed_history table.
        """
        with self._lock:
            self._samples.clear()
    
    def set_window_seconds(self, window_seconds: int) -> None:
        """Update the rolling window duration.
        
        Args:
            window_seconds: New window duration in seconds
        """
        with self._lock:
            self.window_seconds = window_seconds
            self._cleanup_old_samples()
    
    @property
    def sample_count(self) -> int:
        """Get the current number of samples in the rolling window."""
        with self._lock:
            return len(self._samples)
    
    @property
    def window_start_time(self) -> float:
        """Get the timestamp of the oldest sample in the window."""
        with self._lock:
            if not self._samples:
                return time.time()
            return self._samples[0].timestamp
