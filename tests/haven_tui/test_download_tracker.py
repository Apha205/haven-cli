"""Tests for the unified download progress interface.

Tests cover:
- DownloadStatus enum
- DownloadProgress dataclass
- DownloadProgressTracker service
- YouTubeProgressAdapter
- BitTorrentProgressAdapter
- Integration with database models and event bus
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

from haven_tui.data.download_tracker import (
    DownloadStatus,
    DownloadProgress,
    DownloadProgressTracker,
    YouTubeProgressAdapter,
    BitTorrentProgressAdapter,
    get_download_tracker,
    reset_download_tracker,
    format_bytes,
    format_duration,
)
from haven_cli.database.models import Download, Video, PipelineSnapshot
from haven_cli.pipeline.events import EventBus, EventType, Event


class TestFormatUtils:
    """Test formatting utilities."""
    
    def test_format_bytes_zero(self):
        """Test formatting zero bytes."""
        assert format_bytes(0) == "0 B"
    
    def test_format_bytes_bytes(self):
        """Test formatting bytes."""
        assert format_bytes(500) == "500.00 B"
    
    def test_format_bytes_kilobytes(self):
        """Test formatting kilobytes."""
        assert format_bytes(1536) == "1.50 KB"
    
    def test_format_bytes_megabytes(self):
        """Test formatting megabytes."""
        assert format_bytes(1572864) == "1.50 MB"
    
    def test_format_bytes_gigabytes(self):
        """Test formatting gigabytes."""
        assert format_bytes(1610612736) == "1.50 GB"
    
    def test_format_duration_negative(self):
        """Test formatting negative duration."""
        assert format_duration(-1) == "--:--"
    
    def test_format_duration_seconds_only(self):
        """Test formatting duration under a minute."""
        assert format_duration(45) == "00:45"
    
    def test_format_duration_minutes(self):
        """Test formatting duration in minutes."""
        assert format_duration(125) == "02:05"
    
    def test_format_duration_hours(self):
        """Test formatting duration with hours."""
        assert format_duration(3665) == "01:01:05"


class TestDownloadStatus:
    """Test DownloadStatus enum."""
    
    def test_enum_values(self):
        """Test that enum values are correct."""
        assert DownloadStatus.PENDING.value == "pending"
        assert DownloadStatus.QUEUED.value == "queued"
        assert DownloadStatus.DOWNLOADING.value == "downloading"
        assert DownloadStatus.PAUSED.value == "paused"
        assert DownloadStatus.VERIFYING.value == "verifying"
        assert DownloadStatus.COMPLETED.value == "completed"
        assert DownloadStatus.FAILED.value == "failed"
        assert DownloadStatus.STALLED.value == "stalled"


class TestDownloadProgress:
    """Test DownloadProgress dataclass."""
    
    def test_formatted_speed(self):
        """Test formatted speed property."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            download_rate=1572864,  # 1.5 MiB/s = 1.5 * 1024 * 1024
        )
        assert progress.formatted_speed == "1.50 MB/s"
    
    def test_basic_creation(self):
        """Test creating a basic DownloadProgress."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
        )
        assert progress.source_id == "test123"
        assert progress.source_type == "youtube"
        assert progress.status == DownloadStatus.PENDING
        assert not progress.is_active
    
    def test_is_active_downloading(self):
        """Test is_active when downloading."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            status=DownloadStatus.DOWNLOADING,
        )
        assert progress.is_active
    
    def test_is_active_pending(self):
        """Test is_active when pending."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            status=DownloadStatus.PENDING,
        )
        assert not progress.is_active
    
    def test_formatted_eta_none(self):
        """Test formatted ETA when None."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            eta_seconds=None,
        )
        assert progress.formatted_eta == "--:--"
    
    def test_formatted_eta_with_value(self):
        """Test formatted ETA with value."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            eta_seconds=3665,
        )
        assert progress.formatted_eta == "01:01:05"
    
    def test_formatted_size(self):
        """Test formatted size property."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            total_size=1073741824,  # 1 GB
        )
        assert progress.formatted_size == "1.00 GB"
    
    def test_formatted_downloaded(self):
        """Test formatted downloaded property."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            downloaded=536870912,  # 512 MB
        )
        assert progress.formatted_downloaded == "512.00 MB"
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            video_id=1,
            title="Test Video",
            total_size=1000000,
            downloaded=500000,
            progress_pct=50.0,
            download_rate=10000,
            status=DownloadStatus.DOWNLOADING,
        )
        d = progress.to_dict()
        assert d["source_id"] == "test123"
        assert d["source_type"] == "youtube"
        assert d["video_id"] == 1
        assert d["title"] == "Test Video"
        assert d["progress_pct"] == 50.0
        assert d["is_active"] is True
        assert d["status"] == "downloading"


class TestDownloadProgressTracker:
    """Test DownloadProgressTracker service."""
    
    @pytest.fixture
    def mock_event_bus(self):
        """Create a mock event bus."""
        bus = Mock(spec=EventBus)
        # Create a mock for the coroutine return
        async def mock_publish(*args, **kwargs):
            pass
        bus.publish = mock_publish
        return bus
    
    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)
        session.query = Mock(return_value=session)
        session.filter_by = Mock(return_value=session)
        session.order_by = Mock(return_value=session)
        session.first = Mock(return_value=None)
        session.commit = Mock()
        session.add = Mock()
        
        factory = Mock(return_value=session)
        return factory, session
    
    @pytest.fixture
    def tracker(self, mock_event_bus, mock_session_factory):
        """Create a DownloadProgressTracker with mocked dependencies."""
        factory, session = mock_session_factory
        # Configure session to return None for first() to simulate no existing download
        session.first.return_value = None
        return DownloadProgressTracker(
            event_bus=mock_event_bus,
            db_session_factory=factory,
            enable_events=True
        )
    
    def test_report_progress_caches_data(self, tracker):
        """Test that report_progress caches the progress data."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            video_id=1,
        )
        
        tracker.report_progress(progress)
        
        cached = tracker.get_progress("test123")
        assert cached is not None
        assert cached.source_id == "test123"
    
    def test_get_progress_not_found(self, tracker):
        """Test getting progress for non-existent source."""
        result = tracker.get_progress("nonexistent")
        assert result is None
    
    def test_get_all_active(self, tracker):
        """Test getting all active downloads."""
        # Add downloading progress
        downloading = DownloadProgress(
            source_id="active1",
            source_type="youtube",
            status=DownloadStatus.DOWNLOADING,
        )
        tracker.report_progress(downloading)
        
        # Add pending progress
        pending = DownloadProgress(
            source_id="pending1",
            source_type="youtube",
            status=DownloadStatus.PENDING,
        )
        tracker.report_progress(pending)
        
        active = tracker.get_all_active()
        assert len(active) == 1
        assert active[0].source_id == "active1"
    
    def test_get_all(self, tracker):
        """Test getting all tracked downloads."""
        for i in range(3):
            progress = DownloadProgress(
                source_id=f"test{i}",
                source_type="youtube",
            )
            tracker.report_progress(progress)
        
        all_downloads = tracker.get_all()
        assert len(all_downloads) == 3
    
    def test_remove_download(self, tracker):
        """Test removing a download from tracking."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
        )
        tracker.report_progress(progress)
        
        assert tracker.get_progress("test123") is not None
        
        removed = tracker.remove_download("test123")
        assert removed is True
        assert tracker.get_progress("test123") is None
    
    def test_remove_download_not_found(self, tracker):
        """Test removing a non-existent download."""
        removed = tracker.remove_download("nonexistent")
        assert removed is False
    
    def test_clear_cache(self, tracker):
        """Test clearing all cached data."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
        )
        tracker.report_progress(progress)
        
        assert len(tracker.get_all()) == 1
        
        tracker.clear_cache()
        
        assert len(tracker.get_all()) == 0
    
    def test_get_aggregate_stats(self, tracker):
        """Test getting aggregate statistics."""
        # Add active download
        active = DownloadProgress(
            source_id="active1",
            source_type="youtube",
            status=DownloadStatus.DOWNLOADING,
            download_rate=1000,
            upload_rate=500,
        )
        tracker.report_progress(active)
        
        # Add bittorrent download
        bt = DownloadProgress(
            source_id="bt1",
            source_type="bittorrent",
            status=DownloadStatus.DOWNLOADING,
            download_rate=2000,
            upload_rate=1000,
        )
        tracker.report_progress(bt)
        
        stats = tracker.get_aggregate_stats()
        
        assert stats["total_active"] == 2
        assert stats["total_download_speed"] == 3000
        assert stats["total_upload_speed"] == 1500
        assert stats["by_type"]["youtube"] == 1
        assert stats["by_type"]["bittorrent"] == 1
    
    def test_link_video_to_download(self, tracker):
        """Test linking a video to a download."""
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            video_id=None,
        )
        tracker.report_progress(progress)
        
        tracker.link_video_to_download("test123", 42)
        
        cached = tracker.get_progress("test123")
        assert cached.video_id == 42


