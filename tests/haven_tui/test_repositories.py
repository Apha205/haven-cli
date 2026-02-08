"""Tests for Haven TUI Data Access Layer (Repository Pattern).

This module tests the TUI-specific repository classes:
- PipelineSnapshotRepository (TUI version)
- DownloadRepository (TUI version)
- JobHistoryRepository (TUI version)
- SpeedHistoryRepository (TUI version)

And the view models:
- PipelineStage
- StageStatus
- VideoView
- StageInfo
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Generator, List

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
    DownloadRepository as CliDownloadRepository,
    EncryptionJobRepository,
    UploadJobRepository,
    SyncJobRepository,
    AnalysisJobRepository,
    PipelineSnapshotRepository as CliPipelineSnapshotRepository,
)

from haven_tui.models.video_view import (
    PipelineStage,
    StageStatus,
    VideoView,
    StageInfo,
)
from haven_tui.data.repositories import (
    PipelineSnapshotRepository,
    DownloadRepository,
    JobHistoryRepository,
    SpeedHistoryRepository,
)


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


@pytest.fixture
def sample_videos(db_session: Session) -> List[Video]:
    """Create multiple sample videos for testing."""
    videos = []
    for i in range(5):
        video = Video(
            source_path=f"/test/video{i}.mp4",
            title=f"Test Video {i}",
            duration=120.0 + i * 10,
            file_size=1000000 + i * 100000,
            plugin_name="youtube" if i % 2 == 0 else "torrent",
        )
        db_session.add(video)
        videos.append(video)

    db_session.commit()
    for video in videos:
        db_session.refresh(video)

    return videos


@pytest.fixture
def active_snapshots(db_session: Session, sample_videos: List[Video]) -> List[PipelineSnapshot]:
    """Create active pipeline snapshots for testing."""
    cli_repo = CliPipelineSnapshotRepository(db_session)
    snapshots = []
    stages = ["download", "encrypt", "upload", "sync", "analysis"]

    for i, video in enumerate(sample_videos):
        snapshot = cli_repo.get_or_create(video.id)
        snapshot.overall_status = "active"
        snapshot.current_stage = stages[i % len(stages)]
        snapshot.stage_progress_percent = 50.0 + i * 5
        snapshot.stage_speed = 100000 * (i + 1)
        snapshot.stage_eta = 60 - i * 5
        snapshot.total_bytes = 1000000 + i * 100000
        db_session.add(snapshot)
        snapshots.append(snapshot)

    db_session.commit()
    return snapshots


# =============================================================================
# View Model Tests
# =============================================================================

class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_stage_values(self) -> None:
        """Test that stages have correct values."""
        assert PipelineStage.DOWNLOAD.value == "download"
        assert PipelineStage.INGEST.value == "ingest"
        assert PipelineStage.ANALYSIS.value == "analysis"
        assert PipelineStage.ENCRYPT.value == "encrypt"
        assert PipelineStage.UPLOAD.value == "upload"
        assert PipelineStage.SYNC.value == "sync"
        assert PipelineStage.COMPLETE.value == "complete"

    def test_stage_from_string(self) -> None:
        """Test creating stage from string."""
        assert PipelineStage("download") == PipelineStage.DOWNLOAD
        assert PipelineStage("upload") == PipelineStage.UPLOAD
        assert PipelineStage("complete") == PipelineStage.COMPLETE


class TestStageStatus:
    """Tests for StageStatus enum."""

    def test_status_values(self) -> None:
        """Test that statuses have correct values."""
        assert StageStatus.PENDING.value == "pending"
        assert StageStatus.ACTIVE.value == "active"
        assert StageStatus.COMPLETED.value == "completed"
        assert StageStatus.FAILED.value == "failed"


class TestVideoView:
    """Tests for VideoView dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a VideoView."""
        view = VideoView(
            id=1,
            title="Test Video",
            source_path="/test/video.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_progress=50.0,
            stage_speed=100000,
            stage_eta=60,
            overall_status="active",
            has_error=False,
            error_message=None,
            file_size=1000000,
            plugin="youtube",
        )

        assert view.id == 1
        assert view.title == "Test Video"
        assert view.current_stage == PipelineStage.DOWNLOAD
        assert view.stage_progress == 50.0
        assert not view.is_complete
        assert view.is_active

    def test_is_complete(self) -> None:
        """Test is_complete property."""
        view = VideoView(
            id=1,
            title="Test Video",
            source_path="/test/video.mp4",
            current_stage=PipelineStage.COMPLETE,
            overall_status="completed",
            file_size=1000000,
            plugin="youtube",
        )
        assert view.is_complete

    def test_formatted_speed(self) -> None:
        """Test formatted_speed property."""
        # Zero speed
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_speed=0,
            overall_status="active",
            file_size=1000000,
            plugin="youtube",
        )
        assert view.formatted_speed == "-"

        # KB/s
        view.stage_speed = 500 * 1024  # 500 KB/s
        assert view.formatted_speed == "500.0KB/s"

        # MB/s
        view.stage_speed = 5 * 1024 * 1024  # 5 MB/s
        assert view.formatted_speed == "5.0MB/s"

    def test_formatted_eta(self) -> None:
        """Test formatted_eta property."""
        # None ETA
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_eta=None,
            overall_status="active",
            file_size=1000000,
            plugin="youtube",
        )
        assert view.formatted_eta == "--:--"

        # Minutes and seconds
        view.stage_eta = 125  # 2m 5s
        assert view.formatted_eta == "2:05"

        # Hours
        view.stage_eta = 3665  # 1h 1m 5s
        assert view.formatted_eta == "1h01m"

    def test_formatted_file_size(self) -> None:
        """Test formatted_file_size property."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            file_size=0,
            overall_status="active",
            plugin="youtube",
        )
        assert view.formatted_file_size == "-"

        view.file_size = 500
        assert view.formatted_file_size == "500B"

        view.file_size = 500 * 1024
        assert view.formatted_file_size == "500.0KB"

        view.file_size = 500 * 1024 * 1024
        assert view.formatted_file_size == "500.0MB"

    def test_display_title(self) -> None:
        """Test display_title property."""
        view = VideoView(
            id=1,
            title="Short",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000000,
            plugin="youtube",
        )
        assert view.display_title == "Short"

        # Long title should be truncated
        view.title = "A" * 100
        assert len(view.display_title) <= 53  # 50 + "..."
        assert view.display_title.endswith("...")

    def test_to_dict(self) -> None:
        """Test to_dict method."""
        view = VideoView(
            id=1,
            title="Test Video",
            source_path="/test/video.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_progress=50.0,
            stage_speed=100000,
            stage_eta=60,
            overall_status="active",
            has_error=False,
            error_message=None,
            file_size=1000000,
            plugin="youtube",
        )

        data = view.to_dict()
        assert data["id"] == 1
        assert data["title"] == "Test Video"
        assert data["current_stage"] == "download"
        assert data["formatted_speed"] == "97.7KB/s"
        assert data["is_complete"] is False
        assert data["is_active"] is True


