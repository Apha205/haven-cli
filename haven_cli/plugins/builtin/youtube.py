"""YouTube archiver plugin for Haven CLI.

This plugin uses yt-dlp to discover and download videos from YouTube channels
and playlists. It supports quality selection, subtitle downloads, and
cookie-based authentication for age-restricted content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from haven_cli.plugins.base import (
    ArchiverPlugin,
    ArchiveResult,
    MediaSource,
    PluginCapability,
    PluginInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class YouTubeConfig:
    """YouTube plugin configuration.
    
    Attributes:
        channel_ids: List of YouTube channel IDs to monitor
        playlist_ids: List of YouTube playlist IDs to monitor
        max_videos: Maximum videos to discover per channel/playlist
        quality: Video quality (best, 1080p, 720p, 480p, 360p)
        format: Container format (mp4, webm, mkv)
        output_dir: Directory to save downloaded videos
        cookies_file: Path to YouTube cookies file for age-restricted content
        download_subtitles: Whether to download subtitles
        max_retries: Maximum retry attempts for failed downloads
    """
    
    channel_ids: List[str] = field(default_factory=list)
    playlist_ids: List[str] = field(default_factory=list)
    max_videos: int = 10
    quality: str = "best"
    format: str = "mp4"
    output_dir: Path = field(default_factory=lambda: Path("./downloads"))
    cookies_file: Optional[Path] = None
    download_subtitles: bool = False
    max_retries: int = 3
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "YouTubeConfig":
        """Create config from dictionary."""
        # Expand home directory in paths
        output_dir = config.get("output_dir", "./downloads")
        cookies_file = config.get("cookies_file")
        
        return cls(
            channel_ids=config.get("channel_ids", []),
            playlist_ids=config.get("playlist_ids", []),
            max_videos=config.get("max_videos", 10),
            quality=config.get("quality", "best"),
            format=config.get("format", "mp4"),
            output_dir=Path(output_dir).expanduser(),
            cookies_file=Path(cookies_file).expanduser() if cookies_file else None,
            download_subtitles=config.get("download_subtitles", False),
            max_retries=config.get("max_retries", 3),
        )


class _YTDLPLogger:
    """Logger for yt-dlp that redirects output to Python logging.
    
    This prevents yt-dlp output from polluting the TUI.
    """
    
    def debug(self, msg: str) -> None:
        # Filter out progress messages - they go through progress_hooks
        if not msg.startswith('[download]'):
            logger.debug(f"yt-dlp: {msg}")
    
    def info(self, msg: str) -> None:
        if not msg.startswith('[download]'):
            logger.info(f"yt-dlp: {msg}")
    
    def warning(self, msg: str) -> None:
        logger.warning(f"yt-dlp: {msg}")
    
    def error(self, msg: str) -> None:
        logger.error(f"yt-dlp: {msg}")


class YouTubePlugin(ArchiverPlugin):
    """YouTube video archiver plugin using yt-dlp with progress tracking.
    
    This plugin discovers videos from configured YouTube channels and playlists
    and archives them using yt-dlp. It supports quality selection, cookie-based
    authentication, retry logic for resilient downloads, and real-time progress
    tracking through the DownloadProgressTracker.
    
    Example:
        plugin = YouTubePlugin(config={
            "channel_ids": ["UC_x5XG1OV2P6uZZ5FSM9Ttw"],
            "quality": "1080p",
            "output_dir": "~/videos/youtube"
        })
        await plugin.initialize()
        
        # Set progress tracker (injected by plugin manager)
        plugin.set_progress_tracker(tracker)
        
        # Discover videos
        sources = await plugin.discover_sources()
        
        # Archive a video with progress tracking
        result = await plugin.archive(sources[0])
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the YouTube plugin.
        
        Args:
            config: Plugin configuration dictionary
        """
        super().__init__(config)
        self._yt_config = YouTubeConfig.from_dict(self._config)
        self._js_runtime_type: Optional[str] = None
        self._js_runtime_path: Optional[str] = None
        self._seen_videos: set[str] = set()  # Track seen videos to avoid duplicates
        self._archived_videos: Dict[str, Dict[str, Any]] = {}
        
        # Progress tracking
        self._progress_tracker: Optional[Any] = None
        self._current_downloads: Dict[str, Any] = {}
    
    def set_progress_tracker(self, tracker: Any) -> None:
        """Inject progress tracker (called by plugin manager).
        
        Args:
            tracker: DownloadProgressTracker instance for reporting progress
        """
        self._progress_tracker = tracker
    
    @property
    def info(self) -> PluginInfo:
        """Get plugin information."""
        return PluginInfo(
            name="YouTubePlugin",
            display_name="YouTube Archiver",
            version="1.0.0",
            description="Archive videos from YouTube channels and playlists using yt-dlp",
            author="Haven Team",
            media_types=["youtube"],
            capabilities=[
                PluginCapability.DISCOVER,
                PluginCapability.ARCHIVE,
                PluginCapability.METADATA,
                PluginCapability.HEALTH_CHECK,
            ],
        )
    
    async def initialize(self) -> None:
        """Initialize the plugin.
        
        Verifies that yt-dlp is installed and detects available JavaScript
        runtimes (Deno or Node.js) for enhanced download capabilities.
        
        Raises:
            RuntimeError: If yt-dlp is not installed
        """
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
        
        # Detect JavaScript runtime for enhanced YouTube extraction
        self._js_runtime_type, self._js_runtime_path = self._detect_js_runtime()
        if self._js_runtime_path:
            logger.info(f"JavaScript runtime detected: {self._js_runtime_type}")
        else:
            logger.warning(
                "No JavaScript runtime (Deno/Node.js) detected. "
                "Some videos may fail to download."
            )
        
        # Create output directory if it doesn't exist
        self._yt_config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load seen videos from persistent storage if available
        seen_file = self._yt_config.output_dir / ".youtube_seen_videos.json"
        if seen_file.exists():
            try:
                with open(seen_file, "r") as f:
                    data = json.load(f)
                    self._seen_videos = set(data.get("seen", []))
                    self._archived_videos = data.get("archived", {})
            except Exception as e:
                logger.warning(f"Could not load seen videos: {e}")
        
        self._initialized = True
        logger.info("YouTubePlugin initialized successfully")
    
    async def shutdown(self) -> None:
        """Shutdown the plugin and save state."""
        # Save seen videos to persistent storage
        seen_file = self._yt_config.output_dir / ".youtube_seen_videos.json"
        try:
            with open(seen_file, "w") as f:
                json.dump({
                    "seen": list(self._seen_videos),
                    "archived": self._archived_videos,
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save seen videos: {e}")
        
        self._initialized = False
    
    async def health_check(self) -> bool:
        """Check if the plugin is healthy.
        
        Verifies yt-dlp availability and output directory accessibility.
        
        Returns:
            True if plugin is healthy and operational
        """
        if not self._initialized:
            return False
        
        try:
            # Check yt-dlp availability
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                logger.error("Health check failed: yt-dlp not available")
                return False
            
            # Check output directory exists
            if not self._yt_config.output_dir.exists():
                logger.error(f"Health check failed: output directory does not exist")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def discover_sources(self) -> List[MediaSource]:
        """Discover videos from configured channels and playlists.
        
        Polls all configured YouTube channels and playlists for new videos.
        Tracks seen videos to avoid returning duplicates.
        
        Returns:
            List of MediaSource objects representing new videos
        """
        if not self._initialized:
            logger.error("Plugin not initialized")
            return []
        
        sources: List[MediaSource] = []
        
        # Discover from channels
        for channel_id in self._yt_config.channel_ids:
            try:
                channel_sources = await self._discover_channel(channel_id)
                sources.extend(channel_sources)
            except Exception as e:
                logger.error(f"Error discovering from channel {channel_id}: {e}")
        
        # Discover from playlists
        for playlist_id in self._yt_config.playlist_ids:
            try:
                playlist_sources = await self._discover_playlist(playlist_id)
                sources.extend(playlist_sources)
            except Exception as e:
                logger.error(f"Error discovering from playlist {playlist_id}: {e}")
        
        logger.info(f"Discovered {len(sources)} new videos")
        return sources
    
    async def archive(self, source: MediaSource) -> ArchiveResult:
        """Archive a YouTube video with progress tracking.
        
        Downloads the video using yt-dlp with configured quality settings.
        Reports download progress through the DownloadProgressTracker if set.
        Implements retry logic for transient failures.
        
        Args:
            source: MediaSource to archive
            
        Returns:
            ArchiveResult with success status and file information
        """
        if not self._initialized:
            return ArchiveResult(
                success=False,
                error="Plugin not initialized"
            )
        
        if source.media_type != "youtube":
            return ArchiveResult(
                success=False,
                error=f"Unsupported media type: {source.media_type}"
            )
        
        video_id = source.source_id
        
        # Check if already archived
        if video_id in self._archived_videos:
            logger.info(f"Video {video_id} already archived")
            archived_info = self._archived_videos[video_id]
            return ArchiveResult(
                success=True,
                output_path=archived_info.get("output_path", ""),
                file_size=archived_info.get("file_size", 0),
                metadata={"already_archived": True, **source.metadata},
            )
        
        # Build output template
        channel_name = source.metadata.get("channel_name", "unknown")
        safe_channel = "".join(c for c in channel_name if c.isalnum() or c in (" ", "-", "_"))
        channel_dir = self._yt_config.output_dir / safe_channel
        channel_dir.mkdir(parents=True, exist_ok=True)
        
        output_template = str(channel_dir / f"%(title)s_{video_id}.%(ext)s")
        
        # Attempt download with retries
        for attempt in range(self._yt_config.max_retries):
            try:
                result = await self._download_video_with_progress(
                    source, output_template, attempt + 1
                )
                
                if result["success"]:
                    # Verify the file exists
                    output_path = result.get("output_path")
                    if output_path and os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        
                        # Mark as archived
                        self._archived_videos[video_id] = {
                            "video_id": video_id,
                            "title": source.metadata.get("title", ""),
                            "output_path": output_path,
                            "file_size": file_size,
                            "archived_at": asyncio.get_event_loop().time(),
                        }
                        
                        # Get video duration if possible
                        duration = await self._get_video_duration(output_path)
                        
                        return ArchiveResult(
                            success=True,
                            output_path=output_path,
                            file_size=file_size,
                            duration=int(duration),
                            metadata=source.metadata,
                        )
                    else:
                        return ArchiveResult(
                            success=False,
                            error="Download completed but file not found"
                        )
                else:
                    error = result.get("error", "Unknown error")
                    
                    # Check if error is retryable
                    if not self._is_retryable_error(error):
                        # Report final failure
                        await self._report_failure(source, error)
                        return ArchiveResult(success=False, error=error)
                    
                    if attempt < self._yt_config.max_retries - 1:
                        delay = 2 ** attempt  # Exponential backoff
                        logger.warning(f"Retryable error, waiting {delay}s before retry...")
                        await asyncio.sleep(delay)
                    else:
                        # Report final failure after all retries
                        await self._report_failure(source, error)
                        return ArchiveResult(success=False, error=error)
                        
            except Exception as e:
                logger.error(f"Error during download attempt {attempt + 1}: {e}")
                if attempt < self._yt_config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    await self._report_failure(source, str(e))
                    return ArchiveResult(success=False, error=str(e))
        
        return ArchiveResult(
            success=False,
            error="All download attempts failed"
        )
    
    def configure(self, config: Dict[str, Any]) -> None:
        """Update plugin configuration.
        
        Args:
            config: New configuration values to merge
        """
        super().configure(config)
        self._yt_config = YouTubeConfig.from_dict(self._config)
    
    def _detect_js_runtime(self) -> Tuple[Optional[str], Optional[str]]:
        """Detect available JavaScript runtime (Deno or Node.js).
        
        JavaScript runtime is required by yt-dlp for decrypting YouTube's
        signature ciphers and accessing premium formats.
        
        Returns:
            Tuple of (runtime_type, path) or (None, None) if not found
        """
        # Check Deno first (smaller, faster)
        try:
            result = subprocess.run(
                ["deno", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return ("deno", "deno")
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        # Check Node.js as fallback
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return ("nodejs", "node")
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        
        return (None, None)
    
    def _is_retryable_error(self, error_message: str) -> bool:
        """Determine if an error is retryable.
        
        Args:
            error_message: The error message to check
            
        Returns:
            True if the error appears to be transient
        """
        error_lower = error_message.lower()
        
        # Non-retryable errors
        non_retryable = [
            "video unavailable",
            "private video",
            "copyright",
            "removed",
            "not found",
            "404",
            "410",
            "invalid",
            "forbidden",
            "403",
        ]
        
        for pattern in non_retryable:
            if pattern in error_lower:
                return False
        
        # Retryable errors
        retryable = [
            "javascript runtime",
            "requested format is not available",
            "network",
            "timeout",
            "connection",
            "429",
            "too many requests",
            "rate limit",
            "temporary",
            "server error",
            "503",
            "502",
            "504",
        ]
        
        for pattern in retryable:
            if pattern in error_lower:
                return True
        
        return True  # Default to retryable if uncertain
    
    async def _discover_channel(self, channel_id: str) -> List[MediaSource]:
        """Discover videos from a YouTube channel.
        
        Args:
            channel_id: The YouTube channel ID
            
        Returns:
            List of MediaSource objects for new videos
        """
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
        return await self._extract_video_list(url, channel_id)
    
    async def _discover_playlist(self, playlist_id: str) -> List[MediaSource]:
        """Discover videos from a YouTube playlist.
        
        Args:
            playlist_id: The YouTube playlist ID
            
        Returns:
            List of MediaSource objects for new videos
        """
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        return await self._extract_video_list(url, playlist_id)
    
    async def _extract_video_list(
        self, url: str, source_id: str
    ) -> List[MediaSource]:
        """Extract video list from URL using yt-dlp.
        
        Args:
            url: URL to extract videos from
            source_id: Identifier for the source (channel or playlist)
            
        Returns:
            List of MediaSource objects for new videos
        """
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(self._yt_config.max_videos),
        ]
        
        # Add cookies if available
        if self._yt_config.cookies_file and self._yt_config.cookies_file.exists():
            cmd.extend(["--cookies", str(self._yt_config.cookies_file)])
        
        # Note: yt-dlp doesn't support --remote-components or --js-runtimes options
        # It auto-detects available JS runtimes internally
        
        cmd.append(url)
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            logger.error(f"yt-dlp error: {stderr.decode()}")
            return []
        
        sources = []
        channel_name = None
        
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                video_id = data.get("id", "")
                
                # Skip if already seen
                if video_id in self._seen_videos:
                    continue
                
                self._seen_videos.add(video_id)
                
                # Get channel name from first video if not provided
                if channel_name is None:
                    channel_name = data.get("channel") or data.get("uploader") or source_id
                
                sources.append(MediaSource(
                    source_id=video_id,
                    media_type="youtube",
                    uri=f"https://www.youtube.com/watch?v={video_id}",
                    title=data.get("title", ""),
                    priority="medium",
                    metadata={
                        "title": data.get("title", ""),
                        "channel_name": channel_name,
                        "uploader": data.get("uploader", ""),
                        "duration": data.get("duration"),
                        "thumbnail": data.get("thumbnail"),
                        "upload_date": data.get("upload_date"),
                        "view_count": data.get("view_count"),
                        "source_id": source_id,
                    },
                ))
            except json.JSONDecodeError:
                continue
        
        return sources
    
    async def _download_video_with_progress(
        self,
        source: MediaSource,
        output_template: str,
        attempt: int = 1
    ) -> Dict[str, Any]:
        """Download a YouTube video with progress tracking.
        
        This method uses yt-dlp's Python API when progress tracking is enabled,
        or falls back to subprocess execution otherwise. Progress updates are
        reported through the DownloadProgressTracker.
        
        Args:
            source: MediaSource to download
            output_template: Output file path template
            attempt: Current attempt number
            
        Returns:
            Dict with success status, output_path, and error message
        """
        video_id = source.source_id
        
        # Try using yt-dlp Python API for better progress tracking
        if self._progress_tracker is not None:
            try:
                return await self._download_with_ytdlp_api(source, output_template)
            except Exception as e:
                logger.warning(f"yt-dlp API download failed, falling back to subprocess: {e}")
                return await self._download_with_subprocess(source, output_template, attempt)
        else:
            # No progress tracker, use subprocess
            return await self._download_with_subprocess(source, output_template, attempt)
    
    async def _download_with_ytdlp_api(
        self,
        source: MediaSource,
        output_template: str
    ) -> Dict[str, Any]:
        """Download using yt-dlp Python API with progress hooks.
        
        Args:
            source: MediaSource to download
            output_template: Output file path template
            
        Returns:
            Dict with success status, output_path, and error message
        """
        import yt_dlp
        from datetime import datetime, timezone
        from haven_tui.data.download_tracker import DownloadProgress, DownloadStatus
        
        video_id = source.source_id
        output_path: Optional[str] = None
        error_msg: Optional[str] = None
        
        # Initialize progress
        progress = DownloadProgress(
            source_id=video_id,
            source_type="youtube",
            title=source.title,
            uri=source.uri,
            status=DownloadStatus.QUEUED,
            metadata={
                "youtube_id": video_id,
                "channel": source.metadata.get("channel_name"),
                "attempt": 1,
            }
        )
        self._current_downloads[video_id] = progress
        
        def progress_hook(d: Dict[str, Any]) -> None:
            """Progress hook called by yt-dlp during download."""
            nonlocal output_path
            
            status = d.get("status", "downloading")
            
            if status == "downloading":
                progress.status = DownloadStatus.DOWNLOADING
                progress.downloaded = d.get("downloaded_bytes", 0)
                progress.total_size = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                
                # Calculate progress percentage
                if progress.total_size > 0:
                    progress.progress_pct = (progress.downloaded / progress.total_size) * 100
                
                # Speed and ETA
                progress.download_rate = d.get("speed", 0) or 0
                progress.eta_seconds = d.get("eta")
                progress.connections = 1  # yt-dlp typically uses single connection per file
                
                # Parse percentage string if available (more accurate)
                if "_percent_str" in d:
                    try:
                        pct_str = d["_percent_str"].replace("%", "").strip()
                        progress.progress_pct = float(pct_str)
                    except (ValueError, TypeError):
                        pass
                
                # Update timestamps
                if progress.started_at is None:
                    progress.started_at = datetime.now(timezone.utc)
                progress.updated_at = datetime.now(timezone.utc)
                
                # Report progress
                self._report_progress(progress)
                
            elif status == "finished":
                progress.status = DownloadStatus.VERIFYING
                progress.downloaded = d.get("downloaded_bytes", progress.downloaded)
                progress.total_size = d.get("total_bytes", progress.total_size)
                if progress.total_size > 0:
                    progress.progress_pct = 100.0
                progress.updated_at = datetime.now(timezone.utc)
                output_path = d.get("filename")
                self._report_progress(progress)
        
        try:
            # Build format string based on quality setting
            quality = source.metadata.get("video_quality", self._yt_config.quality)
            fmt = source.metadata.get("video_format", self._yt_config.format)
            
            if quality == "best":
                format_str = f"bestvideo[ext={fmt}]+bestaudio/best[ext={fmt}]/best"
            else:
                # Extract height from quality (e.g., "1080p" -> 1080)
                height = quality.replace("p", "")
                format_str = (
                    f"bestvideo[height<={height}][ext={fmt}]+bestaudio/"
                    f"best[height<={height}][ext={fmt}]/"
                    f"best[height<={height}]"
                )
            
            # Build yt-dlp options
            ydl_opts = {
                "format": format_str,
                "outtmpl": output_template,
                "noplaylist": True,
                "progress_hooks": [progress_hook],
                "logger": _YTDLPLogger(),
            }
            
            # Add cookies if available
            if self._yt_config.cookies_file and self._yt_config.cookies_file.exists():
                ydl_opts["cookiesfrombrowser"] = None
                ydl_opts["cookies"] = str(self._yt_config.cookies_file)
            
            # Add subtitle options
            if source.metadata.get("download_subtitles", self._yt_config.download_subtitles):
                ydl_opts["writesubtitles"] = True
                ydl_opts["writeautomaticsub"] = True
                ydl_opts["subtitleslangs"] = ["en"]
            
            # Run download in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def do_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(source.uri, download=True)
                    return ydl.prepare_filename(info), info
            
            prepared_path, info = await loop.run_in_executor(None, do_download)
            
            # Update to completed
            progress.status = DownloadStatus.COMPLETED
            progress.progress_pct = 100.0
            progress.total_size = progress.downloaded or info.get("filesize") or info.get("filesize_approx", 0)
            progress.completed_at = datetime.now(timezone.utc)
            self._report_progress(progress)
            
            # Determine actual output path
            if output_path is None:
                output_path = prepared_path
            
            # Verify file exists and get actual path
            if os.path.exists(output_path):
                return {
                    "success": True,
                    "output_path": output_path,
                }
            else:
                # Try to find the file with the actual extension
                base_path = output_path.rsplit(".", 1)[0] if "." in output_path else output_path
                for ext in ["mp4", "webm", "mkv", "avi", "mov"]:
                    potential_path = f"{base_path}.{ext}"
                    if os.path.exists(potential_path):
                        return {
                            "success": True,
                            "output_path": potential_path,
                        }
                
                return {
                    "success": False,
                    "error": f"Download completed but file not found: {output_path}"
                }
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"yt-dlp API download error: {error_msg}")
            
            # Report failure
            progress.status = DownloadStatus.FAILED
            progress.error_message = error_msg
            progress.failed_at = datetime.now(timezone.utc)
            self._report_progress(progress)
            
            return {
                "success": False,
                "error": error_msg,
            }
        finally:
            # Clean up
            if video_id in self._current_downloads:
                del self._current_downloads[video_id]
    
    async def _download_with_subprocess(
        self,
        source: MediaSource,
        output_template: str,
        attempt: int = 1
    ) -> Dict[str, Any]:
        """Download using yt-dlp subprocess (fallback method).
        
        Args:
            source: MediaSource to download
            output_template: Output file path template
            attempt: Current attempt number
            
        Returns:
            Dict with success status, output_path, and error message
        """
        # Build format string based on quality setting
        quality = source.metadata.get("video_quality", self._yt_config.quality)
        fmt = source.metadata.get("video_format", self._yt_config.format)
        
        if quality == "best":
            format_str = f"bestvideo[ext={fmt}]+bestaudio/best[ext={fmt}]/best"
        else:
            # Extract height from quality (e.g., "1080p" -> 1080)
            height = quality.replace("p", "")
            format_str = (
                f"bestvideo[height<={height}][ext={fmt}]+bestaudio/"
                f"best[height<={height}][ext={fmt}]/"
                f"best[height<={height}]"
            )
        
        cmd = [
            "yt-dlp",
            "--format", format_str,
            "--output", output_template,
            "--no-playlist",
            "--newline",
        ]
        
        # Add cookies if available
        if self._yt_config.cookies_file and self._yt_config.cookies_file.exists():
            cmd.extend(["--cookies", str(self._yt_config.cookies_file)])
        
        # Add subtitle options
        if source.metadata.get("download_subtitles", self._yt_config.download_subtitles):
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-lang", "en"])
        
        cmd.append(source.uri)
        
        logger.info(f"Downloading {source.source_id} (attempt {attempt}): {' '.join(cmd)}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode()
        stderr_str = stderr.decode()
        
        if proc.returncode != 0:
            error_msg = stderr_str or stdout_str or "yt-dlp failed"
            logger.error(f"Download failed: {error_msg[:500]}")
            return {
                "success": False,
                "error": error_msg,
            }
        
        # Extract output path from yt-dlp output
        output_path = self._extract_output_path(stdout_str, stderr_str, output_template)
        
        return {
            "success": True,
            "output_path": output_path,
        }
    
    def _report_progress(self, progress: Any) -> None:
        """Report progress to tracker (writes to downloads table).
        
        Args:
            progress: DownloadProgress object to report
        """
        if self._progress_tracker is not None:
            try:
                self._progress_tracker.report_progress(progress)
            except Exception as e:
                logger.error(f"Error reporting progress: {e}")
    
    async def _report_failure(self, source: MediaSource, error: str) -> None:
        """Report download failure to tracker.
        
        Args:
            source: MediaSource that failed
            error: Error message
        """
        if self._progress_tracker is not None:
            try:
                from haven_tui.data.download_tracker import DownloadProgress, DownloadStatus
                from datetime import datetime, timezone
                
                progress = DownloadProgress(
                    source_id=source.source_id,
                    source_type="youtube",
                    title=source.title,
                    uri=source.uri,
                    status=DownloadStatus.FAILED,
                    error_message=error,
                    metadata={
                        "youtube_id": source.source_id,
                        "channel": source.metadata.get("channel_name"),
                    }
                )
                self._progress_tracker.report_progress(progress)
            except Exception as e:
                logger.error(f"Error reporting failure: {e}")
    
    def _extract_output_path(
        self, stdout: str, stderr: str, output_template: str
    ) -> Optional[str]:
        """Extract the output file path from yt-dlp output.
        
        Args:
            stdout: yt-dlp stdout
            stderr: yt-dlp stderr
            output_template: Expected output template
            
        Returns:
            Path to the downloaded file or None
        """
        # Look for merge patterns in output
        merge_patterns = [
            "[ffmpeg] Merging formats into",
            "[Merger] Merging into",
            "[download] Merging formats into",
        ]
        
        for pattern in merge_patterns:
            for line in stdout.split("\n"):
                if pattern in line:
                    # Extract path between quotes
                    parts = line.split(pattern)
                    if len(parts) > 1:
                        path = parts[1].strip().strip('"').strip("'")
                        if os.path.exists(path):
                            return path
        
        # Look for download destination lines
        for line in stdout.split("\n"):
            if "[download] Destination:" in line:
                path = line.split("[download] Destination:")[1].strip()
                if os.path.exists(path):
                    return path
        
        # Try to find file by template pattern
        template_base = output_template.replace(".%(ext)s", "")
        for ext in ["mp4", "webm", "mkv", "avi", "mov"]:
            potential_path = f"{template_base}.{ext}"
            if os.path.exists(potential_path):
                return potential_path
        
        # Search for recently modified files in the output directory
        output_dir = os.path.dirname(output_template.replace("%(title)s", "*").replace("%(id)s", "*"))
        if os.path.exists(output_dir):
            try:
                files = [
                    os.path.join(output_dir, f)
                    for f in os.listdir(output_dir)
                    if f.endswith((".mp4", ".webm", ".mkv", ".avi", ".mov"))
                ]
                if files:
                    # Return most recently modified file
                    return max(files, key=os.path.getmtime)
            except Exception:
                pass
        
        return None
    
    async def _get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Duration in seconds
        """
        try:
            from haven_cli.media.metadata import extract_video_duration
            return await extract_video_duration(Path(video_path))
        except Exception as e:
            logger.warning(f"Could not get video duration: {e}")
            return 0.0
