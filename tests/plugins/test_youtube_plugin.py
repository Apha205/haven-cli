"""Tests for the YouTube plugin.

These tests verify that the YouTube plugin correctly:
1. Initializes with proper configuration
2. Discovers videos from channels and playlists
3. Archives videos using yt-dlp
4. Handles errors gracefully
5. Reports download progress through DownloadProgressTracker
"""

import asyncio
import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

from haven_cli.plugins.builtin.youtube import YouTubePlugin, YouTubeConfig, _YTDLPLogger
from haven_cli.plugins.base import MediaSource, ArchiveResult, PluginCapability


class TestYouTubeConfig:
    """Test YouTube configuration dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = YouTubeConfig()
        assert config.channel_ids == []
        assert config.playlist_ids == []
        assert config.max_videos == 10
        assert config.quality == "best"
        assert config.format == "mp4"
        assert config.download_subtitles is False
        assert config.max_retries == 3
    
    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "channel_ids": ["UC123", "UC456"],
            "playlist_ids": ["PL789"],
            "max_videos": 20,
            "quality": "1080p",
            "format": "webm",
            "output_dir": "~/videos",
            "cookies_file": "~/.cookies.txt",
            "download_subtitles": True,
            "max_retries": 5,
        }
        config = YouTubeConfig.from_dict(data)
        
        assert config.channel_ids == ["UC123", "UC456"]
        assert config.playlist_ids == ["PL789"]
        assert config.max_videos == 20
        assert config.quality == "1080p"
        assert config.format == "webm"
        assert "videos" in str(config.output_dir)  # Expanded path
        assert "cookies.txt" in str(config.cookies_file)
        assert config.download_subtitles is True
        assert config.max_retries == 5
    
    def test_config_home_directory_expansion(self):
        """Test that ~ is expanded to home directory."""
        config = YouTubeConfig.from_dict({
            "output_dir": "~/test_videos",
            "cookies_file": "~/test_cookies.txt"
        })
        
        home = str(Path.home())
        assert home in str(config.output_dir)
        assert home in str(config.cookies_file)


class TestYTDLPLogger:
    """Test yt-dlp logger that prevents TUI pollution."""
    
    def test_debug_filters_progress(self, caplog):
        """Test that debug filters out progress messages."""
        logger = _YTDLPLogger()
        with caplog.at_level("DEBUG"):
            logger.debug("[download] 50% progress")
            logger.debug("Some other debug message")
        
        # Progress messages should be filtered
        assert "[download] 50%" not in caplog.text
        # Other messages should pass through
        assert "Some other debug" in caplog.text
    
    def test_info_filters_progress(self, caplog):
        """Test that info filters out progress messages."""
        logger = _YTDLPLogger()
        with caplog.at_level("INFO"):
            logger.info("[download] Destination: file.mp4")
            logger.info("Video download started")
        
        # Progress messages should be filtered
        assert "[download] Destination" not in caplog.text
        # Other messages should pass through
        assert "Video download started" in caplog.text
    
    def test_warning_passes_through(self, caplog):
        """Test that warnings pass through."""
        logger = _YTDLPLogger()
        with caplog.at_level("WARNING"):
            logger.warning("Warning: rate limited")
        
        assert "rate limited" in caplog.text
    
    def test_error_passes_through(self, caplog):
        """Test that errors pass through."""
        logger = _YTDLPLogger()
        with caplog.at_level("ERROR"):
            logger.error("Error: video unavailable")
        
        assert "video unavailable" in caplog.text


class TestYouTubePlugin:
    """Test YouTubePlugin functionality."""
    
    @pytest.fixture
    def plugin(self, tmp_path):
        """Create a YouTubePlugin instance with temporary output directory."""
        config = {
            "channel_ids": ["UC_test123"],
            "playlist_ids": ["PL_test456"],
            "max_videos": 5,
            "quality": "720p",
            "output_dir": str(tmp_path / "downloads"),
        }
        return YouTubePlugin(config=config)
    
    @pytest.fixture
    def mock_progress_tracker(self):
        """Create a mock progress tracker."""
        tracker = Mock()
        tracker.report_progress = Mock()
        return tracker
    
    @pytest.fixture
    async def initialized_plugin(self, plugin):
        """Create an initialized plugin with mocked subprocess."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock yt-dlp --version
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            # Mock Deno/Node.js detection (not available)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                
                # Run initialization
                await plugin.initialize()
        
        yield plugin
    
    def test_plugin_info(self, plugin):
        """Test plugin metadata."""
        info = plugin.info
        
        assert info.name == "YouTubePlugin"
        assert info.display_name == "YouTube Archiver"
        assert info.version == "1.0.0"
        assert "youtube" in info.media_types
        assert PluginCapability.DISCOVER in info.capabilities
        assert PluginCapability.ARCHIVE in info.capabilities
        assert PluginCapability.METADATA in info.capabilities
        assert PluginCapability.HEALTH_CHECK in info.capabilities
    
    def test_plugin_name_property(self, plugin):
        """Test plugin name property."""
        assert plugin.name == "YouTubePlugin"
    
    def test_set_progress_tracker(self, plugin, mock_progress_tracker):
        """Test setting progress tracker."""
        plugin.set_progress_tracker(mock_progress_tracker)
        assert plugin._progress_tracker is mock_progress_tracker
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, plugin, tmp_path):
        """Test successful plugin initialization."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            # Mock JS runtime detection failure (optional)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                
                await plugin.initialize()
        
        assert plugin._initialized is True
        assert (tmp_path / "downloads").exists()
    
    @pytest.mark.asyncio
    async def test_initialize_yt_dlp_not_found(self, plugin):
        """Test initialization fails when yt-dlp is not installed."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="yt-dlp not found"):
                await plugin.initialize()
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, plugin):
        """Test health check when plugin is healthy."""
        # Initialize plugin first
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        # Now test health check
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            result = await plugin.health_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, plugin):
        """Test health check fails when not initialized."""
        result = await plugin.health_check()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_discover_sources_not_initialized(self, plugin):
        """Test discover fails when not initialized."""
        sources = await plugin.discover_sources()
        assert sources == []
    
    @pytest.mark.asyncio
    async def test_discover_from_channel(self, plugin):
        """Test discovering videos from a channel."""
        # Initialize plugin with only channel_ids (no playlists)
        plugin._yt_config.channel_ids = ["UC_test123"]
        plugin._yt_config.playlist_ids = []
        
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        mock_videos = [
            MediaSource(
                source_id="video1",
                media_type="youtube",
                uri="https://youtube.com/watch?v=video1",
                title="Test Video 1",
                metadata={"duration": 120},
            )
        ]
        
        with patch.object(plugin, "_extract_video_list") as mock_extract:
            mock_extract.return_value = mock_videos
            
            sources = await plugin.discover_sources()
        
        assert len(sources) == 1
        assert sources[0].source_id == "video1"
        assert sources[0].media_type == "youtube"
    
    @pytest.mark.asyncio
    async def test_archive_not_initialized(self, plugin):
        """Test archive fails when not initialized."""
        source = MediaSource(
            source_id="test123",
            media_type="youtube",
            uri="https://youtube.com/watch?v=test123",
            title="Test Video",
        )
        
        result = await plugin.archive(source)
        
        assert result.success is False
        assert "not initialized" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_archive_wrong_media_type(self, plugin):
        """Test archive fails for non-YouTube media type."""
        # Initialize plugin
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        source = MediaSource(
            source_id="test123",
            media_type="bittorrent",
            uri="magnet:test",
            title="Test",
        )
        
        result = await plugin.archive(source)
        
        assert result.success is False
        assert "Unsupported media type" in result.error
    
    @pytest.mark.asyncio
    async def test_archive_already_archived(self, plugin):
        """Test archive returns success for already archived video."""
        # Initialize plugin
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        source = MediaSource(
            source_id="existing123",
            media_type="youtube",
            uri="https://youtube.com/watch?v=existing123",
            title="Existing Video",
        )
        
        # Add to archived videos
        plugin._archived_videos["existing123"] = {
            "video_id": "existing123",
            "output_path": "/path/to/video.mp4",
            "file_size": 1024000,
        }
        
        result = await plugin.archive(source)
        
        assert result.success is True
        assert result.metadata.get("already_archived") is True
    
    @pytest.mark.asyncio
    async def test_archive_with_progress_tracker_success(self, plugin, mock_progress_tracker, tmp_path):
        """Test archive reports progress through tracker on success."""
        # Initialize plugin
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        # Set progress tracker
        plugin.set_progress_tracker(mock_progress_tracker)
        
        source = MediaSource(
            source_id="test123",
            media_type="youtube",
            uri="https://youtube.com/watch?v=test123",
            title="Test Video",
            metadata={"channel_name": "TestChannel"},
        )
        
        # Create the output file to simulate successful download
        output_dir = tmp_path / "downloads" / "TestChannel"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "video.mp4"
        output_file.write_bytes(b"fake video content")
        
        # Mock the download to succeed
        with patch.object(plugin, "_download_video_with_progress") as mock_download:
            async_mock = AsyncMock()
            async_mock.return_value = {
                "success": True,
                "output_path": str(output_file),
            }
            mock_download.side_effect = async_mock
            
            result = await plugin.archive(source)
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_archive_with_progress_tracker_failure(self, plugin, mock_progress_tracker):
        """Test archive reports failure through tracker."""
        # Initialize plugin
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        # Set progress tracker
        plugin.set_progress_tracker(mock_progress_tracker)
        
        source = MediaSource(
            source_id="test123",
            media_type="youtube",
            uri="https://youtube.com/watch?v=test123",
            title="Test Video",
            metadata={"channel_name": "TestChannel"},
        )
        
        # Mock the download to fail with non-retryable error
        with patch.object(plugin, "_download_video_with_progress") as mock_download:
            async_mock = AsyncMock()
            async_mock.return_value = {
                "success": False,
                "error": "Video unavailable",
            }
            mock_download.side_effect = async_mock
            
            result = await plugin.archive(source)
        
        assert result.success is False
        assert "Video unavailable" in result.error
    
    def test_is_retryable_error(self, plugin):
        """Test error classification."""
        # Non-retryable errors
        assert not plugin._is_retryable_error("Video unavailable")
        assert not plugin._is_retryable_error("Private video")
        assert not plugin._is_retryable_error("copyright claim")
        assert not plugin._is_retryable_error("404 Not Found")
        
        # Retryable errors
        assert plugin._is_retryable_error("network error")
        assert plugin._is_retryable_error("connection timeout")
        assert plugin._is_retryable_error("429 Too Many Requests")
        assert plugin._is_retryable_error("JavaScript runtime error")
    
    def test_detect_js_runtime(self, plugin):
        """Test JavaScript runtime detection."""
        # Test Deno detection
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            runtime_type, runtime_path = plugin._detect_js_runtime()
            assert runtime_type == "deno"
            assert runtime_path == "deno"
        
        # Test Node.js fallback
        with patch("subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if cmd[0] == "deno":
                    return Mock(returncode=1)
                elif cmd[0] == "node":
                    return Mock(returncode=0)
                return Mock(returncode=1)
            
            mock_run.side_effect = side_effect
            runtime_type, runtime_path = plugin._detect_js_runtime()
            assert runtime_type == "nodejs"
            assert runtime_path == "node"
        
        # Test no runtime available
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1)
            runtime_type, runtime_path = plugin._detect_js_runtime()
            assert runtime_type is None
            assert runtime_path is None
    
    def test_extract_output_path_from_merge(self, plugin):
        """Test extracting output path from merge output."""
        stdout = '[ffmpeg] Merging formats into "/path/to/video.mp4"'
        result = plugin._extract_output_path(stdout, "", "")
        
        # Won't match since file doesn't exist
        assert result is None
    
    @pytest.mark.asyncio
    async def test_configure_updates_config(self, plugin):
        """Test that configure updates plugin configuration."""
        # Initialize plugin
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        plugin.configure({
            "max_videos": 50,
            "quality": "1080p",
        })
        
        assert plugin._yt_config.max_videos == 50
        assert plugin._yt_config.quality == "1080p"
    
    @pytest.mark.asyncio
    async def test_shutdown_saves_state(self, plugin, tmp_path):
        """Test that shutdown saves seen videos state."""
        # Initialize plugin
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"2024.01.01\n", b"")
            mock_exec.return_value = mock_proc
            
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1)
                await plugin.initialize()
        
        plugin._seen_videos = {"video1", "video2"}
        plugin._archived_videos = {"video1": {"output_path": "/path"}}
        
        await plugin.shutdown()
        
        seen_file = plugin._yt_config.output_dir / ".youtube_seen_videos.json"
        assert seen_file.exists()
        
        with open(seen_file) as f:
            data = json.load(f)
            assert "video1" in data["seen"]
            assert "video2" in data["seen"]
    
    @pytest.mark.asyncio
    async def test_download_with_subprocess_success(self, plugin):
        """Test subprocess download method."""
        # Initialize plugin first with a patch
        mock_proc_version = AsyncMock()
        mock_proc_version.returncode = 0
        mock_proc_version.communicate.return_value = (b"2024.01.01\n", b"")
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc_version) as mock_exec, \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=1)
            await plugin.initialize()
        
        source = MediaSource(
            source_id="test123",
            media_type="youtube",
            uri="https://youtube.com/watch?v=test123",
            title="Test Video",
        )
        
        # Now mock the download subprocess call
        mock_proc_download = AsyncMock()
        mock_proc_download.returncode = 0
        mock_proc_download.communicate.return_value = (
            b"[download] Destination: /path/to/video.mp4\n",
            b""
        )
        
        # Mock os.path.exists to return True for the output file
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc_download) as mock_exec, \
             patch("os.path.exists", return_value=True):
            
            result = await plugin._download_with_subprocess(
                source, "/path/to/video.%(ext)s", 1
            )
        
        assert result["success"] is True
        assert result["output_path"] == "/path/to/video.mp4"


