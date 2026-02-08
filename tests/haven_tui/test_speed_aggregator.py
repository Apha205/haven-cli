"""Tests for the Download Speed Aggregator.

Tests cover:
- SpeedSample dataclass
- SpeedAggregate dataclass
- SpeedAggregator service
- Database integration with downloads and speed_history tables
- Thread-safety
"""

import pytest
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

from haven_tui.data.speed_aggregator import (
    SpeedSample,
    SpeedAggregate,
    SpeedAggregator,
)
from haven_cli.database.models import Download, SpeedHistory, Video


class TestSpeedSample:
    """Test SpeedSample dataclass."""
    
    def test_basic_creation(self):
        """Test creating a basic SpeedSample."""
        sample = SpeedSample(
            timestamp=time.time(),
            video_id=1,
            stage="download",
            download_rate=1000000,
            upload_rate=500000
        )
        assert sample.video_id == 1
        assert sample.stage == "download"
        assert sample.download_rate == 1000000
        assert sample.upload_rate == 500000
    
    def test_creation_with_zero_rates(self):
        """Test creating a SpeedSample with zero rates."""
        sample = SpeedSample(
            timestamp=time.time(),
            video_id=1,
            stage="download",
            download_rate=0,
            upload_rate=0
        )
        assert sample.download_rate == 0
        assert sample.upload_rate == 0


class TestSpeedAggregate:
    """Test SpeedAggregate dataclass."""
    
    def test_default_values(self):
        """Test default values of SpeedAggregate."""
        agg = SpeedAggregate()
        assert agg.current_download == 0.0
        assert agg.current_upload == 0.0
        assert agg.average_download == 0.0
        assert agg.average_upload == 0.0
        assert agg.peak_download == 0.0
        assert agg.peak_upload == 0.0
        assert agg.sample_count == 0
    
    def test_custom_values(self):
        """Test creating SpeedAggregate with custom values."""
        agg = SpeedAggregate(
            current_download=1000000,
            current_upload=500000,
            average_download=800000,
            average_upload=400000,
            peak_download=2000000,
            peak_upload=1000000,
            sample_count=10
        )
        assert agg.current_download == 1000000
        assert agg.current_upload == 500000
        assert agg.sample_count == 10


