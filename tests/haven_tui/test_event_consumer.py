"""Tests for TUI Event Consumer.

This module tests the TUIEventConsumer and TUIStateManager classes:
- Event subscription and unsubscription
- Event handler methods for all event types
- State updates from events
- Speed history tracking
- Thread-safety
- Change notification callbacks
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_cli.pipeline.events import Event, EventType, EventBus
from haven_tui.models.video_view import VideoView, PipelineStage
from haven_tui.data.event_consumer import TUIEventConsumer, TUIStateManager


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
    repo.get_video_summary = MagicMock(return_value=None)
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
def sample_video_view():
    """Create a sample video view."""
    return VideoView(
        id=1,
        title="Test Video",
        source_path="/test/video.mp4",
        current_stage=PipelineStage.DOWNLOAD,
        stage_progress=50.0,
        stage_speed=100000,
        stage_eta=60,
        overall_status="active",
        has_error=False,
        error_message=None,
        file_size=1000000,
        plugin="youtube",
    )


# =============================================================================
# TUIStateManager Tests
# =============================================================================

class TestTUIStateManager:
    """Tests for TUIStateManager."""
    
    def test_initialization(self):
        """Test state manager initialization."""
        manager = TUIStateManager()
        
        assert manager._videos == {}
        assert manager._speed_history == {}
        assert manager._max_history == 1000
    
    def test_initialization_custom_max_history(self):
        """Test state manager with custom max history."""
        manager = TUIStateManager(max_history=500)
        
        assert manager._max_history == 500
    
    def test_merge_video(self):
        """Test merging a video into state."""
        manager = TUIStateManager()
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        manager.merge_video(video)
        
        assert 1 in manager._videos
        assert manager._videos[1].title == "Test"
    
    def test_get_video(self):
        """Test getting a video by ID."""
        manager = TUIStateManager()
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video)
        
        result = manager.get_video(1)
        
        assert result is not None
        assert result.id == 1
        assert result.title == "Test"
    
    def test_get_video_not_found(self):
        """Test getting a non-existent video."""
        manager = TUIStateManager()
        
        result = manager.get_video(999)
        
        assert result is None
    
    def test_get_videos(self):
        """Test getting all videos."""
        manager = TUIStateManager()
        
        for i in range(3):
            video = VideoView(
                id=i,
                title=f"Video {i}",
                source_path=f"/test{i}.mp4",
                current_stage=PipelineStage.DOWNLOAD,
                overall_status="active",
                file_size=1000,
                plugin="youtube",
            )
            manager.merge_video(video)
        
        videos = manager.get_videos()
        
        assert len(videos) == 3
    
    def test_get_videos_with_filter(self):
        """Test getting videos with filter."""
        manager = TUIStateManager()
        
        video1 = VideoView(
            id=1,
            title="Active",
            source_path="/test1.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        video2 = VideoView(
            id=2,
            title="Pending",
            source_path="/test2.mp4",
            current_stage=PipelineStage.PENDING,
            overall_status="pending",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video1)
        manager.merge_video(video2)
        
        active_videos = manager.get_videos(lambda v: v.overall_status == "active")
        
        assert len(active_videos) == 1
        assert active_videos[0].id == 1
    
    def test_update_video_stage(self):
        """Test updating video stage."""
        manager = TUIStateManager()
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.PENDING,
            stage_progress=0.0,
            stage_speed=0,
            overall_status="pending",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video)
        
        manager.update_video_stage(
            video_id=1,
            stage=PipelineStage.DOWNLOAD,
            progress=50.0,
            speed=1024,
            eta=60,
        )
        
        updated = manager.get_video(1)
        assert updated.current_stage == PipelineStage.DOWNLOAD
        assert updated.stage_progress == 50.0
        assert updated.stage_speed == 1024
        assert updated.stage_eta == 60
    
    def test_update_video_stage_not_in_state(self):
        """Test updating stage for video not in state."""
        manager = TUIStateManager()
        
        # Should not raise, just log debug message
        manager.update_video_stage(
            video_id=999,
            stage=PipelineStage.DOWNLOAD,
            progress=50.0,
        )
        
        assert 999 not in manager._videos
    
    def test_speed_history_tracking(self):
        """Test speed history is tracked."""
        manager = TUIStateManager()
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video)
        
        # Add speed samples
        manager.update_video_stage(
            video_id=1,
            stage=PipelineStage.DOWNLOAD,
            progress=25.0,
            speed=1000,
        )
        manager.update_video_stage(
            video_id=1,
            stage=PipelineStage.DOWNLOAD,
            progress=50.0,
            speed=2000,
        )
        
        history = manager.get_speed_history(1, seconds=60)
        
        assert len(history) == 2
        assert history[0][1] == 1000
        assert history[1][1] == 2000
    
    def test_speed_history_maxlen(self):
        """Test speed history respects max length."""
        manager = TUIStateManager(max_history=5)
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video)
        
        # Add more samples than max_history
        for i in range(10):
            manager.update_video_stage(
                video_id=1,
                stage=PipelineStage.DOWNLOAD,
                progress=float(i * 10),
                speed=float(i * 100),
            )
        
        history = manager.get_speed_history(1, seconds=3600)
        
        assert len(history) == 5
    
    def test_remove_video(self):
        """Test removing a video from state."""
        manager = TUIStateManager()
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video)
        
        result = manager.remove_video(1)
        
        assert result is True
        assert 1 not in manager._videos
    
    def test_remove_video_not_found(self):
        """Test removing a non-existent video."""
        manager = TUIStateManager()
        
        result = manager.remove_video(999)
        
        assert result is False
    
    def test_clear(self):
        """Test clearing all state."""
        manager = TUIStateManager()
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        manager.merge_video(video)
        
        manager.clear()
        
        assert manager._videos == {}
        assert manager._speed_history == {}
    
    def test_on_change_callback(self):
        """Test registering change callback."""
        manager = TUIStateManager()
        callback = MagicMock()
        
        manager.on_change(callback)
        
        assert callback in manager._change_callbacks
    
    def test_off_change_callback(self):
        """Test unregistering change callback."""
        manager = TUIStateManager()
        callback = MagicMock()
        manager.on_change(callback)
        
        result = manager.off_change(callback)
        
        assert result is True
        assert callback not in manager._change_callbacks
    
    def test_off_change_not_found(self):
        """Test unregistering callback that doesn't exist."""
        manager = TUIStateManager()
        callback = MagicMock()
        
        result = manager.off_change(callback)
        
        assert result is False
    
    def test_notify_change_calls_callback(self):
        """Test that changes notify callbacks."""
        manager = TUIStateManager()
        callback = MagicMock()
        manager.on_change(callback)
        
        manager._notify_change(1, "test_field", "test_value")
        
        callback.assert_called_once_with(1, "test_field", "test_value")
    
    @pytest.mark.asyncio
    async def test_notify_change_async_callback(self):
        """Test that async callbacks are handled."""
        manager = TUIStateManager()
        async_callback = AsyncMock()
        manager.on_change(async_callback)
        
        manager._notify_change(1, "test_field", "test_value")
        
        # Give async task time to run
        await asyncio.sleep(0.01)
        
        async_callback.assert_called_once_with(1, "test_field", "test_value")


