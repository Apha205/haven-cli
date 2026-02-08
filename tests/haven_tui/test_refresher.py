"""Tests for DataRefresher and RefreshStrategy.

This module tests the DataRefresher class:
- Initialization with different modes
- Start/stop lifecycle
- Full refresh from PipelineSnapshot
- Incremental refresh (snapshot refresh)
- Manual refresh on keypress
- Refresh mode switching
- Callback notifications
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_cli.pipeline.events import EventBus
from haven_tui.models.video_view import VideoView, PipelineStage
from haven_tui.data.event_consumer import TUIEventConsumer, TUIStateManager
from haven_tui.data.refresher import DataRefresher, RefreshMode


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a fresh event bus for testing."""
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def state_manager():
    """Create a fresh state manager for testing."""
    return TUIStateManager()


@pytest.fixture
def mock_snapshot_repository():
    """Create a mock snapshot repository."""
    repo = MagicMock()
    repo.get_active_videos = MagicMock(return_value=[])
    return repo


@pytest.fixture
def event_consumer(event_bus, state_manager, mock_snapshot_repository):
    """Create an event consumer with mocked dependencies."""
    consumer = TUIEventConsumer(
        event_bus=event_bus,
        state_manager=state_manager,
        snapshot_repository=mock_snapshot_repository
    )
    return consumer


@pytest.fixture
def sample_video_views():
    """Create sample video views for testing."""
    return [
        VideoView(
            id=1,
            title="Video 1",
            source_path="/test/video1.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_progress=50.0,
            stage_speed=100000,
            overall_status="active",
            file_size=1000000,
            plugin="youtube",
        ),
        VideoView(
            id=2,
            title="Video 2",
            source_path="/test/video2.mp4",
            current_stage=PipelineStage.ENCRYPT,
            stage_progress=75.0,
            stage_speed=0,
            overall_status="active",
            file_size=2000000,
            plugin="torrent",
        ),
    ]


@pytest.fixture
def refresher(mock_snapshot_repository, state_manager, event_consumer):
    """Create a DataRefresher with mocked dependencies."""
    return DataRefresher(
        snapshot_repo=mock_snapshot_repository,
        state_manager=state_manager,
        event_consumer=event_consumer,
        mode=RefreshMode.HYBRID,
        refresh_rate=0.1,  # Fast refresh for testing
    )


# =============================================================================
# RefreshMode Enum Tests
# =============================================================================

class TestRefreshMode:
    """Tests for RefreshMode enum."""
    
    def test_mode_values(self):
        """Test that modes have correct values."""
        assert RefreshMode.EVENT_DRIVEN.value == "event_driven"
        assert RefreshMode.POLLING.value == "polling"
        assert RefreshMode.HYBRID.value == "hybrid"
    
    def test_mode_from_string(self):
        """Test creating mode from string."""
        assert RefreshMode("event_driven") == RefreshMode.EVENT_DRIVEN
        assert RefreshMode("polling") == RefreshMode.POLLING
        assert RefreshMode("hybrid") == RefreshMode.HYBRID


# =============================================================================
# DataRefresher Initialization Tests
# =============================================================================

class TestDataRefresherInitialization:
    """Tests for DataRefresher initialization."""
    
    def test_initialization_default_mode(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test initialization with default mode."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
        )
        
        assert refresher.mode == RefreshMode.HYBRID
        assert refresher.refresh_rate == 5.0
        assert refresher._running is False
        assert refresher._last_refresh_time is None
    
    def test_initialization_custom_mode(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test initialization with custom mode."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
            mode=RefreshMode.EVENT_DRIVEN,
            refresh_rate=1.0,
        )
        
        assert refresher.mode == RefreshMode.EVENT_DRIVEN
        assert refresher.refresh_rate == 1.0
    
    def test_initialization_polling_mode(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test initialization with polling mode."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
            mode=RefreshMode.POLLING,
        )
        
        assert refresher.mode == RefreshMode.POLLING


# =============================================================================
# DataRefresher Lifecycle Tests
# =============================================================================

