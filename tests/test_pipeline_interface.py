"""Unit tests for PipelineInterface.

Tests cover:
- Context manager functionality
- Event subscription wrappers
- Database query methods
- Unified download view
- TUI-first operations
"""

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import List
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
from haven_cli.database.models import (
    Base,
    Video,
    Download,
    TorrentDownload,
    PipelineSnapshot,
)
from haven_cli.database.repositories import VideoRepository
from haven_cli.pipeline.events import EventType, Event, EventBus


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db_session(temp_db_path):
    """Create a database session with test data."""
    engine = create_engine(f"sqlite:///{temp_db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    engine.dispose()


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = MagicMock(spec=EventBus)
    bus.subscribe = MagicMock(return_value=MagicMock())
    bus.subscribe_all = MagicMock(return_value=MagicMock())
    bus.publish = AsyncMock()
    return bus


class TestPipelineInterfaceContextManager:
    """Test context manager functionality."""
    
    @pytest.mark.asyncio
    async def test_aenter_initializes_session(self, temp_db_path):
        """Test that __aenter__ initializes the database session."""
        interface = PipelineInterface(database_path=temp_db_path)
        
        async with interface as iface:
            assert iface._db_session is not None
    
    @pytest.mark.asyncio
    async def test_aenter_initializes_event_bus(self, temp_db_path):
        """Test that __aenter__ initializes the event bus."""
        interface = PipelineInterface(database_path=temp_db_path)
        
        async with interface as iface:
            assert iface._event_bus is not None
    
    @pytest.mark.asyncio
    async def test_aexit_closes_session(self, temp_db_path):
        """Test that __aexit__ closes the database session."""
        interface = PipelineInterface(database_path=temp_db_path)
        
        async with interface as iface:
            pass
        
        assert interface._db_session is None
    
    @pytest.mark.asyncio
    async def test_custom_event_bus_preserved(self, temp_db_path, mock_event_bus):
        """Test that custom event bus is preserved."""
        interface = PipelineInterface(
            database_path=temp_db_path,
            event_bus=mock_event_bus
        )
        
        async with interface as iface:
            assert iface._event_bus is mock_event_bus


class TestEventSubscriptions:
    """Test event subscription functionality."""
    
    @pytest.mark.asyncio
    async def test_on_event_with_sync_handler(self, temp_db_path):
        """Test subscribing with a sync handler."""
        interface = PipelineInterface(database_path=temp_db_path)
        mock_bus = MagicMock(spec=EventBus)
        mock_bus.subscribe = MagicMock(return_value=MagicMock())
        interface._event_bus = mock_bus
        interface._db_session = MagicMock()
        
        events_received = []
        
        def sync_handler(event: Event):
            events_received.append(event)
        
        interface.on_event(EventType.DOWNLOAD_PROGRESS, sync_handler)
        
        # Verify subscription was made
        assert mock_bus.subscribe.called
        call_args = mock_bus.subscribe.call_args
        assert call_args[0][0] == EventType.DOWNLOAD_PROGRESS
    
    @pytest.mark.asyncio
    async def test_on_event_with_async_handler(self, temp_db_path):
        """Test subscribing with an async handler."""
        interface = PipelineInterface(database_path=temp_db_path)
        mock_bus = MagicMock(spec=EventBus)
        mock_bus.subscribe = MagicMock(return_value=MagicMock())
        interface._event_bus = mock_bus
        interface._db_session = MagicMock()
        
        async def async_handler(event: Event):
            pass
        
        interface.on_event(EventType.DOWNLOAD_PROGRESS, async_handler)
        
        # Verify subscription was made
        assert mock_bus.subscribe.called
    
    @pytest.mark.asyncio
    async def test_on_any_event(self, temp_db_path):
        """Test subscribing to all events."""
        interface = PipelineInterface(database_path=temp_db_path)
        mock_bus = MagicMock(spec=EventBus)
        mock_bus.subscribe_all = MagicMock(return_value=MagicMock())
        interface._event_bus = mock_bus
        interface._db_session = MagicMock()
        
        def handler(event: Event):
            pass
        
        interface.on_any_event(handler)
        
        # Verify subscription was made
        assert mock_bus.subscribe_all.called
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self, temp_db_path):
        """Test unsubscribing a handler."""
        interface = PipelineInterface(database_path=temp_db_path)
        interface._event_bus = MagicMock()
        interface._db_session = MagicMock()
        
        def handler(event: Event):
            pass
        
        # First subscribe
        interface.on_event(EventType.DOWNLOAD_PROGRESS, handler)
        
        # Then unsubscribe
        result = interface.unsubscribe(EventType.DOWNLOAD_PROGRESS, handler)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_unsubscribe_not_found(self, temp_db_path):
        """Test unsubscribing a handler that wasn't subscribed."""
        interface = PipelineInterface(database_path=temp_db_path)
        
        def handler(event: Event):
            pass
        
        result = interface.unsubscribe(EventType.DOWNLOAD_PROGRESS, handler)
        
        assert result is False