class TestYouTubeProgressAdapter:
    """Test YouTube progress adapter."""
    
    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker."""
        return Mock(spec=DownloadProgressTracker)
    
    @pytest.fixture
    def adapter(self, mock_tracker):
        """Create a YouTube adapter."""
        return YouTubeProgressAdapter(
            tracker=mock_tracker,
            source_id="abc123",
            video_id=1,
            source_uri="https://youtube.com/watch?v=abc123",
            title="Test Video"
        )
    
    def test_from_ytdlp_progress_downloading(self, adapter):
        """Test converting yt-dlp downloading progress."""
        ytdlp_data = {
            "status": "downloading",
            "downloaded_bytes": 500000,
            "total_bytes": 1000000,
            "speed": 10000,
            "eta": 50,
            "filename": "test.mp4",
        }
        
        progress = adapter.from_ytdlp_progress(ytdlp_data)
        
        assert progress.source_id == "abc123"
        assert progress.source_type == "youtube"
        assert progress.video_id == 1
        assert progress.title == "Test Video"
        assert progress.status == DownloadStatus.DOWNLOADING
        assert progress.downloaded == 500000
        assert progress.total_size == 1000000
        assert progress.progress_pct == 50.0
        assert progress.download_rate == 10000
        assert progress.eta_seconds == 50
    
    def test_from_ytdlp_progress_finished(self, adapter):
        """Test converting yt-dlp finished progress."""
        ytdlp_data = {
            "status": "finished",
            "downloaded_bytes": 1000000,
            "total_bytes": 1000000,
            "filename": "test.mp4",
        }
        
        progress = adapter.from_ytdlp_progress(ytdlp_data)
        
        assert progress.status == DownloadStatus.COMPLETED
        assert progress.progress_pct == 100.0
    
    def test_from_ytdlp_progress_error(self, adapter):
        """Test converting yt-dlp error progress."""
        ytdlp_data = {
            "status": "error",
            "error": "Network error",
        }
        
        progress = adapter.from_ytdlp_progress(ytdlp_data)
        
        assert progress.status == DownloadStatus.FAILED
        assert progress.error_message == "Network error"
    
    def test_report(self, adapter, mock_tracker):
        """Test report convenience method."""
        ytdlp_data = {
            "status": "downloading",
            "downloaded_bytes": 500000,
            "total_bytes": 1000000,
        }
        
        adapter.report(ytdlp_data)
        
        mock_tracker.report_progress.assert_called_once()
        progress = mock_tracker.report_progress.call_args[0][0]
        assert progress.source_id == "abc123"


class TestBitTorrentProgressAdapter:
    """Test BitTorrent progress adapter."""
    
    @pytest.fixture
    def mock_tracker(self):
        """Create a mock tracker."""
        return Mock(spec=DownloadProgressTracker)
    
    @pytest.fixture
    def adapter(self, mock_tracker):
        """Create a BitTorrent adapter."""
        return BitTorrentProgressAdapter(
            tracker=mock_tracker,
            infohash="abc123def456",
            video_id=1,
            magnet_uri="magnet:?xt=urn:btih:abc123",
            title="Test Torrent"
        )
    
    def test_from_libtorrent_status_downloading(self, adapter):
        """Test converting libtorrent downloading status."""
        # Mock libtorrent status object
        status = Mock()
        status.is_finished = False
        status.paused = False
        status.errc = None
        status.progress = 0.5
        status.total_wanted = 1000000
        status.total_wanted_done = 500000
        status.download_rate = 50000
        status.upload_rate = 10000
        status.num_peers = 10
        status.num_seeds = 5
        
        progress = adapter.from_libtorrent_status(status)
        
        assert progress.source_id == "abc123def456"
        assert progress.source_type == "bittorrent"
        assert progress.status == DownloadStatus.DOWNLOADING
        assert progress.progress_pct == 50.0
        assert progress.connections == 10
        assert progress.seeds == 5
        assert progress.leechers == 5
    
    def test_from_libtorrent_status_finished(self, adapter):
        """Test converting libtorrent finished status."""
        status = Mock()
        status.is_finished = True
        status.paused = False
        status.errc = None
        status.progress = 1.0
        status.total_wanted = 1000000
        status.total_wanted_done = 1000000
        status.download_rate = 0
        status.upload_rate = 5000
        status.num_peers = 0
        status.num_seeds = 0
        
        progress = adapter.from_libtorrent_status(status)
        
        assert progress.status == DownloadStatus.COMPLETED
        assert progress.progress_pct == 100.0
    
    def test_from_libtorrent_status_paused(self, adapter):
        """Test converting libtorrent paused status."""
        status = Mock()
        status.is_finished = False
        status.paused = True
        status.errc = None
        status.progress = 0.3
        status.total_wanted = 1000000
        status.total_wanted_done = 300000
        status.download_rate = 0
        status.upload_rate = 0
        status.num_peers = 0
        status.num_seeds = 0
        
        progress = adapter.from_libtorrent_status(status)
        
        assert progress.status == DownloadStatus.PAUSED
    
    def test_from_dict(self, adapter):
        """Test converting from dictionary."""
        data = {
            "status": "downloading",
            "progress": 0.5,
            "total_size": 1000000,
            "downloaded_size": 500000,
            "download_rate": 50000,
            "upload_rate": 10000,
            "peers": 10,
            "seeds": 5,
            "title": "Updated Title",
        }
        
        progress = adapter.from_dict(data)
        
        assert progress.status == DownloadStatus.DOWNLOADING
        assert progress.progress_pct == 50.0
        assert progress.total_size == 1000000
        assert progress.title == "Updated Title"
    
    def test_report_status(self, adapter, mock_tracker):
        """Test report_status convenience method."""
        status = Mock()
        status.is_finished = False
        status.paused = False
        status.errc = None
        status.progress = 0.5
        status.total_wanted = 1000000
        status.total_wanted_done = 500000
        status.download_rate = 50000
        status.upload_rate = 10000
        status.num_peers = 10
        status.num_seeds = 5
        
        adapter.report_status(status)
        
        mock_tracker.report_progress.assert_called_once()
        progress = mock_tracker.report_progress.call_args[0][0]
        assert progress.source_id == "abc123def456"


class TestSingleton:
    """Test singleton functionality."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_download_tracker()
    
    def teardown_method(self):
        """Reset singleton after each test."""
        reset_download_tracker()
    
    def test_get_download_tracker_creates_instance(self):
        """Test that get_download_tracker creates an instance."""
        mock_event_bus = Mock(spec=EventBus)
        mock_factory = Mock()
        
        tracker = get_download_tracker(mock_event_bus, mock_factory)
        
        assert tracker is not None
        assert isinstance(tracker, DownloadProgressTracker)
    
    def test_get_download_tracker_returns_same_instance(self):
        """Test that get_download_tracker returns the same instance."""
        mock_event_bus = Mock(spec=EventBus)
        mock_factory = Mock()
        
        tracker1 = get_download_tracker(mock_event_bus, mock_factory)
        tracker2 = get_download_tracker()  # Should return same instance
        
        assert tracker1 is tracker2
    
    def test_get_download_tracker_requires_deps_first_time(self):
        """Test that get_download_tracker requires deps on first call."""
        with pytest.raises(ValueError, match="event_bus and db_session_factory required"):
            get_download_tracker()
    
    def test_reset_download_tracker(self):
        """Test reset_download_tracker."""
        mock_event_bus = Mock(spec=EventBus)
        mock_factory = Mock()
        
        tracker1 = get_download_tracker(mock_event_bus, mock_factory)
        reset_download_tracker()
        tracker2 = get_download_tracker(mock_event_bus, mock_factory)
        
        assert tracker1 is not tracker2


