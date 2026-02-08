# Task 3.2: Stage-Specific Progress Indicators

**Priority:** Critical
**Estimated Effort:** 3 days

**Description:**
Create visual indicators that adapt based on the current pipeline stage, showing relevant metrics from the respective job tables.

**Implementation:**
```python
# src/haven_tui/ui/components/progress_indicators.py

class StageProgressIndicator:
    """Renders stage-specific progress information from job tables."""
    
    STAGE_COLORS = {
        PipelineStage.DOWNLOAD: curses.COLOR_BLUE,
        PipelineStage.INGEST: curses.COLOR_CYAN,
        PipelineStage.ANALYSIS: curses.COLOR_YELLOW,
        PipelineStage.ENCRYPT: curses.COLOR_MAGENTA,
        PipelineStage.UPLOAD: curses.COLOR_GREEN,
        PipelineStage.SYNC: curses.COLOR_WHITE,
    }
    
    def render(self, stdscr, y: int, x: int, video: VideoView, width: int):
        """Render stage progress at position."""
        color = self.STAGE_COLORS.get(video.current_stage, curses.COLOR_WHITE)
        
        if video.current_stage == PipelineStage.DOWNLOAD:
            self._render_download_progress(stdscr, y, x, video, width, color)
        elif video.current_stage == PipelineStage.ENCRYPT:
            self._render_encrypt_progress(stdscr, y, x, video, width, color)
        elif video.current_stage == PipelineStage.UPLOAD:
            self._render_upload_progress(stdscr, y, x, video, width, color)
        else:
            self._render_generic_progress(stdscr, y, x, video, width, color)
    
    def _render_download_progress(self, stdscr, y, x, video: VideoView, width, color):
        """Download stage: query downloads table for extra details."""
        progress_bar = self._make_progress_bar(video.stage_progress, width - 20)
        
        # Basic: "██████░░░░ 45% 2.4MB/s"
        line = f"{progress_bar} {video.stage_progress:.0f}% "
        
        # Query downloads table for source-specific info
        download = self._get_download_details(video.id)
        if download:
            if download.source_type == "bittorrent":
                # Show peers/seeds from downloads table metadata
                peers = download.source_metadata.get("peers", 0)
                seeds = download.source_metadata.get("seeds", 0)
                line += f"↓{seeds} ↑{peers}"
            else:
                # YouTube/direct download - show speed from VideoView
                line += video.formatted_speed
        
        stdscr.addstr(y, x, line[:width], curses.color_pair(color))
    
    def _render_encrypt_progress(self, stdscr, y, x, video: VideoView, width, color):
        """Encryption stage: query encryption_jobs table."""
        progress_bar = self._make_progress_bar(video.stage_progress, width - 25)
        
        # Query encryption_jobs for bytes info
        job = self._get_encryption_job(video.id)
        if job and job.bytes_total:
            enc = self._human_readable_bytes(job.bytes_processed or 0)
            src = self._human_readable_bytes(job.bytes_total)
            size_info = f"{enc}/{src}"
        else:
            size_info = video.formatted_speed
        
        line = f"{progress_bar} {video.stage_progress:.0f}% {size_info}"
        stdscr.addstr(y, x, line[:width], curses.color_pair(color))
    
    def _render_upload_progress(self, stdscr, y, x, video: VideoView, width, color):
        """Upload stage: query upload_jobs table."""
        progress_bar = self._make_progress_bar(video.stage_progress, width - 20)
        
        # Query upload_jobs for target info
        job = self._get_upload_job(video.id)
        if job:
            target = job.target[:8]  # "ipfs", "arkiv", etc.
            line = f"{progress_bar} {video.stage_progress:.0f}% {target}"
        else:
            line = f"{progress_bar} {video.stage_progress:.0f}%"
        
        stdscr.addstr(y, x, line[:width], curses.color_pair(color))
    
    def _get_download_details(self, video_id: int) -> Optional[Download]:
        """Query downloads table for details."""
        # This would be called through repository
        return self.download_repo.get_download_by_video(video_id)
    
    def _get_encryption_job(self, video_id: int) -> Optional[EncryptionJob]:
        """Query encryption_jobs table for details."""
        return self.job_repo.get_latest_encryption_job(video_id)
    
    def _get_upload_job(self, video_id: int) -> Optional[UploadJob]:
        """Query upload_jobs table for details."""
        return self.job_repo.get_latest_upload_job(video_id)
```

**Visual Examples:**
```
# Download stage (BitTorrent) - from downloads table metadata
Download:  ██████░░░░ 45% ↓12 ↑45        # Shows seeds/peers

# Download stage (YouTube) - from downloads table  
Download:  ████████░░ 80% 2.4MB/s        # Shows speed

# Encryption stage - from encryption_jobs table
Encrypt:   ████░░░░░░ 38% 1.2GB/3.2GB    # Shows bytes encrypted/total

# Upload stage - from upload_jobs table
Upload:    ███████░░░ 68% ipfs           # Shows target
Upload:    ████████░░ 82% arkiv          
```

**Acceptance Criteria:**
- [ ] Each stage queries its respective job table for details
- [ ] Download shows peers/seeds for torrents (from downloads.metadata)
- [ ] Encryption shows encrypted size vs original (from encryption_jobs)
- [ ] Upload shows target backend (from upload_jobs.target)
- [ ] Analysis shows frames processed (from analysis_jobs) if available
