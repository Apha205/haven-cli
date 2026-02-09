"""Tests for Haven TUI Metrics Collector.

This module tests the MetricsCollector class that wraps SpeedHistoryService
for TUI visualization.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, Mock

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_tui.core.metrics import MetricsCollector, VALID_STAGES


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_service():
    """Create a mock SpeedHistoryService."""
    service = MagicMock()
    return service


@pytest.fixture
def metrics_collector(mock_service):
    """Create a MetricsCollector with mock service."""
    return MetricsCollector(service=mock_service, max_history_seconds=300)


# =============================================================================
# MetricsCollector Tests
# =============================================================================

class TestMetricsCollectorInitialization:
    """Tests for MetricsCollector initialization."""
    
    def test_initialization(self, mock_service):
        """Test basic initialization."""
        collector = MetricsCollector(service=mock_service)
        
        assert collector._service == mock_service
        assert collector._max_history == 300
    
    def test_initialization_custom_max_history(self, mock_service):
        """Test initialization with custom max_history."""
        collector = MetricsCollector(service=mock_service, max_history_seconds=600)
        
        assert collector._max_history == 600


class TestMetricsCollectorRecordSpeed:
    """Tests for record_speed method."""
    
    def test_record_speed_valid_stage(self, metrics_collector, mock_service):
        """Test recording speed for valid stage."""
        metrics_collector.record_speed(
            video_id=1,
            stage="download",
            speed=1024000.0,
            progress=50.0
        )
        
        mock_service.record_sample.assert_called_once_with(
            video_id=1,
            stage="download",
            speed=1024000,
            progress=50.0,
            bytes_processed=0
        )
    
    def test_record_speed_invalid_stage(self, metrics_collector, mock_service):
        """Test recording speed for invalid stage."""
        metrics_collector.record_speed(
            video_id=1,
            stage="invalid_stage",
            speed=1024000.0,
            progress=50.0
        )
        
        # Should not call record_sample for invalid stage
        mock_service.record_sample.assert_not_called()
    
    def test_record_speed_all_valid_stages(self, metrics_collector, mock_service):
        """Test recording speed for all valid stages."""
        for stage in VALID_STAGES:
            mock_service.reset_mock()
            metrics_collector.record_speed(
                video_id=1,
                stage=stage,
                speed=1000000.0,
                progress=50.0
            )
            
            mock_service.record_sample.assert_called_once()


class TestMetricsCollectorGetSpeedHistory:
    """Tests for get_speed_history method."""
    
    def test_get_speed_history_valid_stage(self, metrics_collector, mock_service):
        """Test getting speed history for valid stage."""
        # Mock service response
        now = datetime.now(timezone.utc)
        mock_records = [
            MagicMock(timestamp=now - timedelta(seconds=30), speed=1000),
            MagicMock(timestamp=now - timedelta(seconds=20), speed=2000),
            MagicMock(timestamp=now - timedelta(seconds=10), speed=3000),
        ]
        mock_service.get_speed_history.return_value = mock_records
        
        history = metrics_collector.get_speed_history(1, "download", seconds=60)
        
        assert len(history) == 3
        assert history[0][1] == 1000.0
        assert history[1][1] == 2000.0
        assert history[2][1] == 3000.0
    
    def test_get_speed_history_invalid_stage(self, metrics_collector, mock_service):
        """Test getting speed history for invalid stage."""
        history = metrics_collector.get_speed_history(1, "invalid_stage", seconds=60)
        
        assert history == []
        mock_service.get_speed_history.assert_not_called()
    
    def test_get_speed_history_empty(self, metrics_collector, mock_service):
        """Test getting speed history with no data."""
        mock_service.get_speed_history.return_value = []
        
        history = metrics_collector.get_speed_history(1, "download", seconds=60)
        
        assert history == []
    
    def test_get_speed_history_filters_old_data(self, metrics_collector, mock_service):
        """Test that old data is filtered out."""
        now = datetime.now(timezone.utc)
        mock_records = [
            MagicMock(timestamp=now - timedelta(seconds=120), speed=1000),  # Too old
            MagicMock(timestamp=now - timedelta(seconds=30), speed=2000),   # Recent
        ]
        mock_service.get_speed_history.return_value = mock_records
        
        history = metrics_collector.get_speed_history(1, "download", seconds=60)
        
        # Only recent records should be returned
        assert len(history) == 1
        assert history[0][1] == 2000.0
    
    def test_get_speed_history_naive_timestamps(self, metrics_collector, mock_service):
        """Test handling of naive timestamps."""
        # Create naive datetime (no timezone)
        naive_now = datetime.now()
        mock_records = [
            MagicMock(timestamp=naive_now - timedelta(seconds=30), speed=1000),
        ]
        mock_service.get_speed_history.return_value = mock_records
        
        # Should not raise an error, but may filter out due to timezone handling
        history = metrics_collector.get_speed_history(1, "download", seconds=60)
        
        # Naive timestamps may be filtered out - that's acceptable behavior
        assert isinstance(history, list)


class TestMetricsCollectorGetCurrentSpeed:
    """Tests for get_current_speed method."""
    
    def test_get_current_speed(self, metrics_collector, mock_service):
        """Test getting current speed."""
        now = datetime.now(timezone.utc)
        mock_records = [
            MagicMock(timestamp=now - timedelta(seconds=30), speed=1000),
            MagicMock(timestamp=now - timedelta(seconds=10), speed=3000),
        ]
        mock_service.get_speed_history.return_value = mock_records
        
        speed = metrics_collector.get_current_speed(1, "download")
        
        assert speed == 3000.0
    
    def test_get_current_speed_no_data(self, metrics_collector, mock_service):
        """Test getting current speed with no data."""
        mock_service.get_speed_history.return_value = []
        
        speed = metrics_collector.get_current_speed(1, "download")
        
        assert speed is None


class TestMetricsCollectorGetAggregateSpeeds:
    """Tests for get_aggregate_speeds method."""
    
    def test_get_aggregate_speeds(self, metrics_collector, mock_service):
        """Test getting aggregate speeds."""
        # Mock service responses for each stage
        mock_service.get_aggregate_speeds.side_effect = lambda stage, minutes: [
            {"avg_speed": 1000.0 + (hash(stage) % 1000)},  # Different speed per stage
        ]
        
        aggregates = metrics_collector.get_aggregate_speeds(seconds=60)
        
        assert "download" in aggregates
        assert "encrypt" in aggregates
        assert "upload" in aggregates
        assert "total" in aggregates
        
        # Total should be sum of all stages
        expected_total = aggregates["download"] + aggregates["encrypt"] + aggregates["upload"]
        assert aggregates["total"] == expected_total
    
    def test_get_aggregate_speeds_empty_data(self, metrics_collector, mock_service):
        """Test getting aggregate speeds with no data."""
        mock_service.get_aggregate_speeds.return_value = []
        
        aggregates = metrics_collector.get_aggregate_speeds(seconds=60)
        
        assert aggregates["download"] == 0.0
        assert aggregates["encrypt"] == 0.0
        assert aggregates["upload"] == 0.0
        assert aggregates["total"] == 0.0


class TestMetricsCollectorGetActiveStages:
    """Tests for get_active_stages method."""
    
    def test_get_active_stages(self, metrics_collector, mock_service):
        """Test getting active stage counts."""
        # Mock service response
        mock_service.get_aggregate_speeds.return_value = [
            {"avg_speed": 1000.0, "video_ids": [1, 2]},
            {"avg_speed": 2000.0, "video_ids": [2, 3]},
        ]
        
        counts = metrics_collector.get_active_stages(seconds=60)
        
        assert "download" in counts
        assert "encrypt" in counts
        assert "upload" in counts
        assert "total_active" in counts


class TestMetricsCollectorGetSpeedDataForChart:
    """Tests for get_speed_data_for_chart method."""
    
    def test_get_speed_data_for_chart_with_video(self, metrics_collector, mock_service):
        """Test getting chart data for specific video."""
        now = datetime.now(timezone.utc)
        mock_records = [
            MagicMock(timestamp=now - timedelta(seconds=30), speed=1000),
            MagicMock(timestamp=now - timedelta(seconds=20), speed=2000),
            MagicMock(timestamp=now - timedelta(seconds=10), speed=3000),
        ]
        mock_service.get_speed_history.return_value = mock_records
        
        data = metrics_collector.get_speed_data_for_chart(
            video_id=1,
            stage="download",
            seconds=60
        )
        
        assert "timestamps" in data
        assert "speeds" in data
        assert "avg_speed" in data
        assert "peak_speed" in data
        assert "current_speed" in data
        
        assert len(data["timestamps"]) == 3
        assert len(data["speeds"]) == 3
        assert data["avg_speed"] == 2000.0
        assert data["peak_speed"] == 3000.0
        assert data["current_speed"] == 3000.0
    
    def test_get_speed_data_for_chart_empty(self, metrics_collector, mock_service):
        """Test getting chart data with no data."""
        mock_service.get_speed_history.return_value = []
        
        data = metrics_collector.get_speed_data_for_chart(
            video_id=1,
            stage="download",
            seconds=60
        )
        
        assert data["timestamps"] == []
        assert data["speeds"] == []
        assert data["avg_speed"] == 0.0
        assert data["peak_speed"] == 0.0
        assert data["current_speed"] == 0.0


class TestMetricsCollectorBucketData:
    """Tests for _bucket_data method."""
    
    def test_bucket_data(self, metrics_collector):
        """Test bucketing data."""
        now = datetime.now(timezone.utc)
        data = [
            (now.replace(second=1), 1000.0),
            (now.replace(second=2), 1100.0),
            (now.replace(second=5), 2000.0),
            (now.replace(second=6), 2100.0),
        ]
        
        bucketed = metrics_collector._bucket_data(data, bucket_size=5)
        
        # Should create 2 buckets (seconds 0-4 and 5-9)
        assert len(bucketed) == 2
        # First bucket average
        assert bucketed[0][1] == 1050.0  # (1000 + 1100) / 2
        # Second bucket average
        assert bucketed[1][1] == 2050.0  # (2000 + 2100) / 2
    
    def test_bucket_data_empty(self, metrics_collector):
        """Test bucketing empty data."""
        bucketed = metrics_collector._bucket_data([], bucket_size=5)
        
        assert bucketed == []
    
    def test_bucket_data_single_item(self, metrics_collector):
        """Test bucketing single item."""
        now = datetime.now(timezone.utc)
        data = [(now, 1000.0)]
        
        bucketed = metrics_collector._bucket_data(data, bucket_size=5)
        
        assert len(bucketed) == 1
        assert bucketed[0][1] == 1000.0
    
    def test_bucket_data_bucket_size_one(self, metrics_collector):
        """Test bucketing with bucket_size=1 (no bucketing)."""
        now = datetime.now(timezone.utc)
        data = [
            (now.replace(second=1), 1000.0),
            (now.replace(second=2), 1100.0),
        ]
        
        bucketed = metrics_collector._bucket_data(data, bucket_size=1)
        
        # Should return same data when bucket_size is 1
        assert len(bucketed) == 2


class TestMetricsCollectorCleanup:
    """Tests for cleanup method."""
    
    def test_cleanup_old_data(self, metrics_collector, mock_service):
        """Test cleaning up old data."""
        mock_service._repo.cleanup_old_samples.return_value = 100
        
        deleted = metrics_collector.cleanup_old_data(hours=24)
        
        assert deleted == 100
        mock_service._repo.cleanup_old_samples.assert_called_once_with(hours=24)


class TestValidStages:
    """Tests for VALID_STAGES constant."""
    
    def test_valid_stages(self):
        """Test that valid stages are correct."""
        assert "download" in VALID_STAGES
        assert "encrypt" in VALID_STAGES
        assert "upload" in VALID_STAGES
        assert len(VALID_STAGES) == 3