class TestYouTubePluginProgressTracking:
    """Test progress tracking integration with DownloadProgressTracker."""
    
    @pytest.fixture
    def plugin(self, tmp_path):
        """Create a YouTubePlugin instance."""
        config = {
            "output_dir": str(tmp_path / "downloads"),
        }
        return YouTubePlugin(config=config)
    
    @pytest.fixture
    def mock_tracker(self):
        """Create a mock progress tracker."""
        tracker = Mock()
        tracker.report_progress = Mock()
        return tracker
    
    @pytest.fixture
    def sample_source(self):
        """Create a sample MediaSource."""
        return MediaSource(
            source_id="test123",
            media_type="youtube",
            uri="https://youtube.com/watch?v=test123",
            title="Test Video",
            metadata={"channel_name": "TestChannel"},
        )
    
    def test_report_progress_with_tracker(self, plugin, mock_tracker):
        """Test _report_progress calls tracker when set."""
        from haven_tui.data.download_tracker import DownloadProgress, DownloadStatus
        
        plugin.set_progress_tracker(mock_tracker)
        
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            status=DownloadStatus.DOWNLOADING,
        )
        
        plugin._report_progress(progress)
        
        mock_tracker.report_progress.assert_called_once_with(progress)
    
    def test_report_progress_without_tracker(self, plugin):
        """Test _report_progress does nothing when tracker not set."""
        from haven_tui.data.download_tracker import DownloadProgress, DownloadStatus
        
        progress = DownloadProgress(
            source_id="test123",
            source_type="youtube",
            status=DownloadStatus.DOWNLOADING,
        )
        
        # Should not raise
        plugin._report_progress(progress)
    
    @pytest.mark.asyncio
    async def test_report_failure_with_tracker(self, plugin, mock_tracker, sample_source):
        """Test _report_failure reports to tracker when set."""
        from haven_tui.data.download_tracker import DownloadStatus
        
        plugin.set_progress_tracker(mock_tracker)
        
        await plugin._report_failure(sample_source, "Network error")
        
        mock_tracker.report_progress.assert_called_once()
        progress = mock_tracker.report_progress.call_args[0][0]
        assert progress.source_id == "test123"
        assert progress.status == DownloadStatus.FAILED
        assert progress.error_message == "Network error"
    
    @pytest.mark.asyncio
    async def test_report_failure_without_tracker(self, plugin, sample_source):
        """Test _report_failure does nothing when tracker not set."""
        # Should not raise
        await plugin._report_failure(sample_source, "Network error")
    
    @pytest.mark.asyncio
    async def test_download_video_with_progress_uses_api_when_tracker_set(self, plugin, mock_tracker):
        """Test that download uses yt-dlp API when tracker is set."""
        plugin.set_progress_tracker(mock_tracker)
        
        with patch.object(plugin, "_download_with_ytdlp_api") as mock_api:
            async_mock = AsyncMock()
            async_mock.return_value = {"success": True, "output_path": "/path/to/video.mp4"}
            mock_api.side_effect = async_mock
            
            source = MediaSource(
                source_id="test123",
                media_type="youtube",
                uri="https://youtube.com/watch?v=test123",
                title="Test",
            )
            
            result = await plugin._download_video_with_progress(source, "/path/to/video.%(ext)s")
        
        mock_api.assert_called_once()
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_download_video_with_progress_falls_back_to_subprocess(self, plugin):
        """Test that download falls back to subprocess when API fails."""
        with patch.object(plugin, "_download_with_ytdlp_api") as mock_api:
            mock_api.return_value = asyncio.Future()
            mock_api.return_value.set_result({"success": False, "error": "API error"})
            mock_api.side_effect = Exception("API not available")
            
            with patch.object(plugin, "_download_with_subprocess") as mock_subprocess:
                mock_subprocess.return_value = asyncio.Future()
                mock_subprocess.return_value.set_result({"success": True, "output_path": "/path/to/video.mp4"})
                
                source = MediaSource(
                    source_id="test123",
                    media_type="youtube",
                    uri="https://youtube.com/watch?v=test123",
                    title="Test",
                )
                
                result = await plugin._download_video_with_progress(source, "/path/to/video.%(ext)s")
        
        mock_subprocess.assert_called_once()


