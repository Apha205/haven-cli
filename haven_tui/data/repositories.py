"""Data Access Layer for Haven TUI (Repository Pattern).

Provides repositories for querying video and pipeline data from the haven-cli database
using the table-based design. Optimized for TUI display and polling efficiency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case, desc, literal

from haven_cli.database.models import (
    Video, Download, EncryptionJob, UploadJob,
    SyncJob, AnalysisJob, PipelineSnapshot, SpeedHistory
)
from haven_tui.models.video_view import VideoView, PipelineStage, StageInfo, StageStatus


class PipelineSnapshotRepository:
    """
    Repository for querying pipeline state via PipelineSnapshot table.

    This is the primary interface for the TUI main view - single table query
    for efficient polling.
    """

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def get_active_videos(self, limit: int = 1000, offset: int = 0) -> List[VideoView]:
        """Get videos currently in pipeline (not completed/failed).

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of VideoView objects for active videos
        """
        query = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.overall_status.in_(["active", "pending"])
        ).order_by(
            desc(PipelineSnapshot.stage_started_at)
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        snapshots = query.all()
        return [self._snapshot_to_view(s) for s in snapshots]

    def get_videos_by_stage(self, stage: PipelineStage, limit: int = 100, offset: int = 0) -> List[VideoView]:
        """Get videos in a specific pipeline stage.

        Args:
            stage: Pipeline stage to filter by
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of VideoView objects for videos in the specified stage
        """
        query = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.current_stage == stage.value,
            PipelineSnapshot.overall_status == "active"
        ).order_by(
            desc(PipelineSnapshot.stage_started_at)
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        snapshots = query.all()
        return [self._snapshot_to_view(s) for s in snapshots]

    def get_video_summary(self, video_id: int) -> Optional[VideoView]:
        """Get current state for a single video.

        Args:
            video_id: Video ID to look up

        Returns:
            VideoView if found, None otherwise
        """
        snapshot = self.session.query(PipelineSnapshot).filter_by(
            video_id=video_id
        ).first()

        if snapshot:
            return self._snapshot_to_view(snapshot)
        return None

    def get_videos_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[VideoView]:
        """Get videos by overall status.

        Args:
            status: Overall status to filter by ("active", "pending", "completed", "failed")
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of VideoView objects with the specified status
        """
        query = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.overall_status == status
        ).order_by(
            desc(PipelineSnapshot.updated_at)
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        snapshots = query.all()
        return [self._snapshot_to_view(s) for s in snapshots]

    def get_videos_with_errors(self, limit: int = 100, offset: int = 0) -> List[VideoView]:
        """Get videos that have errors.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of VideoView objects with errors
        """
        query = self.session.query(PipelineSnapshot).filter(
            PipelineSnapshot.has_error == True
        ).order_by(
            desc(PipelineSnapshot.updated_at)
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        snapshots = query.all()
        return [self._snapshot_to_view(s) for s in snapshots]

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get stats for TUI header bar.

        Returns:
            Dictionary with active count, total speed, and stage breakdown
        """
        result = self.session.query(
            func.count().label('total_active'),
            func.sum(PipelineSnapshot.stage_speed).label('total_speed'),
            func.count(case((PipelineSnapshot.current_stage == 'download', 1))).label('downloading'),
            func.count(case((PipelineSnapshot.current_stage == 'encrypt', 1))).label('encrypting'),
            func.count(case((PipelineSnapshot.current_stage == 'upload', 1))).label('uploading'),
            func.count(case((PipelineSnapshot.current_stage == 'sync', 1))).label('syncing'),
            func.count(case((PipelineSnapshot.current_stage == 'analysis', 1))).label('analyzing'),
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
                'sync': result.syncing or 0,
                'analyze': result.analyzing or 0,
            },
            'error_count': result.errors or 0,
        }

    def get_completed_count(self, since: Optional[datetime] = None) -> int:
        """Get count of completed videos.

        Args:
            since: Only count videos completed since this time

        Returns:
            Number of completed videos
        """
        query = self.session.query(func.count(PipelineSnapshot.id)).filter(
            PipelineSnapshot.overall_status == 'completed'
        )

        if since:
            query = query.filter(PipelineSnapshot.pipeline_completed_at >= since)

        return query.scalar() or 0

    def get_failed_count(self) -> int:
        """Get count of failed videos.

        Returns:
            Number of failed videos
        """
        return self.session.query(func.count(PipelineSnapshot.id)).filter(
            PipelineSnapshot.overall_status == 'failed'
        ).scalar() or 0

    def search_videos(self, query: str, limit: int = 50) -> List[VideoView]:
        """Search videos by title in snapshot.

        Note: This joins with Video table for title search.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching VideoView objects
        """
        snapshots = self.session.query(PipelineSnapshot).join(
            Video, PipelineSnapshot.video_id == Video.id
        ).filter(
            Video.title.ilike(f'%{query}%')
        ).limit(limit).all()

        return [self._snapshot_to_view(s) for s in snapshots]

    def _snapshot_to_view(self, snapshot: PipelineSnapshot) -> VideoView:
        """Convert snapshot to TUI view model.

        Args:
            snapshot: PipelineSnapshot database object

        Returns:
            VideoView object
        """
        # Get video data, handling case where video might be None
        video_title = "Unknown"
        source_path = ""
        plugin_name = "unknown"

        if snapshot.video:
            video_title = snapshot.video.title or "Unknown"
            source_path = snapshot.video.source_path or ""
            plugin_name = snapshot.video.plugin_name or "unknown"

        # Handle unknown stages gracefully
        try:
            stage = PipelineStage(snapshot.current_stage)
        except ValueError:
            stage = PipelineStage.PENDING

        return VideoView(
            id=snapshot.video_id,
            title=video_title,
            source_path=source_path,
            current_stage=stage,
            stage_progress=snapshot.stage_progress_percent or 0,
            stage_speed=snapshot.stage_speed or 0,
            stage_eta=snapshot.stage_eta,
            overall_status=snapshot.overall_status,
            has_error=snapshot.has_error,
            error_message=snapshot.error_message,
            file_size=snapshot.total_bytes or 0,
            plugin=plugin_name,
        )


