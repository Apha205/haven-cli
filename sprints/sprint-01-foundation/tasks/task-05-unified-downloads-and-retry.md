# Task 5: Unified Downloads View & Per-Stage Retry

## Overview
Implement the unified download view and per-stage retry logic. The unified view combines YouTube and BitTorrent downloads into a single interface. The retry logic allows users to retry specific pipeline stages.

## Requirements

### Unified Download View

Extend `PipelineInterface` with:
```python
def get_active_downloads() -> List[UnifiedDownload]
def get_download_history(limit: int = 50) -> List[UnifiedDownload]
def get_download_stats() -> DownloadStats

@dataclass
class DownloadStats:
    """Aggregate download statistics."""
    active_count: int
    pending_count: int
    completed_today: int
    failed_count: int
    total_speed: int  # bytes/sec
    
    # Breakdown by source
    youtube_active: int
    torrent_active: int
    
    # Speed by source
    youtube_speed: int
    torrent_speed: int
```

### UnifiedDownload Model (from Task 2)
```python
@dataclass
class UnifiedDownload:
    """Combined view of YouTube and BitTorrent downloads."""
    id: int  # download job ID
    video_id: int
    source_type: str  # "youtube" | "torrent"
    title: str
    
    # Status
    status: str  # "pending" | "active" | "paused" | "completed" | "failed"
    status_message: Optional[str]  # Error message or status detail
    
    # Progress
    progress_percent: float
    speed: int  # bytes/sec
    eta: Optional[int]  # seconds
    
    # Size
    total_bytes: Optional[int]
    downloaded_bytes: int
    
    # Timing
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    # Source-specific
    youtube_url: Optional[str] = None
    youtube_format: Optional[str] = None
    
    torrent_magnet: Optional[str] = None
    torrent_info_hash: Optional[str] = None
    torrent_peers: Optional[int] = None
    torrent_seeds: Optional[int] = None
    torrent_ratio: Optional[float] = None
```

### Per-Stage Retry Logic

Extend `PipelineInterface` with:
```python
async def retry_video(video_id: int, stage: Optional[str] = None) -> RetryResult
"""Retry a video from a specific stage.

Args:
    video_id: The video to retry
    stage: Specific stage to retry ("download", "encrypt", "upload", "sync", "analysis")
           If None, retries from the failed stage or the beginning

Returns:
    RetryResult with success status and message
"""

async def cancel_video(video_id: int) -> bool
"""Cancel all operations for a video."""

def pause_download(video_id: int) -> bool
"""Pause an active download."""

def resume_download(video_id: int) -> bool
"""Resume a paused download."""

@dataclass
class RetryResult:
    success: bool
    message: str
    new_job_id: Optional[int] = None
```

### Pipeline Stage Retry Logic
```python
class PipelineInterface:
    async def retry_video(self, video_id: int, stage: Optional[str] = None) -> RetryResult:
        """Retry video from specified stage.
        
        Logic:
        1. If stage is None, find the first failed stage or start from beginning
        2. Reset the specified stage status to "pending"
        3. Reset all subsequent stages to "pending"
        4. Trigger pipeline continuation
        """
        # Implementation
```

### Deliverables
- [ ] Implement unified download query combining YouTube + torrent tables
- [ ] Implement `DownloadStats` aggregation
- [ ] Implement `retry_video()` with per-stage support
- [ ] Implement `cancel_video()` 
- [ ] Implement `pause_download()` and `resume_download()`
- [ ] Write unit tests
- [ ] Write integration tests with database

## Technical Details

### Unified Query Implementation
```python
async def get_active_downloads(self) -> List[UnifiedDownload]:
    """Combine YouTube downloads and torrent downloads."""
    downloads = []
    
    # Query YouTube downloads
    youtube_downloads = await self._get_youtube_downloads(active_only=True)
    for d in youtube_downloads:
        downloads.append(UnifiedDownload(
            id=d.id,
            video_id=d.video_id,
            source_type="youtube",
            title=d.video.title,
            status=self._map_status(d.status),
            progress_percent=d.progress_percent,
            speed=d.speed,
            eta=d.eta,
            total_bytes=d.total_bytes,
            downloaded_bytes=d.downloaded_bytes,
            created_at=d.created_at,
            started_at=d.started_at,
            youtube_url=d.video.source_url,
            youtube_format=d.format_id,
        ))
    
    # Query torrent downloads
    torrent_downloads = await self._get_torrent_downloads(active_only=True)
    for d in torrent_downloads:
        downloads.append(UnifiedDownload(
            id=d.id,
            video_id=d.video_id,
            source_type="torrent",
            title=d.video.title,
            status=self._map_torrent_status(d.status),
            progress_percent=d.progress_percent,
            speed=d.download_speed,
            eta=d.eta,
            total_bytes=d.total_size,
            downloaded_bytes=d.downloaded_size,
            created_at=d.created_at,
            started_at=d.started_at,
            torrent_magnet=d.magnet_uri,
            torrent_info_hash=d.info_hash,
            torrent_peers=d.num_peers,
            torrent_seeds=d.num_seeds,
            torrent_ratio=d.ratio,
        ))
    
    # Sort by created_at desc
    downloads.sort(key=lambda d: d.created_at, reverse=True)
    return downloads
```

### Stage Retry Implementation
```python
async def retry_video(self, video_id: int, stage: Optional[str] = None) -> RetryResult:
    """Retry video from specified stage."""
    video_repo = self.get_video_repository()
    video = await video_repo.get_by_id(video_id)
    
    if not video:
        return RetryResult(success=False, message=f"Video {video_id} not found")
    
    # Determine which stage to retry
    if stage is None:
        stage = self._find_failed_stage(video) or "download"
    
    # Validate stage
    valid_stages = ["download", "encrypt", "upload", "sync", "analysis"]
    if stage not in valid_stages:
        return RetryResult(success=False, message=f"Invalid stage: {stage}")
    
    # Reset stage and all subsequent stages
    await self._reset_stage_and_following(video_id, stage)
    
    # Trigger pipeline continuation
    # This would call into PipelineManager to restart processing
    
    return RetryResult(
        success=True, 
        message=f"Retrying video from {stage} stage",
        new_job_id=None  # Set if new job created
    )

async def _reset_stage_and_following(self, video_id: int, from_stage: str):
    """Reset stage status to pending for stage and all following stages."""
    stage_order = ["download", "encrypt", "upload", "sync", "analysis"]
    start_idx = stage_order.index(from_stage)
    stages_to_reset = stage_order[start_idx:]
    
    for stage in stages_to_reset:
        await self._reset_stage(video_id, stage)
```

## Dependencies
- Task 2: Pipeline Core Interface Library (base structure)
- Task 3: State Manager (for state updates after retry)

## Estimated Effort
1 day

## Acceptance Criteria
- [ ] Unified download view shows both YouTube and torrent downloads
- [ ] Downloads sorted by created_at desc
- [ ] Download stats aggregate correctly by source type
- [ ] `retry_video()` works with and without stage parameter
- [ ] Retry resets correct stages and triggers pipeline
- [ ] `cancel_video()` stops all operations for video
- [ ] `pause_download()` and `resume_download()` work for active downloads
- [ ] Unit tests cover retry logic for each stage
- [ ] Integration test shows retry works end-to-end

## Related
- Parent: Sprint 01 - Foundation
- Previous: Task 4 (Metrics Collector)
- Next: Task 6 (Integration & Testing)
- Gap Analysis: Section "Task 11: Pipeline Core Interface Library" (unified downloads, retry)
