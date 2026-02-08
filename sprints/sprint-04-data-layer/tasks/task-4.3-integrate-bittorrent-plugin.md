# Task 4.3: Integrate BitTorrent Plugin with Download Table

**Priority:** P0 (Critical)  
**Owner:** Backend Engineer  
**Effort:** 2 days

**Description:**
Bridge existing TorrentDownload tracking to write unified progress to the `downloads` table alongside the legacy TorrentDownload table.

**Implementation:**

```python
# src/haven_tui/data/torrent_bridge.py

class BitTorrentProgressBridge:
    """
    Bridges TorrentDownload model to DownloadProgressTracker.
    
    Polls database for torrent updates and writes to downloads table.
    Also forwards libtorrent session alerts in real-time.
    """
    
    def __init__(self, tracker: DownloadProgressTracker, db_session_factory):
        self.tracker = tracker
        self.db_session_factory = db_session_factory
        self._polling = False
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update: Dict[str, datetime] = {}
    
    async def start(self):
        """Start monitoring torrent downloads."""
        self._polling = True
        self._poll_task = asyncio.create_task(self._poll_loop())
    
    async def stop(self):
        """Stop monitoring."""
        self._polling = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
    
    async def _poll_loop(self):
        """Poll TorrentDownload table and write to downloads table."""
        while self._polling:
            try:
                with self.db_session_factory() as session:
                    active_torrents = session.query(TorrentDownload).filter(
                        TorrentDownload.status.in_([
                            "downloading", "paused", "checking"
                        ])
                    ).all()
                    
                    for torrent in active_torrents:
                        progress = self._torrent_to_progress(torrent)
                        
                        # Only report if changed
                        last_update = self._last_update.get(torrent.infohash)
                        if (last_update is None or 
                            torrent.last_activity > last_update):
                            
                            self.tracker.report_progress(progress)
                            self._last_update[torrent.infohash] = datetime.utcnow()
                
                await asyncio.sleep(1)  # Poll every second
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Torrent bridge error: {e}")
                await asyncio.sleep(5)
    
    def _torrent_to_progress(self, torrent: TorrentDownload) -> DownloadProgress:
        """Convert TorrentDownload to DownloadProgress for downloads table."""
        # Map torrent status to download status
        status_map = {
            "downloading": DownloadStatus.DOWNLOADING,
            "paused": DownloadStatus.PAUSED,
            "completed": DownloadStatus.COMPLETED,
            "failed": DownloadStatus.FAILED,
            "stalled": DownloadStatus.STALLED,
        }
        
        # Find associated video if exists
        video_id = None
        if torrent.output_path:
            video = self.session.query(Video).filter_by(
                source_path=torrent.output_path
            ).first()
            if video:
                video_id = video.id
        
        return DownloadProgress(
            source_id=torrent.infohash,
            source_type="bittorrent",
            video_id=video_id,
            title=torrent.title or torrent.infohash[:16],
            uri=torrent.magnet_uri or "",
            total_size=torrent.total_size,
            downloaded=torrent.downloaded_size,
            progress_pct=torrent.progress * 100,
            download_rate=torrent.download_rate,
            upload_rate=torrent.upload_rate,
            connections=torrent.peers,
            seeds=torrent.seeds,
            status=status_map.get(torrent.status, DownloadStatus.PENDING),
            started_at=torrent.started_at,
            updated_at=torrent.last_activity,
            metadata={
                "infohash": torrent.infohash,
                "resume_data_available": bool(torrent.resume_data),
                "save_path": torrent.save_path,
            }
        )
    
    def on_torrent_alert(self, alert):
        """Handle libtorrent alert for real-time updates."""
        # This would be called from BitTorrent plugin's alert handler
        # for more responsive updates than polling
        pass
```

**Integration with BitTorrent Plugin:**
```python
# In src/haven_cli/plugins/bittorrent_plugin.py
# Modify existing BitTorrentPlugin class

class BitTorrentPlugin(ArchiverPlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.progress_bridge: Optional[BitTorrentProgressBridge] = None
    
    def set_progress_tracker(self, tracker: DownloadProgressTracker):
        """Set up progress bridge to write to downloads table."""
        self.progress_bridge = BitTorrentProgressBridge(
            tracker, 
            get_db_session
        )
    
    async def initialize(self):
        """Start progress bridge."""
        await super().initialize()
        if self.progress_bridge:
            await self.progress_bridge.start()
    
    async def shutdown(self):
        """Stop progress bridge."""
        if self.progress_bridge:
            await self.progress_bridge.stop()
        await super().shutdown()
```

**Acceptance Criteria:**
- [ ] BitTorrent writes to `downloads` table via bridge
- [ ] Real-time updates via libtorrent alerts (if possible)
- [ ] Progress in unified format in `downloads` table
- [ ] Peer/seeds info included in metadata
- [ ] Handles paused/stalled states correctly