class TestDatabaseQueries:
    """Test database query methods."""
    
    @pytest.mark.asyncio
    async def test_get_video_repository(self, db_session):
        """Test getting video repository."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        repo = interface.get_video_repository()
        
        assert isinstance(repo, VideoRepository)
        assert repo.session is db_session
    
    @pytest.mark.asyncio
    async def test_get_video_detail(self, db_session):
        """Test getting video details."""
        # Create test video
        video = Video(
            source_path="/test/video.mp4",
            title="Test Video",
            duration=120.0,
            file_size=1024,
        )
        db_session.add(video)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = interface.get_video_detail(video.id)
        
        assert result is not None
        assert result.id == video.id
        assert result.title == "Test Video"
    
    @pytest.mark.asyncio
    async def test_get_video_detail_not_found(self, db_session):
        """Test getting video details for non-existent video."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = interface.get_video_detail(99999)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_search_videos(self, db_session):
        """Test searching videos."""
        # Create test videos
        video1 = Video(
            source_path="/test/cat.mp4",
            title="Cat Video",
            creator_handle="catlover",
        )
        video2 = Video(
            source_path="/test/dog.mp4",
            title="Dog Video",
            creator_handle="doglover",
        )
        db_session.add_all([video1, video2])
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        results = interface.search_videos("cat")
        
        assert len(results) == 1
        assert results[0].title == "Cat Video"
    
    @pytest.mark.asyncio
    async def test_search_videos_by_creator(self, db_session):
        """Test searching videos by creator handle."""
        # Create test videos
        video = Video(
            source_path="/test/video.mp4",
            title="Some Video",
            creator_handle="specialcreator",
        )
        db_session.add(video)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        results = interface.search_videos("specialcreator")
        
        assert len(results) == 1
        assert results[0].creator_handle == "specialcreator"
    
    @pytest.mark.asyncio
    async def test_get_pipeline_stats(self, db_session):
        """Test getting pipeline statistics."""
        # Create test video with pipeline snapshot
        video = Video(source_path="/test/video.mp4", title="Test")
        db_session.add(video)
        db_session.commit()
        
        snapshot = PipelineSnapshot(
            video_id=video.id,
            current_stage="download",
            overall_status="active",
            stage_speed=1000,
        )
        db_session.add(snapshot)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        stats = interface.get_pipeline_stats()
        
        assert "active_count" in stats
        assert "total_speed" in stats
        assert "by_stage" in stats
        assert "total_videos" in stats


