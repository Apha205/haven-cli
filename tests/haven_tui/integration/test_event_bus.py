"""Integration tests for event bus.

Tests the integration between event bus, event consumer, and state manager.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_cli.pipeline.events import EventBus, EventType, Event
from haven_tui.data.event_consumer import TUIEventConsumer, TUIStateManager
from haven_tui.models.video_view import VideoView, PipelineStage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def event_bus():
    """Create a fresh event bus."""
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def state_manager():
    """Create a fresh state manager."""
    return TUIStateManager()


@pytest.fixture
def snapshot_repository():
    """Create a mock snapshot repository."""
    repo = MagicMock()
    repo.get_video_summary = MagicMock(return_value=None)
    return repo


@pytest.fixture
async def event_consumer(event_bus, state_manager, snapshot_repository):
    """Create an event consumer."""
    consumer = TUIEventConsumer(
        event_bus=event_bus,
        state_manager=state_manager,
        snapshot_repository=snapshot_repository
    )
    yield consumer
    if consumer._running:
        await consumer.stop()


# =============================================================================
# Event Subscription Tests
# =============================================================================

class TestEventSubscription:
    """Tests for event subscription and unsubscription."""
    
    @pytest.mark.asyncio
    async def test_subscribe_to_all_events(self, event_bus, state_manager, snapshot_repository):
        """Test that consumer subscribes to all relevant events."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        await consumer.start()
        
        # Should have multiple subscriptions
        assert len(consumer._unsubscribers) > 10
        assert consumer._running is True
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_unsubscribe_on_stop(self, event_bus, state_manager, snapshot_repository):
        """Test that consumer unsubscribes on stop."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        await consumer.start()
        initial_count = len(consumer._unsubscribers)
        assert initial_count > 0
        
        await consumer.stop()
        
        assert len(consumer._unsubscribers) == 0
        assert consumer._running is False
    
    @pytest.mark.asyncio
    async def test_event_handler_called(self, event_bus, state_manager, snapshot_repository):
        """Test that event handler is called when event is published."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        # Add a video to state
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        state_manager.merge_video(video)
        
        await consumer.start()
        
        # Publish event
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={
                "video_id": 1,
                "progress_percent": 75.0,
                "download_rate": 1000000,
            },
        )
        await event_bus.publish(event)
        
        # Give handler time to process
        await asyncio.sleep(0.01)
        
        # Verify state was updated
        updated = state_manager.get_video(1)
        assert updated.stage_progress == 75.0
        assert updated.stage_speed == 1000000
        
        await consumer.stop()


# =============================================================================
# Event Flow Tests
# =============================================================================