class TestIntegration:
    """Integration tests with real database session."""
    
    @pytest.fixture
    def event_bus(self):
        """Create a real event bus."""
        return EventBus()
    
    @pytest.fixture
    def db_engine(self, tmp_path):
        """Create a temporary database engine."""
        from sqlalchemy import create_engine
        from haven_cli.database.models import Base
        
        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        return engine
    
    @pytest.fixture
    def db_session(self, db_engine):
        """Create a temporary database session."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        return Session()
    
    @pytest.fixture
    def tracker(self, event_bus, db_engine):
        """Create tracker with real dependencies."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        def session_factory():
            return Session()
        
        return DownloadProgressTracker(
            event_bus=event_bus,
            db_session_factory=session_factory,
            enable_events=False  # Disable events for simpler tests
        )
    
    def test_persist_to_downloads_table(self, tracker, db_engine):
        """Test persisting progress to downloads table."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        # Create a video first
        with Session() as session:
            video = Video(
                source_path="/test/video.mp4",
                title="Test Video",
            )
            session.add(video)
            session.commit()
            video_id = video.id
        
        # Report progress
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            video_id=video_id,
            title="Test Video",
            total_size=1000000,
            downloaded=500000,
            progress_pct=50.0,
            download_rate=10000,
            status=DownloadStatus.DOWNLOADING,
        )
        tracker.report_progress(progress)
        
        # Verify in database
        with Session() as session:
            download = session.query(Download).filter_by(video_id=video_id).first()
            assert download is not None
            assert download.source_type == "youtube"
            assert download.status == "downloading"
            assert download.progress_percent == 50.0
            assert download.bytes_downloaded == 500000
            assert download.bytes_total == 1000000
    
    def test_update_pipeline_snapshot(self, tracker, db_engine):
        """Test updating pipeline snapshot."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        # Create a video first
        with Session() as session:
            video = Video(
                source_path="/test/video.mp4",
                title="Test Video",
            )
            session.add(video)
            session.commit()
            video_id = video.id
        
        # Report progress
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            video_id=video_id,
            title="Test Video",
            total_size=1000000,
            downloaded=500000,
            progress_pct=50.0,
            download_rate=10000,
            status=DownloadStatus.DOWNLOADING,
        )
        tracker.report_progress(progress)
        
        # Verify snapshot in database
        with Session() as session:
            snapshot = session.query(PipelineSnapshot).filter_by(video_id=video_id).first()
            assert snapshot is not None
            assert snapshot.current_stage == "download"
            assert snapshot.overall_status == "active"
            assert snapshot.stage_progress_percent == 50.0
            assert snapshot.stage_speed == 10000
            assert snapshot.downloaded_bytes == 500000
            assert snapshot.total_bytes == 1000000
    
    @pytest.mark.asyncio
    async def test_emit_progress_event(self, event_bus, db_engine):
        """Test emitting progress events."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        events_received = []
        
        async def handler(event):
            events_received.append(event)
        
        event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, handler)
        
        def session_factory():
            return Session()
        
        tracker = DownloadProgressTracker(
            event_bus=event_bus,
            db_session_factory=session_factory,
            enable_events=True
        )
        
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            video_id=1,
            status=DownloadStatus.DOWNLOADING,
        )
        
        tracker.report_progress(progress)
        
        # Give async event time to process
        await asyncio.sleep(0.1)
        
        assert len(events_received) == 1
        assert events_received[0].event_type == EventType.DOWNLOAD_PROGRESS
        assert events_received[0].payload["source_id"] == "test123"