class TestUnifiedDownloads:
    """Test unified download view functionality."""
    
    @pytest.mark.asyncio
    async def test_get_active_downloads_empty(self, db_session):
        """Test getting active downloads when none exist."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        downloads = interface.get_active_downloads()
        
        assert isinstance(downloads, list)
        assert len(downloads) == 0
    
    @pytest.mark.asyncio
    async def test_get_active_downloads_youtube(self, db_session):
        """Test getting YouTube downloads."""
        # Create test video and download
        video = Video(source_path="/test/video.mp4", title="YouTube Video")
        db_session.add(video)
        db_session.commit()
        
        download = Download(
            video_id=video.id,
            source_type="youtube",
            status="downloading",
            progress_percent=50.0,
            download_rate=1024,
            bytes_downloaded=512,
            bytes_total=1024,
            eta_seconds=60,
            source_metadata={"url": "https://youtube.com/watch?v=test"},
        )
        db_session.add(download)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        downloads = interface.get_active_downloads()
        
        assert len(downloads) == 1
        assert downloads[0].source_type == "youtube"
        assert downloads[0].title == "YouTube Video"
        assert downloads[0].youtube_url == "https://youtube.com/watch?v=test"
    
    @pytest.mark.asyncio
    async def test_get_active_downloads_torrent(self, db_session):
        """Test getting BitTorrent downloads."""
        # Create test torrent download
        torrent = TorrentDownload(
            infohash="abc123",
            source_id="test_source",
            title="Torrent Video",
            status="downloading",
            progress=0.75,
            download_rate=2048,
            total_size=10000,
            downloaded_size=7500,
            peers=10,
            seeds=5,
            magnet_uri="magnet:?xt=urn:btih:abc123",
        )
        db_session.add(torrent)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        downloads = interface.get_active_downloads()
        
        assert len(downloads) == 1
        assert downloads[0].source_type == "torrent"
        assert downloads[0].title == "Torrent Video"
        assert downloads[0].torrent_magnet == "magnet:?xt=urn:btih:abc123"
        assert downloads[0].torrent_peers == 10
        assert downloads[0].torrent_seeds == 5
    
    @pytest.mark.asyncio
    async def test_unified_download_status_mapping(self, db_session):
        """Test that torrent status is correctly mapped to unified status."""
        # Note: get_active_downloads only returns downloading/paused torrents
        # We test status mapping directly through the interface logic
        test_cases = [
            ("downloading", "active"),
            ("paused", "paused"),
        ]
        
        for torrent_status, expected_status in test_cases:
            # Clear previous torrents
            db_session.query(TorrentDownload).delete()
            db_session.commit()
            
            torrent = TorrentDownload(
                infohash=f"hash_{torrent_status}",
                source_id=f"source_{torrent_status}",
                status=torrent_status,
                progress=0.5,
            )
            db_session.add(torrent)
            db_session.commit()
            
            interface = PipelineInterface()
            interface._db_session = db_session
            interface._event_bus = MagicMock()
            
            downloads = interface.get_active_downloads()
            
            assert len(downloads) == 1
            assert downloads[0].status == expected_status, f"Failed for status: {torrent_status}"


class TestTuiOperations:
    """Test TUI-first operations."""
    
    @pytest.mark.asyncio
    async def test_retry_video_not_found(self, db_session):
        """Test retrying a non-existent video."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = await interface.retry_video(99999)
        
        assert isinstance(result, RetryResult)
        assert result.success is False
        assert "not found" in result.message
    
    @pytest.mark.asyncio
    async def test_retry_video_success(self, db_session):
        """Test retrying an existing video."""
        # Create test video with failed snapshot
        video = Video(source_path="/test/video.mp4", title="Failed Video")
        db_session.add(video)
        db_session.commit()
        
        snapshot = PipelineSnapshot(
            video_id=video.id,
            current_stage="upload",
            overall_status="failed",
            has_error=True,
            error_stage="upload",
            error_message="Upload failed",
        )
        db_session.add(snapshot)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = AsyncMock()
        
        result = await interface.retry_video(video.id)
        
        assert isinstance(result, RetryResult)
        assert result.success is True
        assert "upload" in result.message
        
        # Check that error state was cleared
        db_session.refresh(snapshot)
        assert snapshot.has_error is False
        assert snapshot.overall_status == "active"
    
    @pytest.mark.asyncio
    async def test_retry_video_with_stage(self, db_session):
        """Test retrying a video from a specific stage."""
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = AsyncMock()
        
        result = await interface.retry_video(video.id, stage="encrypt")
        
        assert isinstance(result, RetryResult)
        assert result.success is True
        assert "encrypt" in result.message
        
        # Verify event was published
        assert interface._event_bus.publish.called
    
    @pytest.mark.asyncio
    async def test_cancel_video_not_found(self, db_session):
        """Test cancelling a non-existent video."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = await interface.cancel_video(99999)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_cancel_video_success(self, db_session):
        """Test cancelling an existing video."""
        video = Video(source_path="/test/video.mp4", title="To Cancel")
        db_session.add(video)
        db_session.commit()
        
        snapshot = PipelineSnapshot(
            video_id=video.id,
            current_stage="download",
            overall_status="active",
        )
        db_session.add(snapshot)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = AsyncMock()
        
        result = await interface.cancel_video(video.id)
        
        assert result is True
        
        # Check snapshot was updated
        db_session.refresh(snapshot)
        assert snapshot.overall_status == "cancelled"
        
        # Verify event was published
        assert interface._event_bus.publish.called
    
    def test_pause_download(self, db_session):
        """Test pausing a download."""
        # Create test video and download
        video = Video(source_path="/test/video.mp4", title="To Pause")
        db_session.add(video)
        db_session.commit()
        
        download = Download(
            video_id=video.id,
            source_type="youtube",
            status="downloading",
        )
        db_session.add(download)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = interface.pause_download(video.id)
        
        assert result is True
        
        # Check download was paused
        db_session.refresh(download)
        assert download.status == "paused"
    
    def test_pause_download_not_found(self, db_session):
        """Test pausing a download for non-existent video."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = interface.pause_download(99999)
        
        assert result is False
    
    def test_resume_download(self, db_session):
        """Test resuming a paused download."""
        # Create test video and download
        video = Video(source_path="/test/video.mp4", title="To Resume")
        db_session.add(video)
        db_session.commit()
        
        download = Download(
            video_id=video.id,
            source_type="youtube",
            status="paused",
        )
        db_session.add(download)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = interface.resume_download(video.id)
        
        assert result is True
        
        # Check download was resumed
        db_session.refresh(download)
        assert download.status == "downloading"


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_no_session_error(self):
        """Test that methods requiring session raise error when not in context."""
        interface = PipelineInterface()
        
        with pytest.raises(RuntimeError, match="No active database session"):
            interface.get_video_repository()
    
    @pytest.mark.asyncio
    async def test_no_event_bus_error(self, db_session):
        """Test error when event operations called without event bus."""
        interface = PipelineInterface()
        interface._db_session = db_session
        # Don't set _event_bus
        
        with pytest.raises(RuntimeError, match="Event bus not initialized"):
            interface.on_event(EventType.DOWNLOAD_PROGRESS, lambda e: None)
        
        with pytest.raises(RuntimeError, match="Event bus not initialized"):
            interface.on_any_event(lambda e: None)