# =============================================================================
# TUIEventConsumer Tests
# =============================================================================

class TestTUIEventConsumerLifecycle:
    """Tests for TUIEventConsumer lifecycle."""
    
    @pytest.mark.asyncio
    async def test_start_subscribes_to_events(self, event_consumer, event_bus):
        """Test that start() subscribes to all relevant events."""
        await event_consumer.start()
        
        # Should be subscribed to multiple event types
        assert len(event_consumer._unsubscribers) >= 10
        assert event_consumer._running is True
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_start_idempotent(self, event_consumer):
        """Test that calling start() twice is safe."""
        await event_consumer.start()
        initial_count = len(event_consumer._unsubscribers)
        
        await event_consumer.start()  # Should not subscribe again
        
        assert len(event_consumer._unsubscribers) == initial_count
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self, event_consumer):
        """Test that stop() unsubscribes from all events."""
        await event_consumer.start()
        assert len(event_consumer._unsubscribers) > 0
        
        await event_consumer.stop()
        
        assert len(event_consumer._unsubscribers) == 0
        assert event_consumer._running is False
    
    @pytest.mark.asyncio
    async def test_stop_idempotent(self, event_consumer):
        """Test that calling stop() twice is safe."""
        await event_consumer.start()
        await event_consumer.stop()
        
        await event_consumer.stop()  # Should not raise
        
        assert event_consumer._running is False