class TestStageInfo:
    """Tests for StageInfo dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating StageInfo."""
        stage = StageInfo(
            stage=PipelineStage.DOWNLOAD,
            status=StageStatus.ACTIVE,
            progress=50.0,
            speed=100000,
            eta=60,
        )

        assert stage.stage == PipelineStage.DOWNLOAD
        assert stage.status == StageStatus.ACTIVE
        assert stage.is_active
        assert not stage.is_complete
        assert not stage.has_failed


# =============================================================================
# PipelineSnapshotRepository Tests
# =============================================================================

class TestPipelineSnapshotRepository:
    """Tests for TUI PipelineSnapshotRepository."""

    def test_get_active_videos(self, db_session: Session, active_snapshots: List[PipelineSnapshot]) -> None:
        """Test getting active videos."""
        repo = PipelineSnapshotRepository(db_session)

        views = repo.get_active_videos()

        assert len(views) == 5
        for view in views:
            assert view.overall_status in ["active", "pending"]
            assert isinstance(view.current_stage, PipelineStage)

    def test_get_active_videos_with_pagination(self, db_session: Session, active_snapshots: List[PipelineSnapshot]) -> None:
        """Test pagination for active videos."""
        repo = PipelineSnapshotRepository(db_session)

        # Test limit
        views = repo.get_active_videos(limit=2)
        assert len(views) == 2

        # Test offset
        views = repo.get_active_videos(limit=2, offset=2)
        assert len(views) == 2

    def test_get_videos_by_stage(self, db_session: Session, active_snapshots: List[PipelineSnapshot]) -> None:
        """Test getting videos by stage."""
        repo = PipelineSnapshotRepository(db_session)

        download_views = repo.get_videos_by_stage(PipelineStage.DOWNLOAD)
        assert len(download_views) == 1
        assert download_views[0].current_stage == PipelineStage.DOWNLOAD

    def test_get_video_summary(self, db_session: Session, sample_video: Video) -> None:
        """Test getting video summary."""
        repo = PipelineSnapshotRepository(db_session)
        cli_repo = CliPipelineSnapshotRepository(db_session)

        # Create snapshot
        snapshot = cli_repo.get_or_create(sample_video.id)
        snapshot.current_stage = "upload"
        snapshot.overall_status = "active"
        snapshot.stage_progress_percent = 75.0
        db_session.commit()

        view = repo.get_video_summary(sample_video.id)

        assert view is not None
        assert view.id == sample_video.id
        assert view.title == sample_video.title
        assert view.current_stage == PipelineStage.UPLOAD
        assert view.stage_progress == 75.0

    def test_get_video_summary_not_found(self, db_session: Session) -> None:
        """Test getting video summary for non-existent video."""
        repo = PipelineSnapshotRepository(db_session)

        view = repo.get_video_summary(9999)
        assert view is None

    def test_get_aggregate_stats(self, db_session: Session, active_snapshots: List[PipelineSnapshot]) -> None:
        """Test getting aggregate stats."""
        repo = PipelineSnapshotRepository(db_session)

        stats = repo.get_aggregate_stats()

        assert stats["active_count"] == 5
        assert stats["total_speed"] == 100000 + 200000 + 300000 + 400000 + 500000
        assert stats["by_stage"]["download"] == 1
        assert stats["by_stage"]["encrypt"] == 1
        assert stats["by_stage"]["upload"] == 1
        assert stats["error_count"] == 0

    def test_get_videos_with_errors(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting videos with errors."""
        repo = PipelineSnapshotRepository(db_session)
        cli_repo = CliPipelineSnapshotRepository(db_session)

        # Create snapshots with errors
        for i, video in enumerate(sample_videos[:2]):
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.has_error = True
            snapshot.error_message = f"Error {i}"
            snapshot.overall_status = "failed"

        db_session.commit()

        error_views = repo.get_videos_with_errors()

        assert len(error_views) == 2
        for view in error_views:
            assert view.has_error is True
            assert view.error_message is not None

    def test_get_completed_count(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting completed video count."""
        repo = PipelineSnapshotRepository(db_session)
        cli_repo = CliPipelineSnapshotRepository(db_session)

        # Create completed snapshots
        for video in sample_videos[:3]:
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.overall_status = "completed"
            snapshot.pipeline_completed_at = datetime.now(timezone.utc)

        db_session.commit()

        count = repo.get_completed_count()
        assert count == 3

    def test_get_failed_count(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting failed video count."""
        repo = PipelineSnapshotRepository(db_session)
        cli_repo = CliPipelineSnapshotRepository(db_session)

        # Create failed snapshots
        for video in sample_videos[:2]:
            snapshot = cli_repo.get_or_create(video.id)
            snapshot.overall_status = "failed"

        db_session.commit()

        count = repo.get_failed_count()
        assert count == 2

    def test_search_videos(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test searching videos by title."""
        repo = PipelineSnapshotRepository(db_session)
        cli_repo = CliPipelineSnapshotRepository(db_session)

        # Create snapshots for all videos
        for video in sample_videos:
            cli_repo.get_or_create(video.id)

        db_session.commit()

        results = repo.search_videos("Video 0")
        assert len(results) == 1
        assert results[0].title == "Test Video 0"


# =============================================================================
# DownloadRepository Tests
# =============================================================================

class TestDownloadRepository:
    """Tests for TUI DownloadRepository."""

    def test_get_active_downloads(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting active downloads."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)

        # Create downloads
        cli_repo.create(video_id=sample_videos[0].id, source_type="youtube", status="downloading")
        cli_repo.create(video_id=sample_videos[1].id, source_type="torrent", status="downloading")
        cli_repo.create(video_id=sample_videos[2].id, source_type="youtube", status="completed")

        active = tui_repo.get_active_downloads()

        assert len(active) == 2
        assert all(d.status == "downloading" for d in active)

    def test_get_download_by_video(self, db_session: Session, sample_video: Video) -> None:
        """Test getting download by video."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)

        # Create multiple downloads for same video
        cli_repo.create(video_id=sample_video.id, source_type="youtube")
        import time
        time.sleep(0.01)  # Small delay to ensure different timestamps
        latest = cli_repo.create(video_id=sample_video.id, source_type="torrent")

        result = tui_repo.get_download_by_video(sample_video.id)

        assert result is not None
        assert result.id == latest.id

    def test_get_download_history(self, db_session: Session, sample_video: Video) -> None:
        """Test getting download history."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)

        # Create multiple downloads
        for i in range(5):
            cli_repo.create(video_id=sample_video.id, source_type="youtube")

        history = tui_repo.get_download_history(sample_video.id, limit=3)

        assert len(history) == 3

    def test_get_aggregate_download_speed(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting aggregate download speed."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)

        # Create active downloads with rates
        d1 = cli_repo.create(video_id=sample_videos[0].id, source_type="youtube", status="downloading")
        d2 = cli_repo.create(video_id=sample_videos[1].id, source_type="torrent", status="downloading")

        cli_repo.update_progress(d1.id, 100000, 1000000, 100000, 10)
        cli_repo.update_progress(d2.id, 200000, 1000000, 200000, 5)

        total_speed = tui_repo.get_aggregate_download_speed()

        assert total_speed == 300000

    def test_get_pending_downloads(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting pending downloads."""
        cli_repo = CliDownloadRepository(db_session)
        tui_repo = DownloadRepository(db_session)

        cli_repo.create(video_id=sample_videos[0].id, source_type="youtube", status="pending")
        cli_repo.create(video_id=sample_videos[1].id, source_type="torrent", status="downloading")

        pending = tui_repo.get_pending_downloads()

        assert len(pending) == 1
        assert pending[0].status == "pending"


# =============================================================================
# JobHistoryRepository Tests
# =============================================================================

class TestJobHistoryRepository:
    """Tests for TUI JobHistoryRepository."""

    def test_get_video_pipeline_history(self, db_session: Session, sample_video: Video) -> None:
        """Test getting complete pipeline history."""
        # Create various jobs
        download_repo = CliDownloadRepository(db_session)
        encrypt_repo = EncryptionJobRepository(db_session)
        upload_repo = UploadJobRepository(db_session)
        sync_repo = SyncJobRepository(db_session)
        analysis_repo = AnalysisJobRepository(db_session)

        download_repo.create(video_id=sample_video.id, source_type="youtube")
        encrypt_repo.create(video_id=sample_video.id)
        upload_repo.create(video_id=sample_video.id, target="ipfs")
        sync_repo.create(video_id=sample_video.id)
        analysis_repo.create(video_id=sample_video.id, analysis_type="vlm")

        repo = JobHistoryRepository(db_session)
        history = repo.get_video_pipeline_history(sample_video.id)

        assert len(history["downloads"]) == 1
        assert len(history["encryption_jobs"]) == 1
        assert len(history["upload_jobs"]) == 1
        assert len(history["sync_jobs"]) == 1
        assert len(history["analysis_jobs"]) == 1

    def test_get_latest_cid(self, db_session: Session, sample_video: Video) -> None:
        """Test getting latest CID."""
        upload_repo = UploadJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Create completed upload with CID
        upload = upload_repo.create(video_id=sample_video.id, target="ipfs")
        upload_repo.complete_upload(upload.id, "QmTest123")

        cid = repo.get_latest_cid(sample_video.id)

        assert cid == "QmTest123"

    def test_get_latest_cid_no_completed(self, db_session: Session, sample_video: Video) -> None:
        """Test getting CID when no completed uploads."""
        upload_repo = UploadJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Create pending upload
        upload_repo.create(video_id=sample_video.id, target="ipfs", status="pending")

        cid = repo.get_latest_cid(sample_video.id)

        assert cid is None

    def test_is_encrypted(self, db_session: Session, sample_video: Video) -> None:
        """Test checking if video is encrypted."""
        encrypt_repo = EncryptionJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Not encrypted initially
        assert not repo.is_encrypted(sample_video.id)

        # Create completed encryption job
        job = encrypt_repo.create(video_id=sample_video.id)
        encrypt_repo.update_status(job.id, "completed")

        assert repo.is_encrypted(sample_video.id)

    def test_get_encryption_info(self, db_session: Session, sample_video: Video) -> None:
        """Test getting encryption info."""
        encrypt_repo = EncryptionJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Create encryption job
        job = encrypt_repo.create(video_id=sample_video.id, bytes_total=1000000)
        encrypt_repo.update_progress(job.id, 500000, 50000)

        info = repo.get_encryption_info(sample_video.id)

        assert info is not None
        assert info["status"] == "pending"
        assert info["progress"] == 50.0

    def test_get_upload_info(self, db_session: Session, sample_video: Video) -> None:
        """Test getting upload info."""
        upload_repo = UploadJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Create upload job
        upload_repo.create(video_id=sample_video.id, target="ipfs")

        info = repo.get_upload_info(sample_video.id)

        assert info is not None
        assert info["target"] == "ipfs"
        assert info["status"] == "pending"

    def test_get_sync_info(self, db_session: Session, sample_video: Video) -> None:
        """Test getting sync info."""
        sync_repo = SyncJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Create sync job
        sync_repo.create(video_id=sample_video.id)

        info = repo.get_sync_info(sample_video.id)

        assert info is not None
        assert info["status"] == "pending"

    def test_get_failed_jobs(self, db_session: Session, sample_videos: List[Video]) -> None:
        """Test getting failed jobs."""
        download_repo = CliDownloadRepository(db_session)
        upload_repo = UploadJobRepository(db_session)
        repo = JobHistoryRepository(db_session)

        # Create failed jobs
        d1 = download_repo.create(video_id=sample_videos[0].id, source_type="youtube")
        download_repo.update_status(d1.id, "failed", "Network error")

        u1 = upload_repo.create(video_id=sample_videos[1].id, target="ipfs")
        # Note: upload status update is different, using update_progress or complete_upload
        # For simplicity, we'll just test with download failures

        failed = repo.get_failed_jobs(limit=10)

        assert len(failed) >= 1
        assert failed[0]["stage"] == "download"
        assert failed[0]["error_message"] == "Network error"


# =============================================================================
# SpeedHistoryRepository Tests
# =============================================================================

class TestSpeedHistoryRepository:
    """Tests for TUI SpeedHistoryRepository."""

    def test_get_speed_history(self, db_session: Session, sample_video: Video) -> None:
        """Test getting speed history."""
        repo = SpeedHistoryRepository(db_session)

        # Create speed history entries
        for i in range(5):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=100000 + i * 10000,
                progress=i * 20,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
            db_session.add(entry)
        db_session.commit()

        history = repo.get_speed_history(sample_video.id, "download", minutes=10)

        assert len(history) == 5

    def test_get_aggregate_speeds(self, db_session: Session, sample_video: Video) -> None:
        """Test getting aggregate speeds."""
        repo = SpeedHistoryRepository(db_session)

        # Create speed history entries
        for i in range(10):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download" if i < 5 else "upload",
                speed=100000,
                progress=i * 10,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
            db_session.add(entry)
        db_session.commit()

        # Get all aggregate speeds
        speeds = repo.get_aggregate_speeds(minutes=10)

        assert len(speeds) > 0

        # Filter by stage
        download_speeds = repo.get_aggregate_speeds(stage="download", minutes=10)
        assert len(download_speeds) > 0

    def test_get_speed_trends(self, db_session: Session, sample_video: Video) -> None:
        """Test getting speed trends."""
        repo = SpeedHistoryRepository(db_session)

        # Create speed history entries
        for i in range(10):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=100000 + i * 5000,
                progress=i * 10,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
            db_session.add(entry)
        db_session.commit()

        trends = repo.get_speed_trends(sample_video.id, "download", interval_minutes=60)

        assert len(trends) > 0
        assert "avg_speed" in trends[0]
        assert "max_speed" in trends[0]
        assert "min_speed" in trends[0]

    def test_record_speed(self, db_session: Session, sample_video: Video) -> None:
        """Test recording speed."""
        repo = SpeedHistoryRepository(db_session)

        entry = repo.record_speed(
            video_id=sample_video.id,
            stage="upload",
            speed=200000,
            progress=50.0,
            bytes_processed=500000,
        )

        assert entry.id is not None
        assert entry.video_id == sample_video.id
        assert entry.stage == "upload"
        assert entry.speed == 200000

    def test_cleanup_old_entries(self, db_session: Session, sample_video: Video) -> None:
        """Test cleaning up old entries."""
        repo = SpeedHistoryRepository(db_session)

        # Create old entries
        for i in range(5):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=100000,
                timestamp=datetime.now(timezone.utc) - timedelta(days=10),
            )
            db_session.add(entry)

        # Create recent entries
        for i in range(5):
            entry = SpeedHistory(
                video_id=sample_video.id,
                stage="download",
                speed=100000,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(entry)

        db_session.commit()

        deleted = repo.cleanup_old_entries(days=7)

        assert deleted == 5  # Old entries deleted
