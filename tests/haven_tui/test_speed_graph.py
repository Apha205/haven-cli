"""Tests for Speed Graph Component.

Tests the SpeedGraphComponent and SpeedGraphWidget classes.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from haven_tui.ui.components.speed_graph import (
    SpeedGraphComponent,
    SpeedGraphWidget,
    SpeedDataPoint,
    SpeedStats,
)


class MockSpeedHistory:
    """Mock SpeedHistory entry for testing."""
    
    def __init__(self, timestamp: datetime, speed: int, progress: float = 0.0):
        self.timestamp = timestamp
        self.speed = speed
        self.progress = progress


class TestSpeedDataPoint:
    """Tests for SpeedDataPoint dataclass."""
    
    def test_create_speed_data_point(self) -> None:
        """Test creating a SpeedDataPoint."""
        now = time.time()
        point = SpeedDataPoint(
            timestamp=now,
            speed=1024 * 1024,  # 1 MB/s
            progress=50.0,
        )
        
        assert point.timestamp == now
        assert point.speed == 1024 * 1024
        assert point.progress == 50.0


class TestSpeedStats:
    """Tests for SpeedStats dataclass."""
    
    def test_create_speed_stats(self) -> None:
        """Test creating SpeedStats."""
        stats = SpeedStats(
            current=1024 * 1024,
            average=512 * 1024,
            peak=2 * 1024 * 1024,
            min_val=256 * 1024,
        )
        
        assert stats.current == 1024 * 1024
        assert stats.average == 512 * 1024
        assert stats.peak == 2 * 1024 * 1024
        assert stats.min_val == 256 * 1024


class TestSpeedGraphComponent:
    """Tests for SpeedGraphComponent."""
    
    def test_initialization(self) -> None:
        """Test component initialization."""
        component = SpeedGraphComponent()
        
        assert component.graph_width == 60
        assert component.graph_height == 15
        assert component.history_seconds == 60
        assert component.video_id is None
        assert component.current_stage == "download"
        assert component.speed_history_repo is None
    
    def test_initialization_with_custom_params(self) -> None:
        """Test initialization with custom parameters."""
        mock_repo = MagicMock()
        component = SpeedGraphComponent(
            speed_history_repo=mock_repo,
            width=80,
            height=20,
            history_seconds=120,
        )
        
        assert component.graph_width == 80
        assert component.graph_height == 20
        assert component.history_seconds == 120
        assert component.speed_history_repo == mock_repo
    
    def test_set_repository(self) -> None:
        """Test setting repository."""
        component = SpeedGraphComponent()
        mock_repo = MagicMock()
        
        component.set_repository(mock_repo)
        
        assert component.speed_history_repo == mock_repo
    
    def test_set_video(self) -> None:
        """Test setting video."""
        component = SpeedGraphComponent()
        
        component.set_video(123, "upload")
        
        assert component.video_id == 123
        assert component.current_stage == "upload"
    
    def test_format_speed_bytes(self) -> None:
        """Test speed formatting for bytes."""
        component = SpeedGraphComponent()
        
        result = component._format_speed(500)
        
        assert result == "500 B/s"
    
    def test_format_speed_kib(self) -> None:
        """Test speed formatting for KiB."""
        component = SpeedGraphComponent()
        
        result = component._format_speed(1536)
        
        assert result == "1.5 KiB/s"
    
    def test_format_speed_mib(self) -> None:
        """Test speed formatting for MiB."""
        component = SpeedGraphComponent()
        
        result = component._format_speed(2.5 * 1024 * 1024)
        
        assert result == "2.5 MiB/s"
    
    def test_format_speed_gib(self) -> None:
        """Test speed formatting for GiB."""
        component = SpeedGraphComponent()
        
        result = component._format_speed(3 * 1024 * 1024 * 1024)
        
        assert result == "3.0 GiB/s"
    
    def test_format_speed_zero(self) -> None:
        """Test speed formatting for zero."""
        component = SpeedGraphComponent()
        
        result = component._format_speed(0)
        
        assert result == "-"
    
    def test_update_stats_with_data(self) -> None:
        """Test statistics calculation with data."""
        component = SpeedGraphComponent()
        now = time.time()
        
        component._speed_data = [
            SpeedDataPoint(timestamp=now - 30, speed=1024 * 1024, progress=10),
            SpeedDataPoint(timestamp=now - 20, speed=2 * 1024 * 1024, progress=20),
            SpeedDataPoint(timestamp=now - 10, speed=512 * 1024, progress=30),
        ]
        
        component._update_stats()
        
        assert component._stats.current == 512 * 1024
        assert component._stats.peak == 2 * 1024 * 1024
        assert component._stats.min_val == 512 * 1024
        assert component._stats.average == (1024 * 1024 + 2 * 1024 * 1024 + 512 * 1024) / 3
    
    def test_update_stats_empty(self) -> None:
        """Test statistics calculation with no data."""
        component = SpeedGraphComponent()
        
        component._speed_data = []
        component._update_stats()
        
        assert component._stats.current == 0
        assert component._stats.average == 0
        assert component._stats.peak == 0
        assert component._stats.min_val == 0
    
    def test_render_empty_state(self) -> None:
        """Test rendering empty state."""
        component = SpeedGraphComponent(width=40, height=10)
        
        result = component._render_empty()
        
        assert "No speed data available" in result
        assert "Speed History" in result
    
    def test_render_stats(self) -> None:
        """Test rendering statistics."""
        component = SpeedGraphComponent()
        component._stats = SpeedStats(
            current=1024 * 1024,
            average=512 * 1024,
            peak=2 * 1024 * 1024,
            min_val=256 * 1024,
        )
        
        result = component._render_stats()
        
        assert "Current:" in result
        assert "Average:" in result
        assert "Peak:" in result
        assert "1.0 MiB/s" in result  # current
        assert "512.0 KiB/s" in result  # average
        assert "2.0 MiB/s" in result  # peak
    
    def test_render_stage_timeline(self) -> None:
        """Test rendering stage timeline."""
        component = SpeedGraphComponent()
        now = time.time()
        
        stage_data = {
            "download": [
                SpeedDataPoint(timestamp=now - 30, speed=1024 * 1024, progress=10),
            ],
            "encrypt": [
                SpeedDataPoint(timestamp=now - 10, speed=512 * 1024, progress=50),
            ],
        }
        
        result = component._render_stage_timeline(stage_data)
        
        assert "[Download]" in result
        assert "[Encrypt]" in result
        assert "[Upload]" in result
        assert "►" in result
    
    def test_refresh_graph_no_video(self) -> None:
        """Test refresh with no video set."""
        component = SpeedGraphComponent()
        
        component.refresh_graph()
        
        assert component._speed_data == []
        assert component._stats.current == 0
    
    def test_refresh_graph_with_data(self) -> None:
        """Test refresh with repository data."""
        mock_repo = MagicMock()
        now = datetime.now(timezone.utc)
        
        mock_repo.get_speed_history.return_value = [
            MockSpeedHistory(timestamp=now, speed=1024 * 1024, progress=10),
            MockSpeedHistory(timestamp=now, speed=2 * 1024 * 1024, progress=20),
        ]
        
        component = SpeedGraphComponent(speed_history_repo=mock_repo)
        component.video_id = 123
        component.current_stage = "download"
        
        # Mock time to ensure data is within window
        with patch("time.time", return_value=now.timestamp() + 1):
            component.refresh_graph()
        
        mock_repo.get_speed_history.assert_called_once_with(
            video_id=123,
            stage="download",
            minutes=2,  # history_seconds=60 -> 1 + 1 = 2
        )
        assert len(component._speed_data) == 2
    
    def test_refresh_graph_filters_old_data(self) -> None:
        """Test that old data outside history window is filtered."""
        mock_repo = MagicMock()
        now = datetime.now(timezone.utc)
        
        # Data from 2 minutes ago (outside default 60s window)
        old_time = datetime.fromtimestamp(now.timestamp() - 120, timezone.utc)
        
        mock_repo.get_speed_history.return_value = [
            MockSpeedHistory(timestamp=old_time, speed=1024 * 1024, progress=10),
            MockSpeedHistory(timestamp=now, speed=2 * 1024 * 1024, progress=20),
        ]
        
        component = SpeedGraphComponent(
            speed_history_repo=mock_repo,
            history_seconds=60,
        )
        component.video_id = 123
        
        with patch("time.time", return_value=now.timestamp()):
            component.refresh_graph()
        
        # Only recent data should be included
        assert len(component._speed_data) == 1
        assert component._speed_data[0].speed == 2 * 1024 * 1024
    
    def test_render_fallback_graph(self) -> None:
        """Test fallback graph rendering."""
        component = SpeedGraphComponent(width=40, height=15)
        now = time.time()
        
        component._speed_data = [
            SpeedDataPoint(timestamp=now - 50, speed=1024 * 1024, progress=10),
            SpeedDataPoint(timestamp=now - 40, speed=2 * 1024 * 1024, progress=20),
            SpeedDataPoint(timestamp=now - 30, speed=1.5 * 1024 * 1024, progress=30),
            SpeedDataPoint(timestamp=now - 20, speed=512 * 1024, progress=40),
            SpeedDataPoint(timestamp=now - 10, speed=1024 * 1024, progress=50),
        ]
        
        lines = component._render_fallback_graph()
        
        assert len(lines) > 0
        # Check for axis labels
        assert any("now" in line for line in lines)
    
    def test_render_multi_stage(self) -> None:
        """Test multi-stage rendering."""
        mock_repo = MagicMock()
        now = datetime.now(timezone.utc)
        
        mock_repo.get_speed_history.side_effect = lambda **kwargs: {
            ("download",): [
                MockSpeedHistory(timestamp=now, speed=1024 * 1024, progress=10),
            ],
            ("encrypt",): [
                MockSpeedHistory(timestamp=now, speed=512 * 1024, progress=50),
            ],
            ("upload",): [],
        }.get((kwargs.get("stage"),), [])
        
        component = SpeedGraphComponent(speed_history_repo=mock_repo)
        component.video_id = 123
        
        with patch("time.time", return_value=now.timestamp() + 1):
            result = component.render_multi_stage()
        
        assert "Multi-Stage Speed History" in result
    
    def test_render_multi_stage_no_data(self) -> None:
        """Test multi-stage rendering with no data."""
        mock_repo = MagicMock()
        mock_repo.get_speed_history.return_value = []
        
        component = SpeedGraphComponent(speed_history_repo=mock_repo)
        component.video_id = 123
        
        result = component.render_multi_stage()
        
        assert "No speed data available" in result


class TestSpeedGraphWidget:
    """Tests for SpeedGraphWidget."""
    
    def test_initialization(self) -> None:
        """Test widget initialization."""
        mock_repo = MagicMock()
        widget = SpeedGraphWidget(speed_history_repo=mock_repo)
        
        assert widget._graph_component is not None
        assert widget._graph_component.speed_history_repo == mock_repo
    
    def test_set_video(self) -> None:
        """Test setting video on widget."""
        widget = SpeedGraphWidget()
        
        with patch.object(widget._graph_component, "set_video") as mock_set:
            widget.set_video(123, "encrypt")
            
            mock_set.assert_called_once_with(123, "encrypt")
    
    def test_set_repository(self) -> None:
        """Test setting repository on widget."""
        widget = SpeedGraphWidget()
        mock_repo = MagicMock()
        
        with patch.object(widget._graph_component, "set_repository") as mock_set:
            widget.set_repository(mock_repo)
            
            mock_set.assert_called_once_with(mock_repo)


class TestIntegration:
    """Integration tests for speed graph component."""
    
    def test_end_to_end_flow(self) -> None:
        """Test complete flow from data to render."""
        mock_repo = MagicMock()
        now = datetime.now(timezone.utc)
        
        # Create realistic speed data
        speed_data: List[MockSpeedHistory] = []
        for i in range(10):
            speed = int((1024 * 1024) * (1 + (i / 10)))  # Increasing speed
            timestamp = datetime.fromtimestamp(now.timestamp() - (10 - i) * 5, timezone.utc)
            speed_data.append(MockSpeedHistory(timestamp=timestamp, speed=speed, progress=i * 10))
        
        mock_repo.get_speed_history.return_value = speed_data
        
        component = SpeedGraphComponent(
            speed_history_repo=mock_repo,
            width=60,
            height=15,
            history_seconds=60,
        )
        
        # Set video and refresh
        with patch("time.time", return_value=now.timestamp() + 1):
            component.set_video(123, "download")
        
        # Verify data was loaded
        assert len(component._speed_data) == 10
        assert component._stats.peak > 0
        assert component._stats.current > 0
        
        # Verify rendering
        output = component._render()
        assert "Speed History" in output
        assert "Current:" in output
        assert "Average:" in output
        assert "Peak:" in output
    
    def test_rolling_history(self) -> None:
        """Test that only recent history within window is shown."""
        mock_repo = MagicMock()
        now = datetime.now(timezone.utc)
        
        # Create data spanning 2 minutes
        speed_data: List[MockSpeedHistory] = []
        for i in range(24):  # 24 data points, 5 seconds apart
            speed = 1024 * 1024
            timestamp = datetime.fromtimestamp(now.timestamp() - (24 - i) * 5, timezone.utc)
            speed_data.append(MockSpeedHistory(timestamp=timestamp, speed=speed, progress=i * 4))
        
        mock_repo.get_speed_history.return_value = speed_data
        
        component = SpeedGraphComponent(
            speed_history_repo=mock_repo,
            history_seconds=60,  # Only show last 60 seconds
        )
        
        with patch("time.time", return_value=now.timestamp() + 1):
            component.set_video(123, "download")
        
        # Should only have data from last 60 seconds (~12 points)
        assert len(component._speed_data) <= 13
        assert len(component._speed_data) >= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