class TestTUIEventConsumerProgressEvents:
    """Tests for progress event handlers.
    
    Note: ANALYSIS_PROGRESS event type does not exist in the event system.
    Analysis progress is tracked through ANALYSIS_REQUESTED and ANALYSIS_COMPLETE.
    """
    
    @pytest.mark.asyncio
    async def test_on_download_progress(self, event_consumer, state_manager, sample_video_view):
        """Test handling download progress events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={
                "video_id": 1,
                "progress_percent": 75.0,
                "download_rate": 2048,
                "eta_seconds": 30,
                "bytes_downloaded": 750000,
                "bytes_total": 1000000,
            },
        )
        
        await event_consumer._on_download_progress(event)
        
        video = state_manager.get_video(1)
        assert video.current_stage == PipelineStage.DOWNLOAD
        assert video.stage_progress == 75.0
        assert video.stage_speed == 2048
        assert video.stage_eta == 30
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_download_progress_missing_video_id(self, event_consumer):
        """Test handling download progress without video_id."""
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={
                "progress_percent": 50.0,
            },
        )
        
        # Should not raise
        await event_consumer._on_download_progress(event)
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_download_progress_video_not_in_state(self, event_consumer, mock_snapshot_repository):
        """Test handling download progress for video not in state."""
        await event_consumer.start()
        
        # Mock repository to return a video
        video = VideoView(
            id=999,
            title="New Video",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        mock_snapshot_repository.get_video_summary.return_value = video
        
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={
                "video_id": 999,
                "progress_percent": 50.0,
            },
        )
        
        await event_consumer._on_download_progress(event)
        
        # Should have loaded video from repository
        assert event_consumer.state.get_video(999) is not None
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_encrypt_progress(self, event_consumer, state_manager, sample_video_view):
        """Test handling encryption progress events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.ENCRYPT_PROGRESS,
            payload={
                "video_id": 1,
                "progress": 80.0,
                "encrypt_speed": 512,
                "job_id": 123,
                "bytes_processed": 800000,
            },
        )
        
        await event_consumer._on_encrypt_progress(event)
        
        video = state_manager.get_video(1)
        assert video.current_stage == PipelineStage.ENCRYPT
        assert video.stage_progress == 80.0
        assert video.stage_speed == 512
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_upload_progress(self, event_consumer, state_manager, sample_video_view):
        """Test handling upload progress events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.UPLOAD_PROGRESS,
            payload={
                "video_id": 1,
                "progress": 60.0,
                "upload_speed": 1024,
                "job_id": 456,
            },
        )
        
        await event_consumer._on_upload_progress(event)
        
        video = state_manager.get_video(1)
        assert video.current_stage == PipelineStage.UPLOAD
        assert video.stage_progress == 60.0
        assert video.stage_speed == 1024
        
        await event_consumer.stop()
    


class TestTUIEventConsumerCompletionEvents:
    """Tests for completion event handlers."""
    
    @pytest.mark.asyncio
    async def test_on_encrypt_complete(self, event_consumer, state_manager, sample_video_view):
        """Test handling encryption complete events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.ENCRYPT_COMPLETE,
            payload={"video_id": 1},
        )
        
        await event_consumer._on_encrypt_complete(event)
        
        video = state_manager.get_video(1)
        assert video.stage_progress == 100.0
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_upload_complete(self, event_consumer, state_manager, sample_video_view):
        """Test handling upload complete events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.UPLOAD_COMPLETE,
            payload={"video_id": 1},
        )
        
        await event_consumer._on_upload_complete(event)
        
        video = state_manager.get_video(1)
        assert video.stage_progress == 100.0
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_sync_complete(self, event_consumer, state_manager, sample_video_view):
        """Test handling sync complete events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.SYNC_COMPLETE,
            payload={"video_id": 1},
        )
        
        await event_consumer._on_sync_complete(event)
        
        video = state_manager.get_video(1)
        assert video.stage_progress == 100.0
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_analysis_complete(self, event_consumer, state_manager, sample_video_view):
        """Test handling analysis complete events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.ANALYSIS_COMPLETE,
            payload={"video_id": 1},
        )
        
        await event_consumer._on_analysis_complete(event)
        
        video = state_manager.get_video(1)
        assert video.stage_progress == 100.0
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_ingest_complete(self, event_consumer, state_manager, mock_snapshot_repository):
        """Test handling video ingested events."""
        await event_consumer.start()
        
        # Mock repository to return a video
        video = VideoView(
            id=2,
            title="New Video",
            source_path="/test.mp4",
            current_stage=PipelineStage.PENDING,
            overall_status="pending",
            file_size=1000,
            plugin="youtube",
        )
        mock_snapshot_repository.get_video_summary.return_value = video
        
        event = Event(
            event_type=EventType.VIDEO_INGESTED,
            payload={"video_id": 2},
        )
        
        await event_consumer._on_ingest_complete(event)
        
        # Should have loaded video from repository
        assert event_consumer.state.get_video(2) is not None
        
        await event_consumer.stop()


class TestTUIEventConsumerFailureEvents:
    """Tests for failure event handlers."""
    
    @pytest.mark.asyncio
    async def test_on_pipeline_failed(self, event_consumer, state_manager, sample_video_view):
        """Test handling pipeline failure events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.PIPELINE_FAILED,
            payload={
                "video_id": 1,
                "stage": "upload",
                "error": "Network timeout",
            },
        )
        
        await event_consumer._on_pipeline_failed(event)
        
        video = state_manager.get_video(1)
        assert video.overall_status == "failed"
        assert video.has_error is True
        assert video.error_message == "Network timeout"
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_upload_failed(self, event_consumer, state_manager, sample_video_view):
        """Test handling upload failure events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.UPLOAD_FAILED,
            payload={
                "video_id": 1,
                "error": "Upload failed",
            },
        )
        
        await event_consumer._on_upload_failed(event)
        
        video = state_manager.get_video(1)
        assert video.overall_status == "failed"
        assert video.has_error is True
        
        await event_consumer.stop()


class TestTUIEventConsumerStepEvents:
    """Tests for step lifecycle event handlers."""
    
    @pytest.mark.asyncio
    async def test_on_step_started(self, event_consumer, state_manager, sample_video_view):
        """Test handling step started events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.STEP_STARTED,
            payload={
                "video_id": 1,
                "stage": "upload",
            },
        )
        
        await event_consumer._on_step_started(event)
        
        video = state_manager.get_video(1)
        assert video.overall_status == "active"
        assert video.current_stage == PipelineStage.UPLOAD
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_step_complete(self, event_consumer, state_manager, sample_video_view):
        """Test handling step complete events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.STEP_COMPLETE,
            payload={
                "video_id": 1,
                "stage": "download",
            },
        )
        
        await event_consumer._on_step_complete(event)
        
        video = state_manager.get_video(1)
        assert video.stage_progress == 100.0
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_step_failed(self, event_consumer, state_manager, sample_video_view):
        """Test handling step failed events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.STEP_FAILED,
            payload={
                "video_id": 1,
                "stage": "encrypt",
                "error": "Encryption failed",
            },
        )
        
        await event_consumer._on_step_failed(event)
        
        video = state_manager.get_video(1)
        assert video.overall_status == "failed"
        assert video.has_error is True
        
        await event_consumer.stop()


