"""Tests for BitTorrent progress bridge.

Tests cover:
- BitTorrentProgressBridge initialization and lifecycle
- Polling and syncing torrent downloads
- Converting TorrentDownload to DownloadProgress
- Real-time alert handling
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

from haven_tui.data.torrent_bridge import BitTorrentProgressBridge
from haven_tui.data.download_tracker import (
    DownloadStatus,
    DownloadProgress,
    DownloadProgressTracker,
)
from haven_cli.database.models import TorrentDownload, Video


class TestBitTorrentProgressBridge:
    """Test BitTorrent progress bridge."""
    
    @pytest.fixture
    def mock_tracker(self):
        """Create a mock progress tracker."""
        return Mock(spec=DownloadProgressTracker)
    
    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        session = MagicMock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)
        session.query = Mock(return_value=session)
        session.filter = Mock(return_value=session)
        session.filter_by = Mock(return_value=session)
        session.all = Mock(return_value=[])
        session.first = Mock(return_value=None)
        session.commit = Mock()
        
        factory = Mock(return_value=session)
        return factory, session
    
    @pytest.fixture
    def bridge(self, mock_tracker, mock_session_factory):
        """Create a BitTorrentProgressBridge with mocked dependencies."""
        factory, _ = mock_session_factory
        return BitTorrentProgressBridge(
            tracker=mock_tracker,
            db_session_factory=factory,
            poll_interval=0.1,  # Fast polling for tests
        )
    
    @pytest.mark.asyncio
    async def test_start_stop(self, bridge):
        """Test starting and stopping the bridge."""
        # Should not be polling initially
        assert bridge._polling is False
        
        # Start the bridge
        await bridge.start()
        assert bridge._polling is True
        assert bridge._poll_task is not None
        
        # Stop the bridge
        await bridge.stop()
        assert bridge._polling is False
        assert bridge._poll_task is None
    
    @pytest.mark.asyncio
    async def test_double_start(self, bridge):
        """Test starting an already started bridge."""
        await bridge.start()
        
        # Should not raise error or create duplicate task
        await bridge.start()
        assert bridge._polling is True
        
        await bridge.stop()
    
    @pytest.mark.asyncio
    async def test_stop_not_started(self, bridge):
        """Test stopping a bridge that was never started."""
        # Should not raise error
        await bridge.stop()
        assert bridge._polling is False
    
    @pytest.mark.asyncio
    async def test_sync_active_torrents(self, bridge, mock_session_factory, mock_tracker):
        """Test syncing active torrents."""
        factory, session = mock_session_factory
        
        # Create mock torrent
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000
        torrent.progress = 0.5
        torrent.download_rate = 1000
        torrent.upload_rate = 500
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        session.all.return_value = [torrent]
        
        # Sync torrents
        await bridge._sync_active_torrents()
        
        # Verify tracker was called
        assert mock_tracker.report_progress.called
        progress = mock_tracker.report_progress.call_args[0][0]
        assert progress.source_id == "abc123"
        assert progress.source_type == "bittorrent"
        assert progress.status == DownloadStatus.DOWNLOADING
    
    @pytest.mark.asyncio
    async def test_sync_skips_unchanged(self, bridge, mock_session_factory, mock_tracker):
        """Test that unchanged torrents are not reported."""
        factory, session = mock_session_factory
        
        now = datetime.now(timezone.utc)
        
        # Create mock torrent
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000
        torrent.progress = 0.5
        torrent.download_rate = 1000
        torrent.upload_rate = 500
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = now
        torrent.last_activity = now
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        session.all.return_value = [torrent]
        
        # First sync - should report
        await bridge._sync_active_torrents()
        assert mock_tracker.report_progress.call_count == 1
        
        # Second sync without changes - should not report again
        await bridge._sync_active_torrents()
        assert mock_tracker.report_progress.call_count == 1  # Still 1
    
    def test_torrent_to_progress_downloading(self, bridge, mock_session_factory):
        """Test converting a downloading torrent."""
        factory, session = mock_session_factory
        
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000
        torrent.progress = 0.5
        torrent.download_rate = 1000
        torrent.upload_rate = 500
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        progress = bridge._torrent_to_progress(torrent, session)
        
        assert progress.source_id == "abc123"
        assert progress.source_type == "bittorrent"
        assert progress.title == "Test Torrent"
        assert progress.status == DownloadStatus.DOWNLOADING
        assert progress.total_size == 1000000
        assert progress.downloaded == 500000
        assert progress.progress_pct == 50.0
        assert progress.download_rate == 1000.0
        assert progress.upload_rate == 500.0
        assert progress.connections == 10
        assert progress.seeds == 5
        assert progress.leechers == 5
    
    def test_torrent_to_progress_paused(self, bridge, mock_session_factory):
        """Test converting a paused torrent."""
        factory, session = mock_session_factory
        
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "paused"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 300000
        torrent.progress = 0.3
        torrent.download_rate = 0
        torrent.upload_rate = 0
        torrent.peers = 0
        torrent.seeds = 0
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        progress = bridge._torrent_to_progress(torrent, session)
        
        assert progress.status == DownloadStatus.PAUSED
        assert progress.progress_pct == 30.0
    
    def test_torrent_to_progress_stalled(self, bridge, mock_session_factory):
        """Test converting a stalled torrent."""
        factory, session = mock_session_factory
        
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "stalled"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 100000
        torrent.progress = 0.1
        torrent.download_rate = 0
        torrent.upload_rate = 0
        torrent.peers = 0
        torrent.seeds = 0
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = "Stalled for 300s"
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        progress = bridge._torrent_to_progress(torrent, session)
        
        assert progress.status == DownloadStatus.STALLED
        assert progress.error_message == "Stalled for 300s"
    
    def test_torrent_to_progress_with_video(self, bridge, mock_session_factory):
        """Test converting a torrent with associated video."""
        factory, session = mock_session_factory
        
        # Create mock video
        video = Mock(spec=Video)
        video.id = 42
        session.first.return_value = video
        
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000
        torrent.progress = 0.5
        torrent.download_rate = 1000
        torrent.upload_rate = 500
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = "/downloads/video.mp4"
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = "base64data"
        
        progress = bridge._torrent_to_progress(torrent, session)
        
        assert progress.video_id == 42
        assert progress.metadata["save_path"] == "/downloads/video.mp4"
        assert progress.metadata["resume_data_available"] is True
    
    def test_torrent_to_progress_eta_calculation(self, bridge, mock_session_factory):
        """Test ETA calculation."""
        factory, session = mock_session_factory
        
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000  # 500KB remaining
        torrent.progress = 0.5
        torrent.download_rate = 1000  # 1KB/s
        torrent.upload_rate = 0
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        progress = bridge._torrent_to_progress(torrent, session)
        
        # 500000 bytes remaining at 1000 bytes/sec = 500 seconds
        assert progress.eta_seconds == 500
    
    def test_on_torrent_alert(self, bridge, mock_session_factory, mock_tracker):
        """Test handling libtorrent alerts."""
        factory, session = mock_session_factory
        
        # Create mock torrent
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 600000
        torrent.progress = 0.6
        torrent.download_rate = 2000
        torrent.upload_rate = 1000
        torrent.peers = 15
        torrent.seeds = 8
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        session.filter_by.return_value.first.return_value = torrent
        
        # Simulate alert with progress update
        alert_data = {
            "progress": 0.7,
            "download_rate": 3000,
            "upload_rate": 1500,
            "peers": 20,
            "seeds": 10,
            "downloaded_size": 700000,
        }
        
        bridge.on_torrent_alert("abc123", alert_data)
        
        # Verify torrent was updated
        assert torrent.progress == 0.7
        assert torrent.download_rate == 3000
        
        # Verify tracker was called
        assert mock_tracker.report_progress.called
    
    @pytest.mark.asyncio
    async def test_sync_torrent_manual(self, bridge, mock_session_factory, mock_tracker):
        """Test manually syncing a specific torrent."""
        factory, session = mock_session_factory
        
        # Create mock torrent
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123"
        torrent.status = "downloading"
        torrent.title = "Test Torrent"
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000
        torrent.progress = 0.5
        torrent.download_rate = 1000
        torrent.upload_rate = 500
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        session.filter_by.return_value.first.return_value = torrent
        
        progress = await bridge.sync_torrent("abc123")
        
        assert progress is not None
        assert progress.source_id == "abc123"
        assert mock_tracker.report_progress.called
    
    @pytest.mark.asyncio
    async def test_sync_torrent_not_found(self, bridge, mock_session_factory, mock_tracker):
        """Test syncing a non-existent torrent."""
        factory, session = mock_session_factory
        session.filter_by.return_value.first.return_value = None
        
        progress = await bridge.sync_torrent("nonexistent")
        
        assert progress is None
    
    def test_clear_cache(self, bridge):
        """Test clearing the last update cache."""
        # Add some cached data
        bridge._last_update["abc123"] = datetime.now(timezone.utc)
        bridge._last_update["def456"] = datetime.now(timezone.utc)
        
        assert len(bridge._last_update) == 2
        
        bridge.clear_cache()
        
        assert len(bridge._last_update) == 0
    
    @pytest.mark.asyncio
    async def test_poll_loop_error_recovery(self, bridge, mock_session_factory):
        """Test that poll loop recovers from errors."""
        factory, session = mock_session_factory
        
        # Make query raise exception first time, succeed second time
        call_count = 0
        def raise_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Database error")
            return session
        
        session.query.side_effect = raise_once
        
        # Start bridge briefly - should not crash
        await bridge.start()
        await asyncio.sleep(0.3)  # Wait for at least one error and recovery
        await bridge.stop()
    
    def test_torrent_to_progress_default_title(self, bridge, mock_session_factory):
        """Test that infohash prefix is used when title is empty."""
        factory, session = mock_session_factory
        
        torrent = Mock(spec=TorrentDownload)
        torrent.infohash = "abc123def456"
        torrent.status = "downloading"
        torrent.title = None  # No title
        torrent.magnet_uri = "magnet:?xt=urn:btih:abc123"
        torrent.total_size = 1000000
        torrent.downloaded_size = 500000
        torrent.progress = 0.5
        torrent.download_rate = 1000
        torrent.upload_rate = 500
        torrent.peers = 10
        torrent.seeds = 5
        torrent.started_at = datetime.now(timezone.utc)
        torrent.last_activity = datetime.now(timezone.utc)
        torrent.output_path = None
        torrent.error_message = None
        torrent.selected_file_index = 0
        torrent.source_id = "source123"
        torrent.resume_data = None
        
        progress = bridge._torrent_to_progress(torrent, session)
        
        assert progress.title == "abc123def456"[:16]