class TestUnifiedDownloadDataclass:
    """Test UnifiedDownload dataclass."""
    
    def test_unified_download_creation(self):
        """Test creating a UnifiedDownload instance."""
        download = UnifiedDownload(
            id=1,
            video_id=2,
            source_type="youtube",
            title="Test Video",
            status="active",
            progress_percent=50.0,
            speed=1024,
            eta=60,
            total_bytes=1000,
            downloaded_bytes=500,
            started_at=datetime.now(timezone.utc),
            youtube_url="https://youtube.com/watch?v=test",
        )
        
        assert download.id == 1
        assert download.video_id == 2
        assert download.source_type == "youtube"
        assert download.youtube_url == "https://youtube.com/watch?v=test"
    
    def test_unified_download_torrent_fields(self):
        """Test UnifiedDownload with torrent-specific fields."""
        download = UnifiedDownload(
            id=1,
            video_id=2,
            source_type="torrent",
            title="Torrent Video",
            status="active",
            progress_percent=75.0,
            speed=2048,
            eta=120,
            total_bytes=10000,
            downloaded_bytes=7500,
            started_at=datetime.now(timezone.utc),
            torrent_magnet="magnet:?xt=urn:btih:test",
            torrent_peers=10,
            torrent_seeds=5,
        )
        
        assert download.torrent_magnet == "magnet:?xt=urn:btih:test"
        assert download.torrent_peers == 10
        assert download.torrent_seeds == 5


