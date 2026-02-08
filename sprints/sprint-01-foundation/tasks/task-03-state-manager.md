# Task 3: Real-Time State Manager

## Overview
Implement the `StateManager` and `VideoState` classes for thread-safe, real-time state management in the TUI. This provides an in-memory cache of pipeline state with change notifications.

## Requirements

### VideoState Dataclass
```python
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from typing import Optional

@dataclass
class VideoState:
    """Complete state for a single video in the TUI."""
    
    # Identity
    id: int
    title: str
    
    # Download state
    download_status: str  # "pending" | "active" | "paused" | "completed" | "failed"
    download_progress: float  # 0.0 - 100.0
    download_speed: float  # bytes/sec
    download_eta: Optional[int]  # seconds
    
    # Pipeline stages
    encrypt_status: str
    encrypt_progress: float
    
    upload_status: str
    upload_progress: float
    upload_speed: float
    
    sync_status: str
    sync_progress: float
    
    analysis_status: str
    analysis_progress: float
    
    # Computed overall state
    overall_status: str  # "pending" | "active" | "completed" | "failed"
    current_stage: str
    
    # Speed history for graphing (circular buffer)
    speed_history: deque = field(default_factory=lambda: deque(maxlen=300))
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    @property
    def current_progress(self) -> float:
        """Get progress for the current active stage."""
        # Return progress of current_stage
        
    @property
    def current_speed(self) -> float:
        """Get speed for the current active stage."""
        # Return speed of current_stage
        
    @property
    def is_active(self) -> bool:
        """Check if video has any active operations."""
        
    @property
    def has_failed(self) -> bool:
        """Check if video has any failed stages."""
```

### StateManager Class
```python
from typing import Callable, Dict, List, Optional
import asyncio
from threading import Lock

class StateManager:
    """Thread-safe state manager for TUI."""
    
    def __init__(self, pipeline: PipelineInterface)
    
    # Lifecycle
    async def initialize()  # Load initial state from database
    async def shutdown()  # Cleanup and unsubscribe
    
    # State access
    def get_video(video_id: int) -> Optional[VideoState]
    def get_all_videos() -> List[VideoState]
    def get_active() -> List[VideoState]
    def get_by_status(status: str) -> List[VideoState]
    
    # Change notifications
    def on_change(callback: Callable[[int, str, any], None]) -> None
    """Register callback for state changes. 
    Callback receives: (video_id, field_name, new_value)
    """
    def off_change(callback: Callable) -> None
    
    # Internal event handlers
    def _setup_event_handlers()
    def _on_download_progress(event: Event)
    def _on_upload_progress(event: Event)
    def _on_encrypt_progress(event: Event)
    def _on_analysis_progress(event: Event)
    def _on_stage_complete(event: Event)
    def _on_pipeline_failed(event: Event)
```

### Deliverables
- [ ] Implement `VideoState` dataclass with all properties
- [ ] Implement `StateManager` class with in-memory cache
- [ ] Implement thread-safe state access (use `asyncio.Lock`)
- [ ] Implement event handlers for all progress event types
- [ ] Implement change notification system
- [ ] Write unit tests
- [ ] Write integration tests with mock events

## Technical Details

### In-Memory Cache Strategy
```python
class StateManager:
    def __init__(self, pipeline: PipelineInterface):
        self._pipeline = pipeline
        self._state: Dict[int, VideoState] = {}
        self._lock = asyncio.Lock()
        self._change_callbacks: List[Callable] = []
        self._event_handlers: List[tuple] = []  # Track for cleanup
```

### Thread-Safe Updates
```python
async def _on_download_progress(self, event):
    async with self._lock:
        video_id = event.video_id
        if video_id not in self._state:
            await self._load_video(video_id)
        
        state = self._state[video_id]
        old_speed = state.download_speed
        state.download_speed = event.speed
        state.download_progress = event.progress
        
        # Update speed history
        state.speed_history.append({
            'timestamp': datetime.now(),
            'speed': event.speed,
            'progress': event.progress
        })
    
    # Notify outside lock to prevent deadlocks
    self._notify_change(video_id, 'download_speed', event.speed)
```

### Change Notification
```python
def _notify_change(self, video_id: int, field: str, value: any):
    """Notify all registered callbacks of state change."""
    for callback in self._change_callbacks:
        try:
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback(video_id, field, value))
            else:
                callback(video_id, field, value)
        except Exception as e:
            logger.error(f"Change callback error: {e}")
```

### Event Subscription Management
```python
async def initialize(self):
    """Load initial state and setup event handlers."""
    # Load all active videos
    active_videos = await self._pipeline.get_active_videos()
    for video in active_videos:
        await self._load_video(video.id)
    
    # Subscribe to events
    self._setup_event_handlers()

async def shutdown(self):
    """Unsubscribe from events and cleanup."""
    for event_type, handler in self._event_handlers:
        self._pipeline.unsubscribe(event_type, handler)
    self._state.clear()
```

## Dependencies
- Task 1: Setup haven_tui Package Structure
- Task 2: Pipeline Core Interface Library

## Estimated Effort
2 days

## Acceptance Criteria
- [ ] VideoState dataclass implemented with all properties
- [ ] StateManager maintains in-memory cache
- [ ] Thread-safe access with proper locking
- [ ] All progress events update state correctly
- [ ] Change callbacks fire on all relevant updates
- [ ] State initializes from database on startup
- [ ] Cleanup properly unsubscribes from events
- [ ] Unit tests cover state transitions
- [ ] Performance test with 100+ videos

## Related
- Parent: Sprint 01 - Foundation
- Previous: Task 2 (Pipeline Interface)
- Next: Task 4 (Metrics Collector)
- Gap Analysis: Section "Task 12: Real-Time State Manager"
