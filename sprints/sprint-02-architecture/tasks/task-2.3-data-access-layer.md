# Task 2.3: Data Access Layer (Repository Pattern)

**Priority:** Critical
**Estimated Effort:** 3 days

**Description:**
Create repositories for querying video and pipeline data from the haven-cli database using the table-based design.

### Snapshot Repository (Main Query Interface)

```python
# src/haven_tui/data/repositories.py
from sqlalchemy.orm import Session, joinedload
from haven_cli.database.models import (
    Video, Download, EncryptionJob, UploadJob, 
    SyncJob, AnalysisJob, PipelineSnapshot, SpeedHistory
)
from haven_tui.models.video_view import VideoView, PipelineStage, StageInfo

class PipelineSnapshotRepository:
    """
    Repository for querying pipeline state via PipelineSnapshot table.
    
    This is the primary interface for the TUI main view - single table query
    for efficient polling.
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_active_videos(self, limit: int = 1000) -> list[VideoView]:
        """Get videos currently in pipeline (not completed/failed)."""
        snapshots = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.overall_status.in_(["active", "pending"])
        ).order_by(
            PipelineSnapshot.stage_started_at.desc().nulls_last()
        ).limit(limit).all()
        
        return [self._snapshot_to_view(s) for s in snapshots]
    
    def get_videos_by_stage(self, stage: PipelineStage, limit: int = 100) -> list[VideoView]:
        """Get videos in a specific pipeline stage."""
        snapshots = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.current_stage == stage.value,
            PipelineSnapshot.overall_status == "active"
        ).order_by(
            PipelineSnapshot.stage_started_at.desc()
        ).limit(limit).all()
        
        return [self._snapshot_to_view(s) for s in snapshots]
    
    def get_video_summary(self, video_id: int) -> Optional[VideoView]:
        """Get current state for a single video."""
        snapshot = self.session.query(PipelineSnapshot).filter_by(
            video_id=video_id
        ).first()
        
        if snapshot:
            return self._snapshot_to_view(snapshot)
        return None
    
    def get_aggregate_stats(self) -> dict:
        """Get stats for TUI header bar."""
        from sqlalchemy import func, case
        
        result = self.session.query(
            func.count().label('total_active'),
            func.sum(PipelineSnapshot.stage_speed).label('total_speed'),
            func.count(case((PipelineSnapshot.current_stage == 'download', 1))).label('downloading'),
            func.count(case((PipelineSnapshot.current_stage == 'encrypt', 1))).label('encrypting'),
            func.count(case((PipelineSnapshot.current_stage == 'upload', 1))).label('uploading'),
            func.sum(case((PipelineSnapshot.has_error == True, 1))).label('errors'),
        ).filter(
            PipelineSnapshot.overall_status == 'active'
        ).first()
        
        return {
            'active_count': result.total_active or 0,
            'total_speed': result.total_speed or 0,
            'by_stage': {
                'download': result.downloading or 0,
                'encrypt': result.encrypting or 0,
                'upload': result.uploading or 0,
            },
            'error_count': result.errors or 0,
        }
    
    def _snapshot_to_view(self, snapshot: PipelineSnapshot) -> VideoView:
        """Convert snapshot to TUI view model."""
        return VideoView(
            id=snapshot.video_id,
            title=snapshot.video.title if snapshot.video else "Unknown",
            source_path=snapshot.video.source_path if snapshot.video else "",
            current_stage=PipelineStage(snapshot.current_stage),
            stage_progress=snapshot.stage_progress_percent or 0,
            stage_speed=snapshot.stage_speed or 0,
            stage_eta=snapshot.stage_eta,
            overall_status=snapshot.overall_status,
            has_error=snapshot.has_error,
            error_message=snapshot.error_message,
            file_size=snapshot.total_bytes or 0,
            plugin=snapshot.video.plugin_name if snapshot.video else "unknown",
        )
```

### Download Repository

```python
class DownloadRepository:
    """Repository for download-specific queries."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_active_downloads(self) -> list[Download]:
        """Get all active downloads with video info."""
        return self.session.query(Download).options(
            joinedload(Download.video)
        ).filter(
            Download.status == "downloading"
        ).all()
    
    def get_download_by_video(self, video_id: int) -> Optional[Download]:
        """Get latest download record for a video."""
        return self.session.query(Download).filter_by(
            video_id=video_id
        ).order_by(
            Download.created_at.desc()
        ).first()
    
    def get_aggregate_download_speed(self) -> int:
        """Sum of all active download rates for TUI header."""
        result = self.session.query(
            func.sum(Download.download_rate)
        ).filter(
            Download.status == "downloading"
        ).scalar()
        return result or 0
```

### Job History Repository

