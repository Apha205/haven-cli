"""Event consumer for real-time TUI state updates.

This module provides the TUIEventConsumer class that listens to haven-cli's
event bus and updates the TUI state in real-time. Events reflect changes to
the job tables (Download, EncryptionJob, UploadJob, etc.).
"""

import asyncio
import inspect
import logging
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from haven_cli.pipeline.events import EventBus, EventType, Event
from haven_tui.models.video_view import VideoView, PipelineStage
from haven_tui.data.repositories import PipelineSnapshotRepository

# Set up logging
logger = logging.getLogger(__name__)


class TUIStateManager:
    """Thread-safe state management for TUI using table-based data.
    
    This class maintains in-memory state for video pipeline progress
    with thread-safe access and speed history tracking for graphing.
    
    Attributes:
        _videos: Dictionary mapping video_id to VideoView
        _speed_history: Dictionary mapping video_id to deque of speed samples
        _lock: asyncio.Lock for thread-safe access
        _max_history: Maximum number of speed samples to keep per video
    """
    
    def __init__(self, max_history: int = 1000):
        """Initialize the state manager.
        
        Args:
            max_history: Maximum number of speed samples to keep per video
        """
        self._videos: Dict[int, VideoView] = {}
        self._speed_history: Dict[int, deque] = {}
        self._lock = asyncio.Lock()
        self._max_history = max_history
        self._change_callbacks: List[Callable[[int, str, Any], None]] = []
    
    def on_change(self, callback: Callable[[int, str, Any], None]) -> None:
        """Register callback for state changes.
        
        The callback receives: (video_id, field_name, new_value)
        
        Args:
            callback: Function to call when state changes
        """
        self._change_callbacks.append(callback)
    
    def off_change(self, callback: Callable[[int, str, Any], None]) -> bool:
        """Unregister a state change callback.
        
        Args:
            callback: The callback to remove
            
        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._change_callbacks.remove(callback)
            return True
        except ValueError:
            return False
    
    def _notify_change(self, video_id: int, field: str, value: Any) -> None:
        """Notify all registered callbacks of a state change.
        
        Args:
            video_id: The video that changed
            field: The name of the field that changed
            value: The new value
        """
        for callback in self._change_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    asyncio.create_task(callback(video_id, field, value))
                else:
                    callback(video_id, field, value)
            except Exception as e:
                logger.error(f"Change callback error: {e}")
    
    def update_video_stage(
        self,
        video_id: int,
        stage: PipelineStage,
        progress: float,
        speed: float = 0,
        eta: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update stage information for a video.
        
        Args:
            video_id: The video ID to update
            stage: The current pipeline stage
            progress: Progress percentage (0-100)
            speed: Current speed in bytes/sec
            eta: Estimated time remaining in seconds
            metadata: Additional metadata to store
        """
        # Note: This method assumes the video already exists in state.
        # New videos should be added via merge_video() from snapshot data.
        if video_id not in self._videos:
            logger.debug(f"Video {video_id} not in state, skipping stage update")
            return
        
        video = self._videos[video_id]
        video.current_stage = stage
        video.stage_progress = progress
        video.stage_speed = int(speed)
        video.stage_eta = eta
        
        # Update speed history for graphs
        if speed > 0:
            self._add_speed_sample(video_id, speed)
        
        # Notify callbacks
        self._notify_change(video_id, 'current_stage', stage)
        self._notify_change(video_id, 'stage_progress', progress)
        self._notify_change(video_id, 'stage_speed', speed)
    
    def _add_speed_sample(self, video_id: int, speed: float) -> None:
        """Add a speed sample to the history.
        
        Args:
            video_id: The video ID
            speed: Speed in bytes/sec
        """
        if video_id not in self._speed_history:
            self._speed_history[video_id] = deque(maxlen=self._max_history)
        
        self._speed_history[video_id].append((time.time(), speed))
    
    def merge_video(self, video: VideoView) -> None:
        """Merge video state from database snapshot.
        
        Args:
            video: VideoView to merge into state
        """
        self._videos[video.id] = video
        self._notify_change(video.id, 'video_added', video)
    
    def get_video(self, video_id: int) -> Optional[VideoView]:
        """Get video by ID.
        
        Args:
            video_id: The video ID to look up
            
        Returns:
            VideoView if found, None otherwise
        """
        return self._videos.get(video_id)
    
    def get_videos(self, filter_fn: Optional[Callable[[VideoView], bool]] = None) -> List[VideoView]:
        """Get videos, optionally filtered.
        
        Args:
            filter_fn: Optional filter function that takes a VideoView and returns bool
            
        Returns:
            List of VideoView objects
        """
        videos = list(self._videos.values())
        if filter_fn:
            videos = [v for v in videos if filter_fn(v)]
        return videos
    
    def get_speed_history(
        self,
        video_id: int,
        seconds: int = 60
    ) -> List[tuple[float, float]]:
        """Get speed history for graphing.
        
        Args:
            video_id: The video ID
            seconds: Time window in seconds
            
        Returns:
            List of (timestamp, speed) tuples
        """
        history = self._speed_history.get(video_id, deque())
        cutoff = time.time() - seconds
        return [(ts, speed) for ts, speed in history if ts >= cutoff]
    
    def remove_video(self, video_id: int) -> bool:
        """Remove a video from state.
        
        Args:
            video_id: The video ID to remove
            
        Returns:
            True if video was found and removed, False otherwise
        """
        if video_id in self._videos:
            del self._videos[video_id]
            if video_id in self._speed_history:
                del self._speed_history[video_id]
            self._notify_change(video_id, 'video_removed', None)
            return True
        return False
    
    def clear(self) -> None:
        """Clear all state."""
        self._videos.clear()
        self._speed_history.clear()