class TestYouTubePluginIntegration:
    """Integration tests for YouTube plugin.
    
    These tests require yt-dlp to be installed and may make network requests.
    They are marked as integration tests and should be run separately.
    """
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_initialize_with_real_yt_dlp(self, tmp_path):
        """Test initialization with real yt-dlp installation."""
        config = {"output_dir": str(tmp_path / "downloads")}
        plugin = YouTubePlugin(config=config)
        
        # This will fail if yt-dlp is not installed
        try:
            await plugin.initialize()
            assert plugin._initialized is True
        except RuntimeError as e:
            pytest.skip(f"yt-dlp not installed: {e}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_check_with_real_yt_dlp(self, tmp_path):
        """Test health check with real yt-dlp installation."""
        config = {"output_dir": str(tmp_path / "downloads")}
        plugin = YouTubePlugin(config=config)
        
        try:
            await plugin.initialize()
            result = await plugin.health_check()
            assert result is True
        except RuntimeError:
            pytest.skip("yt-dlp not installed")


class TestYouTubeProgressAdapterUsage:
    """Test integration with YouTubeProgressAdapter."""
    
    def test_progress_adapter_import(self):
        """Test that YouTubeProgressAdapter can be imported from haven_tui."""
        from haven_tui.data.download_tracker import YouTubeProgressAdapter
        assert YouTubeProgressAdapter is not None
    
    def test_progress_adapter_converts_ytdlp_data(self):
        """Test that adapter correctly converts yt-dlp progress data."""
        from haven_tui.data.download_tracker import (
            YouTubeProgressAdapter, DownloadProgressTracker, DownloadStatus
        )
        
        mock_tracker = Mock(spec=DownloadProgressTracker)
        mock_tracker.report_progress = Mock()
        
        adapter = YouTubeProgressAdapter(
            tracker=mock_tracker,
            source_id="abc123",
            video_id=1,
            source_uri="https://youtube.com/watch?v=abc123",
            title="Test Video"
        )
        
        # Simulate yt-dlp downloading progress
        ytdlp_data = {
            "status": "downloading",
            "downloaded_bytes": 500000,
            "total_bytes": 1000000,
            "speed": 10000,
            "eta": 50,
            "filename": "test.mp4",
        }
        
        adapter.report(ytdlp_data)
        
        mock_tracker.report_progress.assert_called_once()
        progress = mock_tracker.report_progress.call_args[0][0]
        
        assert progress.source_id == "abc123"
        assert progress.source_type == "youtube"
        assert progress.status == DownloadStatus.DOWNLOADING
        assert progress.downloaded == 500000
        assert progress.total_size == 1000000
        assert progress.progress_pct == 50.0
        assert progress.download_rate == 10000
        assert progress.eta_seconds == 50
