"""Metrics collection for TUI.

This module provides the MetricsCollector class - a thin TUI-facing wrapper
around SpeedHistoryService that provides simplified access for visualization
components.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any

from haven_cli.services.speed_history import SpeedHistoryService

logger = logging.getLogger(__name__)

# Valid stages for pipeline processing
VALID_STAGES = {"download", "encrypt", "upload"}


class MetricsCollector:
    """TUI-facing metrics collector.
    
    Thin wrapper around SpeedHistoryService that provides
    simplified access for visualization components.
    
    Example:
        from haven_cli.services.speed_history import SpeedHistoryService
        
        service = SpeedHistoryService(db_session, event_bus)
        await service.start()
        
        collector = MetricsCollector(service)
        
        # Record speed
        collector.record_speed(1, "download", 1024000.0, 50.0)
        
        # Get speed history
        history = collector.get_speed_history(1, "download", seconds=60)
        
        # Get aggregate speeds
        aggregates = collector.get_aggregate_speeds(seconds=60)
    """
    
    def __init__(self, service: SpeedHistoryService, max_history_seconds: int = 300):
        """Initialize the metrics collector.
        
        Args:
            service: SpeedHistoryService instance to wrap
            max_history_seconds: Maximum history to keep in seconds (default 5 minutes)
        """
        self._service = service
        self._max_history = max_history_seconds
    
    # Recording (typically called by StateManager)
    
    def record_speed(self, video_id: int, stage: str, speed: float, progress: float = 0) -> None:
        """Record speed sample - delegates to service.
        
        Args:
            video_id: Video ID
            stage: Stage name ("download", "encrypt", "upload")
            speed: Speed in bytes/sec
            progress: Progress percentage (0-100)
        """
        if stage not in VALID_STAGES:
            logger.warning(f"Invalid stage '{stage}' for speed recording")
            return
        
        self._service.record_sample(
            video_id=video_id,
            stage=stage,
            speed=int(speed),
            progress=progress,
            bytes_processed=0  # Can be calculated if needed
        )
    
    # Per-video queries
    
    def get_speed_history(
        self,
        video_id: int,
        stage: str,
        seconds: int = 60
    ) -> List[Tuple[datetime, float]]:
        """Get speed history for a specific video and stage.
        
        Args:
            video_id: Video ID
            stage: Stage name ("download", "encrypt", "upload")
            seconds: Time window in seconds
            
        Returns:
            List of (timestamp, speed_bps) tuples
        """
        if stage not in VALID_STAGES:
            return []
        
        # Convert seconds to minutes, minimum 1 minute
        minutes = max(1, seconds // 60)
        
        # Clamp to max history
        max_minutes = max(1, self._max_history // 60)
        minutes = min(minutes, max_minutes)
        
        records = self._service.get_speed_history(video_id, stage, minutes)
        
        # Filter to exact seconds window
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        filtered = []
        for r in records:
            ts = r.timestamp
            # Ensure timestamp is timezone-aware for comparison
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                filtered.append(r)
        
        return [(r.timestamp.replace(tzinfo=timezone.utc) if r.timestamp.tzinfo is None else r.timestamp, float(r.speed)) for r in filtered]
    
    def get_current_speed(self, video_id: int, stage: str) -> Optional[float]:
        """Get most recent speed for video/stage.
        
        Args:
            video_id: Video ID
            stage: Stage name
            
        Returns:
            Most recent speed in bytes/sec, or None if no data
        """
        history = self.get_speed_history(video_id, stage, seconds=60)
        
        if not history:
            return None
        
        return history[-1][1]
    
    # Aggregate queries
    
    def get_aggregate_speeds(self, seconds: int = 60) -> Dict[str, float]:
        """Get aggregate speeds across all videos.
        
        Args:
            seconds: Time window in seconds
            
        Returns:
            Dictionary with speeds in bytes/sec:
            {
                'download': float,
                'encrypt': float,
                'upload': float,
                'total': float
            }
        """
        # Convert seconds to minutes, minimum 1 minute
        minutes = max(1, seconds // 60)
        
        aggregates = {
            'download': 0.0,
            'encrypt': 0.0,
            'upload': 0.0,
            'total': 0.0
        }
        
        for stage in VALID_STAGES:
            stage_data = self._service.get_aggregate_speeds(stage, minutes)
            
            # Calculate average from bucketed data
            if stage_data:
                avg_speed = sum(d['avg_speed'] for d in stage_data) / len(stage_data)
                aggregates[stage] = avg_speed
                aggregates['total'] += avg_speed
        
        return aggregates
    
    def get_active_stages(self, seconds: int = 60) -> Dict[str, int]:
        """Get count of videos in each active stage.
        
        Args:
            seconds: Time window to consider "active"
            
        Returns:
            Dictionary with counts:
            {
                'download': int,
                'encrypt': int,
                'upload': int,
                'total_active': int
            }
        """
        # Convert seconds to minutes, minimum 1 minute
        minutes = max(1, seconds // 60)
        
        counts = {
            'download': 0,
            'encrypt': 0,
            'upload': 0,
            'total_active': 0
        }
        
        # Track unique video IDs to avoid double-counting
        active_videos = set()
        
        for stage in VALID_STAGES:
            stage_data = self._service.get_aggregate_speeds(stage, minutes)
            
            if stage_data:
                # Count unique videos with activity in this stage
                videos_in_stage = set()
                for bucket in stage_data:
                    # Each bucket may contain multiple video IDs
                    if 'video_ids' in bucket:
                        videos_in_stage.update(bucket['video_ids'])
                    elif 'video_id' in bucket:
                        videos_in_stage.add(bucket['video_id'])
                
                counts[stage] = len(videos_in_stage)
                active_videos.update(videos_in_stage)
        
        counts['total_active'] = len(active_videos)
        
        return counts
    
    # Visualization helpers
    
    def get_speed_data_for_chart(
        self,
        video_id: Optional[int] = None,
        stage: Optional[str] = None,
        seconds: int = 60,
        bucket_size: int = 5  # seconds per bucket
    ) -> Dict[str, Any]:
        """Get formatted data for charting libraries.
        
        Args:
            video_id: Optional video ID to filter by
            stage: Optional stage to filter by
            seconds: Time window in seconds
            bucket_size: Seconds per bucket for aggregation
            
        Returns:
            Dictionary with chart data:
            {
                'timestamps': List[datetime],
                'speeds': List[float],
                'avg_speed': float,
                'peak_speed': float,
                'current_speed': float
            }
        """
        if video_id is not None and stage is not None:
            data = self.get_speed_history(video_id, stage, seconds)
        else:
            # Aggregate data across all videos for the specified stage
            data = self._get_aggregate_history(stage, seconds)
        
        if not data:
            return {
                'timestamps': [],
                'speeds': [],
                'avg_speed': 0.0,
                'peak_speed': 0.0,
                'current_speed': 0.0
            }
        
        # Bucket data if bucket_size is specified
        if bucket_size > 1 and len(data) > 1:
            data = self._bucket_data(data, bucket_size)
        
        timestamps = [d[0] for d in data]
        speeds = [d[1] for d in data]
        
        return {
            'timestamps': timestamps,
            'speeds': speeds,
            'avg_speed': sum(speeds) / len(speeds) if speeds else 0.0,
            'peak_speed': max(speeds) if speeds else 0.0,
            'current_speed': speeds[-1] if speeds else 0.0
        }
    
    def _get_aggregate_history(
        self,
        stage: Optional[str] = None,
        seconds: int = 60
    ) -> List[Tuple[datetime, float]]:
        """Get aggregated speed history across all videos.
        
        Args:
            stage: Optional stage to filter by
            seconds: Time window in seconds
            
        Returns:
            List of (timestamp, total_speed) tuples
        """
        minutes = max(1, seconds // 60)
        
        if stage:
            stages_to_query = [stage] if stage in VALID_STAGES else []
        else:
            stages_to_query = list(VALID_STAGES)
        
        # Collect data from all stages
        all_data = defaultdict(list)
        
        for s in stages_to_query:
            stage_data = self._service.get_aggregate_speeds(s, minutes)
            for bucket in stage_data:
                # Extract timestamp from bucket data
                if 'timestamp' in bucket:
                    ts = bucket['timestamp']
                    if isinstance(ts, str):
                        # Parse ISO format
                        ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    all_data[ts].append(bucket.get('avg_speed', 0))
                elif 'minute' in bucket:
                    # Use minute as timestamp
                    ts = bucket['minute']
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    all_data[ts].append(bucket.get('avg_speed', 0))
        
        # Sum speeds for each timestamp
        result = []
        for ts in sorted(all_data.keys()):
            total_speed = sum(all_data[ts])
            result.append((ts, total_speed))
        
        # Filter to time window
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        result = [(ts, speed) for ts, speed in result if ts >= cutoff]
        
        return result
    
    def _bucket_data(
        self,
        data: List[Tuple[datetime, float]],
        bucket_size: int
    ) -> List[Tuple[datetime, float]]:
        """Bucket data by time intervals.
        
        Args:
            data: List of (timestamp, speed) tuples
            bucket_size: Seconds per bucket
            
        Returns:
            Bucketed data with average speeds per bucket
        """
        if not data or bucket_size <= 1:
            return data
        
        buckets = defaultdict(list)
        
        for ts, speed in data:
            # Create bucket key by rounding timestamp to bucket_size
            bucket_ts = ts.replace(
                second=(ts.second // bucket_size) * bucket_size,
                microsecond=0
            )
            buckets[bucket_ts].append(speed)
        
        # Calculate average for each bucket
        result = []
        for ts in sorted(buckets.keys()):
            avg_speed = sum(buckets[ts]) / len(buckets[ts])
            result.append((ts, avg_speed))
        
        return result
    
    # Maintenance
    
    def cleanup_old_data(self, hours: int = 24) -> int:
        """Clean up old metrics data.
        
        Args:
            hours: Age in hours beyond which to delete data
            
        Returns:
            Number of records deleted
        """
        return self._service._repo.cleanup_old_samples(hours=hours)