class DownloadRepository:
    """Repository for download-specific queries."""

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def get_active_downloads(self, limit: int = 100) -> List[Download]:
        """Get all active downloads with video info.

        Args:
            limit: Maximum number of results

        Returns:
            List of active Download objects with video loaded
        """
        return self.session.query(Download).options(
            joinedload(Download.video)
        ).filter(
            Download.status == "downloading"
        ).order_by(
            desc(Download.started_at)
        ).limit(limit).all()

    def get_download_by_video(self, video_id: int) -> Optional[Download]:
        """Get latest download record for a video.

        Args:
            video_id: Video ID to look up

        Returns:
            Most recent Download for the video, or None
        """
        return self.session.query(Download).filter_by(
            video_id=video_id
        ).order_by(
            desc(Download.created_at)
        ).first()

    def get_download_history(self, video_id: int, limit: int = 10) -> List[Download]:
        """Get download history for a video.

        Args:
            video_id: Video ID to look up
            limit: Maximum number of results

        Returns:
            List of Download objects ordered by created_at desc
        """
        return self.session.query(Download).filter_by(
            video_id=video_id
        ).order_by(
            desc(Download.created_at)
        ).limit(limit).all()

    def get_aggregate_download_speed(self) -> int:
        """Sum of all active download rates for TUI header.

        Returns:
            Total download speed in bytes/sec
        """
        result = self.session.query(
            func.sum(Download.download_rate)
        ).filter(
            Download.status == "downloading"
        ).scalar()
        return result or 0

    def get_pending_downloads(self, limit: int = 100) -> List[Download]:
        """Get downloads waiting to start.

        Args:
            limit: Maximum number of results

        Returns:
            List of pending Download objects
        """
        return self.session.query(Download).options(
            joinedload(Download.video)
        ).filter(
            Download.status == "pending"
        ).order_by(
            desc(Download.created_at)
        ).limit(limit).all()