class TestSpeedAggregator:
    """Test SpeedAggregator service."""
    
    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)
        session.query = Mock(return_value=session)
        session.filter = Mock(return_value=session)
        session.filter_by = Mock(return_value=session)
        session.order_by = Mock(return_value=session)
        session.all = Mock(return_value=[])
        session.first = Mock(return_value=None)
        session.scalar = Mock(return_value=None)
        session.commit = Mock()
        session.add = Mock()
        session.rollback = Mock()
        
        factory = Mock(return_value=session)
        return factory, session
    
    @pytest.fixture
    def aggregator(self, mock_session_factory):
        """Create a SpeedAggregator with mocked dependencies."""
        factory, session = mock_session_factory
        return SpeedAggregator(
            db_session_factory=factory,
            window_seconds=60
        )
    
    def test_initialization(self, mock_session_factory):
        """Test SpeedAggregator initialization."""
        factory, _ = mock_session_factory
        aggregator = SpeedAggregator(
            db_session_factory=factory,
            window_seconds=120
        )
        assert aggregator.db_session_factory == factory
        assert aggregator.window_seconds == 120
        assert aggregator.sample_count == 0
    
    def test_add_sample(self, aggregator):
        """Test adding a sample."""
        aggregator.add_sample(
            video_id=1,
            stage="download",
            download_rate=1000000,
            upload_rate=500000
        )
        
        assert aggregator.sample_count == 1
        
        stats = aggregator.get_aggregate_stats()
        assert stats.current_download == 1000000
        assert stats.current_upload == 500000
        assert stats.sample_count == 1
    
    def test_add_multiple_samples(self, aggregator):
        """Test adding multiple samples."""
        for i in range(5):
            aggregator.add_sample(
                video_id=1,
                stage="download",
                download_rate=1000000.0 * (i + 1),
                upload_rate=500000.0 * (i + 1)
            )
        
        assert aggregator.sample_count == 5
        
        stats = aggregator.get_aggregate_stats()
        assert stats.current_download == 5000000.0  # Last sample
        assert stats.peak_download == 5000000.0  # Max
        assert stats.average_download == 3000000.0  # Average of 1, 2, 3, 4, 5 MB
    
    def test_cleanup_old_samples(self, aggregator):
        """Test that old samples are cleaned up."""
        # Add a sample
        aggregator.add_sample(
            video_id=1,
            stage="download",
            download_rate=1000000
        )
        
        # Manually set timestamp to be old
        with aggregator._lock:
            aggregator._samples[0].timestamp = time.time() - 120  # 2 minutes ago
        
        # Add another sample (triggers cleanup)
        aggregator.add_sample(
            video_id=1,
            stage="download",
            download_rate=2000000
        )
        
        # Old sample should be removed
        assert aggregator.sample_count == 1
    
    def test_set_window_seconds(self, aggregator):
        """Test updating the window duration."""
        # Add old samples
        for i in range(3):
            aggregator.add_sample(
                video_id=1,
                stage="download",
                download_rate=1000000.0 * (i + 1)
            )
        
        # Set timestamp of first sample to be old
        with aggregator._lock:
            aggregator._samples[0].timestamp = time.time() - 45
        
        # Reduce window to 30 seconds
        aggregator.set_window_seconds(30)
        
        # Old sample should be removed
        assert aggregator.window_seconds == 30
        assert aggregator.sample_count == 2
    
    def test_clear_samples(self, aggregator):
        """Test clearing all samples."""
        for i in range(5):
            aggregator.add_sample(
                video_id=1,
                stage="download",
                download_rate=1000000
            )
        
        assert aggregator.sample_count == 5
        
        aggregator.clear_samples()
        
        assert aggregator.sample_count == 0
    
    def test_get_samples_by_video(self, aggregator):
        """Test getting samples by video ID."""
        aggregator.add_sample(video_id=1, stage="download", download_rate=1000000)
        aggregator.add_sample(video_id=2, stage="download", download_rate=2000000)
        aggregator.add_sample(video_id=1, stage="download", download_rate=3000000)
        
        samples = aggregator.get_samples_by_video(1)
        assert len(samples) == 2
        assert all(s.video_id == 1 for s in samples)
    
    def test_get_samples_by_stage(self, aggregator):
        """Test getting samples by stage."""
        aggregator.add_sample(video_id=1, stage="download", download_rate=1000000)
        aggregator.add_sample(video_id=1, stage="upload", download_rate=500000)
        aggregator.add_sample(video_id=1, stage="download", download_rate=2000000)
        
        samples = aggregator.get_samples_by_stage("download")
        assert len(samples) == 2
        assert all(s.stage == "download" for s in samples)
    
    def test_sample_from_downloads_table_empty(self, aggregator, mock_session_factory):
        """Test sampling when no active downloads."""
        factory, session = mock_session_factory
        session.all.return_value = []
        
        count = aggregator.sample_from_downloads_table()
        
        assert count == 0
        assert aggregator.sample_count == 0
    
    def test_sample_from_downloads_table_with_downloads(self, aggregator, mock_session_factory):
        """Test sampling with active downloads."""
        factory, session = mock_session_factory
        
        # Create mock downloads
        download1 = Mock()
        download1.video_id = 1
        download1.download_rate = 1000000
        download1.progress_percent = 50.0
        download1.bytes_downloaded = 500000
        download1.source_metadata = None
        
        download2 = Mock()
        download2.video_id = 2
        download2.download_rate = 2000000
        download2.progress_percent = 75.0
        download2.bytes_downloaded = 750000
        download2.source_metadata = {"upload_rate": 500000}
        
        session.all.return_value = [download1, download2]
        
        count = aggregator.sample_from_downloads_table()
        
        assert count == 2
        assert aggregator.sample_count == 2
    
    def test_get_current_speeds_empty(self, aggregator, mock_session_factory):
        """Test getting current speeds when no active downloads."""
        factory, session = mock_session_factory
        
        # Mock the query result for sum
        mock_result = Mock()
        mock_result.__getitem__ = Mock(return_value=None)
        session.first.return_value = (None, None)
        session.all.return_value = []
        
        download_rate, upload_rate = aggregator.get_current_speeds()
        
        assert download_rate == 0.0
        assert upload_rate == 0.0
    
    def test_get_current_speeds_with_active(self, aggregator, mock_session_factory):
        """Test getting current speeds with active downloads."""
        factory, session = mock_session_factory
        
        # Mock the query result for sum
        session.first.return_value = (3000000, None)
        
        # Mock active downloads for upload rate calculation
        download1 = Mock()
        download1.source_metadata = None
        
        download2 = Mock()
        download2.source_metadata = {"upload_rate": 500000}
        
        session.all.return_value = [download1, download2]
        
        download_rate, upload_rate = aggregator.get_current_speeds()
        
        assert download_rate == 3000000.0
        assert upload_rate == 500000.0
    
    def test_thread_safety(self, aggregator):
        """Test thread-safety of add_sample."""
        errors = []
        
        def add_samples(thread_id):
            try:
                for i in range(100):
                    aggregator.add_sample(
                        video_id=thread_id,
                        stage="download",
                        download_rate=1000000.0 * (i + 1)
                    )
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=add_samples, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert aggregator.sample_count == 500