class TestDataRefresherLifecycle:
    """Tests for DataRefresher start/stop lifecycle."""
    
    @pytest.mark.asyncio
    async def test_start_hybrid_mode(self, refresher):
        """Test starting in hybrid mode."""
        await refresher.start()
        
        assert refresher._running is True
        assert refresher.events._running is True
        assert refresher._refresh_task is not None
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_start_event_driven_mode(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test starting in event-driven mode."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
            mode=RefreshMode.EVENT_DRIVEN,
        )
        
        await refresher.start()
        
        assert refresher._running is True
        assert refresher.events._running is True
        assert refresher._refresh_task is None  # No polling in event-driven mode
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_start_polling_mode(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test starting in polling mode."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
            mode=RefreshMode.POLLING,
            refresh_rate=0.1,
        )
        
        await refresher.start()
        
        assert refresher._running is True
        assert refresher.events._running is False  # No events in polling mode
        assert refresher._refresh_task is not None
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_start_idempotent(self, refresher):
        """Test that calling start() twice is safe."""
        await refresher.start()
        task = refresher._refresh_task
        
        await refresher.start()  # Should not create new task
        
        assert refresher._refresh_task is task
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_stop_cleans_up_resources(self, refresher):
        """Test that stop() cleans up all resources."""
        await refresher.start()
        assert refresher._running is True
        
        await refresher.stop()
        
        assert refresher._running is False
        assert refresher.events._running is False
        assert refresher._refresh_task is None
    
    @pytest.mark.asyncio
    async def test_stop_idempotent(self, refresher):
        """Test that calling stop() twice is safe."""
        await refresher.start()
        await refresher.stop()
        
        await refresher.stop()  # Should not raise
        
        assert refresher._running is False


# =============================================================================
# DataRefresher Refresh Tests
# =============================================================================

class TestDataRefresherRefresh:
    """Tests for DataRefresher refresh operations."""
    
    @pytest.mark.asyncio
    async def test_full_refresh_loads_videos(self, refresher, sample_video_views):
        """Test that full refresh loads videos from repository."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        await refresher._full_refresh()
        
        assert len(refresher.state.get_videos()) == 2
        assert refresher.state.get_video(1) is not None
        assert refresher.state.get_video(2) is not None
    
    @pytest.mark.asyncio
    async def test_full_refresh_updates_last_refresh_time(self, refresher, sample_video_views):
        """Test that full refresh updates last refresh time."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        assert refresher._last_refresh_time is None
        
        await refresher._full_refresh()
        
        assert refresher._last_refresh_time is not None
        assert isinstance(refresher._last_refresh_time, datetime)
    
    @pytest.mark.asyncio
    async def test_full_refresh_handles_empty_result(self, refresher):
        """Test that full refresh handles empty result gracefully."""
        refresher.snapshot_repo.get_active_videos.return_value = []
        
        await refresher._full_refresh()
        
        assert len(refresher.state.get_videos()) == 0
    
    @pytest.mark.asyncio
    async def test_full_refresh_merges_existing_videos(self, refresher, sample_video_views):
        """Test that full refresh merges videos properly."""
        # First, add a video
        refresher.snapshot_repo.get_active_videos.return_value = [sample_video_views[0]]
        await refresher._full_refresh()
        
        # Now update and refresh again
        updated_video = VideoView(
            id=1,
            title="Updated Video 1",
            source_path="/test/video1.mp4",
            current_stage=PipelineStage.UPLOAD,
            stage_progress=90.0,
            overall_status="active",
            file_size=1000000,
            plugin="youtube",
        )
        refresher.snapshot_repo.get_active_videos.return_value = [updated_video]
        await refresher._full_refresh()
        
        video = refresher.state.get_video(1)
        assert video.title == "Updated Video 1"
        assert video.current_stage == PipelineStage.UPLOAD
        assert video.stage_progress == 90.0
    
    @pytest.mark.asyncio
    async def test_snapshot_refresh_incremental(self, refresher, sample_video_views):
        """Test incremental snapshot refresh."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        await refresher._snapshot_refresh()
        
        assert len(refresher.state.get_videos()) == 2
        assert refresher._last_refresh_time is not None
    
    @pytest.mark.asyncio
    async def test_manual_refresh_triggers_full_refresh(self, refresher, sample_video_views):
        """Test that manual refresh triggers a full refresh."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        await refresher.manual_refresh()
        
        assert len(refresher.state.get_videos()) == 2


# =============================================================================
# DataRefresher Polling Tests
# =============================================================================

