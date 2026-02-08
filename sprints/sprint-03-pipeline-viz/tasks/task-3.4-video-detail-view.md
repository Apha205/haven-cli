# Task 3.4: Video Detail View

**Priority:** High
**Estimated Effort:** 3 days

**Description:**
Create a detailed view for a single video showing complete pipeline state from all job tables, similar to aria2tui's download detail view.

**Implementation:**
```python
# src/haven_tui/ui/views/video_detail.py

class VideoDetailView:
    """Detailed view for a single video's pipeline state from job tables."""
    
    def __init__(self, job_repo: JobHistoryRepository):
        self.job_repo = job_repo
    
    def render(self, stdscr, video_id: int):
        """Render video details by querying job tables."""
        # Fetch complete history from all job tables
        history = self.job_repo.get_video_pipeline_history(video_id)
        
        # Get latest CID from upload_jobs
        latest_cid = self.job_repo.get_latest_cid(video_id)
        
        # Check encryption status from encryption_jobs
        is_encrypted = self.job_repo.is_encrypted(video_id)
        
        max_y, max_x = stdscr.getmaxyx()
        
        # Header
        video = self._get_video(video_id)
        title = f"Video: {video.title[:max_x-10] if video else 'Unknown'}"
        stdscr.addstr(1, 2, title, curses.A_BOLD)
        
        # Basic info section
        y = 3
        stdscr.addstr(y, 2, "Basic Information", curses.A_UNDERLINE)
        stdscr.addstr(y + 1, 4, f"Source: {video.source_path if video else 'N/A'}")
        stdscr.addstr(y + 2, 4, f"Size: {self._format_size(video.file_size if video else 0)}")
        stdscr.addstr(y + 3, 4, f"Plugin: {video.plugin_name if video else 'unknown'}")
        
        # Pipeline stages section - from job tables
        y = 9
        stdscr.addstr(y, 2, "Pipeline Progress", curses.A_UNDERLINE)
        
        # Show download stage from downloads table
        downloads = history.get('downloads', [])
        if downloads:
            latest_download = downloads[0]  # Most recent
            self._render_stage_line(stdscr, y + 2, "download", latest_download)
        
        # Show analysis from analysis_jobs table
        analysis_jobs = history.get('analysis_jobs', [])
        if analysis_jobs:
            self._render_stage_line(stdscr, y + 3, "analysis", analysis_jobs[0])
        
        # Show encryption from encryption_jobs table
        encryption_jobs = history.get('encryption_jobs', [])
        if encryption_jobs:
            self._render_stage_line(stdscr, y + 4, "encrypt", encryption_jobs[0])
        
        # Show upload from upload_jobs table
        upload_jobs = history.get('upload_jobs', [])
        if upload_jobs:
            self._render_stage_line(stdscr, y + 5, "upload", upload_jobs[0])
        
        # Show sync from sync_jobs table
        sync_jobs = history.get('sync_jobs', [])
        if sync_jobs:
            self._render_stage_line(stdscr, y + 6, "sync", sync_jobs[0])
        
        # Results section - from job tables
        y = y + 8
        stdscr.addstr(y, 2, "Results", curses.A_UNDERLINE)
        if latest_cid:
            stdscr.addstr(y + 1, 4, f"IPFS CID: {latest_cid}")
        if is_encrypted:
            stdscr.addstr(y + 2, 4, "Encrypted: Yes (Lit Protocol)")
        if analysis_jobs and analysis_jobs[0].status == "completed":
            stdscr.addstr(y + 3, 4, "AI Analysis: Complete")
    
    def _render_stage_line(self, stdscr, y: int, stage_name: str, job):
        """Render a single stage line from job table record."""
        status_symbol = self._status_symbol(job.status)
        stdscr.addstr(y, 4, f"{status_symbol} {stage_name:12}")
        
        # Progress bar
        progress = getattr(job, 'progress_percent', 0) or 0
        progress_bar = self._mini_progress_bar(progress, 20)
        stdscr.addstr(y, 20, progress_bar)
        
        # Status details
        if job.status == "downloading":
            speed = getattr(job, 'download_rate', 0) or 0
            detail = f"{progress:.1f}% {self._format_speed(speed)}"
            if hasattr(job, 'eta_seconds') and job.eta_seconds:
                detail += f" ETA: {self._format_duration(job.eta_seconds)}"
        elif job.status == "completed" and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds() if job.started_at else 0
            detail = f"Done in {self._format_duration(duration)}"
        elif job.status == "failed":
            detail = f"Error: {job.error_message[:30] if job.error_message else 'Unknown'}"
        else:
            detail = job.status
        
        stdscr.addstr(y, 45, detail)
    
    def _status_symbol(self, status: str) -> str:
        """Get Unicode symbol for status."""
        return {
            "pending": "○",
            "downloading": "◐",
            "encrypting": "◐",
            "uploading": "◐",
            "analyzing": "◐",
            "completed": "●",
            "failed": "✗",
        }.get(status, "?")
```

**Visual Design:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Video: Big Buck Bunny - Blender Foundation                               │
├─────────────────────────────────────────────────────────────────────────┤
│ Basic Information                                                        │
│   Source: /home/user/videos/Big_Buck_Bunny_1080p.mp4                    │
│   Size: 450.2 MB                                                         │
│   Plugin: youtube                                                        │
│                                                                          │
│ Pipeline Progress                                                        │
│   ● download    ████████████████████ Done in 2m 34s                     │
│   ● ingest      ████████████████████ Done in 0m 12s                     │
│   ⊘ analysis    ░░░░░░░░░░░░░░░░░░░░ Skipped                            │
│   ● encrypt     ████████████████████ Done in 1m 45s                     │
│   ◐ upload      ████████████████░░░░ 82% 1.1MB/s ETA: 0m 45s            │
│   ○ sync        ░░░░░░░░░░░░░░░░░░░░ Pending                            │
│                                                                          │
│ Results                                                                  │
│   IPFS CID: bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55f... │
│   Encrypted: Yes (Lit Protocol)                                         │
│                                                                          │
│ [b Back] [r Retry failed stages] [l View logs]                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Queries all job tables (downloads, analysis_jobs, encryption_jobs, upload_jobs, sync_jobs)
- [ ] Shows all pipeline stages with status from respective tables
- [ ] Progress bar for each stage from job records
- [ ] Timing information (duration for completed, ETA for active)
- [ ] Error messages for failed stages from job.error_message
- [ ] Final results (CID from upload_jobs, encryption status, etc.)
- [ ] Navigation back to list view
