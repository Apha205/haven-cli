# Task 2.4: Event Consumer / Real-time Updates

**Priority:** Critical
**Estimated Effort:** 3 days

**Description:**
Create an event consumer that listens to haven-cli's event bus and updates the TUI state in real-time. Events reflect changes to the job tables.

**Event Consumer Architecture:**
```python
# src/haven_tui/data/event_consumer.py
import asyncio
from haven_cli.pipeline.events import EventBus, EventType, Event
from haven_tui.models.video_view import VideoView, PipelineStage

class TUIEventConsumer:
    """Consumes haven-cli events and updates TUI state."""
    
    def __init__(self, event_bus: EventBus, state_manager: StateManager):
        self.event_bus = event_bus
        self.state = state_manager
        self._unsubscribers: list[callable] = []
        self._running = False
    
    async def start(self):
        """Subscribe to all relevant events."""
        self._running = True
        
        # Subscribe to progress events (from job table updates)
        self._unsubscribers.extend([
            self.event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, self._on_download_progress),
            self.event_bus.subscribe(EventType.ENCRYPT_PROGRESS, self._on_encrypt_progress),
            self.event_bus.subscribe(EventType.UPLOAD_PROGRESS, self._on_upload_progress),
            self.event_bus.subscribe(EventType.ANALYSIS_PROGRESS, self._on_analysis_progress),
            
            # Completion events (job status changes)
            self.event_bus.subscribe(EventType.VIDEO_INGESTED, self._on_ingest_complete),
            self.event_bus.subscribe(EventType.ENCRYPT_COMPLETE, self._on_encrypt_complete),
            self.event_bus.subscribe(EventType.UPLOAD_COMPLETE, self._on_upload_complete),
            
            # Failure events
            self.event_bus.subscribe(EventType.PIPELINE_FAILED, self._on_pipeline_failed),
            
            # Snapshot updates (full state refresh)
            self.event_bus.subscribe(EventType.PIPELINE_SNAPSHOT_UPDATED, self._on_snapshot_update),
        ])
    
    async def _on_download_progress(self, event: Event):
        """Handle download progress event (from Download table)."""
        video_id = event.payload["video_id"]
        progress = event.payload["progress_percent"]
        speed = event.payload.get("download_rate", 0)
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.DOWNLOAD,
            progress=progress,
            speed=speed,
            eta=event.payload.get("eta_seconds"),
            metadata={
                "download_id": event.payload.get("download_id"),
                "bytes_downloaded": event.payload.get("bytes_downloaded"),
                "bytes_total": event.payload.get("bytes_total"),
            }
        )
    
    async def _on_encrypt_progress(self, event: Event):
        """Handle encryption progress event (from EncryptionJob table)."""
        video_id = event.payload["video_id"]
        
        self.state.update_video_stage(
            video_id=video_id,
            stage=PipelineStage.ENCRYPT,
            progress=event.payload.get("progress", 0),
            speed=event.payload.get("encrypt_speed", 0),
            metadata={
                "job_id": event.payload.get("job_id"),
                "bytes_processed": event.payload.get("bytes_processed"),
            }
        )
    
    async def _on_snapshot_update(self, event: Event):
        """Handle full snapshot update (from PipelineSnapshot table)."""
        # Refresh entire video state from snapshot
        snapshot_data = event.payload["snapshot"]
        self.state.merge_video(VideoView(**snapshot_data))
```

**State Manager:**
```python
# src/haven_tui/data/state_manager.py
from collections import deque
from threading import Lock

class StateManager:
    """Thread-safe state management for TUI using table-based data."""
    
    def __init__(self, max_history: int = 1000):
        self._videos: dict[int, VideoView] = {}  # video_id -> VideoView
        self._speed_history: dict[int, deque] = {}  # video_id -> deque of (timestamp, speed)
        self._lock = Lock()
        self._max_history = max_history
    
    def update_video_stage(self, video_id: int, stage: PipelineStage,
                          progress: float, speed: float = 0, 
                          eta: Optional[int] = None, metadata: dict = None):
        """Update stage information for a video."""
        with self._lock:
            if video_id not in self._videos:
                # New video, will be populated on next snapshot refresh
                return
            
            video = self._videos[video_id]
            video.current_stage = stage
            video.stage_progress = progress
            video.stage_speed = int(speed)
            video.stage_eta = eta
            
            # Update speed history for graphs
            if speed > 0:
                self._add_speed_sample(video_id, speed)
    
    def merge_video(self, video: VideoView):
        """Merge video state from database snapshot."""
        with self._lock:
            self._videos[video.id] = video
    
    def get_video(self, video_id: int) -> Optional[VideoView]:
        """Get video by ID."""
        with self._lock:
            return self._videos.get(video_id)
    
    def get_videos(self, filter_fn=None) -> list[VideoView]:
        """Get videos, optionally filtered."""
        with self._lock:
            videos = list(self._videos.values())
            if filter_fn:
                videos = [v for v in videos if filter_fn(v)]
            return videos
    
    def get_speed_history(self, video_id: int, seconds: int = 60) -> list[tuple[float, float]]:
        """Get speed history for graphing."""
        with self._lock:
            history = self._speed_history.get(video_id, deque())
            cutoff = time.time() - seconds
            return [(ts, speed) for ts, speed in history if ts >= cutoff]
```

**Acceptance Criteria:**
- [ ] Event consumer subscribes to all progress events
- [ ] State updates are thread-safe
- [ ] Speed history maintained for graphing
- [ ] Graceful handling of new videos via snapshot refresh
