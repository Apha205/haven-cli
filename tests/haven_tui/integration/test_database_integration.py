"""Integration tests for database layer.

Tests the integration between repositories and the database.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from haven_cli.database.models import (
    Base,
    Video,
    Download,
    EncryptionJob,
    UploadJob,
    SyncJob,
    AnalysisJob,
    PipelineSnapshot,
    SpeedHistory,
)
from haven_cli.database.repositories import (
    PipelineSnapshotRepository as CliPipelineSnapshotRepository,
    DownloadRepository as CliDownloadRepository,
)
from haven_tui.data.repositories import (
    PipelineSnapshotRepository,
    DownloadRepository,
    JobHistoryRepository,
    SpeedHistoryRepository,
)
from haven_tui.models.video_view import PipelineStage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_video(db_session: Session) -> Video:
    """Create a sample video for testing."""
    video = Video(
        source_path="/test/video.mp4",
        title="Test Video",
        duration=120.0,
        file_size=1000000,
        plugin_name="youtube",
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


# =============================================================================
# PipelineSnapshotRepository Integration Tests
# =============================================================================

class TestPipelineSnapshotRepositoryIntegration:
    """Integration tests for PipelineSnapshotRepository."""
    
    def test_full_video_lifecycle(self, db_session: Session, sample_video: Video):
        """Test full video lifecycle from pending to completed."""
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        
        # Create initial snapshot
        snapshot = cli_repo.get_or_create(sample_video.id)
        snapshot.overall_status = "pending"
        snapshot.current_stage = "pending"
        db_session.commit()
        
        # Verify pending state
        view = tui_repo.get_video_summary(sample_video.id)
        assert view.overall_status == "pending"
        assert view.current_stage == PipelineStage.PENDING
        
        # Move to download stage
        snapshot.overall_status = "active"
        snapshot.current_stage = "download"
        snapshot.stage_progress_percent = 50.0
        snapshot.stage_speed = 1024000
        db_session.commit()
        
        view = tui_repo.get_video_summary(sample_video.id)
        assert view.current_stage == PipelineStage.DOWNLOAD
        assert view.stage_progress == 50.0
        assert view.stage_speed == 1024000
        
        # Move to encrypt stage
        snapshot.current_stage = "encrypt"
        snapshot.stage_progress_percent = 75.0
        snapshot.stage_speed = 0
        db_session.commit()
        
        view = tui_repo.get_video_summary(sample_video.id)
        assert view.current_stage == PipelineStage.ENCRYPT
        assert view.stage_progress == 75.0
        
        # Complete
        snapshot.overall_status = "completed"
        snapshot.current_stage = "complete"
        snapshot.stage_progress_percent = 100.0
        snapshot.pipeline_completed_at = datetime.now(timezone.utc)
        db_session.commit()
        
        view = tui_repo.get_video_summary(sample_video.id)
        assert view.overall_status == "completed"
        assert view.current_stage == PipelineStage.COMPLETE
        assert view.is_complete is True
    
    def test_error_handling(self, db_session: Session, sample_video: Video):
        """Test error state handling."""
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        
        # Create snapshot with error
        snapshot = cli_repo.get_or_create(sample_video.id)
        snapshot.overall_status = "failed"
        snapshot.has_error = True
        snapshot.error_message = "Network timeout"
        db_session.commit()
        
        # Verify error state
        error_videos = tui_repo.get_videos_with_errors()
        assert len(error_videos) == 1
        assert error_videos[0].has_error is True
        assert error_videos[0].error_message == "Network timeout"
    
    def test_pagination(self, db_session: Session):
        """Test pagination with multiple videos."""
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        
        # Create 10 videos
        videos = []
        for i in range(10):
            video = Video(
                source_path=f"/test/video{i}.mp4",
                title=f"Video {i}",
                duration=120.0,
                file_size=1000000,
                plugin_name="youtube",
            )
            db_session.add(video)
            videos.append(video)
        
        db_session.commit()
        
        # Create active snapshots for all
        for video in videos:
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.overall_status = "active"
            snapshot.current_stage = "download"
            db_session.add(snapshot)
        
        db_session.commit()
        
        # Test pagination
        page1 = tui_repo.get_active_videos(limit=3, offset=0)
        assert len(page1) == 3
        
        page2 = tui_repo.get_active_videos(limit=3, offset=3)
        assert len(page2) == 3
        
        page3 = tui_repo.get_active_videos(limit=3, offset=6)
        assert len(page3) == 3
        
        page4 = tui_repo.get_active_videos(limit=3, offset=9)
        assert len(page4) == 1
    
    def test_aggregate_stats_with_varying_states(self, db_session: Session):
        """Test aggregate stats with videos in different states."""
        cli_repo = CliPipelineSnapshotRepository(db_session)
        tui_repo = PipelineSnapshotRepository(db_session)
        
        # Create videos in different stages
        stages = [
            ("download", 1000000),
            ("download", 2000000),
            ("encrypt", 0),
            ("upload", 500000),
            ("sync", 0),
            ("analysis", 0),
        ]
        
        for i, (stage, speed) in enumerate(stages):
            video = Video(
                source_path=f"/test/video{i}.mp4",
                title=f"Video {i}",
                duration=120.0,
                file_size=1000000,
                plugin_name="youtube",
            )
            db_session.add(video)
            db_session.flush()
            
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.overall_status = "active"
            snapshot.current_stage = stage
            snapshot.stage_speed = speed
            db_session.add(snapshot)
        
        db_session.commit()
        
        # Get aggregate stats
        stats = tui_repo.get_aggregate_stats()
        
        assert stats["active_count"] == 6
        assert stats["total_speed"] == 1000000 + 2000000 + 500000
        assert stats["by_stage"]["download"] == 2
        assert stats["by_stage"]["encrypt"] == 1
        assert stats["by_stage"]["upload"] == 1
        assert stats["by_stage"]["sync"] == 1
        assert stats["by_stage"]["analyze"] == 1


# =============================================================================
# DownloadRepository Integration Tests
# =============================================================================

class TestDownloadRepositoryIntegration:
    """Integration tests for DownloadRepository."""
    
    def test_download_lifecycle(self, db_session: Session, sample_video: Video):
        """Test full download lifecycle."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)
        
        # Create pending download
        download = cli_repo.create(
            video_id=sample_video.id,
            source_type="youtube",
            status="pending",
        )
        db_session.commit()
        
        # Verify pending
        pending = tui_repo.get_pending_downloads()
        assert len(pending) == 1
        
        # Start download
        cli_repo.update_status(download.id, "downloading")
        cli_repo.update_progress(download.id, 500000, 1000000, 100000, 10)
        db_session.commit()
        
        # Verify active
        active = tui_repo.get_active_downloads()
        assert len(active) == 1
        assert active[0].status == "downloading"
        
        # Complete download
        cli_repo.update_status(download.id, "completed")
        cli_repo.update_progress(download.id, 1000000, 1000000, 0, 0)
        db_session.commit()
        
        # Verify no longer active
        active = tui_repo.get_active_downloads()
        assert len(active) == 0
        
        # Check history
        history = tui_repo.get_download_history(sample_video.id)
        assert len(history) == 1
    
    def test_aggregate_download_speed(self, db_session: Session):
        """Test aggregate download speed calculation."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)
        
        # Create multiple active downloads
        for i in range(3):
            video = Video(
                source_path=f"/test/video{i}.mp4",
                title=f"Video {i}",
                duration=120.0,
                file_size=1000000,
                plugin_name="youtube",
            )
            db_session.add(video)
            db_session.flush()
            
            download = cli_repo.create(
                video_id=video.id,
                source_type="youtube",
                status="downloading",
            )
            cli_repo.update_progress(download.id, 500000, 1000000, 100000 * (i + 1), 10)
        
        db_session.commit()
        
        # Check aggregate speed
        total_speed = tui_repo.get_aggregate_download_speed()
        expected = 100000 + 200000 + 300000
        assert total_speed == expected


# =============================================================================
# JobHistoryRepository Integration Tests
# =============================================================================

class TestJobHistoryRepositoryIntegration:
    """Integration tests for JobHistoryRepository."""
    
    def test_complete_pipeline_history(self, db_session: Session, sample_video: Video):
        """Test getting complete pipeline history."""
        from haven_cli.database.repositories import (
            EncryptionJobRepository,
            UploadJobRepository,
            SyncJobRepository,
            AnalysisJobRepository,
        )
        
        cli_download_repo = CliDownloadRepository(db_session)
        encrypt_repo = EncryptionJobRepository(db_session)
        upload_repo = UploadJobRepository(db_session)
        sync_repo = SyncJobRepository(db_session)
        analysis_repo = AnalysisJobRepository(db_session)
        tui_repo = JobHistoryRepository(db_session)
        
        # Create jobs for all stages
        cli_download_repo.create(video_id=sample_video.id, source_type="youtube")
        encrypt_repo.create(video_id=sample_video.id)
        upload_repo.create(video_id=sample_video.id, target="ipfs")
        sync_repo.create(video_id=sample_video.id)
        analysis_repo.create(video_id=sample_video.id, analysis_type="vlm")
        
        db_session.commit()
        
        # Get full history
        history = tui_repo.get_video_pipeline_history(sample_video.id)
        
        assert len(history["downloads"]) == 1
        assert len(history["encryption_jobs"]) == 1
        assert len(history["upload_jobs"]) == 1
        assert len(history["sync_jobs"]) == 1
        assert len(history["analysis_jobs"]) == 1
    
    def test_encryption_info(self, db_session: Session, sample_video: Video):
        """Test getting encryption info."""
        from haven_cli.database.repositories import EncryptionJobRepository
        
        encrypt_repo = EncryptionJobRepository(db_session)
        tui_repo = JobHistoryRepository(db_session)
        
        # Create encryption job
        job = encrypt_repo.create(
            video_id=sample_video.id,
            bytes_total=1000000,
        )
        encrypt_repo.update_progress(job.id, 500000, 50000)
        db_session.commit()
        
        # Get encryption info
        info = tui_repo.get_encryption_info(sample_video.id)
        
        assert info is not None
        assert info["status"] == "pending"
        assert info["progress"] == 50.0
        
        # Complete encryption
        encrypt_repo.update_status(job.id, "completed")
        db_session.commit()
        
        # Verify is_encrypted
        assert tui_repo.is_encrypted(sample_video.id) is True
    
    def test_upload_info_with_cid(self, db_session: Session, sample_video: Video):
        """Test getting upload info with CID."""
        from haven_cli.database.repositories import UploadJobRepository
        
        upload_repo = UploadJobRepository(db_session)
        tui_repo = JobHistoryRepository(db_session)
        
        # Create upload job
        job = upload_repo.create(video_id=sample_video.id, target="ipfs")
        upload_repo.complete_upload(job.id, "QmTest123")
        db_session.commit()
        
        # Get upload info
        info = tui_repo.get_upload_info(sample_video.id)
        
        assert info is not None
        assert info["status"] == "completed"
        assert info["remote_cid"] == "QmTest123"
        
        # Get latest CID
        cid = tui_repo.get_latest_cid(sample_video.id)
        assert cid == "QmTest123"


# =============================================================================
# SpeedHistoryRepository Integration Tests
# =============================================================================

class TestSpeedHistoryRepositoryIntegration:
    """Integration tests for SpeedHistoryRepository."""
    
    def test_speed_history_recording(self, db_session: Session, sample_video: Video):
        """Test recording and retrieving speed history."""
        repo = SpeedHistoryRepository(db_session)
        
        # Record speeds
        for i in range(10):
            repo.record_speed(
                video_id=sample_video.id,
                stage="download",
                speed=100000 + i * 10000,
                progress=i * 10,
                bytes_processed=i * 100000,
            )
        
        # Get history
        history = repo.get_speed_history(sample_video.id, "download", minutes=5)
        
        assert len(history) == 10
        assert history[0].speed == 100000
        assert history[9].speed == 190000
    
    def test_speed_trends(self, db_session: Session, sample_video: Video):
        """Test speed trends aggregation."""
        repo = SpeedHistoryRepository(db_session)
        
        # Record speeds over time
        now = datetime.now(timezone.utc)
        for i in range(10):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=100000 + i * 5000,
                progress=i * 10,
                timestamp=now - timedelta(minutes=i),
            )
            db_session.add(entry)
        
        db_session.commit()
        
        # Get trends
        trends = repo.get_speed_trends(sample_video.id, "download", interval_minutes=60)
        
        assert len(trends) > 0
        for trend in trends:
            assert "avg_speed" in trend
            assert "max_speed" in trend
            assert "min_speed" in trend
    
    def test_cleanup_old_entries(self, db_session: Session, sample_video: Video):
        """Test cleaning up old speed entries."""
        repo = SpeedHistoryRepository(db_session)
        
        # Create old entries
        old_time = datetime.now(timezone.utc) - timedelta(days=10)
        for i in range(5):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=100000,
                timestamp=old_time,
            )
            db_session.add(entry)
        
        # Create recent entries
        for i in range(5):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=200000,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(entry)
        
        db_session.commit()
        
        # Cleanup old entries
        deleted = repo.cleanup_old_entries(days=7)
        
        assert deleted == 5  # Old entries deleted
        
        # Verify recent entries remain
        remaining = db_session.query(SpeedHistory).filter(
            SpeedHistory.video_id == sample_video.id
        ).all()
        
        assert len(remaining) == 5
        for entry in remaining:
            assert entry.speed == 200000
    
    def test_aggregate_speeds(self, db_session: Session, sample_video: Video):
        """Test aggregate speeds across multiple videos."""
        repo = SpeedHistoryRepository(db_session)
        
        # Create entries for multiple videos
        now = datetime.now(timezone.utc)
        for i in range(3):
            video = Video(
                source_path=f"/test/video{i}.mp4",
                title=f"Video {i}",
                duration=120.0,
                file_size=1000000,
                plugin_name="youtube",
            )
            db_session.add(video)
            db_session.flush()
            
            for j in range(5):
                entry = SpeedHistory(
                    video_id=video.id,
                    stage="download",
                    speed=100000 * (i + 1),
                    timestamp=now - timedelta(minutes=j),
                )
                db_session.add(entry)
        
        db_session.commit()
        
        # Get aggregate speeds
        aggregates = repo.get_aggregate_speeds(stage="download", minutes=10)
        
        assert len(aggregates) > 0
        for agg in aggregates:
            assert "avg_speed" in agg
            assert "sample_count" in agg