```python
class JobHistoryRepository:
    """For TUI detail view - get complete job history for a video."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_video_pipeline_history(self, video_id: int) -> dict:
        """Get all jobs for a video across all stages."""
        return {
            'downloads': self.session.query(Download).filter_by(
                video_id=video_id
            ).order_by(Download.created_at.desc()).all(),
            
            'analysis_jobs': self.session.query(AnalysisJob).filter_by(
                video_id=video_id
            ).order_by(AnalysisJob.created_at.desc()).all(),
            
            'encryption_jobs': self.session.query(EncryptionJob).filter_by(
                video_id=video_id
            ).order_by(EncryptionJob.created_at.desc()).all(),
            
            'upload_jobs': self.session.query(UploadJob).filter_by(
                video_id=video_id
            ).order_by(UploadJob.created_at.desc()).all(),
            
            'sync_jobs': self.session.query(SyncJob).filter_by(
                video_id=video_id
            ).order_by(SyncJob.created_at.desc()).all(),
        }
    
    def get_latest_cid(self, video_id: int) -> Optional[str]:
        """Get the most recent successful upload CID."""
        upload = self.session.query(UploadJob).filter_by(
            video_id=video_id,
            status="completed"
        ).order_by(
            UploadJob.completed_at.desc().nulls_last()
        ).first()
        
        return upload.remote_cid if upload else None
    
    def is_encrypted(self, video_id: int) -> bool:
        """Check if video has completed encryption."""
        return self.session.query(EncryptionJob).filter_by(
            video_id=video_id,
            status="completed"
        ).first() is not None
```

### Speed History Repository

```python
class SpeedHistoryRepository:
    """Repository for speed history queries (for graphing)."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_speed_history(self, video_id: int, stage: str, 
                          minutes: int = 5) -> list[SpeedHistory]:
        """Get speed history for graphing."""
        since = datetime.now() - timedelta(minutes=minutes)
        
        return self.session.query(SpeedHistory).filter(
            SpeedHistory.video_id == video_id,
            SpeedHistory.stage == stage,
            SpeedHistory.timestamp >= since
        ).order_by(SpeedHistory.timestamp).all()
    
    def get_aggregate_speeds(self, minutes: int = 5) -> dict:
        """Get aggregate download/upload speeds over time for header graph."""
        since = datetime.now() - timedelta(minutes=minutes)
        
        from sqlalchemy import func
        
        # Group by 10-second buckets
        results = self.session.query(
            func.strftime('%Y-%m-%d %H:%M:%S', 
                func.datetime(SpeedHistory.timestamp, 'start of minute'),
                '+' + func.cast(func.strftime('%S', SpeedHistory.timestamp) / 10 * 10, 'text') + ' seconds'
            ).label('bucket'),
            SpeedHistory.stage,
            func.avg(SpeedHistory.speed).label('avg_speed')
        ).filter(
            SpeedHistory.timestamp >= since
        ).group_by(
            'bucket',
            SpeedHistory.stage
        ).order_by('bucket').all()
        
        return self._transform_for_plotting(results)
```

### Video View Model

```python
# src/haven_tui/models/video_view.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

class PipelineStage(Enum):
    DOWNLOAD = "download"
    INGEST = "ingest"
    ANALYSIS = "analysis"
    ENCRYPT = "encrypt"
    UPLOAD = "upload"
    SYNC = "sync"
    COMPLETE = "complete"

class StageStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class VideoView:
    """Aggregated view of video for TUI display from PipelineSnapshot."""
    id: int
    title: str
    source_path: str
    current_stage: PipelineStage
    stage_progress: float  # 0.0 - 100.0
    stage_speed: int       # bytes/sec (if applicable)
    stage_eta: Optional[int]  # seconds remaining
    overall_status: str    # "active", "pending", "completed", "failed"
    has_error: bool
    error_message: Optional[str]
    file_size: int
    plugin: str
    
    @property
    def is_complete(self) -> bool:
        """Check if video completed all pipeline stages."""
        return self.current_stage == PipelineStage.COMPLETE
    
    @property
    def formatted_speed(self) -> str:
        """Format speed for display."""
        if self.stage_speed == 0:
            return "-"
        return self._human_readable_bytes(self.stage_speed) + "/s"
    
    @property
    def formatted_eta(self) -> str:
        """Format ETA for display."""
        if self.stage_eta is None:
            return "--:--"
        minutes, seconds = divmod(self.stage_eta, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h{minutes:02d}m"
        return f"{minutes}:{seconds:02d}"
    
    def _human_readable_bytes(self, size: int) -> str:
        """Convert bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
```

**Acceptance Criteria:**
- [ ] `PipelineSnapshotRepository.get_active_videos()` queries single table efficiently
- [ ] `PipelineSnapshotRepository.get_aggregate_stats()` provides header data
- [ ] `JobHistoryRepository` can fetch complete job timeline
- [ ] All repositories use proper SQLAlchemy relationships
- [ ] Pagination support for large datasets