class TUIEventConsumer:
    """Consumes haven-cli events and updates TUI state.
    
    This class subscribes to the haven-cli event bus and updates the TUI
    state manager in real-time based on pipeline events. It handles:
    
    - Progress events (download, encrypt, upload, analysis)
    - Completion events (video ingested, encrypt complete, upload complete)
    - Failure events (pipeline failed)
    - Snapshot updates (full state refresh)
    
    Example:
        event_bus = get_event_bus()
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager)
        await consumer.start()
        
        # Later...
        await consumer.stop()
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        state_manager: TUIStateManager,
        snapshot_repository: Optional[PipelineSnapshotRepository] = None
    ):
        """Initialize the event consumer.
        
        Args:
            event_bus: The event bus to subscribe to
            state_manager: The state manager to update
            snapshot_repository: Optional repository for loading video snapshots
        """
        self.event_bus = event_bus
        self.state = state_manager
        self.snapshot_repository = snapshot_repository
        self._unsubscribers: List[Callable[[], None]] = []
        self._running = False
    
    async def start(self) -> None:
        """Subscribe to all relevant events.
        
        This method subscribes to progress events, completion events,
        failure events, and snapshot updates from the event bus.
        """
        if self._running:
            logger.warning("TUIEventConsumer already started")
            return
        
        self._running = True
        logger.debug("Starting TUIEventConsumer")
        
        # Subscribe to progress events (from job table updates)
        self._unsubscribers.extend([
            self.event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, self._on_download_progress),
            self.event_bus.subscribe(EventType.ENCRYPT_PROGRESS, self._on_encrypt_progress),
            self.event_bus.subscribe(EventType.UPLOAD_PROGRESS, self._on_upload_progress),
            
            # Completion events (job status changes)
            self.event_bus.subscribe(EventType.VIDEO_INGESTED, self._on_ingest_complete),
            self.event_bus.subscribe(EventType.ENCRYPT_COMPLETE, self._on_encrypt_complete),
            self.event_bus.subscribe(EventType.UPLOAD_COMPLETE, self._on_upload_complete),
            self.event_bus.subscribe(EventType.SYNC_COMPLETE, self._on_sync_complete),
            self.event_bus.subscribe(EventType.ANALYSIS_COMPLETE, self._on_analysis_complete),
            
            # Failure events
            self.event_bus.subscribe(EventType.PIPELINE_FAILED, self._on_pipeline_failed),
            self.event_bus.subscribe(EventType.UPLOAD_FAILED, self._on_upload_failed),
            self.event_bus.subscribe(EventType.ANALYSIS_FAILED, self._on_analysis_failed),
            
            # Step lifecycle events
            self.event_bus.subscribe(EventType.STEP_STARTED, self._on_step_started),
            self.event_bus.subscribe(EventType.STEP_COMPLETE, self._on_step_complete),
            self.event_bus.subscribe(EventType.STEP_FAILED, self._on_step_failed),
            
            # Pipeline lifecycle events
            self.event_bus.subscribe(EventType.PIPELINE_STARTED, self._on_pipeline_started),
            self.event_bus.subscribe(EventType.PIPELINE_COMPLETE, self._on_pipeline_complete),
        ])
        
        logger.debug(f"TUIEventConsumer subscribed to {len(self._unsubscribers)} event types")
    
    async def stop(self) -> None:
        """Unsubscribe from all events and stop the consumer."""
        if not self._running:
            return
        
        logger.debug("Stopping TUIEventConsumer")
        
        # Unsubscribe from all events
        for unsubscriber in self._unsubscribers:
            try:
                unsubscriber()
            except Exception as e:
                logger.error(f"Error unsubscribing from event: {e}")
        
        self._unsubscribers.clear()
        self._running = False
        logger.debug("TUIEventConsumer stopped")
    
    async def _ensure_video_in_state(self, video_id: int) -> bool:
        """Ensure a video exists in the state manager.
        
        If the video is not in state and a snapshot repository is available,
        attempts to load it from the database.
        
        Args:
            video_id: The video ID to ensure
            
        Returns:
            True if video is now in state, False otherwise
        """
        if video_id in self.state._videos:
            return True
        
        if self.snapshot_repository is None:
            logger.debug(f"Video {video_id} not in state and no repository available")
            return False
        
        try:
            video_view = self.snapshot_repository.get_video_summary(video_id)
            if video_view:
                self.state.merge_video(video_view)
                logger.debug(f"Loaded video {video_id} from snapshot repository")
                return True
            else:
                logger.warning(f"Video {video_id} not found in snapshot repository")
                return False
        except Exception as e:
            logger.error(f"Error loading video {video_id} from repository: {e}")
            return False
    
    async def _on_download_progress(self, event: Event) -> None:
        """Handle download progress event (from Download table).
        
        Args:
            event: The download progress event with payload containing:
                - video_id: The video ID
                - progress_percent: Download progress (0-100)
                - download_rate: Current download speed in bytes/sec
                - eta_seconds: Estimated time remaining
                - bytes_downloaded: Bytes downloaded so far
                - bytes_total: Total bytes to download
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            logger.warning("Download progress event missing video_id")
            return
        
        # Ensure video is in state
        if not await self._ensure_video_in_state(video_id):
            return
        
        # Update state
        progress = payload.get("progress_percent", 0)
        speed = payload.get("download_rate", 0)
        eta = payload.get("eta_seconds")
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.DOWNLOAD,
            progress=progress,
            speed=speed,
            eta=eta,
            metadata={
                "download_id": payload.get("download_id"),
                "bytes_downloaded": payload.get("bytes_downloaded"),
                "bytes_total": payload.get("bytes_total"),
            }
        )
        
        logger.debug(f"Updated download progress for video {video_id}: {progress:.1f}%")
    
    async def _on_encrypt_progress(self, event: Event) -> None:
        """Handle encryption progress event (from EncryptionJob table).
        
        Args:
            event: The encryption progress event with payload containing:
                - video_id: The video ID
                - progress: Encryption progress (0-100)
                - encrypt_speed: Encryption speed in bytes/sec (optional)
                - job_id: The encryption job ID
                - bytes_processed: Bytes processed so far
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            logger.warning("Encrypt progress event missing video_id")
            return
        
        # Ensure video is in state
        if not await self._ensure_video_in_state(video_id):
            return
        
        # Update state
        progress = payload.get("progress", 0)
        speed = payload.get("encrypt_speed", 0)
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.ENCRYPT,
            progress=progress,
            speed=speed,
            metadata={
                "job_id": payload.get("job_id"),
                "bytes_processed": payload.get("bytes_processed"),
            }
        )
        
        logger.debug(f"Updated encrypt progress for video {video_id}: {progress:.1f}%")
    
    async def _on_upload_progress(self, event: Event) -> None:
        """Handle upload progress event (from UploadJob table).
        
        Args:
            event: The upload progress event with payload containing:
                - video_id: The video ID
                - progress: Upload progress (0-100)
                - upload_speed: Upload speed in bytes/sec
                - job_id: The upload job ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            logger.warning("Upload progress event missing video_id")
            return
        
        # Ensure video is in state
        if not await self._ensure_video_in_state(video_id):
            return
        
        # Update state
        progress = payload.get("progress", 0)
        speed = payload.get("upload_speed", 0)
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.UPLOAD,
            progress=progress,
            speed=speed,
            metadata={
                "job_id": payload.get("job_id"),
            }
        )
        
        logger.debug(f"Updated upload progress for video {video_id}: {progress:.1f}%")
    
    async def _on_ingest_complete(self, event: Event) -> None:
        """Handle video ingested event.
        
        Args:
            event: The video ingested event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            logger.warning("Video ingested event missing video_id")
            return
        
        # Load the newly ingested video into state
        await self._ensure_video_in_state(video_id)
        
        logger.debug(f"Video {video_id} ingested and added to state")
    
    async def _on_encrypt_complete(self, event: Event) -> None:
        """Handle encryption complete event.
        
        Args:
            event: The encryption complete event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.ENCRYPT,
            progress=100.0,
            metadata={"status": "completed"}
        )
        
        logger.debug(f"Video {video_id} encryption completed")
    
    async def _on_upload_complete(self, event: Event) -> None:
        """Handle upload complete event.
        
        Args:
            event: The upload complete event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.UPLOAD,
            progress=100.0,
            metadata={"status": "completed"}
        )
        
        logger.debug(f"Video {video_id} upload completed")
    
    async def _on_sync_complete(self, event: Event) -> None:
        """Handle sync complete event.
        
        Args:
            event: The sync complete event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.SYNC,
            progress=100.0,
            metadata={"status": "completed"}
        )
        
        logger.debug(f"Video {video_id} sync completed")
    
    async def _on_analysis_complete(self, event: Event) -> None:
        """Handle analysis complete event.
        
        Args:
            event: The analysis complete event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.ANALYSIS,
            progress=100.0,
            metadata={"status": "completed"}
        )
        
        logger.debug(f"Video {video_id} analysis completed")
    
    async def _on_pipeline_failed(self, event: Event) -> None:
        """Handle pipeline failure event.
        
        Args:
            event: The pipeline failed event with payload containing:
                - video_id: The video ID
                - stage: The stage that failed
                - error: Error message
        """
        payload = event.payload
        video_id = payload.get("video_id")
        failed_stage = payload.get("stage", "unknown")
        error_message = payload.get("error", "Unknown error")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        video = self.state.get_video(video_id)
        if video:
            video.overall_status = "failed"
            video.has_error = True
            video.error_message = error_message
            self.state._notify_change(video_id, 'overall_status', 'failed')
            self.state._notify_change(video_id, 'has_error', True)
        
        logger.debug(f"Video {video_id} pipeline failed at stage {failed_stage}: {error_message}")
    
    async def _on_upload_failed(self, event: Event) -> None:
        """Handle upload failure event.
        
        Args:
            event: The upload failed event with payload containing:
                - video_id: The video ID
                - error: Error message
        """
        await self._on_pipeline_failed(event)
    
    async def _on_analysis_failed(self, event: Event) -> None:
        """Handle analysis failure event.
        
        Args:
            event: The analysis failed event with payload containing:
                - video_id: The video ID
                - error: Error message
        """
        await self._on_pipeline_failed(event)
    
    async def _on_step_started(self, event: Event) -> None:
        """Handle step started event.
        
        Args:
            event: The step started event with payload containing:
                - video_id: The video ID
                - stage: The stage that started
        """
        payload = event.payload
        video_id = payload.get("video_id")
        stage = payload.get("stage")
        
        if not video_id or not stage:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        # Map stage string to PipelineStage enum
        stage_map = {
            "download": PipelineStage.DOWNLOAD,
            "encrypt": PipelineStage.ENCRYPT,
            "upload": PipelineStage.UPLOAD,
            "sync": PipelineStage.SYNC,
            "analysis": PipelineStage.ANALYSIS,
        }
        
        pipeline_stage = stage_map.get(stage, PipelineStage.PENDING)
        
        video = self.state.get_video(video_id)
        if video:
            video.overall_status = "active"
            video.current_stage = pipeline_stage
            self.state._notify_change(video_id, 'overall_status', 'active')
        
        logger.debug(f"Video {video_id} step started: {stage}")
    
    async def _on_step_complete(self, event: Event) -> None:
        """Handle step complete event.
        
        Args:
            event: The step complete event with payload containing:
                - video_id: The video ID
                - stage: The stage that completed
        """
        payload = event.payload
        video_id = payload.get("video_id")
        stage = payload.get("stage")
        
        if not video_id or not stage:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        # Map stage string to PipelineStage enum
        stage_map = {
            "download": PipelineStage.DOWNLOAD,
            "encrypt": PipelineStage.ENCRYPT,
            "upload": PipelineStage.UPLOAD,
            "sync": PipelineStage.SYNC,
            "analysis": PipelineStage.ANALYSIS,
        }
        
        pipeline_stage = stage_map.get(stage, PipelineStage.PENDING)
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=pipeline_stage,
            progress=100.0,
            metadata={"status": "completed"}
        )
        
        logger.debug(f"Video {video_id} step completed: {stage}")
    
    async def _on_step_failed(self, event: Event) -> None:
        """Handle step failure event.
        
        Args:
            event: The step failed event with payload containing:
                - video_id: The video ID
                - stage: The stage that failed
                - error: Error message
        """
        await self._on_pipeline_failed(event)
    
    async def _on_pipeline_started(self, event: Event) -> None:
        """Handle pipeline started event.
        
        Args:
            event: The pipeline started event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        video = self.state.get_video(video_id)
        if video:
            video.overall_status = "active"
            self.state._notify_change(video_id, 'overall_status', 'active')
        
        logger.debug(f"Video {video_id} pipeline started")
    
    async def _on_pipeline_complete(self, event: Event) -> None:
        """Handle pipeline complete event.
        
        Args:
            event: The pipeline complete event with payload containing:
                - video_id: The video ID
        """
        payload = event.payload
        video_id = payload.get("video_id")
        
        if not video_id:
            return
        
        if not await self._ensure_video_in_state(video_id):
            return
        
        video = self.state.get_video(video_id)
        if video:
            video.overall_status = "completed"
            video.current_stage = PipelineStage.COMPLETE
            self.state._notify_change(video_id, 'overall_status', 'completed')
        
        logger.debug(f"Video {video_id} pipeline completed")
