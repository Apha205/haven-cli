# Task 4.2: Integrate YouTube Plugin with Download Table

**Priority:** P0 (Critical)  
**Owner:** Backend Engineer  
**Effort:** 2 days

**Description:**
Modify the existing YouTube plugin (within haven-cli) to report download progress through the unified tracker, which writes to the `downloads` table.

**Implementation:**

```python
# In src/haven_cli/plugins/youtube_plugin.py
# Modify existing YouTubePlugin class

from haven_cli.pipeline.download_tracker import DownloadProgressTracker, DownloadProgress

class YouTubePlugin(ArchiverPlugin):
    """YouTube archiver plugin with progress tracking to downloads table."""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.progress_tracker: Optional[DownloadProgressTracker] = None
        self._current_downloads: Dict[str, DownloadProgress] = {}
    
    def set_progress_tracker(self, tracker: DownloadProgressTracker):
        """Inject progress tracker (called by plugin manager)."""
        self.progress_tracker = tracker
    
    async def archive(self, source: MediaSource) -> ArchiveResult:
        """Archive YouTube video with progress tracking to downloads table."""
        # Initialize progress object
        progress = DownloadProgress(
            source_id=source.source_id,
            source_type="youtube",
            title=source.title,
            uri=source.uri,
            status=DownloadStatus.QUEUED,
            metadata={
                "youtube_id": source.source_id,
                "channel": getattr(source, 'channel', None),
            }
        )
        
        self._current_downloads[source.source_id] = progress
        
        # yt-dlp options with progress hook
        ydl_opts = {
            'progress_hooks': [self._make_progress_hook(source.source_id)],
            'logger': self._YTDLPLogger(),
            # ... other options
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source.uri, download=True)
                
                # Update to completed
                progress.status = DownloadStatus.COMPLETED
                progress.progress_pct = 100.0
                progress.total_size = progress.downloaded  # Final size
                self._report_progress(progress)
                
                return ArchiveResult(
                    success=True,
                    output_path=ydl.prepare_filename(info),
                    file_size=progress.total_size,
                )
                
        except Exception as e:
            progress.status = DownloadStatus.FAILED
            progress.error_message = str(e)
            self._report_progress(progress)
            raise
        finally:
            del self._current_downloads[source.source_id]
    
    def _make_progress_hook(self, source_id: str):
        """Create progress hook for yt-dlp that writes to downloads table."""
        def hook(d):
            progress = self._current_downloads.get(source_id)
            if not progress:
                return
            
            if d['status'] == 'downloading':
                progress.status = DownloadStatus.DOWNLOADING
                progress.downloaded = d.get('downloaded_bytes', 0)
                progress.total_size = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                
                # Calculate progress percentage
                if progress.total_size > 0:
                    progress.progress_pct = (progress.downloaded / progress.total_size) * 100
                
                # Speed and ETA
                progress.download_rate = d.get('speed', 0) or 0
                progress.eta_seconds = d.get('eta')
                progress.connections = 1  # yt-dlp doesn't expose connection count easily
                
                # Parse percentage string if available
                if '_percent_str' in d:
                    try:
                        progress.progress_pct = float(d['_percent_str'].replace('%', ''))
                    except ValueError:
                        pass
                
                # Update timestamps
                if progress.started_at is None:
                    progress.started_at = datetime.utcnow()
                progress.updated_at = datetime.utcnow()
                
                self._report_progress(progress)
                
            elif d['status'] == 'finished':
                progress.status = DownloadStatus.VERIFYING
                self._report_progress(progress)
        
        return hook
    
    def _report_progress(self, progress: DownloadProgress):
        """Report progress to tracker (writes to downloads table)."""
        if self.progress_tracker:
            self.progress_tracker.report_progress(progress)
```

**Acceptance Criteria:**
- [ ] YouTube plugin writes to `downloads` table via DownloadProgressTracker
- [ ] Progress updates in real-time during download
- [ ] Speed and ETA calculated correctly
- [ ] Failed downloads report error status
- [ ] No yt-dlp output pollution in TUI
