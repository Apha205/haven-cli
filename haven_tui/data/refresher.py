"""Refresh strategy for keeping TUI data synchronized with the database and events.

This module provides the DataRefresher class that manages data synchronization
between the database (PipelineSnapshot table) and the TUI state, supporting
event-driven updates, periodic polling, and hybrid modes.

Example:
    >>> from haven_tui.data.refresher import DataRefresher, RefreshMode
    >>> refresher = DataRefresher(
    ...     snapshot_repo=snapshot_repo,
    ...     state_manager=state_manager,
    ...     event_consumer=event_consumer,
    ...     mode=RefreshMode.HYBRID,
    ...     refresh_rate=5.0,
    ... )
    >>> await refresher.start()
    >>> # ... use TUI ...
    >>> await refresher.stop()
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, List, Optional

from haven_tui.data.repositories import PipelineSnapshotRepository
from haven_tui.data.event_consumer import TUIEventConsumer, TUIStateManager
from haven_tui.models.video_view import VideoView

# Set up logging
logger = logging.getLogger(__name__)


class RefreshMode(Enum):
    """Data synchronization modes.
    
    Attributes:
        EVENT_DRIVEN: Updates only from events (real-time), no polling.
        POLLING: Periodic database polling only, no event subscription.
        HYBRID: Events for real-time updates + occasional polling as fallback.
    """
    EVENT_DRIVEN = "event_driven"
    POLLING = "polling"
    HYBRID = "hybrid"


class DataRefresher:
    """Manages data synchronization between database and TUI.
    
    This class orchestrates the refresh strategy for keeping TUI data in sync
    with the database. It supports three modes:
    - EVENT_DRIVEN: Only listens to events for updates (lowest DB load)
    - POLLING: Only polls the database periodically (most reliable)
    - HYBRID: Listens to events + occasional polling (recommended)
    
    Attributes:
        snapshot_repo: Repository for querying PipelineSnapshot table.
        state: TUIStateManager for managing in-memory state.
        events: TUIEventConsumer for real-time event updates.
        mode: The refresh mode (event_driven, polling, hybrid).
        refresh_rate: Seconds between polling refreshes.
        _refresh_task: Background task for polling loop.
        _running: Whether the refresher is currently running.
        _last_refresh_time: Timestamp of last successful refresh.
        _refresh_callbacks: Callbacks to invoke on refresh completion.
    """
    
    def __init__(
        self,
        snapshot_repo: PipelineSnapshotRepository,
        state_manager: TUIStateManager,
        event_consumer: TUIEventConsumer,
        mode: RefreshMode = RefreshMode.HYBRID,
        refresh_rate: float = 5.0,
    ):
        """Initialize the data refresher.
        
        Args:
            snapshot_repo: Repository for PipelineSnapshot queries.
            state_manager: State manager for video state.
            event_consumer: Event consumer for real-time updates.
            mode: Refresh strategy mode. Defaults to HYBRID.
            refresh_rate: Seconds between polling refreshes. Defaults to 5.0.
        """
        self.snapshot_repo = snapshot_repo
        self.state = state_manager
        self.events = event_consumer
        self.mode = mode
        self.refresh_rate = refresh_rate
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_refresh_time: Optional[datetime] = None
        self._refresh_callbacks: List[Callable[[], None]] = []
    
    def on_refresh(self, callback: Callable[[], None]) -> None:
        """Register callback to be invoked after each refresh.
        
        Args:
            callback: Function to call after refresh completes.
        """
        self._refresh_callbacks.append(callback)
    
    def off_refresh(self, callback: Callable[[], None]) -> bool:
        """Unregister a refresh callback.
        
        Args:
            callback: The callback to remove.
            
        Returns:
            True if callback was found and removed, False otherwise.
        """
        try:
            self._refresh_callbacks.remove(callback)
            return True
        except ValueError:
            return False
    
    def _notify_refresh(self) -> None:
        """Notify all registered callbacks that a refresh completed."""
        for callback in self._refresh_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Refresh callback error: {e}")
    
    async def start(self) -> None:
        """Start the refresh process.
        
        This method:
        1. Starts the event consumer (for event-driven and hybrid modes)
        2. Performs an initial full load from PipelineSnapshot
        3. Starts background polling (for polling and hybrid modes)
        """
        if self._running:
            logger.warning("DataRefresher already started")
            return
        
        self._running = True
        logger.debug(f"Starting DataRefresher in {self.mode.value} mode")
        
        # Start event consumer for real-time updates (if not in polling-only mode)
        if self.mode in (RefreshMode.EVENT_DRIVEN, RefreshMode.HYBRID):
            await self.events.start()
            logger.debug("Event consumer started")
        
        # Do initial load from PipelineSnapshot table
        await self._full_refresh()
        
        # Start background refresh task (if not in event-only mode)
        if self.mode in (RefreshMode.POLLING, RefreshMode.HYBRID):
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            logger.debug(f"Polling loop started (rate: {self.refresh_rate}s)")
        
        logger.debug("DataRefresher started successfully")
    
    async def stop(self) -> None:
        """Stop the refresh process.
        
        This method stops the event consumer, cancels the polling loop,
        and cleans up all resources.
        """
        if not self._running:
            return
        
        logger.debug("Stopping DataRefresher")
        self._running = False
        
        # Cancel polling task
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        self._refresh_task = None
        
        # Stop event consumer
        if self.mode in (RefreshMode.EVENT_DRIVEN, RefreshMode.HYBRID):
            await self.events.stop()
        
        self._refresh_callbacks.clear()
        logger.debug("DataRefresher stopped")
    
    async def _refresh_loop(self) -> None:
        """Background polling loop - queries PipelineSnapshot table.
        
        This loop runs continuously while the refresher is running,
        performing incremental refreshes at the configured rate.
        """
        while self._running:
            try:
                await asyncio.sleep(self.refresh_rate)
                if self._running:  # Check again after sleep
                    await self._snapshot_refresh()
            except asyncio.CancelledError:
                logger.debug("Refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Refresh error: {e}")
    
    async def _full_refresh(self) -> None:
        """Load all active videos from PipelineSnapshot table.
        
        This method performs a complete refresh, loading all active
        and pending videos from the database into the state manager.
        """
        try:
            logger.debug("Performing full refresh from PipelineSnapshot")
            videos = self.snapshot_repo.get_active_videos()
            
            for video in videos:
                self.state.merge_video(video)
            
            self._last_refresh_time = datetime.now(timezone.utc)
            logger.debug(f"Full refresh complete: loaded {len(videos)} videos")
            self._notify_refresh()
            
        except Exception as e:
            logger.error(f"Full refresh error: {e}")
    
    async def _snapshot_refresh(self) -> None:
        """Incremental refresh from PipelineSnapshot table.
        
        This method performs an incremental refresh, querying only
        snapshots that have been updated since the last refresh.
        """
        try:
            # For incremental refresh, get recently updated snapshots
            # Since the repository doesn't have a direct method for this,
            # we'll reload all active videos (this is still efficient as
            # it only queries the snapshot table)
            logger.debug("Performing incremental refresh")
            
            # Get current active videos
            videos = self.snapshot_repo.get_active_videos()
            
            # Track which video IDs we've seen
            current_ids = set()
            
            for video in videos:
                self.state.merge_video(video)
                current_ids.add(video.id)
            
            # Optional: Clean up videos that are no longer active
            # (completed or failed videos that have been removed from active list)
            existing_ids = set(self.state._videos.keys())
            removed_ids = existing_ids - current_ids
            
            # Only remove videos that are completed or failed
            # (don't remove videos that might just be temporarily missing from query)
            for video_id in list(removed_ids):
                video = self.state.get_video(video_id)
                if video and video.overall_status in ("completed", "failed"):
                    self.state.remove_video(video_id)
                    logger.debug(f"Removed completed/failed video {video_id} from state")
            
            self._last_refresh_time = datetime.now(timezone.utc)
            logger.debug(f"Incremental refresh complete: {len(videos)} active videos")
            self._notify_refresh()
            
        except Exception as e:
            logger.error(f"Incremental refresh error: {e}")
    
    async def manual_refresh(self) -> None:
        """Perform a manual full refresh.
        
        This method can be called on user request (e.g., pressing 'r' key)
        to force an immediate refresh of all data.
        """
        logger.debug("Manual refresh triggered")
        await self._full_refresh()
    
    def get_last_refresh_time(self) -> Optional[datetime]:
        """Get the timestamp of the last successful refresh.
        
        Returns:
            datetime of last refresh, or None if no refresh has occurred.
        """
        return self._last_refresh_time
    
    def is_running(self) -> bool:
        """Check if the refresher is currently running.
        
        Returns:
            True if running, False otherwise.
        """
        return self._running
    
    def set_refresh_rate(self, rate: float) -> None:
        """Update the refresh rate.
        
        This change takes effect on the next polling cycle.
        
        Args:
            rate: New refresh rate in seconds.
        """
        self.refresh_rate = max(0.5, rate)  # Minimum 0.5 seconds
        logger.debug(f"Refresh rate updated to {self.refresh_rate}s")
    
    async def change_mode(self, mode: RefreshMode) -> None:
        """Change the refresh mode.
        
        This method allows dynamic mode switching without restarting.
        
        Args:
            mode: The new refresh mode.
        """
        if mode == self.mode:
            return
        
        logger.debug(f"Changing refresh mode from {self.mode.value} to {mode.value}")
        
        old_mode = self.mode
        self.mode = mode
        
        # Handle transitions
        if old_mode == RefreshMode.POLLING and mode in (RefreshMode.EVENT_DRIVEN, RefreshMode.HYBRID):
            # Need to start event consumer
            await self.events.start()
        
        elif old_mode in (RefreshMode.EVENT_DRIVEN, RefreshMode.HYBRID) and mode == RefreshMode.POLLING:
            # Need to stop event consumer
            await self.events.stop()
        
        # Handle polling task
        if mode == RefreshMode.EVENT_DRIVEN:
            # Stop polling task
            if self._refresh_task and not self._refresh_task.done():
                self._refresh_task.cancel()
                try:
                    await self._refresh_task
                except asyncio.CancelledError:
                    pass
                self._refresh_task = None
        elif mode in (RefreshMode.POLLING, RefreshMode.HYBRID) and self._refresh_task is None:
            # Start polling task
            self._refresh_task = asyncio.create_task(self._refresh_loop())
        
        logger.debug(f"Refresh mode changed to {mode.value}")