class TestDownloadStats:
    """Test DownloadStats dataclass."""
    
    def test_download_stats_creation(self):
        """Test creating a DownloadStats instance."""
        stats = DownloadStats(
            active_count=5,
            pending_count=3,
            completed_today=10,
            failed_count=2,
            total_speed=10240,
            youtube_active=3,
            torrent_active=2,
            youtube_speed=6144,
            torrent_speed=4096,
        )
        
        assert stats.active_count == 5
        assert stats.pending_count == 3
        assert stats.completed_today == 10
        assert stats.failed_count == 2
        assert stats.total_speed == 10240
        assert stats.youtube_active == 3
        assert stats.torrent_active == 2
        assert stats.youtube_speed == 6144
        assert stats.torrent_speed == 4096


class TestRetryResult:
    """Test RetryResult dataclass."""
    
    def test_retry_result_success(self):
        """Test creating a successful RetryResult."""
        result = RetryResult(
            success=True,
            message="Retrying video from download stage",
            new_job_id=123,
        )
        
        assert result.success is True
        assert "download" in result.message
        assert result.new_job_id == 123
    
    def test_retry_result_failure(self):
        """Test creating a failed RetryResult."""
        result = RetryResult(
            success=False,
            message="Video 999 not found",
        )
        
        assert result.success is False
        assert "not found" in result.message
        assert result.new_job_id is None


