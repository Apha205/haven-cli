# Task 2: Pipeline Core Interface Library

## Overview
Implement the `PipelineInterface` class - the primary bridge between the TUI and Haven pipeline core. This class provides controlled access to pipeline operations, database queries, and event subscriptions.

## Requirements

### Core Interface Specification
```python
class PipelineInterface:
    """Primary interface between TUI and Haven pipeline core."""
    
    def __init__(self, database_path: Optional[str] = None, event_bus: Optional[EventBus] = None)
    async def __aenter__(self)  # Context manager entry
    async def __aexit__(self, exc_type, exc_val, exc_tb)  # Context manager exit
    
    # Event subscription
    def on_event(event_type: EventType, handler: Callable) -> None
    def on_any_event(handler: Callable) -> None
    def unsubscribe(event_type: EventType, handler: Callable) -> None
    
    # Database access - Video queries
    def get_video_repository() -> VideoRepository
    def get_active_videos() -> list[Video]
    def get_video_detail(video_id: int) -> Optional[Video]
    def get_pipeline_stats() -> dict
    def search_videos(query: str, limit: int = 50) -> list[Video]
    
    # Plugin access
    def get_plugin_manager() -> PluginManager
    
    # Unified downloads view
    def get_active_downloads() -> list[UnifiedDownload]
    
    # TUI-first operations
    async def retry_video(video_id: int, stage: Optional[str] = None) -> bool
    async def cancel_video(video_id: int) -> bool
    def pause_download(video_id: int) -> bool
```

### Deliverables
- [ ] Implement `PipelineInterface` class
- [ ] Implement context manager support (`__aenter__`, `__aexit__`)
- [ ] Implement event subscription wrappers (`on_event`, `on_any_event`)
- [ ] Implement database query methods
- [ ] Implement unified download view
- [ ] Implement TUI-first operations (`retry_video`, `cancel_video`, `pause_download`)
- [ ] Write unit tests

## Technical Details

### Import Dependencies
```python
from haven_cli.pipeline.events import EventBus, EventType, get_event_bus
from haven_cli.database.connection import get_db_session, AsyncSession
from haven_cli.database.repositories import (
    VideoRepository,
    TorrentDownloadRepository,
    PipelineSnapshotRepository,
)
from haven_cli.plugins.manager import PluginManager, get_plugin_manager
from haven_cli.services.speed_history import SpeedHistoryService
```

### Unified Download Model
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class UnifiedDownload:
    """Combined view of YouTube and BitTorrent downloads."""
    id: int
    video_id: int
    source_type: str  # "youtube" | "torrent"
    title: str
    status: str  # "pending" | "active" | "paused" | "completed" | "failed"
    progress_percent: float
    speed: int  # bytes/sec
    eta: Optional[int]  # seconds
    total_bytes: Optional[int]
    downloaded_bytes: int
    started_at: Optional[datetime]
    
    # Source-specific fields
    youtube_url: Optional[str] = None
    torrent_magnet: Optional[str] = None
    torrent_peers: Optional[int] = None
    torrent_seeds: Optional[int] = None
```

### Event Handler Compatibility
The interface should handle sync/async handler compatibility:
```python
def on_event(self, event_type: EventType, handler: Callable):
    """Subscribe to events with automatic sync/async handling."""
    # Wrap handler to support both sync and async callbacks
    # UI frameworks typically need sync callbacks
```

### Context Manager Behavior
```python
async def __aenter__(self):
    self._db_session = await get_db_session()
    if self._event_bus is None:
        self._event_bus = get_event_bus()
    return self

async def __aexit__(self, exc_type, exc_val, exc_tb):
    if self._db_session:
        await self._db_session.close()
```

## Dependencies
- Task 1: Setup haven_tui Package Structure

## Estimated Effort
2 days

## Acceptance Criteria
- [ ] All interface methods implemented
- [ ] Context manager works correctly with async/await
- [ ] Event subscriptions work with both sync and async handlers
- [ ] Unified download view combines YouTube and torrent downloads
- [ ] `retry_video()` supports per-stage granularity
- [ ] Unit tests cover all public methods
- [ ] Integration test shows interface works with real database

## Related
- Parent: Sprint 01 - Foundation
- Previous: Task 1 (Package Setup)
- Next: Task 3 (State Manager)
- Gap Analysis: Section "Task 11: Pipeline Core Interface Library"