class JobHistoryRepository:
    """For TUI detail view - get complete job history for a video."""

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def get_video_pipeline_history(self, video_id: int) -> Dict[str, List[Any]]:
        """Get all jobs for a video across all stages.

        Args:
            video_id: Video ID to look up

        Returns:
            Dictionary with lists of all job types
        """
        return {
            'downloads': self.session.query(Download).filter_by(
                video_id=video_id
            ).order_by(desc(Download.created_at)).all(),

            'analysis_jobs': self.session.query(AnalysisJob).filter_by(
                video_id=video_id
            ).order_by(desc(AnalysisJob.created_at)).all(),

            'encryption_jobs': self.session.query(EncryptionJob).filter_by(
                video_id=video_id
            ).order_by(desc(EncryptionJob.created_at)).all(),

            'upload_jobs': self.session.query(UploadJob).filter_by(
                video_id=video_id
            ).order_by(desc(UploadJob.created_at)).all(),

            'sync_jobs': self.session.query(SyncJob).filter_by(
                video_id=video_id
            ).order_by(desc(SyncJob.created_at)).all(),
        }

    def get_latest_cid(self, video_id: int) -> Optional[str]:
        """Get the most recent successful upload CID.

        Args:
            video_id: Video ID to look up

        Returns:
            CID string if found, None otherwise
        """
        upload = self.session.query(UploadJob).filter_by(
            video_id=video_id,
            status="completed"
        ).order_by(
            desc(UploadJob.completed_at)
        ).first()

        return upload.remote_cid if upload else None

    def is_encrypted(self, video_id: int) -> bool:
        """Check if video has completed encryption.

        Args:
            video_id: Video ID to check

        Returns:
            True if video has a completed encryption job
        """
        return self.session.query(EncryptionJob).filter_by(
            video_id=video_id,
            status="completed"
        ).first() is not None

    def get_encryption_info(self, video_id: int) -> Optional[Dict[str, Any]]:
        """Get encryption information for a video.

        Args:
            video_id: Video ID to look up

        Returns:
            Dictionary with encryption info if found, None otherwise
        """
        job = self.session.query(EncryptionJob).filter_by(
            video_id=video_id
        ).order_by(
            desc(EncryptionJob.created_at)
        ).first()

        if not job:
            return None

        return {
            'status': job.status,
            'progress': job.progress_percent,
            'lit_cid': job.lit_cid,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        }

    def get_upload_info(self, video_id: int) -> Optional[Dict[str, Any]]:
        """Get latest upload information for a video.

        Args:
            video_id: Video ID to look up

        Returns:
            Dictionary with upload info if found, None otherwise
        """
        job = self.session.query(UploadJob).filter_by(
            video_id=video_id
        ).order_by(
            desc(UploadJob.created_at)
        ).first()

        if not job:
            return None

        return {
            'status': job.status,
            'target': job.target,
            'remote_cid': job.remote_cid,
            'remote_url': job.remote_url,
            'progress': job.progress_percent,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        }

    def get_sync_info(self, video_id: int) -> Optional[Dict[str, Any]]:
        """Get latest sync information for a video.

        Args:
            video_id: Video ID to look up

        Returns:
            Dictionary with sync info if found, None otherwise
        """
        job = self.session.query(SyncJob).filter_by(
            video_id=video_id
        ).order_by(
            desc(SyncJob.created_at)
        ).first()

        if not job:
            return None

        return {
            'status': job.status,
            'tx_hash': job.tx_hash,
            'block_number': job.block_number,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        }

    def get_failed_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent failed jobs across all stages.

        Args:
            limit: Maximum number of results

        Returns:
            List of failed job records with stage, video_id, timestamp, and error
        """
        # Query each table for failed jobs using union
        downloads = self.session.query(
            literal("download").label("stage"),
            Download.video_id,
            Download.failed_at.label("timestamp"),
            Download.error_message
        ).filter(Download.status == "failed")

        encrypts = self.session.query(
            literal("encrypt").label("stage"),
            EncryptionJob.video_id,
            EncryptionJob.completed_at.label("timestamp"),
            EncryptionJob.error_message
        ).filter(EncryptionJob.status == "failed")

        uploads = self.session.query(
            literal("upload").label("stage"),
            UploadJob.video_id,
            UploadJob.completed_at.label("timestamp"),
            UploadJob.error_message
        ).filter(UploadJob.status == "failed")

        syncs = self.session.query(
            literal("sync").label("stage"),
            SyncJob.video_id,
            SyncJob.completed_at.label("timestamp"),
            SyncJob.error_message
        ).filter(SyncJob.status == "failed")

        analyses = self.session.query(
            literal("analyze").label("stage"),
            AnalysisJob.video_id,
            AnalysisJob.completed_at.label("timestamp"),
            AnalysisJob.error_message
        ).filter(AnalysisJob.status == "failed")

        # Union all and order by timestamp
        union_query = downloads.union(
            encrypts, uploads, syncs, analyses
        ).order_by(desc("timestamp")).limit(limit)

        results = union_query.all()

        return [
            {
                "stage": r.stage,
                "video_id": r.video_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "error_message": r.error_message,
            }
            for r in results
        ]


class SpeedHistoryRepository:
    """Repository for speed history queries (for graphing)."""

    def __init__(self, session: Session):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def get_speed_history(
        self,
        video_id: int,
        stage: str,
        minutes: int = 5
    ) -> List[SpeedHistory]:
        """Get speed history for graphing.

        Args:
            video_id: Video ID to look up
            stage: Stage name ("download", "encrypt", "upload")
            minutes: Time window in minutes

        Returns:
            List of SpeedHistory entries
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        return self.session.query(SpeedHistory).filter(
            SpeedHistory.video_id == video_id,
            SpeedHistory.stage == stage,
            SpeedHistory.timestamp >= since
        ).order_by(SpeedHistory.timestamp).all()

    def get_aggregate_speeds(
        self,
        stage: Optional[str] = None,
        minutes: int = 5
    ) -> List[Dict[str, Any]]:
        """Get aggregate speeds over time for header graph.

        Args:
            stage: Filter by stage (optional)
            minutes: Time window in minutes

        Returns:
            List of aggregated speed data points
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        query = self.session.query(
            func.strftime('%Y-%m-%d %H:%M', SpeedHistory.timestamp).label('bucket'),
            SpeedHistory.stage,
            func.avg(SpeedHistory.speed).label('avg_speed'),
            func.count().label('sample_count'),
        ).filter(
            SpeedHistory.timestamp >= since
        )

        if stage:
            query = query.filter(SpeedHistory.stage == stage)

        results = query.group_by(
            'bucket',
            SpeedHistory.stage
        ).order_by('bucket').all()

        return [
            {
                "bucket": r.bucket,
                "stage": r.stage,
                "avg_speed": r.avg_speed,
                "sample_count": r.sample_count,
            }
            for r in results
        ]

    def get_speed_trends(
        self,
        video_id: int,
        stage: str,
        interval_minutes: int = 1
    ) -> List[Dict[str, Any]]:
        """Get speed trends for detailed graphing.

        Args:
            video_id: Video ID to look up
            stage: Stage name
            interval_minutes: Aggregation interval in minutes

        Returns:
            List of trend data points
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=interval_minutes * 60)

        results = self.session.query(
            func.strftime('%Y-%m-%d %H:%M', SpeedHistory.timestamp).label('time_bucket'),
            func.avg(SpeedHistory.speed).label('avg_speed'),
            func.max(SpeedHistory.speed).label('max_speed'),
            func.min(SpeedHistory.speed).label('min_speed'),
            func.avg(SpeedHistory.progress).label('avg_progress'),
        ).filter(
            SpeedHistory.video_id == video_id,
            SpeedHistory.stage == stage,
            SpeedHistory.timestamp >= since
        ).group_by(
            'time_bucket'
        ).order_by('time_bucket').all()

        return [
            {
                "time": r.time_bucket,
                "avg_speed": r.avg_speed,
                "max_speed": r.max_speed,
                "min_speed": r.min_speed,
                "avg_progress": r.avg_progress,
            }
            for r in results
        ]

    def record_speed(
        self,
        video_id: int,
        stage: str,
        speed: int,
        progress: float = 0.0,
        bytes_processed: int = 0
    ) -> SpeedHistory:
        """Record a new speed history entry.

        Args:
            video_id: Video ID
            stage: Stage name
            speed: Speed in bytes/sec
            progress: Progress percentage (0-100)
            bytes_processed: Bytes processed so far

        Returns:
            Created SpeedHistory entry
        """
        entry = SpeedHistory(
            video_id=video_id,
            stage=stage,
            speed=speed,
            progress=progress,
            bytes_processed=bytes_processed,
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def cleanup_old_entries(self, days: int = 7) -> int:
        """Remove speed history entries older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of entries deleted
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.session.query(SpeedHistory).filter(
            SpeedHistory.timestamp < cutoff
        ).delete()
        self.session.commit()
        return result