class TestSpeedAggregatorIntegration:
    """Integration tests with real database."""
    
    @pytest.fixture
    def db_engine(self, tmp_path):
        """Create a temporary database engine."""
        from sqlalchemy import create_engine
        from haven_cli.database.models import Base
        
        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        return engine
    
    @pytest.fixture
    def db_session(self, db_engine):
        """Create a temporary database session."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        return Session()
    
    @pytest.fixture
    def aggregator(self, db_engine):
        """Create aggregator with real database."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        def session_factory():
            return Session()
        
        return SpeedAggregator(
            db_session_factory=session_factory,
            window_seconds=60
        )
    
    def test_persist_to_speed_history(self, aggregator, db_engine):
        """Test recording speed samples to speed_history table."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        # Create a video first
        with Session() as session:
            video = Video(
                source_path="/test/video.mp4",
                title="Test Video",
            )
            session.add(video)
            session.commit()
            video_id = video.id
        
        # Add a sample and record to history
        aggregator.add_sample(
            video_id=video_id,
            stage="download",
            download_rate=1000000,
            upload_rate=500000
        )
        
        # Verify sample is in memory
        assert aggregator.sample_count == 1
        
        # Query speed_history directly
        with Session() as session:
            history = session.query(SpeedHistory).filter_by(video_id=video_id).all()
            # Note: The sample_from_downloads_table records to history,
            # not the add_sample method directly
            # So history should be empty here
            assert len(history) == 0
    
    def test_sample_from_downloads_table_integration(self, aggregator, db_engine):
        """Test sampling with real database."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        # Create a video and download
        with Session() as session:
            video = Video(
                source_path="/test/video.mp4",
                title="Test Video",
            )
            session.add(video)
            session.commit()
            video_id = video.id
            
            download = Download(
                video_id=video_id,
                source_type="youtube",
                status="downloading",
                download_rate=1000000,
                progress_percent=50.0,
                bytes_downloaded=500000,
            )
            session.add(download)
            session.commit()
        
        # Sample from downloads table
        count = aggregator.sample_from_downloads_table()
        
        assert count == 1
        assert aggregator.sample_count == 1
        
        # Verify speed history was recorded
        with Session() as session:
            history = session.query(SpeedHistory).filter_by(video_id=video_id).all()
            assert len(history) == 1
            assert history[0].speed == 1000000
            assert history[0].stage == "download"
    
    def test_get_speed_history_integration(self, aggregator, db_engine):
        """Test getting speed history with real database."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        # Create a video
        with Session() as session:
            video = Video(
                source_path="/test/video.mp4",
                title="Test Video",
            )
            session.add(video)
            session.commit()
            video_id = video.id
        
        # Add speed history entries
        with Session() as session:
            for i in range(5):
                entry = SpeedHistory(
                    video_id=video_id,
                    stage="download",
                    speed=1000000 * (i + 1),
                    progress=20.0 * (i + 1),
                    bytes_processed=100000 * (i + 1),
                )
                session.add(entry)
            session.commit()
        
        # Get speed history
        history = aggregator.get_speed_history_for_graphing(
            video_id=video_id,
            stage="download"
        )
        
        assert len(history) == 5
        # Verify timestamps are in order
        timestamps = [h[0] for h in history]
        assert timestamps == sorted(timestamps)
    
    def test_get_average_speeds_integration(self, aggregator, db_engine):
        """Test getting average speeds with real database."""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=db_engine)
        
        # Create a video
        with Session() as session:
            video = Video(
                source_path="/test/video.mp4",
                title="Test Video",
            )
            session.add(video)
            session.commit()
            video_id = video.id
        
        # Add speed history entries for download stage
        with Session() as session:
            for i in range(5):
                entry = SpeedHistory(
                    video_id=video_id,
                    stage="download",
                    speed=1000000 * (i + 1),  # 1, 2, 3, 4, 5 MB/s
                    progress=20.0 * (i + 1),
                    bytes_processed=100000 * (i + 1),
                )
                session.add(entry)
            session.commit()
        
        # Get average speeds
        download_avg, upload_avg = aggregator.get_average_speeds()
        
        # Average of 1, 2, 3, 4, 5 MB/s = 3 MB/s
        assert download_avg == 3000000.0
        assert upload_avg == 0.0
    
    def test_window_start_time(self, aggregator):
        """Test window_start_time property."""
        # Initially should return current time
        start_time = aggregator.window_start_time
        assert abs(start_time - time.time()) < 1.0
        
        # Add samples
        aggregator.add_sample(video_id=1, stage="download", download_rate=1000000)
        
        # Now should return first sample's timestamp
        start_time = aggregator.window_start_time
        assert abs(start_time - time.time()) < 1.0