class TestDataRefresherPolling:
    """Tests for DataRefresher polling functionality."""
    
    @pytest.mark.asyncio
    async def test_polling_loop_updates_state(self, refresher, sample_video_views):
        """Test that polling loop updates state periodically."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        refresher.refresh_rate = 0.05  # Very fast for testing
        
        await refresher.start()
        
        # Wait for a couple of polling cycles
        await asyncio.sleep(0.15)
        
        # State should have been populated
        assert len(refresher.state.get_videos()) == 2
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_set_refresh_rate(self, refresher):
        """Test updating refresh rate."""
        refresher.set_refresh_rate(10.0)
        
        assert refresher.refresh_rate == 10.0
    
    @pytest.mark.asyncio
    async def test_set_refresh_rate_minimum(self, refresher):
        """Test that refresh rate has a minimum value."""
        refresher.set_refresh_rate(0.1)  # Below minimum
        
        assert refresher.refresh_rate >= 0.5


# =============================================================================
# DataRefresher Mode Switching Tests
# =============================================================================

class TestDataRefresherModeSwitching:
    """Tests for DataRefresher mode switching."""
    
    @pytest.mark.asyncio
    async def test_change_mode_same_mode(self, refresher):
        """Test that changing to same mode does nothing."""
        await refresher.start()
        original_task = refresher._refresh_task
        
        await refresher.change_mode(RefreshMode.HYBRID)
        
        assert refresher._refresh_task is original_task
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_change_mode_to_event_driven(self, refresher):
        """Test changing from hybrid to event-driven."""
        await refresher.start()
        assert refresher._refresh_task is not None
        
        await refresher.change_mode(RefreshMode.EVENT_DRIVEN)
        
        assert refresher.mode == RefreshMode.EVENT_DRIVEN
        assert refresher._refresh_task is None  # Polling stopped
        assert refresher.events._running is True  # Events still running
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_change_mode_to_polling(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test changing from hybrid to polling."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
            mode=RefreshMode.HYBRID,
            refresh_rate=0.1,
        )
        
        await refresher.start()
        assert refresher.events._running is True
        
        await refresher.change_mode(RefreshMode.POLLING)
        
        assert refresher.mode == RefreshMode.POLLING
        assert refresher.events._running is False  # Events stopped
        assert refresher._refresh_task is not None  # Polling still running
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_change_mode_to_hybrid(self, mock_snapshot_repository, state_manager, event_consumer):
        """Test changing from polling to hybrid."""
        refresher = DataRefresher(
            snapshot_repo=mock_snapshot_repository,
            state_manager=state_manager,
            event_consumer=event_consumer,
            mode=RefreshMode.POLLING,
            refresh_rate=0.1,
        )
        
        await refresher.start()
        assert refresher.events._running is False
        
        await refresher.change_mode(RefreshMode.HYBRID)
        
        assert refresher.mode == RefreshMode.HYBRID
        assert refresher.events._running is True  # Events started
        assert refresher._refresh_task is not None  # Polling still running
        
        await refresher.stop()


# =============================================================================
# DataRefresher Callback Tests
# =============================================================================

class TestDataRefresherCallbacks:
    """Tests for DataRefresher callbacks."""
    
    def test_on_refresh_callback(self, refresher):
        """Test registering refresh callback."""
        callback = MagicMock()
        
        refresher.on_refresh(callback)
        
        assert callback in refresher._refresh_callbacks
    
    def test_off_refresh_callback(self, refresher):
        """Test unregistering refresh callback."""
        callback = MagicMock()
        refresher.on_refresh(callback)
        
        result = refresher.off_refresh(callback)
        
        assert result is True
        assert callback not in refresher._refresh_callbacks
    
    def test_off_refresh_not_found(self, refresher):
        """Test unregistering callback that doesn't exist."""
        callback = MagicMock()
        
        result = refresher.off_refresh(callback)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_refresh_notifies_callbacks(self, refresher, sample_video_views):
        """Test that refresh notifies registered callbacks."""
        callback = MagicMock()
        refresher.on_refresh(callback)
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        await refresher._full_refresh()
        
        callback.assert_called_once()


# =============================================================================
# DataRefresher Integration Tests
# =============================================================================

class TestDataRefresherIntegration:
    """Integration tests for DataRefresher."""
    
    @pytest.mark.asyncio
    async def test_full_lifecycle_hybrid_mode(self, refresher, sample_video_views):
        """Test complete lifecycle in hybrid mode."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        # Start
        await refresher.start()
        assert refresher.is_running() is True
        
        # Wait for polling
        await asyncio.sleep(0.15)
        
        # Verify state
        assert len(refresher.state.get_videos()) == 2
        assert refresher.get_last_refresh_time() is not None
        
        # Manual refresh
        await refresher.manual_refresh()
        
        # Stop
        await refresher.stop()
        assert refresher.is_running() is False
    
    @pytest.mark.asyncio
    async def test_initial_full_load_on_start(self, refresher, sample_video_views):
        """Test that initial full load happens on start."""
        refresher.snapshot_repo.get_active_videos.return_value = sample_video_views
        
        await refresher.start()
        
        # Should have loaded videos immediately
        assert len(refresher.state.get_videos()) == 2
        
        await refresher.stop()
    
    @pytest.mark.asyncio
    async def test_completed_videos_removed(self, refresher):
        """Test that completed videos are removed from state."""
        # Add a completed video to state
        completed_video = VideoView(
            id=1,
            title="Completed Video",
            source_path="/test/video.mp4",
            current_stage=PipelineStage.COMPLETE,
            overall_status="completed",
            file_size=1000000,
            plugin="youtube",
        )
        refresher.state.merge_video(completed_video)
        
        # Repository returns no active videos
        refresher.snapshot_repo.get_active_videos.return_value = []
        
        await refresher._snapshot_refresh()
        
        # Completed video should be removed
        assert refresher.state.get_video(1) is None
