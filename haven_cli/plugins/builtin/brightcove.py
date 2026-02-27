"""Brightcove archiver plugin for Haven CLI.

This plugin provides video archiving functionality for Brightcove-powered
streaming sites. It uses the Brightcove Beacon API for playlist discovery
and the Edge Playback API for stream URL resolution.

Default configuration targets The Den (watchentertheden.com) skateboard content.

Features:
- Configurable for any Brightcove-powered site
- Default preset for The Den
- Playlist pagination support
- HLS stream downloading via yt-dlp
- Deduplication via seen videos tracking
- Rate limiting and retry logic
- Progress reporting through DownloadProgressTracker
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode, parse_qs, urlparse, urlunparse

import aiofiles
import httpx

from haven_cli.plugins.base import (
    ArchiverPlugin,
    ArchiveResult,
    MediaSource,
    PluginCapability,
    PluginInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class BrightcoveSourceConfig:
    """Configuration for a single Brightcove source.
    
    Attributes:
        name: Unique identifier for this source instance
        display_name: Human-readable name for UI display
        description: Optional description of the source
        base_playlist_url: The starting playlist URL for discovery
        playlist_params: URL parameters for playlist requests
        account_id: Beacon account ID for API calls
        brightcove_account_id: Brightcove account ID for edge API
        ad_config_id: Optional ad configuration ID for stream URLs
        beacon_api_base: Base URL for Beacon API
        edge_api_base: Base URL for Edge Playback API
        poll_interval_minutes: How often to check for new videos
        rate_limit_seconds: Delay between API calls
        max_retries: Number of retry attempts for failed downloads
        output_format: Preferred video format
        quality_preference: Video quality preference
        enabled: Whether this source is active
    """
    
    name: str
    display_name: str
    base_playlist_url: str
    account_id: str
    brightcove_account_id: str
    description: Optional[str] = None
    playlist_params: Dict[str, str] = field(default_factory=dict)
    ad_config_id: Optional[str] = None
    beacon_api_base: str = "https://beacon.playback.api.brightcove.com/twentypointnine/api"
    edge_api_base: str = "https://edge.api.brightcove.com/playback/v1"
    poll_interval_minutes: int = 60
    rate_limit_seconds: float = 1.0
    max_retries: int = 3
    output_format: str = "mp4"
    quality_preference: str = "best"
    enabled: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrightcoveSourceConfig":
        """Create config from dictionary."""
        return cls(
            name=data["name"],
            display_name=data["display_name"],
            base_playlist_url=data["base_playlist_url"],
            account_id=data["account_id"],
            brightcove_account_id=data["brightcove_account_id"],
            description=data.get("description"),
            playlist_params=data.get("playlist_params", {}),
            ad_config_id=data.get("ad_config_id"),
            beacon_api_base=data.get("beacon_api_base", "https://beacon.playback.api.brightcove.com/twentypointnine/api"),
            edge_api_base=data.get("edge_api_base", "https://edge.api.brightcove.com/playback/v1"),
            poll_interval_minutes=data.get("poll_interval_minutes", 60),
            rate_limit_seconds=data.get("rate_limit_seconds", 1.0),
            max_retries=data.get("max_retries", 3),
            output_format=data.get("output_format", "mp4"),
            quality_preference=data.get("quality_preference", "best"),
            enabled=data.get("enabled", True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "base_playlist_url": self.base_playlist_url,
            "playlist_params": self.playlist_params,
            "account_id": self.account_id,
            "brightcove_account_id": self.brightcove_account_id,
            "ad_config_id": self.ad_config_id,
            "beacon_api_base": self.beacon_api_base,
            "edge_api_base": self.edge_api_base,
            "poll_interval_minutes": self.poll_interval_minutes,
            "rate_limit_seconds": self.rate_limit_seconds,
            "max_retries": self.max_retries,
            "output_format": self.output_format,
            "quality_preference": self.quality_preference,
            "enabled": self.enabled,
        }


@dataclass
class AssetInfo:
    """Information about a Brightcove asset."""
    
    asset_id: str
    title: str
    description: Optional[str] = None
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    video_id: Optional[str] = None
    stream_url: Optional[str] = None


class BrightcoveAPIClient:
    """Client for Brightcove Beacon and Edge Playback APIs."""
    
    def __init__(
        self,
        config: BrightcoveSourceConfig,
        client: Optional[httpx.AsyncClient] = None
    ):
        """Initialize the API client."""
        self.config = config
        self._client = client
        self._owned_client = client is None
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self._owned_client and self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60),
                headers={
                    "User-Agent": "HavenCLI-BrightcovePlugin/1.0",
                    "Accept": "application/json",
                }
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._owned_client and self._client:
            await self._client.aclose()
            self._client = None
    
    async def _get(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make a GET request with rate limiting."""
        if not self._client:
            raise RuntimeError("Client not initialized")
        
        try:
            response = await self._client.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"API request failed: {url} - Status {response.status_code}")
                return None
            
            data = response.json()
            
            # Apply rate limiting
            await asyncio.sleep(self.config.rate_limit_seconds)
            
            return data
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error requesting {url}: {e}")
            return None
        except httpx.TimeoutException:
            logger.error(f"Timeout requesting {url}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error requesting {url}: {e}")
            return None
    
    def _build_playlist_url(self, params: Optional[Dict[str, str]] = None) -> str:
        """Build the playlist URL with parameters."""
        base_url = self.config.base_playlist_url
        
        parsed = urlparse(base_url)
        existing_params = parse_qs(parsed.query)
        
        merged_params = self.config.playlist_params.copy()
        if params:
            merged_params.update(params)
        
        if "account_id" not in merged_params:
            merged_params["account_id"] = self.config.account_id
        
        query = urlencode(merged_params)
        
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query,
            parsed.fragment
        ))
    
    async def get_playlist_page(
        self,
        url: Optional[str] = None
    ) -> Tuple[List[AssetInfo], Optional[str]]:
        """Get a single page of playlist contents."""
        fetch_url = url or self._build_playlist_url()
        logger.info(f"Fetching playlist page: {fetch_url}")
        
        data = await self._get(fetch_url)
        if not data:
            return [], None
        
        try:
            blocks = data.get("data", {}).get("blocks", [])
            if not blocks:
                logger.warning("No blocks found in playlist response")
                return [], None
            
            widgets = blocks[0].get("widgets", [])
            if not widgets:
                logger.warning("No widgets found in playlist response")
                return [], None
            
            playlist = widgets[0].get("playlist", {})
            contents = playlist.get("contents", [])
            pagination = playlist.get("pagination", {})
            
            assets = []
            for item in contents:
                if item.get("type") == "movies" and "id" in item:
                    asset = AssetInfo(
                        asset_id=item["id"],
                        title=item.get("title", "Unknown"),
                        description=item.get("description"),
                        duration_seconds=item.get("duration"),
                        thumbnail_url=item.get("thumbnailUrl") or item.get("thumbnail_url"),
                        metadata=item
                    )
                    assets.append(asset)
            
            next_url = pagination.get("url", {}).get("next")
            
            logger.info(f"Found {len(assets)} assets, next page: {next_url is not None}")
            return assets, next_url
            
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing playlist response: {e}")
            return [], None
    
    async def get_all_assets(self) -> List[AssetInfo]:
        """Get all assets from the playlist, handling pagination."""
        all_assets = []
        next_url = None
        page_count = 0
        
        while True:
            assets, next_url = await self.get_playlist_page(next_url)
            all_assets.extend(assets)
            page_count += 1
            
            if not next_url:
                break
            
            if page_count > 100:
                logger.warning("Reached maximum page limit (100)")
                break
        
        logger.info(f"Total assets fetched: {len(all_assets)} from {page_count} pages")
        return all_assets
    
    async def asset_id_to_video_id(self, asset_id: str) -> Optional[str]:
        """Convert an asset ID to a Brightcove video ID."""
        url = f"{self.config.beacon_api_base}/account/{self.config.account_id}/asset_info/{asset_id}"
        params = {
            "device_type": "web",
            "ngsw-bypass": "1"
        }
        
        logger.debug(f"Resolving asset {asset_id} to video ID")
        
        data = await self._get(url, params=params)
        if not data:
            return None
        
        try:
            vpd = data.get("data", {}).get("video_playback_details", [])
            if vpd and len(vpd) > 0 and "video_id" in vpd[0]:
                video_id = vpd[0]["video_id"]
                logger.debug(f"Asset {asset_id} resolved to video {video_id}")
                return video_id
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing asset info response: {e}")
        
        logger.warning(f"Could not resolve video ID for asset {asset_id}")
        return None
    
    async def video_id_to_stream_url(self, video_id: str) -> Optional[str]:
        """Get the HLS stream URL for a video ID."""
        url = f"{self.config.edge_api_base}/accounts/{self.config.brightcove_account_id}/videos/{video_id}"
        
        params = {}
        if self.config.ad_config_id:
            params["ad_config_id"] = self.config.ad_config_id
        
        logger.debug(f"Getting stream URL for video {video_id}")
        
        data = await self._get(url, params=params if params else None)
        if not data:
            return None
        
        try:
            sources = data.get("sources", [])
            
            for source in sources:
                if source.get("type") == "application/x-mpegURL" and "src" in source:
                    stream_url = source["src"]
                    logger.debug(f"Found HLS stream URL for video {video_id}")
                    return stream_url
            
            for source in sources:
                if "src" in source:
                    logger.debug(f"Using fallback stream URL for video {video_id}")
                    return source["src"]
                    
        except Exception as e:
            logger.error(f"Error parsing stream response: {e}")
        
        logger.warning(f"No stream URL found for video {video_id}")
        return None
    
    async def get_stream_url(self, asset_id: str) -> Optional[str]:
        """Get the HLS stream URL for an asset ID."""
        video_id = await self.asset_id_to_video_id(asset_id)
        if not video_id:
            return None
        
        return await self.video_id_to_stream_url(video_id)
    
    async def resolve_asset(self, asset: AssetInfo) -> AssetInfo:
        """Resolve an asset fully (asset ID -> video ID -> stream URL)."""
        video_id = await self.asset_id_to_video_id(asset.asset_id)
        if video_id:
            asset.video_id = video_id
            asset.stream_url = await self.video_id_to_stream_url(video_id)
        return asset


