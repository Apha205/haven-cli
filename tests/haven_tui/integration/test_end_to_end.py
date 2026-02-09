"""End-to-end integration tests.

Tests complete user workflows from start to finish.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import scoped_session

from haven_cli.database.models import Base, Video, PipelineSnapshot
from haven_cli.database.repositories import PipelineSnapshotRepository as CliPipelineSnapshotRepository
from haven_cli.pipeline.events import EventBus, EventType, Event
from haven_tui.data.repositories import PipelineSnapshotRepository
from haven_tui.data.event_consumer import TUIEventConsumer, TUIStateManager
from haven_tui.models.video_view import VideoView, PipelineStage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)
    
    yield session
    
    session.remove()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def event_bus():
    """Create a fresh event bus."""
    bus = EventBus()
    yield bus
    bus.clear()


# =============================================================================
# End-to-End Pipeline Tests
# =============================================================================

class TestYouTubeDownloadFlow:
    """End-to-end test for YouTube download flow."""
    
    @pytest.mark.asyncio
    async def test_complete_youtube_pipeline(self, db_session, event_bus):
        """Test complete YouTube video pipeline from download to completion."""
        # Setup database
        video = Video(
            source_path="https://youtube.com/watch?v=test123",
            title="Test YouTube Video",
            duration=600.0,
            file_size=500 * 1024 * 1024,  # 500 MB
            plugin_name="youtube",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Setup TUI components
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager, tui_repo)
        
        # Create initial snapshot
        snapshot = cli_repo.get_or_create(video.id)
        snapshot.overall_status = "pending"
        snapshot.current_stage = "pending"
        db_session.commit()
        
        # Load video into state
        video_view = tui_repo.get_video_summary(video.id)
        state_manager.merge_video(video_view)
        
        await consumer.start()
        
        # Simulate pipeline events
        events = [
            # Pipeline starts
            (EventType.PIPELINE_STARTED, {"video_id": video.id}),
            
            # Download phase
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "download"}),
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 25.0,
                "download_rate": 5 * 1024 * 1024,  # 5 MB/s
                "eta_seconds": 60,
                "bytes_downloaded": 125 * 1024 * 1024,
                "bytes_total": 500 * 1024 * 1024,
            }),
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 50.0,
                "download_rate": 6 * 1024 * 1024,
                "eta_seconds": 40,
                "bytes_downloaded": 250 * 1024 * 1024,
                "bytes_total": 500 * 1024 * 1024,
            }),
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 75.0,
                "download_rate": 5.5 * 1024 * 1024,
                "eta_seconds": 20,
                "bytes_downloaded": 375 * 1024 * 1024,
                "bytes_total": 500 * 1024 * 1024,
            }),
            (EventType.STEP_COMPLETE, {"video_id": video.id, "stage": "download"}),
            
            # Encryption phase
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "encrypt"}),
            (EventType.ENCRYPT_PROGRESS, {
                "video_id": video.id,
                "progress": 33.0,
                "bytes_processed": 166 * 1024 * 1024,
            }),
            (EventType.ENCRYPT_PROGRESS, {
                "video_id": video.id,
                "progress": 66.0,
                "bytes_processed": 333 * 1024 * 1024,
            }),
            (EventType.ENCRYPT_COMPLETE, {"video_id": video.id}),
            (EventType.STEP_COMPLETE, {"video_id": video.id, "stage": "encrypt"}),
            
            # Upload phase
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "upload"}),
            (EventType.UPLOAD_PROGRESS, {
                "video_id": video.id,
                "progress": 50.0,
                "upload_speed": 2 * 1024 * 1024,  # 2 MB/s
            }),
            (EventType.UPLOAD_COMPLETE, {"video_id": video.id}),
            (EventType.STEP_COMPLETE, {"video_id": video.id, "stage": "upload"}),
            
            # Sync phase
            (EventType.SYNC_COMPLETE, {"video_id": video.id}),
            
            # Analysis phase
            (EventType.ANALYSIS_COMPLETE, {"video_id": video.id}),
            
            # Pipeline complete
            (EventType.PIPELINE_COMPLETE, {"video_id": video.id}),
        ]
        
        for event_type, payload in events:
            await event_bus.publish(Event(event_type=event_type, payload=payload))
            await asyncio.sleep(0.001)
        
        await asyncio.sleep(0.05)
        
        # Verify final state
        final_state = state_manager.get_video(video.id)
        assert final_state is not None
        assert final_state.overall_status == "completed"
        assert final_state.current_stage == PipelineStage.COMPLETE
        
        await consumer.stop()


class TestBitTorrentDownloadFlow:
    """End-to-end test for BitTorrent download flow."""
    
    @pytest.mark.asyncio
    async def test_complete_torrent_pipeline(self, db_session, event_bus):
        """Test complete BitTorrent video pipeline."""
        # Setup database
        video = Video(
            source_path="magnet:?xt=urn:btih:test123",
            title="Test Torrent Video",
            duration=1200.0,
            file_size=2 * 1024 * 1024 * 1024,  # 2 GB
            plugin_name="bittorrent",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Setup TUI components
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager, tui_repo)
        
        # Create initial snapshot
        snapshot = cli_repo.get_or_create(video.id)
        snapshot.overall_status = "pending"
        snapshot.current_stage = "pending"
        db_session.commit()
        
        # Load video into state
        video_view = tui_repo.get_video_summary(video.id)
        state_manager.merge_video(video_view)
        
        await consumer.start()
        
        # Simulate torrent download with varying speeds
        events = [
            (EventType.PIPELINE_STARTED, {"video_id": video.id}),
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "download"}),
            # Slow start
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 10.0,
                "download_rate": 500 * 1024,  # 500 KB/s
                "eta_seconds": 3600,
            }),
            # Speeding up
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 30.0,
                "download_rate": 2 * 1024 * 1024,  # 2 MB/s
                "eta_seconds": 800,
            }),
            # Peak speed
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 60.0,
                "download_rate": 5 * 1024 * 1024,  # 5 MB/s
                "eta_seconds": 400,
            }),
            # Slowing down
            (EventType.DOWNLOAD_PROGRESS, {
                "video_id": video.id,
                "progress_percent": 90.0,
                "download_rate": 1 * 1024 * 1024,  # 1 MB/s
                "eta_seconds": 200,
            }),
            (EventType.STEP_COMPLETE, {"video_id": video.id, "stage": "download"}),
            (EventType.ENCRYPT_COMPLETE, {"video_id": video.id}),
            (EventType.UPLOAD_COMPLETE, {"video_id": video.id}),
            (EventType.SYNC_COMPLETE, {"video_id": video.id}),
            (EventType.PIPELINE_COMPLETE, {"video_id": video.id}),
        ]
        
        for event_type, payload in events:
            await event_bus.publish(Event(event_type=event_type, payload=payload))
            await asyncio.sleep(0.001)
        
        await asyncio.sleep(0.05)
        
        # Verify final state
        final_state = state_manager.get_video(video.id)
        assert final_state is not None
        assert final_state.overall_status == "completed"
        
        # Verify speed history was tracked
        speed_history = state_manager.get_speed_history(video.id, seconds=3600)
        assert len(speed_history) > 0
        
        await consumer.stop()


class TestEncryptionFlow:
    """End-to-end test for encryption flow."""
    
    @pytest.mark.asyncio
    async def test_encryption_only_flow(self, db_session, event_bus):
        """Test encryption-only pipeline flow."""
        # Setup database with existing downloaded video
        video = Video(
            source_path="/downloads/existing.mp4",
            title="Existing Video",
            duration=300.0,
            file_size=100 * 1024 * 1024,
            plugin_name="local",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Setup TUI components
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager, tui_repo)
        
        # Create initial snapshot at encrypt stage
        snapshot = cli_repo.get_or_create(video.id)
        snapshot.overall_status = "active"
        snapshot.current_stage = "encrypt"
        snapshot.stage_progress_percent = 0.0
        db_session.commit()
        
        # Load video into state
        video_view = tui_repo.get_video_summary(video.id)
        state_manager.merge_video(video_view)
        
        await consumer.start()
        
        # Simulate encryption events
        events = [
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "encrypt"}),
            (EventType.ENCRYPT_PROGRESS, {
                "video_id": video.id,
                "progress": 10.0,
                "bytes_processed": 10 * 1024 * 1024,
            }),
            (EventType.ENCRYPT_PROGRESS, {
                "video_id": video.id,
                "progress": 30.0,
                "bytes_processed": 30 * 1024 * 1024,
            }),
            (EventType.ENCRYPT_PROGRESS, {
                "video_id": video.id,
                "progress": 50.0,
                "bytes_processed": 50 * 1024 * 1024,
            }),
            (EventType.ENCRYPT_PROGRESS, {
                "video_id": video.id,
                "progress": 80.0,
                "bytes_processed": 80 * 1024 * 1024,
            }),
            (EventType.ENCRYPT_COMPLETE, {"video_id": video.id}),
            (EventType.STEP_COMPLETE, {"video_id": video.id, "stage": "encrypt"}),
            (EventType.PIPELINE_COMPLETE, {"video_id": video.id}),
        ]
        
        for event_type, payload in events:
            await event_bus.publish(Event(event_type=event_type, payload=payload))
            await asyncio.sleep(0.001)
        
        await asyncio.sleep(0.05)
        
        # Verify final state
        final_state = state_manager.get_video(video.id)
        assert final_state is not None
        assert final_state.current_stage == PipelineStage.COMPLETE
        assert final_state.overall_status == "completed"
        
        await consumer.stop()


class TestUploadFlow:
    """End-to-end test for upload flow."""
    
    @pytest.mark.asyncio
    async def test_upload_with_retry(self, db_session, event_bus):
        """Test upload flow with retry after failure."""
        # Setup database
        video = Video(
            source_path="/downloads/upload_test.mp4",
            title="Upload Test Video",
            duration=600.0,
            file_size=200 * 1024 * 1024,
            plugin_name="youtube",
        )
        db_session.add(video)
        db_session.commit()
        db_session.refresh(video)
        
        # Setup TUI components
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager, tui_repo)
        
        # Create initial snapshot at upload stage
        snapshot = cli_repo.get_or_create(video.id)
        snapshot.overall_status = "active"
        snapshot.current_stage = "upload"
        snapshot.stage_progress_percent = 0.0
        db_session.commit()
        
        # Load video into state
        video_view = tui_repo.get_video_summary(video.id)
        state_manager.merge_video(video_view)
        
        await consumer.start()
        
        # Simulate upload with failure and retry
        events = [
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "upload"}),
            (EventType.UPLOAD_PROGRESS, {
                "video_id": video.id,
                "progress": 30.0,
                "upload_speed": 1 * 1024 * 1024,
            }),
            (EventType.UPLOAD_PROGRESS, {
                "video_id": video.id,
                "progress": 60.0,
                "upload_speed": 1.5 * 1024 * 1024,
            }),
            # Failure
            (EventType.UPLOAD_FAILED, {
                "video_id": video.id,
                "error": "Connection reset by peer",
            }),
            # Retry
            (EventType.STEP_STARTED, {"video_id": video.id, "stage": "upload"}),
            (EventType.UPLOAD_PROGRESS, {
                "video_id": video.id,
                "progress": 20.0,
                "upload_speed": 800 * 1024,
            }),
            (EventType.UPLOAD_PROGRESS, {
                "video_id": video.id,
                "progress": 60.0,
                "upload_speed": 1 * 1024 * 1024,
            }),
            (EventType.UPLOAD_PROGRESS, {
                "video_id": video.id,
                "progress": 90.0,
                "upload_speed": 1.2 * 1024 * 1024,
            }),
            (EventType.UPLOAD_COMPLETE, {"video_id": video.id}),
            (EventType.SYNC_COMPLETE, {"video_id": video.id}),
            (EventType.PIPELINE_COMPLETE, {"video_id": video.id}),
        ]
        
        for event_type, payload in events:
            await event_bus.publish(Event(event_type=event_type, payload=payload))
            await asyncio.sleep(0.001)
        
        await asyncio.sleep(0.05)
        
        # Verify final state
        final_state = state_manager.get_video(video.id)
        assert final_state is not None
        assert final_state.overall_status == "completed"
        
        await consumer.stop()


class TestMultipleVideosFlow:
    """End-to-end test with multiple videos."""
    
    @pytest.mark.asyncio
    async def test_multiple_videos_pipeline(self, db_session, event_bus):
        """Test pipeline with multiple videos at different stages."""
        # Setup database with multiple videos
        videos = []
        stages = [
            ("download", 25.0),
            ("download", 75.0),
            ("encrypt", 50.0),
            ("upload", 30.0),
            ("sync", 80.0),
        ]
        
        for i, (stage, progress) in enumerate(stages):
            video = Video(
                source_path=f"/downloads/video{i}.mp4",
                title=f"Test Video {i}",
                duration=600.0,
                file_size=100 * 1024 * 1024,
                plugin_name="youtube" if i % 2 == 0 else "bittorrent",
            )
            db_session.add(video)
            db_session.flush()
            
            cli_repo = CliPipelineSnapshotRepository(db_session)
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.overall_status = "active"
            snapshot.current_stage = stage
            snapshot.stage_progress_percent = progress
            snapshot.stage_speed = 1024000
            
            videos.append(video)
        
        db_session.commit()
        
        # Setup TUI components
        tui_repo = PipelineSnapshotRepository(db_session)
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager, tui_repo)
        
        # Load all videos into state
        for video in videos:
            video_view = tui_repo.get_video_summary(video.id)
            state_manager.merge_video(video_view)
        
        await consumer.start()
        
        # Verify initial state
        all_videos = state_manager.get_videos()
        assert len(all_videos) == 5
        
        # Simulate progress on all videos
        for i, video in enumerate(videos):
            if i < 2:  # Downloading videos
                await event_bus.publish(Event(
                    event_type=EventType.DOWNLOAD_PROGRESS,
                    payload={
                        "video_id": video.id,
                        "progress_percent": min(100, video.pipeline_snapshot.stage_progress_percent + 10),
                    },
                ))
            elif i == 2:  # Encrypting video
                await event_bus.publish(Event(
                    event_type=EventType.ENCRYPT_PROGRESS,
                    payload={
                        "video_id": video.id,
                        "progress": min(100, video.pipeline_snapshot.stage_progress_percent + 10),
                    },
                ))
            elif i == 3:  # Uploading video
                await event_bus.publish(Event(
                    event_type=EventType.UPLOAD_PROGRESS,
                    payload={
                        "video_id": video.id,
                        "progress": min(100, video.pipeline_snapshot.stage_progress_percent + 10),
                    },
                ))
        
        await asyncio.sleep(0.05)
        
        # Verify updates
        for i, video in enumerate(videos):
            state = state_manager.get_video(video.id)
            assert state is not None
            assert state.stage_progress > 0
        
        await consumer.stop()


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Performance tests for large video lists."""
    
    @pytest.mark.asyncio
    async def test_100_videos_performance(self, db_session, event_bus):
        """Test performance with 100 videos."""
        # Create 100 videos
        videos = []
        for i in range(100):
            video = Video(
                source_path=f"/downloads/video{i}.mp4",
                title=f"Test Video {i}",
                duration=600.0,
                file_size=100 * 1024 * 1024,
                plugin_name="youtube",
            )
            db_session.add(video)
            db_session.flush()
            
            cli_repo = CliPipelineSnapshotRepository(db_session)
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.overall_status = "active"
            snapshot.current_stage = "download"
            snapshot.stage_progress_percent = i % 100
            snapshot.stage_speed = 1024000
            
            videos.append(video)
        
        db_session.commit()
        
        # Setup TUI components
        tui_repo = PipelineSnapshotRepository(db_session)
        state_manager = TUIStateManager()
        consumer = TUIEventConsumer(event_bus, state_manager, tui_repo)
        
        # Load all videos into state
        start_time = datetime.now(timezone.utc)
        for video in videos:
            video_view = tui_repo.get_video_summary(video.id)
            state_manager.merge_video(video_view)
        load_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Should load 100 videos in reasonable time
        assert load_time < 5.0
        
        await consumer.start()
        
        # Process events for all videos
        start_time = datetime.now(timezone.utc)
        for i, video in enumerate(videos[:50]):  # Process first 50
            await event_bus.publish(Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={
                    "video_id": video.id,
                    "progress_percent": 50.0,
                },
            ))
        
        await asyncio.sleep(0.1)
        process_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Should process 50 events in reasonable time
        assert process_time < 5.0
        
        await consumer.stop()