class TestGetDownloadStats:
    """Test get_download_stats functionality."""
    
    @pytest.mark.asyncio
    async def test_get_download_stats_empty(self, db_session):
        """Test getting stats when no downloads exist."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        stats = interface.get_download_stats()
        
        assert isinstance(stats, DownloadStats)
        assert stats.active_count == 0
        assert stats.pending_count == 0
        assert stats.total_speed == 0
        assert stats.youtube_active == 0
        assert stats.torrent_active == 0
    
    @pytest.mark.asyncio
    async def test_get_download_stats_with_downloads(self, db_session):
        """Test getting stats with active downloads."""
        # Create test downloads
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        # Create active YouTube download
        dl = Download(
            video_id=video.id,
            source_type="youtube",
            status="downloading",
            download_rate=1024,
        )
        db_session.add(dl)
        
        # Create active torrent download
        torrent = TorrentDownload(
            infohash="test_hash",
            source_id="test_source",
            status="downloading",
            download_rate=2048,
        )
        db_session.add(torrent)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        stats = interface.get_download_stats()
        
        assert stats.active_count == 2
        assert stats.total_speed == 3072  # 1024 + 2048
        assert stats.youtube_active == 1
        assert stats.torrent_active == 1
        assert stats.youtube_speed == 1024
        assert stats.torrent_speed == 2048


class TestGetDownloadHistory:
    """Test get_download_history functionality."""
    
    @pytest.mark.asyncio
    async def test_get_download_history_empty(self, db_session):
        """Test getting history when no downloads exist."""
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        history = interface.get_download_history(limit=50)
        
        assert isinstance(history, list)
        assert len(history) == 0
    
    @pytest.mark.asyncio
    async def test_get_download_history_mixed(self, db_session):
        """Test getting history with both YouTube and torrent downloads."""
        # Create test video
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        # Create completed YouTube download
        dl = Download(
            video_id=video.id,
            source_type="youtube",
            status="completed",
            progress_percent=100.0,
        )
        db_session.add(dl)
        
        # Create completed torrent download
        torrent = TorrentDownload(
            infohash="test_hash",
            source_id="test_source",
            status="completed",
            progress=1.0,
        )
        db_session.add(torrent)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        history = interface.get_download_history(limit=50)
        
        assert len(history) == 2
        
        # Check both source types are present
        source_types = [d.source_type for d in history]
        assert "youtube" in source_types
        assert "torrent" in source_types
    
    @pytest.mark.asyncio
    async def test_get_download_history_limit(self, db_session):
        """Test that limit parameter is respected."""
        # Create multiple downloads
        for i in range(10):
            torrent = TorrentDownload(
                infohash=f"hash_{i}",
                source_id=f"source_{i}",
                status="completed",
            )
            db_session.add(torrent)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        # Get with limit
        history = interface.get_download_history(limit=5)
        
        assert len(history) == 5


class TestRetryVideoPerStage:
    """Test retry_video with per-stage support."""
    
    @pytest.mark.asyncio
    async def test_retry_invalid_stage(self, db_session):
        """Test retrying with an invalid stage."""
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = MagicMock()
        
        result = await interface.retry_video(video.id, stage="invalid_stage")
        
        assert isinstance(result, RetryResult)
        assert result.success is False
        assert "Invalid stage" in result.message
    
    @pytest.mark.asyncio
    async def test_retry_finds_failed_stage(self, db_session):
        """Test that retry finds the failed stage when stage is None."""
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        # Create a failed upload job
        from haven_cli.database.models import UploadJob
        upload_job = UploadJob(
            video_id=video.id,
            target="ipfs",
            status="failed",
            error_message="Upload failed",
        )
        db_session.add(upload_job)
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = AsyncMock()
        
        result = await interface.retry_video(video.id, stage=None)
        
        assert isinstance(result, RetryResult)
        assert result.success is True
        # Should retry from upload stage since it failed
        assert "upload" in result.message
    
    @pytest.mark.asyncio
    async def test_retry_resets_subsequent_stages(self, db_session):
        """Test that retry resets the specified stage and all following stages."""
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        # Create jobs at different stages
        from haven_cli.database.models import EncryptionJob, UploadJob, SyncJob
        
        encrypt_job = EncryptionJob(
            video_id=video.id,
            status="completed",
        )
        upload_job = UploadJob(
            video_id=video.id,
            target="ipfs",
            status="failed",
            error_message="Upload failed",
        )
        sync_job = SyncJob(
            video_id=video.id,
            status="completed",
        )
        db_session.add_all([encrypt_job, upload_job, sync_job])
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = AsyncMock()
        
        # Retry from upload stage
        result = await interface.retry_video(video.id, stage="upload")
        
        assert isinstance(result, RetryResult)
        assert result.success is True
        
        # Verify upload job was reset
        db_session.refresh(upload_job)
        assert upload_job.status == "pending"
        assert upload_job.error_message is None
        
        # Verify sync job was reset (subsequent stage)
        db_session.refresh(sync_job)
        assert sync_job.status == "pending"


class TestCancelVideo:
    """Test cancel_video functionality."""
    
    @pytest.mark.asyncio
    async def test_cancel_video_cancels_all_jobs(self, db_session):
        """Test that cancel_video cancels all active jobs."""
        video = Video(source_path="/test/video.mp4", title="Test Video")
        db_session.add(video)
        db_session.commit()
        
        # Create active jobs at different stages
        from haven_cli.database.models import (
            Download, EncryptionJob, UploadJob, SyncJob, AnalysisJob
        )
        
        download = Download(
            video_id=video.id,
            source_type="youtube",
            status="downloading",
        )
        encrypt_job = EncryptionJob(
            video_id=video.id,
            status="encrypting",
        )
        upload_job = UploadJob(
            video_id=video.id,
            target="ipfs",
            status="uploading",
        )
        sync_job = SyncJob(
            video_id=video.id,
            status="syncing",
        )
        analysis_job = AnalysisJob(
            video_id=video.id,
            analysis_type="vlm",
            status="analyzing",
        )
        db_session.add_all([
            download, encrypt_job, upload_job, sync_job, analysis_job
        ])
        db_session.commit()
        
        interface = PipelineInterface()
        interface._db_session = db_session
        interface._event_bus = AsyncMock()
        
        result = await interface.cancel_video(video.id)
        
        assert result is True
        
        # Verify all jobs were cancelled
        db_session.refresh(download)
        db_session.refresh(encrypt_job)
        db_session.refresh(upload_job)
        db_session.refresh(sync_job)
        db_session.refresh(analysis_job)
        
        assert download.status == "cancelled"
        assert encrypt_job.status == "cancelled"
        assert upload_job.status == "cancelled"
        assert sync_job.status == "cancelled"
        assert analysis_job.status == "cancelled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
