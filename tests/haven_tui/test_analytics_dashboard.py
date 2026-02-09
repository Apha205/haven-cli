"""Tests for Analytics Dashboard.

This module tests the analytics components:
- AnalyticsRepository (data access)
- AnalyticsDashboard widget and screen
- Chart components (ASCIIBarChart, StageTimingChart, etc.)
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Generator, List, Dict, Any
from unittest.mock import Mock, MagicMock

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
)
from haven_cli.database.repositories import (
    DownloadRepository as CliDownloadRepository,
    EncryptionJobRepository,
    UploadJobRepository,
    SyncJobRepository,
    AnalysisJobRepository,
    PipelineSnapshotRepository as CliPipelineSnapshotRepository,
)

from haven_tui.data.repositories import AnalyticsRepository
from haven_tui.ui.views.analytics import (
    ASCIIBarChart,
    HorizontalBarChart,
    StageTimingChart,
    SuccessRateChart,
    PluginUsageChart,
    AnalyticsDashboardWidget,
    AnalyticsDashboard,
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
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


@pytest.fixture
def sample_videos(db_session: Session) -> List[Video]:
    """Create multiple sample videos for testing."""
    videos = []
    for i in range(10):
        video = Video(
            source_path=f"/test/video{i}.mp4",
            title=f"Test Video {i}",
            duration=120.0 + i * 10,
            file_size=1000000 + i * 100000,
            plugin_name="youtube" if i % 2 == 0 else "bittorrent",
            created_at=datetime.now(timezone.utc) - timedelta(days=i % 7),
        )
        db_session.add(video)
        videos.append(video)

    db_session.commit()
    for video in videos:
        db_session.refresh(video)

    return videos


@pytest.fixture
def analytics_repo(db_session: Session) -> AnalyticsRepository:
    """Create an analytics repository."""
    return AnalyticsRepository(db_session)


@pytest.fixture
def completed_downloads(db_session: Session, sample_videos: List[Video]) -> List[Download]:
    """Create completed downloads for testing."""
    cli_repo = CliDownloadRepository(db_session)
    downloads = []
    
    for i, video in enumerate(sample_videos[:5]):
        dl = cli_repo.create(
            video_id=video.id,
            source_type="youtube" if i % 2 == 0 else "torrent",
            status="completed",
        )
        # Manually set timing for testing
        dl.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        dl.completed_at = datetime.now(timezone.utc) - timedelta(minutes=30 - i * 5)
        dl.bytes_downloaded = 1000000 + i * 100000
        downloads.append(dl)
    
    db_session.commit()
    return downloads


@pytest.fixture
def completed_encryption_jobs(db_session: Session, sample_videos: List[Video]) -> List[EncryptionJob]:
    """Create completed encryption jobs for testing."""
    enc_repo = EncryptionJobRepository(db_session)
    jobs = []
    
    for i, video in enumerate(sample_videos[:4]):
        job = enc_repo.create(video_id=video.id, bytes_total=1000000)
        job.status = "completed"
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        job.completed_at = datetime.now(timezone.utc) - timedelta(minutes=10 - i * 2)
        job.bytes_processed = 1000000
        jobs.append(job)
    
    db_session.commit()
    return jobs


@pytest.fixture
def completed_upload_jobs(db_session: Session, sample_videos: List[Video]) -> List[UploadJob]:
    """Create completed upload jobs for testing."""
    upload_repo = UploadJobRepository(db_session)
    jobs = []
    
    for i, video in enumerate(sample_videos[:3]):
        job = upload_repo.create(video_id=video.id, target="ipfs")
        job.status = "completed"
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        job.completed_at = datetime.now(timezone.utc) - timedelta(minutes=5 - i)
        job.bytes_uploaded = 1000000
        job.remote_cid = f"QmTest{i}"
        jobs.append(job)
    
    db_session.commit()
    return jobs


@pytest.fixture
def failed_jobs(db_session: Session, sample_videos: List[Video]) -> tuple:
    """Create failed jobs for testing."""
    dl_repo = CliDownloadRepository(db_session)
    upload_repo = UploadJobRepository(db_session)
    
    # Failed download
    failed_dl = dl_repo.create(
        video_id=sample_videos[5].id,
        source_type="youtube",
        status="failed",
    )
    failed_dl.error_message = "Network timeout"
    failed_dl.failed_at = datetime.now(timezone.utc)
    
    # Failed upload
    failed_up = upload_repo.create(
        video_id=sample_videos[6].id,
        target="ipfs",
        status="failed",
    )
    failed_up.error_message = "Insufficient funds"
    
    db_session.commit()
    return (failed_dl, failed_up)


# =============================================================================
# AnalyticsRepository Tests
# =============================================================================

class TestAnalyticsRepository:
    """Tests for AnalyticsRepository."""

    def test_get_videos_per_day(self, db_session: Session, sample_videos: List[Video], analytics_repo: AnalyticsRepository) -> None:
        """Test getting videos per day."""
        result = analytics_repo.get_videos_per_day(days=7)
        
        # Should return 7 days of data
        assert len(result) == 7
        
        # All days should have non-negative counts
        for date_str, count in result.items():
            assert isinstance(date_str, str)
            assert isinstance(count, int)
            assert count >= 0

    def test_get_videos_per_day_empty(self, db_session: Session, analytics_repo: AnalyticsRepository) -> None:
        """Test getting videos per day with no videos."""
        result = analytics_repo.get_videos_per_day(days=7)
        
        assert len(result) == 7
        # All counts should be 0
        assert all(count == 0 for count in result.values())

    def test_get_avg_time_per_stage(
        self,
        db_session: Session,
        sample_videos: List[Video],
        completed_downloads: List[Download],
        completed_encryption_jobs: List[EncryptionJob],
        completed_upload_jobs: List[UploadJob],
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test getting average time per stage."""
        result = analytics_repo.get_avg_time_per_stage(days=30)
        
        # Should return dict with all stages
        assert "download" in result
        assert "encrypt" in result
        assert "upload" in result
        assert "analyze" in result
        assert "sync" in result
        
        # All values should be non-negative
        for stage, time in result.items():
            assert time >= 0
        
        # Stages with completed jobs should have positive times
        assert result["download"] > 0
        assert result["encrypt"] > 0
        assert result["upload"] > 0

    def test_get_avg_time_per_stage_empty(self, db_session: Session, analytics_repo: AnalyticsRepository) -> None:
        """Test getting average time per stage with no data."""
        result = analytics_repo.get_avg_time_per_stage(days=30)
        
        # All stages should return 0 when no data
        assert all(time == 0 for time in result.values())

    def test_get_success_rates(
        self,
        db_session: Session,
        sample_videos: List[Video],
        completed_downloads: List[Download],
        failed_jobs: tuple,
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test getting success rates."""
        result = analytics_repo.get_success_rates(days=30)
        
        # Should return dict with all stages
        assert "download" in result
        assert "encrypt" in result
        assert "upload" in result
        assert "analyze" in result
        assert "sync" in result
        
        # Download should have mixed results
        dl_stats = result["download"]
        assert "success_rate" in dl_stats
        assert "failure_rate" in dl_stats
        assert "success" in dl_stats
        assert "failed" in dl_stats
        assert "total" in dl_stats
        
        # With 5 completed and 1 failed
        assert dl_stats["total"] == 6
        assert dl_stats["success"] == 5
        assert dl_stats["failed"] == 1

    def test_get_plugin_usage_distribution(
        self,
        db_session: Session,
        sample_videos: List[Video],
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test getting plugin usage distribution."""
        result = analytics_repo.get_plugin_usage_distribution(days=30)
        
        # Should have youtube and bittorrent
        assert "youtube" in result
        assert "bittorrent" in result
        
        # Total should equal number of videos
        total = sum(result.values())
        assert total == len(sample_videos)

    def test_get_plugin_usage_percentages(
        self,
        db_session: Session,
        sample_videos: List[Video],
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test getting plugin usage as percentages."""
        result = analytics_repo.get_plugin_usage_percentages(days=30)
        
        # Should have youtube and bittorrent
        assert "youtube" in result
        assert "bittorrent" in result
        
        # Percentages should sum to 100
        total_percentage = sum(result.values())
        assert abs(total_percentage - 100.0) < 0.01  # Allow for floating point error
        
        # All percentages should be between 0 and 100
        for plugin, pct in result.items():
            assert 0 <= pct <= 100

    def test_get_throughput_trends(
        self,
        db_session: Session,
        sample_videos: List[Video],
        completed_downloads: List[Download],
        completed_upload_jobs: List[UploadJob],
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test getting throughput trends."""
        result = analytics_repo.get_throughput_trends(days=7)
        
        # Should return dict with relevant stages
        assert "download" in result
        assert "upload" in result
        assert "encrypt" in result

    def test_get_pipeline_summary(
        self,
        db_session: Session,
        sample_videos: List[Video],
        completed_downloads: List[Download],
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test getting pipeline summary."""
        result = analytics_repo.get_pipeline_summary()
        
        # Should have videos section
        assert "videos" in result
        videos = result["videos"]
        assert "total" in videos
        assert "active" in videos
        assert "completed" in videos
        assert "failed" in videos
        assert "pending" in videos
        
        # Should have data_processed section
        assert "data_processed" in result
        
        # Should have success_rates_7d
        assert "success_rates_7d" in result
        
        # Should have videos_per_day_7d
        assert "videos_per_day_7d" in result
        
        # Total videos should match
        assert videos["total"] == len(sample_videos)


# =============================================================================
# Chart Component Tests
# =============================================================================

class TestASCIIBarChart:
    """Tests for ASCIIBarChart widget."""

    def test_basic_creation(self) -> None:
        """Test creating an ASCII bar chart."""
        chart = ASCIIBarChart(
            title="Test Chart",
            data={"A": 10, "B": 20, "C": 15},
        )
        
        assert chart.chart_title == "Test Chart"
        assert chart.data == {"A": 10, "B": 20, "C": 15}

    def test_render_with_data(self) -> None:
        """Test rendering with data."""
        chart = ASCIIBarChart(
            title="Test Chart",
            data={"A": 10, "B": 20},
            max_bar_width=10,
        )
        
        result = chart.render()
        
        assert "Test Chart" in result
        assert "A" in result
        assert "B" in result
        assert "10" in result
        assert "20" in result

    def test_render_empty(self) -> None:
        """Test rendering with no data."""
        chart = ASCIIBarChart(title="Empty Chart")
        
        result = chart.render()
        
        assert "Empty Chart" in result
        assert "No data" in result

    def test_update_data(self) -> None:
        """Test updating chart data."""
        chart = ASCIIBarChart(data={"A": 10})
        
        chart.update_data({"X": 50, "Y": 100})
        
        assert chart.data == {"X": 50, "Y": 100}


class TestHorizontalBarChart:
    """Tests for HorizontalBarChart widget."""

    def test_basic_creation(self) -> None:
        """Test creating a horizontal bar chart."""
        chart = HorizontalBarChart(
            title="Daily Stats",
            data={"Mon": 10, "Tue": 20, "Wed": 15},
        )
        
        assert chart.chart_title == "Daily Stats"
        assert len(chart.data) == 3

    def test_render_with_daily_data(self) -> None:
        """Test rendering daily data."""
        chart = HorizontalBarChart(
            title="Daily Stats",
            data={"Mon": 12, "Tue": 24, "Wed": 15},
        )
        
        result = chart.render()
        
        assert "Daily Stats" in result
        assert "Mon" in result
        assert "Tue" in result
        assert "Wed" in result


class TestStageTimingChart:
    """Tests for StageTimingChart widget."""

    def test_basic_creation(self) -> None:
        """Test creating a stage timing chart."""
        chart = StageTimingChart(
            data={"download": 300, "encrypt": 150, "upload": 200},
        )
        
        assert "download" in chart.data
        assert "encrypt" in chart.data

    def test_format_duration(self) -> None:
        """Test duration formatting."""
        chart = StageTimingChart()
        
        assert chart._format_duration(0) == "-"
        assert chart._format_duration(60) == "1m 00s"
        assert chart._format_duration(300) == "5m 00s"
        assert chart._format_duration(3665) == "1h 01m"

    def test_render_with_timing_data(self) -> None:
        """Test rendering with timing data."""
        chart = StageTimingChart(
            data={"download": 272, "encrypt": 135, "upload": 225},  # seconds
        )
        
        result = chart.render()
        
        assert "Download" in result or "download" in result
        assert "4m 32s" in result or "272" in result


class TestSuccessRateChart:
    """Tests for SuccessRateChart widget."""

    def test_basic_creation(self) -> None:
        """Test creating a success rate chart."""
        chart = SuccessRateChart(
            data={
                "download": {"success_rate": 95.0},
                "upload": {"success_rate": 90.0},
            },
        )
        
        assert "download" in chart.data
        assert "upload" in chart.data

    def test_render_with_rate_data(self) -> None:
        """Test rendering with rate data."""
        chart = SuccessRateChart(
            data={
                "download": {"success_rate": 95.0},
                "encrypt": {"success_rate": 92.0},
                "upload": {"success_rate": 96.0},
            },
        )
        
        result = chart.render()
        
        assert "95%" in result
        assert "92%" in result
        assert "96%" in result


class TestPluginUsageChart:
    """Tests for PluginUsageChart widget."""

    def test_basic_creation(self) -> None:
        """Test creating a plugin usage chart."""
        chart = PluginUsageChart(
            data={"youtube": 78.0, "bittorrent": 22.0},
        )
        
        assert "youtube" in chart.data
        assert "bittorrent" in chart.data

    def test_render_with_plugin_data(self) -> None:
        """Test rendering with plugin data."""
        chart = PluginUsageChart(
            data={"youtube": 78.0, "bittorrent": 22.0},
        )
        
        result = chart.render()
        
        assert "78%" in result
        assert "22%" in result


# =============================================================================
# AnalyticsDashboard Tests
# =============================================================================

class TestAnalyticsDashboard:
    """Tests for AnalyticsDashboard high-level interface."""

    def test_basic_creation(self, db_session: Session, analytics_repo: AnalyticsRepository) -> None:
        """Test creating an AnalyticsDashboard."""
        dashboard = AnalyticsDashboard(analytics_repo)
        
        assert dashboard.analytics_repo is analytics_repo
        assert dashboard.screen is None

    def test_create_screen(self, db_session: Session, analytics_repo: AnalyticsRepository) -> None:
        """Test creating the screen."""
        dashboard = AnalyticsDashboard(analytics_repo)
        screen = dashboard.create_screen()
        
        assert screen is not None
        assert dashboard.screen is screen


# =============================================================================
# Integration Tests
# =============================================================================

class TestAnalyticsIntegration:
    """Integration tests for analytics components."""

    def test_end_to_end_analytics(
        self,
        db_session: Session,
        sample_videos: List[Video],
        completed_downloads: List[Download],
        completed_encryption_jobs: List[EncryptionJob],
        completed_upload_jobs: List[UploadJob],
        failed_jobs: tuple,
        analytics_repo: AnalyticsRepository,
    ) -> None:
        """Test end-to-end analytics workflow."""
        # Get summary
        summary = analytics_repo.get_pipeline_summary()
        
        # Verify video counts
        assert summary["videos"]["total"] == len(sample_videos)
        
        # Verify we have success rates
        success_rates = summary["success_rates_7d"]
        assert "download" in success_rates
        
        # Verify daily counts
        daily = summary["videos_per_day_7d"]
        assert len(daily) == 7
        
        # Verify stage timings
        timings = analytics_repo.get_avg_time_per_stage()
        assert any(t > 0 for t in timings.values())
        
        # Verify plugin distribution
        plugins = analytics_repo.get_plugin_usage_distribution()
        assert sum(plugins.values()) == len(sample_videos)

    def test_analytics_with_no_data(self, db_session: Session, analytics_repo: AnalyticsRepository) -> None:
        """Test analytics with empty database."""
        summary = analytics_repo.get_pipeline_summary()
        
        assert summary["videos"]["total"] == 0
        assert summary["videos"]["active"] == 0
        assert summary["videos"]["completed"] == 0
        assert summary["videos"]["failed"] == 0
        
        # All success rates should be 0
        for stage, stats in summary["success_rates_7d"].items():
            assert stats["success_rate"] == 0.0
            assert stats["total"] == 0