class TestEventFlow:
    """Tests for event flow through the system."""
    
    @pytest.mark.asyncio
    async def test_download_progress_flow(self, event_bus, state_manager, snapshot_repository):
        """Test download progress event flow."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        state_manager.merge_video(video)
        
        await consumer.start()
        
        # Simulate download progress events
        for i in range(1, 6):
            event = Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={
                    "video_id": 1,
                    "progress_percent": i * 20.0,
                    "download_rate": 1000000 + i * 100000,
                    "eta_seconds": 100 - i * 10,
                },
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.005)
        
        # Verify final state
        final = state_manager.get_video(1)
        assert final.stage_progress == 100.0
        assert final.stage_speed == 1500000
        assert final.stage_eta == 50
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_stage_transition_flow(self, event_bus, state_manager, snapshot_repository):
        """Test stage transition event flow."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.PENDING,
            overall_status="pending",
            file_size=1000,
            plugin="youtube",
        )
        state_manager.merge_video(video)
        
        await consumer.start()
        
        # Pipeline started
        await event_bus.publish(Event(
            event_type=EventType.PIPELINE_STARTED,
            payload={"video_id": 1},
        ))
        await asyncio.sleep(0.005)
        
        assert state_manager.get_video(1).overall_status == "active"
        
        # Download started
        await event_bus.publish(Event(
            event_type=EventType.STEP_STARTED,
            payload={"video_id": 1, "stage": "download"},
        ))
        await asyncio.sleep(0.005)
        
        assert state_manager.get_video(1).current_stage == PipelineStage.DOWNLOAD
        
        # Download progress
        await event_bus.publish(Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={"video_id": 1, "progress_percent": 50.0},
        ))
        await asyncio.sleep(0.005)
        
        assert state_manager.get_video(1).stage_progress == 50.0
        
        # Download complete
        await event_bus.publish(Event(
            event_type=EventType.STEP_COMPLETE,
            payload={"video_id": 1, "stage": "download"},
        ))
        await asyncio.sleep(0.005)
        
        assert state_manager.get_video(1).stage_progress == 100.0
        
        # Encrypt started
        await event_bus.publish(Event(
            event_type=EventType.STEP_STARTED,
            payload={"video_id": 1, "stage": "encrypt"},
        ))
        await asyncio.sleep(0.005)
        
        assert state_manager.get_video(1).current_stage == PipelineStage.ENCRYPT
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_failure_flow(self, event_bus, state_manager, snapshot_repository):
        """Test failure event flow."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        state_manager.merge_video(video)
        
        await consumer.start()
        
        # Some progress
        await event_bus.publish(Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={"video_id": 1, "progress_percent": 50.0},
        ))
        await asyncio.sleep(0.005)
        
        # Failure
        await event_bus.publish(Event(
            event_type=EventType.PIPELINE_FAILED,
            payload={
                "video_id": 1,
                "stage": "download",
                "error": "Network timeout",
            },
        ))
        await asyncio.sleep(0.005)
        
        final = state_manager.get_video(1)
        assert final.overall_status == "failed"
        assert final.has_error is True
        assert final.error_message == "Network timeout"
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_pipeline_completion_flow(self, event_bus, state_manager, snapshot_repository):
        """Test complete pipeline flow from start to finish."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.PENDING,
            overall_status="pending",
            file_size=1000,
            plugin="youtube",
        )
        state_manager.merge_video(video)
        
        await consumer.start()
        
        # Full pipeline flow
        events = [
            (EventType.PIPELINE_STARTED, {"video_id": 1}),
            (EventType.STEP_STARTED, {"video_id": 1, "stage": "download"}),
            (EventType.DOWNLOAD_PROGRESS, {"video_id": 1, "progress_percent": 50.0}),
            (EventType.STEP_COMPLETE, {"video_id": 1, "stage": "download"}),
            (EventType.STEP_STARTED, {"video_id": 1, "stage": "encrypt"}),
            (EventType.ENCRYPT_PROGRESS, {"video_id": 1, "progress": 50.0}),
            (EventType.ENCRYPT_COMPLETE, {"video_id": 1}),
            (EventType.STEP_STARTED, {"video_id": 1, "stage": "upload"}),
            (EventType.UPLOAD_PROGRESS, {"video_id": 1, "progress": 50.0}),
            (EventType.UPLOAD_COMPLETE, {"video_id": 1}),
            (EventType.SYNC_COMPLETE, {"video_id": 1}),
            (EventType.ANALYSIS_COMPLETE, {"video_id": 1}),
            (EventType.PIPELINE_COMPLETE, {"video_id": 1}),
        ]
        
        for event_type, payload in events:
            await event_bus.publish(Event(event_type=event_type, payload=payload))
            await asyncio.sleep(0.002)
        
        final = state_manager.get_video(1)
        assert final.overall_status == "completed"
        assert final.current_stage == PipelineStage.COMPLETE
        
        await consumer.stop()


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety."""
    
    @pytest.mark.asyncio
    async def test_concurrent_event_handling(self, event_bus, state_manager, snapshot_repository):
        """Test handling multiple events concurrently."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        # Add multiple videos
        for i in range(5):
            video = VideoView(
                id=i + 1,
                title=f"Video {i + 1}",
                source_path=f"/test{i}.mp4",
                current_stage=PipelineStage.DOWNLOAD,
                overall_status="active",
                file_size=1000,
                plugin="youtube",
            )
            state_manager.merge_video(video)
        
        await consumer.start()
        
        # Publish events for all videos concurrently
        tasks = []
        for i in range(5):
            event = Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={
                    "video_id": i + 1,
                    "progress_percent": (i + 1) * 20.0,
                },
            )
            tasks.append(event_bus.publish(event))
        
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.05)
        
        # Verify all videos were updated
        for i in range(5):
            video = state_manager.get_video(i + 1)
            assert video.stage_progress == (i + 1) * 20.0
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_callback_thread_safety(self, state_manager):
        """Test callback system thread safety."""
        callback_count = 0
        callback_lock = asyncio.Lock()
        
        async def async_callback(video_id, field, value):
            nonlocal callback_count
            async with callback_lock:
                callback_count += 1
        
        state_manager.on_change(async_callback)
        
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        state_manager.merge_video(video)
        
        # Trigger multiple changes (update_video_stage is not async, so call sequentially)
        for i in range(10):
            state_manager.update_video_stage(
                video_id=1,
                stage=PipelineStage.DOWNLOAD,
                progress=float(i * 10),
                speed=float(i * 1000),
            )
        
        await asyncio.sleep(0.05)
        
        # All callbacks should have been called
        assert callback_count >= 10


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in event processing."""
    
    @pytest.mark.asyncio
    async def test_missing_video_id(self, event_bus, state_manager, snapshot_repository):
        """Test handling event with missing video_id."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        await consumer.start()
        
        # Event without video_id
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={"progress_percent": 50.0},
        )
        
        # Should not raise
        await consumer._on_download_progress(event)
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_video_not_in_state(self, event_bus, state_manager, snapshot_repository):
        """Test handling event for video not in state."""
        consumer = TUIEventConsumer(event_bus, state_manager, snapshot_repository)
        
        # Mock repository to return None (video not found)
        snapshot_repository.get_video_summary.return_value = None
        
        await consumer.start()
        
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={"video_id": 999, "progress_percent": 50.0},
        )
        
        # Should not raise
        await consumer._on_download_progress(event)
        
        await consumer.stop()
    
    @pytest.mark.asyncio
    async def test_callback_error_handling(self, state_manager):
        """Test that callback errors don't break the system."""
        def failing_callback(video_id, field, value):
            raise ValueError("Test error")
        
        state_manager.on_change(failing_callback)
        
        video = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        # Should not raise even though callback fails
        state_manager.merge_video(video)
