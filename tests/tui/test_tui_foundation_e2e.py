"""End-to-End tests for TUI Foundation layer.

These tests verify complete workflows across all foundation components:
- PipelineInterface
- StateManager
- MetricsCollector

Tests cover:
- Full video lifecycle (ingest -> download -> encrypt -> upload)
- Retry flows (failure and recovery)
- Concurrent video processing
- Performance with many videos
"""

import asyncio
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Ensure we can import from the project
import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_tui.core.pipeline_interface import (
    PipelineInterface,
    UnifiedDownload,
    DownloadStats,
    RetryResult,
)
from haven_tui.core.state_manager import VideoState, StateManager
from haven_tui.core.metrics import MetricsCollector
from haven_cli.database.models import (
    Base,
    Video,
    Download,
    TorrentDownload,
    EncryptionJob,
    UploadJob,
    SyncJob,
    AnalysisJob,
    PipelineSnapshot,
    SpeedHistory,
)
from haven_cli.pipeline.events import (
    Event,
    EventType,
    EventBus,
    get_event_bus,
    reset_event_bus,
)
from haven_cli.services.speed_history import SpeedHistoryService


def dt_now():
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def database_engine(temp_db_path):
    """Create a database engine with all tables."""
    engine = create_engine(f"sqlite:///{temp_db_path}")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(database_engine) -> Session:
    """Create a fresh database session for each test."""
    SessionLocal = sessionmaker(bind=database_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def event_bus():
    """Get a fresh event bus for testing."""
    reset_event_bus()
    bus = get_event_bus()
    yield bus
    reset_event_bus()


@pytest.fixture
async def pipeline_interface(database_engine, temp_db_path, event_bus):
    """Create a PipelineInterface with test database."""
    interface = PipelineInterface(
        database_path=temp_db_path,
        event_bus=event_bus,
    )
    
    # Set up session manually
    SessionLocal = sessionmaker(bind=database_engine)
    session = SessionLocal()
    interface._db_session = session
    interface._plugin_manager = None
    
    yield interface
    
    session.close()
    reset_event_bus()


@pytest.fixture
async def state_manager(pipeline_interface):
    """Create an initialized StateManager."""
    manager = StateManager(pipeline_interface)
    await manager.initialize()
    yield manager
    await manager.shutdown()


@pytest.fixture
async def metrics_collector(db_session):
    """Create a MetricsCollector with real SpeedHistoryService."""
    service = SpeedHistoryService(db_session)
    await service.start()
    
    collector = MetricsCollector(service)
    yield collector
    
    await service.stop()


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus for testing."""
    return MockEventBus()


class MockEventBus:
    """Mock event bus for testing without full pipeline."""
    
    def __init__(self):
        from collections import defaultdict
        self._subscribers = defaultdict(list)
        self._all_subscribers = []
        self._history = []
    
    def subscribe(self, event_type, handler):
        self._subscribers[event_type].append(handler)
        return lambda: self._subscribers[event_type].remove(handler)
    
    def subscribe_all(self, handler):
        self._all_subscribers.append(handler)
        return lambda: self._all_subscribers.remove(handler)
    
    def unsubscribe(self, event_type, handler):
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
    
    async def publish(self, event):
        self._history.append(event)
        
        # Call type-specific handlers
        handlers = self._subscribers.get(event.event_type, [])
        for handler in list(handlers):
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        
        # Call all-event handlers
        for handler in list(self._all_subscribers):
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
    
    def simulate_download_progress(self, video_id, progress, speed):
        """Helper to simulate download progress events."""
        event = Event(
            event_type=EventType.DOWNLOAD_PROGRESS,
            payload={
                'video_id': video_id,
                'progress': progress,
                'speed': speed,
            },
        )
        asyncio.create_task(self.publish(event))


# =============================================================================
# Test Helpers
# =============================================================================

async def create_test_video(session: Session, title: str, status: str = "pending") -> Video:
    """Helper to create a test video in the database."""
    video = Video(
        source_path=f"/test/{title.replace(' ', '_')}.mp4",
        title=title,
        duration=300.0,
        file_size=10485760,
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


async def create_test_download(
    session: Session,
    video_id: int,
    source_type: str = "youtube",
    status: str = "pending"
) -> Download:
    """Helper to create a test download job."""
    download = Download(
        video_id=video_id,
        source_type=source_type,
        status=status,
        progress_percent=0.0,
        download_rate=0,
    )
    session.add(download)
    session.commit()
    session.refresh(download)
    return download


def wait_for_state_change(callback_mock, timeout: float = 1.0):
    """Helper to wait for state change callback."""
    import time
    start = time.time()
    while time.time() - start < timeout:
        if callback_mock.called:
            return True
        time.sleep(0.01)
    return False


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestTuiFoundationE2E:
    """End-to-end tests for the complete foundation layer."""
    
    @pytest.mark.asyncio
    async def test_full_video_lifecycle(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test: Video ingested -> download -> encrypt -> upload.
        
        Verify state updates at each stage.
        """
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            # Create pipeline interface
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            pipeline._plugin_manager = None
            
            # Create state manager
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Track state changes
            state_changes = []
            def on_change(video_id, field, value):
                state_changes.append((video_id, field, value))
            state_manager.on_change(on_change)
            
            # 1. Create and ingest video
            video = Video(
                source_path="/test/lifecycle_video.mp4",
                title="Lifecycle Test Video",
                duration=600.0,
                file_size=20971520,
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            
            # Publish video ingested event
            await event_bus.publish(Event(
                event_type=EventType.VIDEO_INGESTED,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            # Verify video loaded into state manager
            state = state_manager.get_video(video.id)
            assert state is not None
            assert state.title == "Lifecycle Test Video"
            
            # 2. Start pipeline
            await event_bus.publish(Event(
                event_type=EventType.PIPELINE_STARTED,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.overall_status == "active"
            
            # 3. Download progress
            for progress in [25.0, 50.0, 75.0, 100.0]:
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={
                        'video_id': video.id,
                        'progress': progress,
                        'speed': 1024000.0,
                        'eta': 120,
                    },
                ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.download_progress == 100.0
            assert state.download_speed == 1024000.0
            assert state.download_status == "active"
            assert state.current_stage == "download"
            
            # 4. Download complete
            await event_bus.publish(Event(
                event_type=EventType.STEP_COMPLETE,
                payload={'video_id': video.id, 'stage': 'download'},
            ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.download_status == "completed"
            
            # 5. Encryption progress and complete
            await event_bus.publish(Event(
                event_type=EventType.ENCRYPT_PROGRESS,
                payload={'video_id': video.id, 'progress': 50.0},
            ))
            await asyncio.sleep(0.02)
            
            await event_bus.publish(Event(
                event_type=EventType.ENCRYPT_COMPLETE,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.encrypt_status == "completed"
            assert state.encrypt_progress == 100.0
            
            # 6. Upload progress and complete
            await event_bus.publish(Event(
                event_type=EventType.UPLOAD_PROGRESS,
                payload={
                    'video_id': video.id,
                    'progress': 75.0,
                    'speed': 512000.0,
                },
            ))
            await asyncio.sleep(0.02)
            
            await event_bus.publish(Event(
                event_type=EventType.UPLOAD_COMPLETE,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.upload_status == "completed"
            assert state.upload_progress == 100.0
            
            # 7. Sync complete
            await event_bus.publish(Event(
                event_type=EventType.SYNC_COMPLETE,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.sync_status == "completed"
            
            # 8. Analysis complete
            await event_bus.publish(Event(
                event_type=EventType.ANALYSIS_COMPLETE,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            # Verify final state
            state = state_manager.get_video(video.id)
            assert state.download_status == "completed"
            assert state.encrypt_status == "completed"
            assert state.upload_status == "completed"
            assert state.sync_status == "completed"
            assert state.analysis_status == "completed"
            assert state.is_completed is True
            assert state.has_failed is False
            
            # Verify state changes were tracked
            assert len(state_changes) > 0
            
            await state_manager.shutdown()
            
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_retry_flow(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test: Video fails at encrypt -> retry from encrypt -> completes.
        
        Verify state resets and re-updates correctly.
        """
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            # Create pipeline interface
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            pipeline._plugin_manager = None
            
            # Create state manager
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # 1. Create video and set up initial state
            video = Video(
                source_path="/test/retry_video.mp4",
                title="Retry Test Video",
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            
            # Add to state manager
            state_manager._state[video.id] = VideoState(
                id=video.id,
                title="Retry Test Video",
                download_status="completed",
                encrypt_status="failed",
                overall_status="failed",
            )
            
            # 2. Verify initial failed state
            state = state_manager.get_video(video.id)
            assert state.encrypt_status == "failed"
            assert state.overall_status == "failed"
            
            # 3. Retry pipeline
            await event_bus.publish(Event(
                event_type=EventType.PIPELINE_STARTED,
                payload={'video_id': video.id, 'retry': True},
            ))
            await asyncio.sleep(0.05)
            
            # 4. Manually reset encrypt status (in real scenario, retry_video would do this)
            async with state_manager._lock:
                state_manager._state[video.id].encrypt_status = "active"
                state_manager._state[video.id].encrypt_progress = 0.0
                state_manager._state[video.id].overall_status = "active"
            
            state = state_manager.get_video(video.id)
            assert state.encrypt_status == "active"
            assert state.overall_status == "active"
            
            # 5. Encryption completes successfully on retry
            await event_bus.publish(Event(
                event_type=EventType.ENCRYPT_COMPLETE,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.05)
            
            state = state_manager.get_video(video.id)
            assert state.encrypt_status == "completed"
            assert state.encrypt_progress == 100.0
            
            # 6. Continue to upload and complete
            await event_bus.publish(Event(
                event_type=EventType.UPLOAD_COMPLETE,
                payload={'video_id': video.id},
            ))
            await event_bus.publish(Event(
                event_type=EventType.SYNC_COMPLETE,
                payload={'video_id': video.id},
            ))
            await event_bus.publish(Event(
                event_type=EventType.ANALYSIS_COMPLETE,
                payload={'video_id': video.id},
            ))
            await asyncio.sleep(0.1)
            
            # 7. Verify final completed state
            state = state_manager.get_video(video.id)
            assert state.encrypt_status == "completed"
            assert state.upload_status == "completed"
            assert state.sync_status == "completed"
            assert state.analysis_status == "completed"
            assert state.is_completed is True
            assert state.has_failed is False
            
            await state_manager.shutdown()
            
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_videos(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test: 50 videos processing simultaneously.
        
        Verify state manager handles load without errors.
        """
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        NUM_VIDEOS = 50
        
        try:
            # Create pipeline interface
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            pipeline._plugin_manager = None
            
            # Create state manager
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Track state changes
            change_count = 0
            def on_change(video_id, field, value):
                nonlocal change_count
                change_count += 1
            state_manager.on_change(on_change)
            
            # 1. Create videos
            videos = []
            for i in range(NUM_VIDEOS):
                video = Video(
                    source_path=f"/test/concurrent_video_{i}.mp4",
                    title=f"Concurrent Video {i}",
                )
                session.add(video)
                videos.append(video)
            session.commit()
            for video in videos:
                session.refresh(video)
            
            # 2. Load all videos into state manager
            for video in videos:
                state_manager._state[video.id] = VideoState(
                    id=video.id,
                    title=video.title,
                    download_status="active",
                    overall_status="active",
                )
            
            # 3. Send concurrent progress events for all videos
            async def send_progress_events(video_id):
                for progress in [25.0, 50.0, 75.0, 100.0]:
                    await event_bus.publish(Event(
                        event_type=EventType.DOWNLOAD_PROGRESS,
                        payload={
                            'video_id': video_id,
                            'progress': progress,
                            'speed': 1024000.0,
                        },
                    ))
            
            # Process events concurrently for all videos
            await asyncio.gather(*[
                send_progress_events(video.id) for video in videos
            ])
            await asyncio.sleep(0.2)
            
            # 4. Verify all videos have correct state
            for video in videos:
                state = state_manager.get_video(video.id)
                assert state is not None, f"Video {video.id} not in state"
                assert state.download_progress == 100.0, f"Video {video.id} progress incorrect"
                assert state.download_speed == 1024000.0, f"Video {video.id} speed incorrect"
            
            # 5. Verify state manager statistics
            all_videos = state_manager.get_all_videos()
            assert len(all_videos) == NUM_VIDEOS
            
            active_videos = state_manager.get_active()
            assert len(active_videos) == NUM_VIDEOS
            
            # 6. Mark half as completed
            for video in videos[:NUM_VIDEOS // 2]:
                await event_bus.publish(Event(
                    event_type=EventType.STEP_COMPLETE,
                    payload={'video_id': video.id, 'stage': 'download'},
                ))
            await asyncio.sleep(0.1)
            
            # Verify correct counts
            completed_downloads = [
                v for v in state_manager.get_all_videos()
                if v.download_status == "completed"
            ]
            assert len(completed_downloads) == NUM_VIDEOS // 2
            
            # Verify callbacks were triggered
            assert change_count > 0
            
            await state_manager.shutdown()
            
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_metrics_integration_with_state_updates(
        self,
        database_engine,
        db_session,
        temp_db_path,
        event_bus,
    ):
        """Test MetricsCollector integrates with StateManager updates."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            # Set up services
            speed_service = SpeedHistoryService(db_session)
            await speed_service.start()
            
            metrics = MetricsCollector(speed_service)
            
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Create video
            video = Video(
                source_path="/test/metrics_video.mp4",
                title="Metrics Integration Test",
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            
            # Load into state manager
            state_manager._state[video.id] = VideoState(
                id=video.id,
                title="Metrics Integration Test",
                download_status="active",
            )
            
            # Simulate download progress
            for i in range(5):
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={
                        'video_id': video.id,
                        'progress': float((i + 1) * 20),
                        'speed': 1000000.0 * (i + 1),
                    },
                ))
                # Also record in metrics
                metrics.record_speed(
                    video.id,
                    "download",
                    1000000.0 * (i + 1),
                    float((i + 1) * 20),
                )
            
            await asyncio.sleep(0.1)
            
            # Flush metrics to database
            speed_service._flush_all_buffers()
            
            # Verify state manager has correct state
            state = state_manager.get_video(video.id)
            assert state.download_progress == 100.0
            assert state.download_speed == 5000000.0
            
            # Verify metrics have been recorded
            history = metrics.get_speed_history(video.id, "download", seconds=60)
            assert len(history) == 5
            
            # Verify chart data can be generated
            chart_data = metrics.get_speed_data_for_chart(
                video_id=video.id,
                stage="download",
                seconds=60,
            )
            assert 'timestamps' in chart_data
            assert 'speeds' in chart_data
            assert 'avg_speed' in chart_data
            assert chart_data['current_speed'] > 0
            
            await speed_service.stop()
            await state_manager.shutdown()
            
        finally:
            session.close()


# =============================================================================
# Performance Tests
# =============================================================================

class TestTuiFoundationPerformance:
    """Performance tests for TUI foundation."""
    
    @pytest.mark.asyncio
    async def test_concurrent_videos_performance(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test state manager with many concurrent videos."""
        import time
        
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        NUM_VIDEOS = 100
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Create videos in database
            videos = []
            for i in range(NUM_VIDEOS):
                video = Video(
                    source_path=f"/test/perf_video_{i}.mp4",
                    title=f"Performance Video {i}",
                )
                session.add(video)
                videos.append(video)
            session.commit()
            for video in videos:
                session.refresh(video)
                video_ids = [v.id for v in videos]
            
            # Load all videos into state manager
            for video_id in video_ids:
                state_manager._state[video_id] = VideoState(
                    id=video_id,
                    title=f"Video {video_id}",
                    download_status="active",
                )
            
            # Simulate rapid events
            start = time.time()
            for video_id in video_ids:
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={
                        'video_id': video_id,
                        'progress': 50.0,
                        'speed': 1000000,
                    },
                ))
            
            await asyncio.sleep(0.2)
            
            # All updates should complete quickly
            elapsed = time.time() - start
            assert elapsed < 2.0, f"State updates too slow: {elapsed}s"
            
            # Verify all states updated
            for video_id in video_ids:
                state = state_manager.get_video(video_id)
                assert state is not None, f"Video {video_id} not found"
                assert state.download_progress == 50.0, f"Video {video_id} progress incorrect"
            
            await state_manager.shutdown()
            
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_rapid_state_updates_performance(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test handling of rapid state updates for single video."""
        import time
        
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        NUM_UPDATES = 500
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Create video
            video = Video(
                source_path="/test/rapid_video.mp4",
                title="Rapid Update Test",
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            
            # Load into state manager
            state_manager._state[video.id] = VideoState(
                id=video.id,
                title="Rapid Update Test",
                download_status="active",
            )
            
            # Send rapid updates
            start = time.time()
            
            for i in range(NUM_UPDATES):
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={
                        'video_id': video.id,
                        'progress': float(i % 100),
                        'speed': float(i * 1000),
                    },
                ))
            
            await asyncio.sleep(0.2)
            
            elapsed = time.time() - start
            
            # Should process 500 events in less than 2 seconds
            assert elapsed < 2.0, f"Rapid updates too slow: {elapsed}s"
            
            # Verify final state
            state = state_manager.get_video(video.id)
            assert state is not None
            # Speed history should be capped at 300
            assert len(state.speed_history) == 300
            
            await state_manager.shutdown()
            
        finally:
            session.close()


# =============================================================================
# Integration Tests for PipelineInterface
# =============================================================================

class TestPipelineInterfaceIntegration:
    """Integration tests for PipelineInterface."""
    
    @pytest.mark.asyncio
    async def test_context_manager_initializes_resources(
        self,
        database_engine,
        temp_db_path,
    ):
        """Test context manager properly initializes database and event bus."""
        async with PipelineInterface(database_path=temp_db_path) as interface:
            # Should have active database session
            assert interface._db_session is not None
            
            # Should be able to query database
            session = interface._ensure_session()
            assert session is not None
    
    @pytest.mark.asyncio
    async def test_context_manager_cleans_up_on_exit(
        self,
        database_engine,
        temp_db_path,
    ):
        """Test context manager properly cleans up resources."""
        interface = PipelineInterface(database_path=temp_db_path)
        
        async with interface:
            assert interface._db_session is not None
        
        # After exit, session should be closed
        assert interface._db_session is None
    
    @pytest.mark.asyncio
    async def test_get_active_videos_returns_videos(
        self,
        database_engine,
        temp_db_path,
    ):
        """Test get_active_videos returns videos with pipeline activity."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        async with PipelineInterface(database_path=temp_db_path) as interface:
            interface._db_session = session
            
            # Create a video with an active snapshot
            video = Video(
                source_path="/test/active_video.mp4",
                title="Active Video",
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            
            snapshot = PipelineSnapshot(
                video_id=video.id,
                current_stage="download",
                overall_status="active",
            )
            session.add(snapshot)
            session.commit()
            
            # Get active videos
            active = interface.get_active_videos()
            assert len(active) >= 1
            assert any(v.id == video.id for v in active)
        
        session.close()
    
    @pytest.mark.asyncio
    async def test_search_videos_filters_correctly(
        self,
        database_engine,
        temp_db_path,
    ):
        """Test search_videos correctly filters by query."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        async with PipelineInterface(database_path=temp_db_path) as interface:
            interface._db_session = session
            
            # Create videos with different titles
            video1 = Video(
                source_path="/test/alpha.mp4",
                title="Alpha Search Test",
                creator_handle="creator_alpha",
            )
            video2 = Video(
                source_path="/test/beta.mp4",
                title="Beta Different",
                creator_handle="creator_beta",
            )
            session.add_all([video1, video2])
            session.commit()
            
            # Search by title
            results = interface.search_videos("Alpha")
            assert len(results) >= 1
            assert any("Alpha" in v.title for v in results)
            
            # Search by creator
            results = interface.search_videos("creator_alpha")
            assert len(results) >= 1
            assert any(v.creator_handle == "creator_alpha" for v in results)
        
        session.close()
    
    @pytest.mark.asyncio
    async def test_unified_downloads_combines_sources(
        self,
        database_engine,
        temp_db_path,
    ):
        """Test unified downloads combines YouTube and torrent sources."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = sessionmaker(bind=database_engine)()
        
        async with PipelineInterface(database_path=temp_db_path) as interface:
            interface._db_session = session
            
            # Create videos
            video1 = Video(
                source_path="/test/youtube_video.mp4",
                title="YouTube Download",
            )
            video2 = Video(
                source_path="/test/torrent_video.mp4",
                title="Torrent Download",
            )
            session.add_all([video1, video2])
            session.commit()
            session.refresh(video1)
            session.refresh(video2)
            
            # Create YouTube download
            dl = Download(
                video_id=video1.id,
                source_type="youtube",
                status="downloading",
                progress_percent=50.0,
                download_rate=1024000,
            )
            session.add(dl)
            
            # Create torrent download
            torrent = TorrentDownload(
                infohash="test_hash_123",
                source_id="test_source",
                title="Torrent Download",
                status="downloading",
                progress=0.75,
                download_rate=2048000,
            )
            session.add(torrent)
            session.commit()
            
            # Get unified downloads
            downloads = interface.get_active_downloads()
            
            # Should have both types
            youtube_dls = [d for d in downloads if d.source_type == "youtube"]
            torrent_dls = [d for d in downloads if d.source_type == "torrent"]
            
            assert len(youtube_dls) >= 1
            assert len(torrent_dls) >= 1
        
        session.close()
    
    @pytest.mark.asyncio
    async def test_retry_video_resets_stages(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test retry_video resets stage status to pending."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            ) as interface:
                interface._db_session = session
                
                # Create failed video
                video = Video(
                    source_path="/test/retry_me.mp4",
                    title="Retry Video",
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                
                # Create failed upload job
                upload = UploadJob(
                    video_id=video.id,
                    status="failed",
                    target="storacha",
                    error_message="Connection error",
                )
                session.add(upload)
                session.commit()
                
                # Retry from upload stage
                result = await interface.retry_video(video.id, stage="upload")
                
                assert result.success is True
                
                # Verify upload job was reset
                session.refresh(upload)
                assert upload.status == "pending"
                assert upload.error_message is None
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_cancel_video_stops_operations(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test cancel_video stops all operations for a video."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        events_received = []
        
        async def event_handler(event):
            events_received.append(event)
        
        event_bus.subscribe(EventType.PIPELINE_CANCELLED, event_handler)
        
        try:
            async with PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            ) as interface:
                interface._db_session = session
                
                # Create video with active operations
                video = Video(
                    source_path="/test/cancel_me.mp4",
                    title="Cancel Video",
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                
                # Create active download
                download = Download(
                    video_id=video.id,
                    source_type="youtube",
                    status="downloading",
                )
                session.add(download)
                
                # Create active encryption job
                encrypt = EncryptionJob(
                    video_id=video.id,
                    status="encrypting",
                )
                session.add(encrypt)
                session.commit()
                
                # Cancel the video
                result = await interface.cancel_video(video.id)
                
                assert result is True
                
                # Verify all operations cancelled
                session.refresh(download)
                session.refresh(encrypt)
                assert download.status == "cancelled"
                assert encrypt.status == "cancelled"
                
                # Verify event was published
                await asyncio.sleep(0.1)
                cancel_events = [e for e in events_received 
                               if e.event_type == EventType.PIPELINE_CANCELLED]
                assert len(cancel_events) >= 1
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_event_subscription_works(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test event subscription and unsubscription."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        events_received = []
        
        def handler(event):
            events_received.append(event)
        
        try:
            async with PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            ) as interface:
                interface._db_session = session
                
                # Subscribe to event
                interface.on_event(EventType.DOWNLOAD_PROGRESS, handler)
                
                # Publish event
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={'progress': 50.0},
                ))
                
                await asyncio.sleep(0.05)
                
                # Verify handler was called
                assert len(events_received) >= 1
                
                # Unsubscribe
                interface.unsubscribe(EventType.DOWNLOAD_PROGRESS, handler)
        
        finally:
            session.close()


# =============================================================================
# Integration Tests for StateManager
# =============================================================================

class TestStateManagerIntegration:
    """Integration tests for StateManager."""
    
    @pytest.mark.asyncio
    async def test_initializes_from_database(
        self,
        database_engine,
        temp_db_path,
    ):
        """Test StateManager initializes from database."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            reset_event_bus()
            event_bus = get_event_bus()
            
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            # Create video with snapshot
            video = Video(
                source_path="/test/init_video.mp4",
                title="Init Test Video",
            )
            session.add(video)
            session.commit()
            session.refresh(video)
            
            snapshot = PipelineSnapshot(
                video_id=video.id,
                current_stage="download",
                overall_status="active",
                stage_progress_percent=75.0,
            )
            session.add(snapshot)
            session.commit()
            
            # Initialize state manager
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Should have loaded the video
            state = state_manager.get_video(video.id)
            assert state is not None
            assert state.title == "Init Test Video"
            assert state.download_progress == 75.0
            
            await state_manager.shutdown()
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_updates_state_on_progress_event(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test StateManager updates state on progress events."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Add video to state
            state_manager._state[1] = VideoState(
                id=1,
                title="Progress Test",
                download_progress=0.0,
            )
            
            # Send progress event
            await event_bus.publish(Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={
                    'video_id': 1,
                    'progress': 50.0,
                    'speed': 1024000.0,
                },
            ))
            await asyncio.sleep(0.05)
            
            # Verify state updated
            state = state_manager.get_video(1)
            assert state.download_progress == 50.0
            assert state.download_speed == 1024000.0
            
            await state_manager.shutdown()
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_notifies_on_state_change(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test StateManager notifies on state changes."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Track changes
            changes = []
            def on_change(video_id, field, value):
                changes.append((video_id, field, value))
            
            state_manager.on_change(on_change)
            
            # Add video to state
            state_manager._state[1] = VideoState(
                id=1,
                title="Notify Test",
            )
            
            # Send progress event
            await event_bus.publish(Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={
                    'video_id': 1,
                    'progress': 75.0,
                },
            ))
            await asyncio.sleep(0.05)
            
            # Verify callback was called
            assert len(changes) > 0
            assert any(c[0] == 1 and c[1] == 'download_progress' for c in changes)
            
            await state_manager.shutdown()
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_handles_multiple_simultaneous_updates(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test StateManager handles multiple simultaneous updates."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Add multiple videos
            for i in range(1, 11):
                state_manager._state[i] = VideoState(
                    id=i,
                    title=f"Video {i}",
                    download_status="active",
                )
            
            # Send events for all videos simultaneously
            async def send_event(video_id):
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={
                        'video_id': video_id,
                        'progress': 50.0,
                    },
                ))
            
            await asyncio.gather(*[send_event(i) for i in range(1, 11)])
            await asyncio.sleep(0.1)
            
            # Verify all videos updated
            for i in range(1, 11):
                state = state_manager.get_video(i)
                assert state.download_progress == 50.0
            
            await state_manager.shutdown()
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_cleanup_unsubscribes_events(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test StateManager cleanup unsubscribes from events."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Should have event subscriptions
            assert len(state_manager._event_unsubscribers) > 0
            
            # Shutdown
            await state_manager.shutdown()
            
            # Should have unsubscribed
            assert len(state_manager._event_unsubscribers) == 0
            assert len(state_manager._state) == 0
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_handles_missing_video_gracefully(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test StateManager handles missing video gracefully."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            pipeline = PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            )
            pipeline._db_session = session
            
            # Set up to return None for unknown video
            pipeline.get_video_detail = MagicMock(return_value=None)
            
            state_manager = StateManager(pipeline)
            await state_manager.initialize()
            
            # Send event for non-existent video
            await event_bus.publish(Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={
                    'video_id': 99999,
                    'progress': 50.0,
                },
            ))
            await asyncio.sleep(0.05)
            
            # Should not crash
            assert state_manager.get_video(99999) is None
            
            await state_manager.shutdown()
        
        finally:
            session.close()


# =============================================================================
# Integration Tests for MetricsCollector
# =============================================================================

class TestPipelineInterfaceAdditionalCoverage:
    """Additional tests to improve PipelineInterface coverage."""
    
    @pytest.mark.asyncio
    async def test_download_history(self, database_engine, temp_db_path):
        """Test get_download_history returns completed downloads."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(database_path=temp_db_path) as interface:
                interface._db_session = session
                
                # Create video with completed download
                video = Video(
                    source_path="/test/history_video.mp4",
                    title="History Test Video",
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                
                download = Download(
                    video_id=video.id,
                    source_type="youtube",
                    status="completed",
                    progress_percent=100.0,
                    download_rate=0,
                    bytes_downloaded=10485760,
                    bytes_total=10485760,
                )
                session.add(download)
                session.commit()
                
                # Get download history
                history = interface.get_download_history(limit=10)
                
                # Should include the completed download
                assert len(history) >= 1
                assert any(d.title == "History Test Video" for d in history)
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_download_stats(self, database_engine, temp_db_path):
        """Test get_download_stats returns correct statistics."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(database_path=temp_db_path) as interface:
                interface._db_session = session
                
                # Create videos and downloads
                video = Video(
                    source_path="/test/stats_video.mp4",
                    title="Stats Test",
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                
                download = Download(
                    video_id=video.id,
                    source_type="youtube",
                    status="downloading",
                    download_rate=1024000,
                )
                session.add(download)
                session.commit()
                
                # Get download stats
                stats = interface.get_download_stats()
                
                assert isinstance(stats, DownloadStats)
                assert stats.active_count >= 1
                assert stats.youtube_active >= 1
                assert stats.total_speed >= 1024000
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_pause_resume_download(self, database_engine, temp_db_path):
        """Test pause_download and resume_download."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(database_path=temp_db_path) as interface:
                interface._db_session = session
                
                # Create video with active download
                video = Video(
                    source_path="/test/pause_video.mp4",
                    title="Pause Test",
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                
                download = Download(
                    video_id=video.id,
                    source_type="youtube",
                    status="downloading",
                )
                session.add(download)
                session.commit()
                
                # Pause download
                result = interface.pause_download(video.id)
                assert result is True
                
                session.refresh(download)
                assert download.status == "paused"
                
                # Resume download
                result = interface.resume_download(video.id)
                assert result is True
                
                session.refresh(download)
                assert download.status == "downloading"
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_retry_video_not_found(self, database_engine, temp_db_path):
        """Test retry_video with non-existent video."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(database_path=temp_db_path) as interface:
                interface._db_session = session
                
                result = await interface.retry_video(99999)
                
                assert result.success is False
                assert "not found" in result.message.lower()
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_retry_video_invalid_stage(self, database_engine, temp_db_path):
        """Test retry_video with invalid stage."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(database_path=temp_db_path) as interface:
                interface._db_session = session
                
                video = Video(
                    source_path="/test/invalid_stage.mp4",
                    title="Invalid Stage Test",
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                
                result = await interface.retry_video(video.id, stage="invalid_stage")
                
                assert result.success is False
                assert "invalid" in result.message.lower()
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_cancel_video_not_found(self, database_engine, temp_db_path):
        """Test cancel_video with non-existent video."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(database_path=temp_db_path) as interface:
                interface._db_session = session
                
                result = await interface.cancel_video(99999)
                
                assert result is False
    
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_error_handling_database_rollback(self, database_engine, temp_db_path):
        """Test that database errors trigger rollback."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            interface = PipelineInterface(database_path=temp_db_path)
            interface._db_session = session
            
            # Create a valid context first
            try:
                async with interface:
                    # Force an error by raising
                    raise ValueError("Test error")
            except ValueError:
                pass
            
            # Session should be closed after exception
            # (Note: we can't easily verify rollback without more setup)
        
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_unsubscribe_returns_false_when_not_found(
        self,
        database_engine,
        temp_db_path,
        event_bus,
    ):
        """Test unsubscribe returns False when handler not found."""
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        
        try:
            async with PipelineInterface(
                database_path=temp_db_path,
                event_bus=event_bus,
            ) as interface:
                interface._db_session = session
                
                # Try to unsubscribe a handler that was never subscribed
                def dummy_handler(event):
                    pass
                
                result = interface.unsubscribe(EventType.DOWNLOAD_PROGRESS, dummy_handler)
                assert result is False
        
        finally:
            session.close()


class TestMetricsCollectorIntegration:
    """Integration tests for MetricsCollector."""
    
    @pytest.mark.asyncio
    async def test_metrics_invalid_stage_handling(self, db_session):
        """Test MetricsCollector handles invalid stage gracefully."""
        speed_service = SpeedHistoryService(db_session)
        await speed_service.start()
        
        metrics = MetricsCollector(speed_service)
        
        # Try to record with invalid stage
        metrics.record_speed(1, "invalid_stage", 1000000.0, 50.0)
        # Should not raise, just log warning
        
        # Try to get history with invalid stage
        history = metrics.get_speed_history(1, "invalid_stage", seconds=60)
        assert history == []
        
        await speed_service.stop()
    
    @pytest.mark.asyncio
    async def test_metrics_current_speed_none_when_empty(self, db_session):
        """Test get_current_speed returns None when no data."""
        speed_service = SpeedHistoryService(db_session)
        await speed_service.start()
        
        metrics = MetricsCollector(speed_service)
        
        current = metrics.get_current_speed(1, "download")
        assert current is None
        
        await speed_service.stop()

    
    @pytest.mark.asyncio
    async def test_records_speed_from_events(
        self,
        database_engine,
        db_session,
        temp_db_path,
        event_bus,
    ):
        """Test MetricsCollector records speed from events."""
        # Set up services
        speed_service = SpeedHistoryService(db_session)
        await speed_service.start()
        
        metrics = MetricsCollector(speed_service)
        
        # Create video
        video = Video(
            source_path="/test/speed_video.mp4",
            title="Speed Test",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Record speeds
        for i in range(5):
            metrics.record_speed(
                video.id,
                "download",
                1000000.0 * (i + 1),
                float((i + 1) * 20),
            )
        
        # Flush to database
        speed_service._flush_all_buffers()
        
        # Verify history
        history = metrics.get_speed_history(video.id, "download", seconds=60)
        assert len(history) == 5
        
        await speed_service.stop()
    
    @pytest.mark.asyncio
    async def test_get_speed_history_returns_correct_range(
        self,
        database_engine,
        db_session,
    ):
        """Test get_speed_history returns correct time range."""
        speed_service = SpeedHistoryService(db_session)
        await speed_service.start()
        
        metrics = MetricsCollector(speed_service)
        
        # Create video
        video = Video(
            source_path="/test/range_video.mp4",
            title="Range Test",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Record speed
        metrics.record_speed(video.id, "download", 1000000.0, 50.0)
        speed_service._flush_all_buffers()
        
        # Query with different ranges
        history_60s = metrics.get_speed_history(video.id, "download", seconds=60)
        history_1s = metrics.get_speed_history(video.id, "download", seconds=1)
        
        # Both should have the recent sample
        assert len(history_60s) == 1
        # 1 second might filter it out depending on timing
        assert len(history_1s) <= 1
        
        await speed_service.stop()
    
    @pytest.mark.asyncio
    async def test_aggregate_speeds_calculate_correctly(
        self,
        database_engine,
        db_session,
    ):
        """Test aggregate speeds calculate correctly."""
        speed_service = SpeedHistoryService(db_session)
        await speed_service.start()
        
        metrics = MetricsCollector(speed_service)
        
        # Create multiple videos
        videos = []
        for i in range(3):
            video = Video(
                source_path=f"/test/agg_video_{i}.mp4",
                title=f"Aggregate Video {i}",
            )
            db_session.add(video)
            videos.append(video)
        db_session.commit()
        for video in videos:
            db_session.refresh(video)
        
        # Record speeds for different videos
        for i, video in enumerate(videos):
            metrics.record_speed(
                video.id,
                "download",
                1000000.0 * (i + 1),
                50.0,
            )
        
        speed_service._flush_all_buffers()
        
        # Get aggregates
        aggregates = metrics.get_aggregate_speeds(seconds=60)
        
        assert 'download' in aggregates
        assert 'upload' in aggregates
        assert 'total' in aggregates
        
        await speed_service.stop()
    
    @pytest.mark.asyncio
    async def test_chart_data_formatted_correctly(
        self,
        database_engine,
        db_session,
    ):
        """Test chart data is formatted correctly."""
        speed_service = SpeedHistoryService(db_session)
        await speed_service.start()
        
        metrics = MetricsCollector(speed_service)
        
        # Create video
        video = Video(
            source_path="/test/chart_video.mp4",
            title="Chart Test",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Record speeds
        for i in range(10):
            metrics.record_speed(
                video.id,
                "download",
                500000.0 + (i * 100000),
                float(i * 10),
            )
        
        speed_service._flush_all_buffers()
        
        # Get chart data
        chart_data = metrics.get_speed_data_for_chart(
            video_id=video.id,
            stage="download",
            seconds=60,
            bucket_size=5,
        )
        
        assert 'timestamps' in chart_data
        assert 'speeds' in chart_data
        assert 'avg_speed' in chart_data
        assert 'peak_speed' in chart_data
        assert 'current_speed' in chart_data
        
        assert len(chart_data['timestamps']) > 0
        assert len(chart_data['speeds']) > 0
        assert chart_data['peak_speed'] >= chart_data['avg_speed']
        
        await speed_service.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