class TestTUIEventConsumerPipelineEvents:
    """Tests for pipeline lifecycle event handlers."""
    
    @pytest.mark.asyncio
    async def test_on_pipeline_started(self, event_consumer, state_manager, sample_video_view):
        """Test handling pipeline started events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.PIPELINE_STARTED,
            payload={"video_id": 1},
        )
        
        await event_consumer._on_pipeline_started(event)
        
        video = state_manager.get_video(1)
        assert video.overall_status == "active"
        
        await event_consumer.stop()
    
    @pytest.mark.asyncio
    async def test_on_pipeline_complete(self, event_consumer, state_manager, sample_video_view):
        """Test handling pipeline complete events."""
        state_manager.merge_video(sample_video_view)
        await event_consumer.start()
        
        event = Event(
            event_type=EventType.PIPELINE_COMPLETE,
            payload={"video_id": 1},
        )
        
        await event_consumer._on_pipeline_complete(event)
        
        video = state_manager.get_video(1)
        assert video.overall_status == "completed"
        assert video.current_stage == PipelineStage.COMPLETE
        
        await event_consumer.stop()


class TestTUIEventConsumerIntegration:
    """Integration tests for TUIEventConsumer with EventBus."""
    
    @pytest.mark.asyncio
    async def test_event_published_updates_state(self, event_bus, state_manager, sample_video_view):
        """Test that events published to bus update state."""
        state_manager.merge_video(sample_video_view)
        
        consumer = TUIEventConsumer(event_bus, state_manager)
        await consumer.start()
        
        # Publish event to bus
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={
                "video_id": 1,
                "progress_percent": 90.0,
                "download_rate": 5000,
            },
        )
        await event_bus.publish(event)
        
        # Give event handlers time to process
        await asyncio.sleep(0.01)
        
        video = state_manager.get_video(1)
        assert video.stage_progress == 90.0
        assert video.stage_speed == 5000
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_multiple_events(self, event_bus, state_manager, sample_video_view):
        """Test handling multiple events in sequence."""
        state_manager.merge_video(sample_video_view)
        
        consumer = TUIEventConsumer(event_bus, state_manager)
        await consumer.start()
        
        # Publish download progress
        await event_bus.publish(Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={"video_id": 1, "progress_percent": 50.0},
        ))
        
        # Publish download complete
        await event_bus.publish(Event(
            event_type=EventType.STEP_COMPLETE,
            payload={"video_id": 1, "stage": "download"},
        ))
        
        # Publish encrypt progress
        await event_bus.publish(Event(
            event_type=EventType.ENCRYPT_PROGRESS,
            payload={"video_id": 1, "progress": 30.0},
        ))
        
        # Give handlers time to process
        await asyncio.sleep(0.01)
        
        video = state_manager.get_video(1)
        assert video.current_stage == PipelineStage.ENCRYPT
        assert video.stage_progress == 30.0
        
        await consumer.stop()