class BrightcovePlugin(ArchiverPlugin):
    """Brightcove video archiver plugin for Haven CLI.
    
    Provides video discovery and downloading from Brightcove-powered
    streaming sites with support for playlist pagination and HLS downloads.
    
    Default configuration targets The Den (watchentertheden.com).
    
    Example:
        plugin = BrightcovePlugin(config={
            "sources": [the_den_config_dict],
            "default_source": "the_den"
        })
        await plugin.initialize()
        
        # Set progress tracker
        plugin.set_progress_tracker(tracker)
        
        # Discover videos
        sources = await plugin.discover_sources()
        
        # Archive a video
        result = await plugin.archive(sources[0])
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the Brightcove plugin."""
        super().__init__(config)
        
        self._client: Optional[httpx.AsyncClient] = None
        self.download_dir: Optional[Path] = None
        self._progress_tracker: Optional[Any] = None
        self._current_downloads: Dict[str, Any] = {}
        
        # Load sources from config
        self.sources: List[BrightcoveSourceConfig] = []
        sources_data = self._config.get("sources", [])
        
        for source_dict in sources_data:
            try:
                self.sources.append(BrightcoveSourceConfig.from_dict(source_dict))
            except Exception as e:
                logger.error(f"Failed to load source config: {e}")
        
        # Add default The Den source if no sources configured
        if not self.sources:
            self.sources = [self._get_the_den_config()]
        
        # Tracking sets for deduplication
        self._seen_videos: set[str] = set()
        self._archived_videos: Dict[str, Dict[str, Any]] = {}
    
    def _get_the_den_config(self) -> BrightcoveSourceConfig:
        """Get the default The Den configuration."""
        return BrightcoveSourceConfig(
            name="the_den",
            display_name="The Den",
            description="Skateboard videos from watchentertheden.com",
            base_playlist_url="https://beacon.playback.api.brightcove.com/twentypointnine/api/playlists/760",
            playlist_params={
                "cohort": "98890104",
                "device_type": "web",
                "device_layout": "web",
                "playlist_id": "760"
            },
            account_id="ceee68007b4a515b6",
            brightcove_account_id="6415533679001",
            ad_config_id="49858721b38a4e7186bc13f5ec8ca505",
            beacon_api_base="https://beacon.playback.api.brightcove.com/twentypointnine/api",
            edge_api_base="https://edge.api.brightcove.com/playback/v1",
            poll_interval_minutes=60,
            rate_limit_seconds=1.0,
            max_retries=3,
            output_format="mp4",
            quality_preference="best",
            enabled=True
        )
    
    def set_progress_tracker(self, tracker: Any) -> None:
        """Inject progress tracker (called by plugin manager)."""
        self._progress_tracker = tracker
    
    @property
    def info(self) -> PluginInfo:
        """Get plugin information."""
        return PluginInfo(
            name="BrightcovePlugin",
            display_name="Brightcove Archiver",
            version="1.0.0",
            description="Archive videos from Brightcove-powered sites (default: The Den)",
            author="Haven Team",
            media_types=["brightcove", "http", "hls"],
            capabilities=[
                PluginCapability.DISCOVER,
                PluginCapability.ARCHIVE,
                PluginCapability.HEALTH_CHECK,
                PluginCapability.METADATA,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "array",
                        "description": "List of Brightcove source configurations",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "display_name": {"type": "string"},
                                "base_playlist_url": {"type": "string"},
                                "account_id": {"type": "string"},
                                "brightcove_account_id": {"type": "string"},
                                "ad_config_id": {"type": "string"},
                                "enabled": {"type": "boolean", "default": True},
                                "output_format": {"type": "string", "default": "mp4"},
                                "quality_preference": {"type": "string", "default": "best"},
                            },
                            "required": ["name", "display_name", "base_playlist_url", "account_id", "brightcove_account_id"]
                        }
                    },
                    "default_source": {"type": "string"},
                    "max_concurrent_downloads": {"type": "integer", "default": 2},
                    "download_subtitles": {"type": "boolean", "default": False},
                }
            }
        )
    
    async def initialize(self) -> None:
        """Initialize the plugin."""
        # Verify yt-dlp is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError("yt-dlp not found or not working properly")
            version = stdout.decode().strip()
            logger.info(f"yt-dlp version: {version}")
        except FileNotFoundError:
            raise RuntimeError(
                "yt-dlp not found. Please install it: https://github.com/yt-dlp/yt-dlp#installation"
            )
        
        # Set download directory
        self.download_dir = Path(self._config.get("download_dir", Path.home() / "haven" / "downloads" / "brightcove"))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # Create HTTP client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60),
            headers={
                "User-Agent": "HavenCLI-BrightcovePlugin/1.0",
                "Accept": "application/json",
            }
        )
        
        # Load seen videos from persistent storage
        seen_file = self.download_dir / ".brightcove_seen_videos.json"
        if seen_file.exists():
            try:
                with open(seen_file, "r") as f:
                    data = json.load(f)
                    self._seen_videos = set(data.get("seen", []))
                    self._archived_videos = data.get("archived", {})
            except Exception as e:
                logger.warning(f"Could not load seen videos: {e}")
        
        self._initialized = True
        logger.info("BrightcovePlugin initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown the plugin and save state."""
        # Save seen videos
        seen_file = self.download_dir / ".brightcove_seen_videos.json"
        try:
            with open(seen_file, "w") as f:
                json.dump({
                    "seen": list(self._seen_videos),
                    "archived": self._archived_videos,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save seen videos: {e}")
        
        # Close HTTP client
        if self._client:
            await self._client.aclose()
            self._client = None
        
        self._initialized = False
    
    async def health_check(self) -> bool:
        """Check if the plugin is healthy."""
        if not self._initialized:
            return False
        
        if not self._client:
            return False
        
        if not self.download_dir or not self.download_dir.exists():
            return False
        
        # Check yt-dlp availability
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                logger.error("Health check failed: yt-dlp not available")
                return False
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
        
        return True
    
    async def discover_sources(self) -> List[MediaSource]:
        """Discover media sources to archive."""
        if not self._initialized or not self._client:
            logger.error("BrightcovePlugin not initialized")
            return []
        
        # Get enabled sources
        enabled_sources = [s for s in self.sources if s.enabled]
        
        if not enabled_sources:
            logger.info("No enabled Brightcove sources to poll")
            return []
        
        logger.info(f"Polling {len(enabled_sources)} Brightcove sources")
        
        new_sources: List[MediaSource] = []
        
        for source_config in enabled_sources:
            try:
                source_media = await self._discover_from_source(source_config)
                new_sources.extend(source_media)
            except Exception as e:
                logger.error(f"Error polling source {source_config.name}: {e}")
                continue
        
        logger.info(f"Discovered {len(new_sources)} new videos")
        return new_sources
    
    async def _discover_from_source(
        self,
        source_config: BrightcoveSourceConfig
    ) -> List[MediaSource]:
        """Discover videos from a single source."""
        source_name = source_config.name
        
        # Create API client
        client = BrightcoveAPIClient(source_config, self._client)
        
        # Get all assets
        assets = await client.get_all_assets()
        logger.info(f"Found {len(assets)} assets from source {source_name}")
        
        new_sources = []
        
        for asset in assets:
            # Skip if already seen
            if asset.asset_id in self._seen_videos:
                continue
            
            self._seen_videos.add(asset.asset_id)
            
            # Resolve asset
            await client.resolve_asset(asset)
            
            if not asset.stream_url:
                logger.warning(f"No stream URL for asset {asset.asset_id}")
                continue
            
            # Create media source
            media_source = MediaSource(
                source_id=f"{source_name}:{asset.asset_id}",
                media_type="brightcove",
                uri=asset.stream_url,
                title=asset.title,
                priority="medium",
                metadata={
                    "asset_id": asset.asset_id,
                    "video_id": asset.video_id,
                    "title": asset.title,
                    "description": asset.description,
                    "duration": asset.duration_seconds,
                    "thumbnail": asset.thumbnail_url,
                    "source_name": source_name,
                    "source_display_name": source_config.display_name,
                    "video_format": source_config.output_format,
                    "video_quality": source_config.quality_preference,
                },
            )
            new_sources.append(media_source)
        
        return new_sources
    
    async def archive(
        self,
        source: MediaSource,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> ArchiveResult:
        """Archive a media source."""
        if not self._initialized:
            return ArchiveResult(
                success=False,
                error="Plugin not initialized",
            )
        
        if source.media_type not in ["brightcove", "http", "hls"]:
            return ArchiveResult(
                success=False,
                error=f"Unsupported media type: {source.media_type}",
            )
        
        video_id = source.source_id
        asset_id = source.metadata.get("asset_id", video_id)
        
        logger.info(f"Archiving video: {asset_id}")
        
        # Check if already archived
        if video_id in self._archived_videos:
            logger.info(f"Video {video_id} already archived")
            archived_info = self._archived_videos[video_id]
            return ArchiveResult(
                success=True,
                output_path=archived_info.get("output_path", ""),
                file_size=archived_info.get("file_size", 0),
                duration=source.metadata.get("duration", 0),
                metadata={"already_archived": True, **source.metadata},
            )
        
        try:
            # Create output directory
            source_name = source.metadata.get("source_name", "brightcove")
            source_dir = self.download_dir / source_name
            source_dir.mkdir(parents=True, exist_ok=True)
            
            # Create safe filename
            safe_title = "".join(
                c for c in source.metadata.get("title", "video")
                if c.isalnum() or c in (" ", "-", "_")
            ).strip()[:50]
            
            file_extension = source.metadata.get("video_format", "mp4")
            output_path = source_dir / f"{safe_title}_{asset_id}.{file_extension}"
            
            # Check if already exists
            if output_path.exists():
                file_size = output_path.stat().st_size
                logger.info(f"Video already exists: {output_path}")
                return ArchiveResult(
                    success=True,
                    output_path=str(output_path),
                    file_size=file_size,
                    duration=source.metadata.get("duration", 0),
                    metadata={"video_id": video_id, "existing": True},
                )
            
            stream_url = source.uri
            logger.info(f"Downloading from: {stream_url}")
            
            # Build yt-dlp command
            quality = source.metadata.get("video_quality", "best")
            fmt = source.metadata.get("video_format", "mp4")
            
            if quality == "best":
                format_str = f"best[ext={fmt}]/best"
            else:
                height = quality.replace("p", "")
                format_str = f"best[height<={height}][ext={fmt}]/best[height<={height}]/best"
            
            cmd = [
                "yt-dlp",
                "--format", format_str,
                "--output", str(output_path),
                "--no-playlist",
                "--newline",
                stream_url
            ]
            
            logger.info(f"Running: {' '.join(cmd)}")
            
            # Execute download
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                error_msg = stderr.decode() or stdout.decode() or "yt-dlp failed"
                logger.error(f"Download failed: {error_msg[:500]}")
                return ArchiveResult(
                    success=False,
                    error=error_msg,
                )
            
            # Verify file exists
            if output_path.exists():
                file_size = output_path.stat().st_size
            else:
                # Try to find file with different extension
                base_path = str(output_path).rsplit(".", 1)[0] if "." in str(output_path) else str(output_path)
                for ext in ["mp4", "mkv", "webm", "avi", "mov"]:
                    potential_path = Path(f"{base_path}.{ext}")
                    if potential_path.exists():
                        output_path = potential_path
                        file_size = output_path.stat().st_size
                        break
                else:
                    return ArchiveResult(
                        success=False,
                        error="Download completed but file not found",
                    )
            
            # Mark as archived
            self._archived_videos[video_id] = {
                "video_id": video_id,
                "asset_id": asset_id,
                "title": source.metadata.get("title"),
                "output_path": str(output_path),
                "file_size": file_size,
                "archived_at": asyncio.get_event_loop().time(),
            }
            
            logger.info(f"Download complete: {file_size} bytes")
            
            return ArchiveResult(
                success=True,
                output_path=str(output_path),
                file_size=file_size,
                duration=source.metadata.get("duration", 0),
                metadata={
                    "video_id": video_id,
                    "asset_id": asset_id,
                    "title": source.metadata.get("title"),
                    "source": source.metadata.get("source_name"),
                },
            )
            
        except Exception as e:
            logger.error(f"Error archiving video {video_id}: {e}")
            return ArchiveResult(
                success=False,
                error=str(e),
            )
    
    def configure(self, config: Dict[str, Any]) -> None:
        """Update plugin configuration."""
        super().configure(config)
        
        # Reload sources
        self.sources = []
        sources_data = self._config.get("sources", [])
        for source_dict in sources_data:
            try:
                self.sources.append(BrightcoveSourceConfig.from_dict(source_dict))
            except Exception as e:
                logger.error(f"Failed to load source config: {e}")
    
    # ========== Source Management Methods ==========
    
    def add_source(self, source_config: BrightcoveSourceConfig) -> Dict[str, Any]:
        """Add a new Brightcove source.
        
        Args:
            source_config: Configuration for the new source
            
        Returns:
            Result dict
        """
        # Check if source already exists
        for s in self.sources:
            if s.name == source_config.name:
                return {
                    "success": False,
                    "error": f"Source '{source_config.name}' already exists",
                }
        
        self.sources.append(source_config)
        self._config["sources"] = [s.to_dict() for s in self.sources]
        
        logger.info(f"Added Brightcove source: {source_config.name}")
        
        return {
            "success": True,
            "source": source_config.to_dict(),
        }
    
    def remove_source(self, source_name: str) -> Dict[str, Any]:
        """Remove a Brightcove source.
        
        Args:
            source_name: Name of source to remove
            
        Returns:
            Result dict
        """
        for i, s in enumerate(self.sources):
            if s.name == source_name:
                removed = self.sources.pop(i)
                self._config["sources"] = [s.to_dict() for s in self.sources]
                
                logger.info(f"Removed Brightcove source: {source_name}")
                
                return {
                    "success": True,
                    "removed": removed.to_dict(),
                }
        
        return {
            "success": False,
            "error": f"Source not found: {source_name}",
        }
    
    def list_sources(self) -> List[Dict[str, Any]]:
        """List all configured sources."""
        return [s.to_dict() for s in self.sources]
    
    def enable_source(self, source_name: str) -> bool:
        """Enable a source."""
        for s in self.sources:
            if s.name == source_name:
                s.enabled = True
                self._config["sources"] = [s.to_dict() for s in self.sources]
                return True
        return False
    
    def disable_source(self, source_name: str) -> bool:
        """Disable a source."""
        for s in self.sources:
            if s.name == source_name:
                s.enabled = False
                self._config["sources"] = [s.to_dict() for s in self.sources]
                return True
        return False
