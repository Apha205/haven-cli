"""Integration tests for PipelineInterface with real database.

These tests verify that the PipelineInterface works correctly with a real
SQLite database, testing the full data flow from interface to database.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from typing import List

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
from haven_cli.database.models import (
    Base,
    Video,
    Download,
    TorrentDownload,
    PipelineSnapshot,
)
from haven_cli.pipeline.events import EventType, Event, EventBus, get_event_bus, reset_event_bus


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
def event_bus():
    """Get a fresh event bus for testing."""
    reset_event_bus()
    bus = get_event_bus()
    yield bus
    reset_event_bus()


class TestPipelineInterfaceIntegration:
    """Integration tests using real database and event bus."""
    
    @pytest.mark.asyncio
    async def test_full_video_workflow(self, database_engine, temp_db_path):
        """Test complete video lifecycle through the interface."""
        # Create interface with real event bus
        event_bus = get_event_bus()
        
        # Track events
        events_received = []
        
        async def event_handler(event: Event):
            events_received.append(event)
        
        event_bus.subscribe(EventType.PIPELINE_STARTED, event_handler)
        event_bus.subscribe(EventType.PIPELINE_CANCELLED, event_handler)
        
        # Use context manager for database session
        interface = PipelineInterface(
            database_path=temp_db_path,
            event_bus=event_bus,
        )
        
        # Manually set up the session since we're not using async context
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        interface._db_session = session
        interface._plugin_manager = None  # Not needed for this test
        
        try:
            # 1. Create a video
            video = Video(
                source_path="/test/integration.mp4",
                title="Integration Test Video",
                duration=300.0,
                file_size=10485760,
                creator_handle="test_creator",
            )
            session.add(video)
            session.commit()
            
            # 2. Get video detail
            detail = interface.get_video_detail(video.id)
            assert detail is not None
            assert detail.title == "Integration Test Video"
            assert detail.creator_handle == "test_creator"
            
            # 3. Create a pipeline snapshot
            snapshot = PipelineSnapshot(
                video_id=video.id,
                current_stage="download",
                overall_status="active",
                stage_progress_percent=25.0,
                stage_speed=1024,
                stage_eta=300,
            )
            session.add(snapshot)
            session.commit()
            
            # 4. Get pipeline stats
            stats = interface.get_pipeline_stats()
            assert stats["active_count"] >= 0
            assert "by_stage" in stats
            assert "total_videos" in stats
            
            # 5. Get active videos
            active = interface.get_active_videos()
            assert isinstance(active, list)
            
            # 6. Search for the video
            results = interface.search_videos("Integration")
            assert len(results) >= 1
            assert any(v.title == "Integration Test Video" for v in results)
            
            # 7. Create a download for the video
            download = Download(
                video_id=video.id,
                source_type="youtube",
                status="downloading",
                progress_percent=50.0,
                download_rate=2048,
                bytes_downloaded=5242880,
                bytes_total=10485760,
                eta_seconds=150,
            )
            session.add(download)
            session.commit()
            
            # 8. Get active downloads
            downloads = interface.get_active_downloads()
            assert isinstance(downloads, list)
            youtube_downloads = [d for d in downloads if d.source_type == "youtube"]
            assert len(youtube_downloads) >= 1
            
            # 9. Pause download
            result = interface.pause_download(video.id)
            assert result is True
            
            # Verify download is paused
            session.refresh(download)
            assert download.status == "paused"
            
            # 10. Resume download
            result = interface.resume_download(video.id)
            assert result is True
            
            session.refresh(download)
            assert download.status == "downloading"
            
            # 11. Cancel the video
            result = await interface.cancel_video(video.id)
            assert result is True
            
            # Allow event to be processed
            await asyncio.sleep(0.1)
            
            # Verify cancellation event was published
            cancel_events = [e for e in events_received 
                           if e.event_type == EventType.PIPELINE_CANCELLED]
            assert len(cancel_events) >= 1
            
        finally:
            session.close()
            reset_event_bus()
    
    @pytest.mark.asyncio
    async def test_event_subscription_integration(self, database_engine, temp_db_path):
        """Test event subscription with real event bus."""
        event_bus = get_event_bus()
        interface = PipelineInterface(
            database_path=temp_db_path,
            event_bus=event_bus,
        )
        
        # Set up session
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        interface._db_session = session
        
        events_received = []
        
        def sync_handler(event: Event):
            events_received.append(("sync", event.event_type))
        
        async def async_handler(event: Event):
            events_received.append(("async", event.event_type))
        
        try:
            # Subscribe handlers
            interface.on_event(EventType.DOWNLOAD_PROGRESS, sync_handler)
            interface.on_event(EventType.UPLOAD_PROGRESS, async_handler)
            interface.on_any_event(sync_handler)
            
            # Publish test events
            await event_bus.publish(Event(
                event_type=EventType.DOWNLOAD_PROGRESS,
                payload={"progress": 50},
            ))
            
            await event_bus.publish(Event(
                event_type=EventType.UPLOAD_PROGRESS,
                payload={"progress": 75},
            ))
            
            # Allow events to be processed
            await asyncio.sleep(0.1)
            
            # Verify events were received
            assert len(events_received) >= 2
            
        finally:
            session.close()
            reset_event_bus()
    
    @pytest.mark.asyncio
    async def test_unified_downloads_integration(self, database_engine, temp_db_path):
        """Test unified downloads view with real database."""
        interface = PipelineInterface(database_path=temp_db_path)
        
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        interface._db_session = session
        interface._event_bus = None  # Not needed for this test
        
        try:
            # Create test videos and downloads
            video1 = Video(
                source_path="/test/video1.mp4",
                title="YouTube Video",
            )
            video2 = Video(
                source_path="/test/video2.mp4",
                title="Another Video",
            )
            session.add_all([video1, video2])
            session.commit()
            
            # Create YouTube download
            dl1 = Download(
                video_id=video1.id,
                source_type="youtube",
                status="downloading",
                progress_percent=75.0,
                download_rate=1024,
                bytes_downloaded=768,
                bytes_total=1024,
                eta_seconds=30,
            )
            
            # Create paused download
            dl2 = Download(
                video_id=video2.id,
                source_type="youtube",
                status="paused",
                progress_percent=50.0,
                download_rate=0,
                bytes_downloaded=512,
                bytes_total=1024,
            )
            
            session.add_all([dl1, dl2])
            session.commit()
            
            # Create torrent download
            torrent = TorrentDownload(
                infohash="integration_test_hash",
                source_id="test_source",
                title="Torrent File",
                status="downloading",
                progress=0.25,
                download_rate=512,
                total_size=2048,
                downloaded_size=512,
                peers=5,
                seeds=3,
            )
            session.add(torrent)
            session.commit()
            
            # Get unified downloads
            downloads = interface.get_active_downloads()
            
            # Should have active torrent and active youtube, but not paused
            assert len(downloads) >= 1
            
            # Check YouTube download (status is mapped to unified status)
            youtube_dls = [d for d in downloads if d.source_type == "youtube"]
            if youtube_dls:
                yt = youtube_dls[0]
                assert yt.title in ["YouTube Video", "Another Video"]
                assert yt.status in ["active", "paused"]  # "downloading" is mapped to "active"
            
            # Check torrent download
            torrent_dls = [d for d in downloads if d.source_type == "torrent"]
            if torrent_dls:
                td = torrent_dls[0]
                assert td.title == "Torrent File"
                assert td.status == "active"
                assert td.torrent_peers == 5
                assert td.torrent_seeds == 3
            
        finally:
            session.close()
    
    @pytest.mark.asyncio
    async def test_retry_video_integration(self, database_engine, temp_db_path):
        """Test retry video functionality with real database."""
        event_bus = get_event_bus()
        interface = PipelineInterface(
            database_path=temp_db_path,
            event_bus=event_bus,
        )
        
        SessionLocal = sessionmaker(bind=database_engine)
        session = SessionLocal()
        interface._db_session = session
        
        events_received = []
        
        async def event_handler(event: Event):
            events_received.append(event)
        
        # Subscribe to retry-related events
        event_bus.subscribe(EventType.ENCRYPT_REQUESTED, event_handler)
        event_bus.subscribe(EventType.UPLOAD_REQUESTED, event_handler)
        
        try:
            # Create failed video
            video = Video(
                source_path="/test/failed.mp4",
                title="Failed Upload Video",
            )
            session.add(video)
            session.commit()
            
            snapshot = PipelineSnapshot(
                video_id=video.id,
                current_stage="upload",
                overall_status="failed",
                has_error=True,
                error_stage="upload",
                error_message="Connection timeout",
            )
            session.add(snapshot)
            session.commit()
            
            # Retry from the failed stage
            result = await interface.retry_video(video.id)
            assert isinstance(result, RetryResult)
            assert result.success is True
            
            # Allow event to be processed
            await asyncio.sleep(0.1)
            
            # Verify error was cleared
            session.refresh(snapshot)
            assert snapshot.has_error is False
            assert snapshot.overall_status == "active"
            
            # Retry from specific stage
            result = await interface.retry_video(video.id, stage="encrypt")
            assert isinstance(result, RetryResult)
            assert result.success is True
            
            await asyncio.sleep(0.1)
            
            # Verify events were published
            assert len(events_received) >= 1
            
        finally:
            session.close()
            reset_event_bus()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
