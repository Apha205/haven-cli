"""Tests for BitTorrent plugin."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from haven_cli.plugins.builtin.bittorrent import BitTorrentPlugin, BitTorrentConfig
from haven_cli.plugins.base import MediaSource


class TestBitTorrentConfig:
    """Tests for BitTorrentConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = BitTorrentConfig()
        assert config.download_dir == "downloads/bittorrent"
        assert config.max_concurrent_downloads == 3
        assert config.max_download_speed == 0
        assert config.max_upload_speed == 0
        assert config.seed_ratio == 0.0
        assert config.seed_time == 0
        assert len(config.video_extensions) > 0
        assert config.min_video_size == 10 * 1024 * 1024
        assert config.max_video_size == 50 * 1024 * 1024 * 1024
        assert config.sources == []
        assert config.enabled is True
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        config = BitTorrentConfig.from_dict({
            "download_dir": "/tmp/torrents",
            "max_concurrent_downloads": 5,
            "max_download_speed": 1024 * 1024,
            "sources": [
                {
                    "name": "test",
                    "type": "forum",
                    "domain": "example.com",
                    "forum_id": "1",
                }
            ],
        })
        assert config.download_dir == "/tmp/torrents"
        assert config.max_concurrent_downloads == 5
        assert config.max_download_speed == 1024 * 1024
        assert len(config.sources) == 1
        assert config.sources[0]["name"] == "test"


class TestBitTorrentPlugin:
    """Tests for BitTorrentPlugin."""
    
    def test_plugin_info(self):
        """Test plugin information."""
        plugin = BitTorrentPlugin()
        info = plugin.info
        
        assert info.name == "bittorrent"
        assert info.display_name == "BitTorrent Archiver"
        assert info.version == "1.0.0"
        assert "libtorrent" in info.description.lower()
        assert info.author == "Haven Team"
        assert "bittorrent" in info.media_types
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_initialize_without_sources(self, mock_lt):
        """Test initialization without sources."""
        mock_lt.version = "2.0.11"
        mock_lt.session.return_value = Mock()
        
        plugin = BitTorrentPlugin(config={"sources": []})
        
        # Should not raise an error
        plugin.initialize()
        
        assert plugin._initialized is True
        mock_lt.session.assert_called_once()
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_initialize_with_forum_source(self, mock_lt):
        """Test initialization with forum source."""
        mock_lt.version = "2.0.11"
        mock_lt.session.return_value = Mock()
        
        plugin = BitTorrentPlugin(config={
            "sources": [
                {
                    "name": "test_forum",
                    "type": "forum",
                    "domain": "example.com",
                    "forum_id": "1",
                    "enabled": True,
                }
            ]
        })
        
        # Mock the ForumScraperSource
        with patch('haven_cli.plugins.builtin.bittorrent.plugin.ForumScraperSource') as mock_source_class:
            mock_source = Mock()
            mock_source.name = "test_forum"
            mock_source.enabled = True
            mock_source_class.return_value = mock_source
            
            plugin.initialize()
            
            assert plugin._initialized is True
            assert len(plugin._sources) == 1
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_discover_sources(self, mock_lt):
        """Test discovering sources."""
        mock_lt.version = "2.0.11"
        mock_lt.session.return_value = Mock()
        
        plugin = BitTorrentPlugin(config={"sources": []})
        plugin.initialize()
        
        # Should return empty list when no sources configured
        sources = plugin.discover_sources()
        assert sources == []
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_already_archived(self, mock_lt):
        """Test archiving an already archived torrent."""
        mock_lt.version = "2.0.11"
        mock_lt.session.return_value = Mock()
        
        plugin = BitTorrentPlugin(config={"sources": []})
        plugin.initialize()
        
        # Mark a torrent as already archived
        infohash = "a" * 40
        plugin._archived_torrents[infohash] = {
            "infohash": infohash,
            "output_path": "/path/to/file.mp4",
            "file_size": 1024 * 1024,
        }
        
        source = MediaSource(
            source_id=infohash,
            media_type="bittorrent",
            uri=f"magnet:?xt=urn:btih:{infohash}",
            title="Test Torrent",
        )
        
        result = plugin.archive(source)
        
        assert result.success is True
        assert result.output_path == "/path/to/file.mp4"
        assert result.file_size == 1024 * 1024
        assert result.metadata.get("already_archived") is True
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_archive_unsupported_media_type(self, mock_lt):
        """Test archiving unsupported media type."""
        mock_lt.version = "2.0.11"
        mock_lt.session.return_value = Mock()
        
        plugin = BitTorrentPlugin(config={"sources": []})
        plugin.initialize()
        
        source = MediaSource(
            source_id="test",
            media_type="youtube",
            uri="https://youtube.com/watch?v=test",
            title="Test",
        )
        
        result = plugin.archive(source)
        
        assert result.success is False
        assert "Unsupported media type" in result.error
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_health_check(self, mock_lt):
        """Test health check."""
        mock_lt.version = "2.0.11"
        mock_lt.session.return_value = Mock()
        
        plugin = BitTorrentPlugin(config={"sources": []})
        plugin.initialize()
        
        # Should return True when initialized
        assert plugin.health_check() is True
    
    def test_health_check_not_initialized(self):
        """Test health check when not initialized."""
        plugin = BitTorrentPlugin()
        
        # Should return False when not initialized
        assert plugin.health_check() is False
    
    @patch('haven_cli.plugins.builtin.bittorrent.plugin.lt')
    def test_shutdown(self, mock_lt):
        """Test plugin shutdown."""
        mock_lt.version = "2.0.11"
        mock_session = Mock()
        mock_lt.session.return_value = mock_session
        
        plugin = BitTorrentPlugin(config={"sources": []})
        plugin.initialize()
        
        # Add a mock active download
        mock_handle = Mock()
        plugin._active_downloads["test"] = mock_handle
        
        plugin.shutdown()
        
        assert plugin._initialized is False
        assert len(plugin._active_downloads) == 0
    
    def test_configure(self):
        """Test updating plugin configuration."""
        plugin = BitTorrentPlugin()
        
        new_config = {
            "download_dir": "/new/path",
            "max_concurrent_downloads": 10,
        }
        
        plugin.configure(new_config)
        
        assert plugin._bt_config.download_dir == "/new/path"
        assert plugin._bt_config.max_concurrent_downloads == 10
    
    def test_get_config(self):
        """Test getting plugin configuration."""
        plugin = BitTorrentPlugin(config={
            "download_dir": "/test/path",
            "max_concurrent_downloads": 5,
        })
        
        config = plugin.get_config()
        
        assert config["download_dir"] == "/test/path"
        assert config["max_concurrent_downloads"] == 5
        assert "video_extensions" in config
        assert "sources" in config
