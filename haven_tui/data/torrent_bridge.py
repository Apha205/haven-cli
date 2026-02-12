"""BitTorrent Bridge for Haven TUI.

This module provides a bridge between the TorrentDownload tracking table
and the unified downloads table. It polls the TorrentDownload table for
updates and writes them to the downloads table via DownloadProgressTracker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from haven_cli.database.models import TorrentDownload, Video
from haven_tui.data.download_tracker import (
    DownloadProgress,
    DownloadProgressTracker,
    DownloadStatus,
)

logger = logging.getLogger(__name__)


class BitTorrentProgressBridge:
    """
    Bridges TorrentDownload model to DownloadProgressTracker.
    
    Polls database for torrent updates and writes to downloads table.
    Also provides hooks for libtorrent session alerts for real-time updates.
    
    Example:
        bridge = BitTorrentProgressBridge(tracker, db_session_factory)
        await bridge.start()
        # Bridge now polls and syncs progress automatically
        await bridge.stop()
    """
    
    def __init__(
        self,
        tracker: DownloadProgressTracker,
        db_session_factory: Callable,
        poll_interval: float = 1.0,
    ):
        """Initialize the BitTorrent progress bridge.
        
        Args:
            tracker: The DownloadProgressTracker to report progress to
            db_session_factory: Factory function that returns a database session
            poll_interval: How often to poll for updates (seconds)
        """
        self.tracker = tracker
        self.db_session_factory = db_session_factory
        self.poll_interval = poll_interval
        self._polling = False
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update: Dict[str, datetime] = {}
    
    async def start(self) -> None:
        """Start monitoring torrent downloads."""
        if self._polling:
            logger.warning("Bridge already started")
            return
        
        self._polling = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("BitTorrent progress bridge started")
    
    async def stop(self) -> None:
        """Stop monitoring."""
        if not self._polling:
            return
        
        self._polling = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.info("BitTorrent progress bridge stopped")
    
    async def _poll_loop(self) -> None:
        """Poll TorrentDownload table and write to downloads table."""
        completed_sync_counter = 0
        while self._polling:
            try:
                await self._sync_active_torrents()
                
                # Sync completed torrents less frequently (every 30 polls ~ 30 seconds)
                completed_sync_counter += 1
                if completed_sync_counter >= 30:
                    await self._sync_completed_torrents()
                    completed_sync_counter = 0
                
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Torrent bridge error: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def _sync_active_torrents(self) -> None:
        """Sync active torrents from TorrentDownload table to downloads table."""
        try:
            with self.db_session_factory() as session:
                # Query active torrents (include skipped for TUI visibility)
                active_torrents = session.query(TorrentDownload).filter(
                    TorrentDownload.status.in_([
                        "downloading", "paused", "checking", "skipped"
                    ])
                ).all()
                
                for torrent in active_torrents:
                    try:
                        progress = self._torrent_to_progress(torrent, session)
                        
                        # Only report if changed (based on last_activity)
                        last_update = self._last_update.get(torrent.infohash)
                        if (last_update is None or 
                            torrent.last_activity > last_update):
                            
                            self.tracker.report_progress(progress)
                            self._last_update[torrent.infohash] = datetime.now(timezone.utc)
                    except Exception as e:
                        logger.warning(f"Error processing torrent {torrent.infohash[:16]}...: {e}")
        
        except Exception as e:
            logger.error(f"Error syncing active torrents: {e}")
            raise
    
    async def _sync_completed_torrents(self) -> None:
        """Sync completed torrents to downloads table to preserve completion timestamps.
        
        Completed torrents only need to be synced once to ensure the downloads table
        has the correct completed_at timestamp from the torrent_downloads table.
        """
        try:
            with self.db_session_factory() as session:
                # Query recently completed torrents (last 24 hours) that haven't been synced
                from datetime import timedelta
                since = datetime.now(timezone.utc) - timedelta(hours=24)
                
                completed_torrents = session.query(TorrentDownload).filter(
                    TorrentDownload.status == "completed",
                    TorrentDownload.completed_at >= since
                ).all()
                
                for torrent in completed_torrents:
                    try:
                        # Only sync if we haven't seen this completed torrent before
                        # or if it was recently completed
                        last_update = self._last_update.get(torrent.infohash)
                        if last_update is None:
                            progress = self._torrent_to_progress(torrent, session)
                            self.tracker.report_progress(progress)
                            self._last_update[torrent.infohash] = datetime.now(timezone.utc)
                            logger.debug(f"Synced completed torrent {torrent.infohash[:16]}...")
                    except Exception as e:
                        logger.warning(f"Error syncing completed torrent {torrent.infohash[:16]}...: {e}")
        
        except Exception as e:
            logger.error(f"Error syncing completed torrents: {e}")
            # Don't raise - completed torrent sync is best-effort
    
    def _torrent_to_progress(
        self,
        torrent: TorrentDownload,
        session,
    ) -> DownloadProgress:
        """Convert TorrentDownload to DownloadProgress for downloads table.
        
        Args:
            torrent: TorrentDownload model instance
            session: Database session for querying related data
            
        Returns:
            DownloadProgress object ready for the downloads table
        """
        # Map torrent status to download status
        status_map = {
            "downloading": DownloadStatus.DOWNLOADING,
            "paused": DownloadStatus.PAUSED,
            "completed": DownloadStatus.COMPLETED,
            "failed": DownloadStatus.FAILED,
            "stalled": DownloadStatus.STALLED,
            "checking": DownloadStatus.VERIFYING,
            "skipped": DownloadStatus.SKIPPED,
        }
        
        # Find associated video if exists
        video_id = None
        if torrent.output_path:
            video = session.query(Video).filter_by(
                source_path=torrent.output_path
            ).first()
            if video:
                video_id = video.id
        
        # Calculate ETA
        eta_seconds = None
        if torrent.download_rate > 0 and torrent.total_size > torrent.downloaded_size:
            remaining = torrent.total_size - torrent.downloaded_size
            eta_seconds = int(remaining / torrent.download_rate)
        
        return DownloadProgress(
            source_id=torrent.infohash,
            source_type="bittorrent",
            video_id=video_id,
            title=torrent.title or torrent.infohash[:16],
            uri=torrent.magnet_uri or "",
            total_size=torrent.total_size,
            downloaded=torrent.downloaded_size,
            progress_pct=torrent.progress * 100,
            download_rate=float(torrent.download_rate),
            download_rate_avg=float(torrent.download_rate),  # Use current as avg for now
            upload_rate=float(torrent.upload_rate),
            eta_seconds=eta_seconds,
            started_at=torrent.started_at,
            completed_at=torrent.completed_at,
            updated_at=torrent.last_activity,
            connections=torrent.peers,
            seeds=torrent.seeds,
            leechers=torrent.peers - torrent.seeds if torrent.peers >= torrent.seeds else 0,
            status=status_map.get(torrent.status, DownloadStatus.PENDING),
            error_message=torrent.error_message,
            metadata={
                "infohash": torrent.infohash,
                "resume_data_available": bool(torrent.resume_data),
                "save_path": torrent.output_path,
                "source_id": torrent.source_id,
                "selected_file_index": torrent.selected_file_index,
            }
        )
    
    def on_torrent_alert(self, infohash: str, alert_data: Dict[str, Any]) -> None:
        """Handle libtorrent alert for real-time updates.
        
        This method can be called from the BitTorrent plugin's alert handler
        for more responsive updates than polling alone.
        
        Args:
            infohash: The torrent infohash
            alert_data: Dictionary with alert information (status, progress, etc.)
        """
        try:
            with self.db_session_factory() as session:
                torrent = session.query(TorrentDownload).filter_by(
                    infohash=infohash
                ).first()
                
                if torrent:
                    # Update torrent with alert data
                    if "progress" in alert_data:
                        torrent.progress = alert_data["progress"]
                    if "download_rate" in alert_data:
                        torrent.download_rate = alert_data["download_rate"]
                    if "upload_rate" in alert_data:
                        torrent.upload_rate = alert_data["upload_rate"]
                    if "peers" in alert_data:
                        torrent.peers = alert_data["peers"]
                    if "seeds" in alert_data:
                        torrent.seeds = alert_data["seeds"]
                    if "downloaded_size" in alert_data:
                        torrent.downloaded_size = alert_data["downloaded_size"]
                    
                    torrent.last_activity = datetime.now(timezone.utc)
                    session.commit()
                    
                    # Convert and report progress
                    progress = self._torrent_to_progress(torrent, session)
                    self.tracker.report_progress(progress)
                    self._last_update[infohash] = datetime.now(timezone.utc)
        
        except Exception as e:
            logger.warning(f"Error handling torrent alert for {infohash[:16]}...: {e}")
    
    async def sync_torrent(self, infohash: str) -> Optional[DownloadProgress]:
        """Manually sync a specific torrent.
        
        Args:
            infohash: The torrent infohash to sync
            
        Returns:
            DownloadProgress if torrent found, None otherwise
        """
        try:
            with self.db_session_factory() as session:
                torrent = session.query(TorrentDownload).filter_by(
                    infohash=infohash
                ).first()
                
                if torrent:
                    progress = self._torrent_to_progress(torrent, session)
                    self.tracker.report_progress(progress)
                    self._last_update[infohash] = datetime.now(timezone.utc)
                    return progress
                
                return None
        
        except Exception as e:
            logger.error(f"Error syncing torrent {infohash[:16]}...: {e}")
            raise
    
    def clear_cache(self) -> None:
        """Clear the last update cache."""
        self._last_update.clear()
