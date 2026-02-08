# Task 2.5: Refresh Strategy / Data Sync

**Priority:** High
**Estimated Effort:** 2 days

**Description:**
Implement the refresh strategy for keeping TUI data synchronized with the database and events.

**Refresh Architecture:**
```python
# src/haven_tui/data/refresher.py
import asyncio
from enum import Enum

class RefreshMode(Enum):
    """Data synchronization modes."""
    EVENT_DRIVEN = "event_driven"    # Updates only from events (real-time)
    POLLING = "polling"              # Periodic database polling
    HYBRID = "hybrid"                # Events + occasional polling

class DataRefresher:
    """Manages data synchronization between database and TUI."""
    
    def __init__(self, 
                 snapshot_repo: PipelineSnapshotRepository,
                 state_manager: StateManager,
                 event_consumer: TUIEventConsumer,
                 mode: RefreshMode = RefreshMode.HYBRID):
        self.snapshot_repo = snapshot_repo
        self.state = state_manager
        self.events = event_consumer
        self.mode = mode
        self._refresh_task: asyncio.Task | None = None
        self._running = False
    
    async def start(self):
        """Start the refresh process."""
        self._running = True
        
        # Start event consumer for real-time updates
        await self.events.start()
        
        # Do initial load from PipelineSnapshot table
        await self._full_refresh()
        
        # Start background refresh task
        if self.mode in (RefreshMode.POLLING, RefreshMode.HYBRID):
            self._refresh_task = asyncio.create_task(self._refresh_loop())
    
    async def _refresh_loop(self):
        """Background polling loop - queries PipelineSnapshot table."""
        while self._running:
            try:
                await asyncio.sleep(self.config.refresh_rate)
                await self._snapshot_refresh()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    async def _full_refresh(self):
        """Load all active videos from PipelineSnapshot table."""
        videos = self.snapshot_repo.get_active_videos()
        for video in videos:
            self.state.merge_video(video)
    
    async def _snapshot_refresh(self):
        """Incremental refresh from PipelineSnapshot table."""
        # Get recently updated snapshots
        since = self.state.last_refresh_time
        recent = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.updated_at >= since
        ).all()
        
        for snapshot in recent:
            view = self.snapshot_repo._snapshot_to_view(snapshot)
            self.state.merge_video(view)
```

**Acceptance Criteria:**
- [ ] Initial full load from PipelineSnapshot on TUI start
- [ ] Real-time updates from events
- [ ] Periodic polling of PipelineSnapshot as fallback
- [ ] Configurable refresh rate
- [ ] Manual refresh on keypress (like aria2tui's 'r')
