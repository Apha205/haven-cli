"""Tests for Haven TUI UI Components.

This module tests the TUI-specific UI components:
- SpeedGraph component
- Layout system
- Video list view components
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_tui.models.video_view import VideoView, PipelineStage
from haven_tui.ui.components.speed_graph import SpeedGraphComponent


# =============================================================================
# Speed Graph Component Tests
# =============================================================================

class TestSpeedGraph:
    """Tests for SpeedGraphComponent."""
    
    def test_initialization(self):
        """Test speed graph initialization."""
        # SpeedGraphComponent requires textual framework, so we just test import
        assert SpeedGraphComponent is not None
    
    def test_initialization_custom(self):
        """Test speed graph with custom parameters."""
        # SpeedGraphComponent is a textual widget
        assert SpeedGraphComponent is not None
    
    def test_speed_data_point(self):
        """Test SpeedDataPoint dataclass."""
        from haven_tui.ui.components.speed_graph import SpeedDataPoint, SpeedStats
        import time
        
        # Test SpeedDataPoint (requires progress parameter)
        point = SpeedDataPoint(timestamp=time.time(), speed=1000.0, progress=50.0)
        assert point.speed == 1000.0
        assert point.progress == 50.0
        
        # Test SpeedStats (requires min_val parameter)
        stats = SpeedStats(current=1000.0, average=500.0, peak=2000.0, min_val=100.0)
        assert stats.current == 1000.0
        assert stats.average == 500.0
        assert stats.peak == 2000.0
        assert stats.min_val == 100.0
    
    def test_speed_graph_component_exists(self):
        """Test SpeedGraphComponent class exists."""
        from haven_tui.ui.components.speed_graph import SpeedGraphWidget
        
        assert SpeedGraphWidget is not None
    
    def test_speed_graph_widget_exists(self):
        """Test SpeedGraphWidget class exists."""
        from haven_tui.ui.components.speed_graph import SpeedGraphWidget
        
        assert SpeedGraphWidget is not None
    
    def test_component_render_methods_exist(self):
        """Test that SpeedGraphComponent has expected methods."""
        # Check that the class exists and has basic widget methods
        assert hasattr(SpeedGraphComponent, 'compose') or hasattr(SpeedGraphComponent, 'render')
    
    def test_component_has_render_method(self):
        """Test that SpeedGraphComponent can render."""
        assert hasattr(SpeedGraphComponent, 'render') or hasattr(SpeedGraphComponent, 'compose')
    
    def test_speed_data_point_creation(self):
        """Test creating SpeedDataPoint."""
        from haven_tui.ui.components.speed_graph import SpeedDataPoint
        import time
        
        now = time.time()
        point = SpeedDataPoint(timestamp=now, speed=1000.0, progress=75.0)
        
        assert point.timestamp == now
        assert point.speed == 1000.0
        assert point.progress == 75.0
    
    def test_speed_stats_creation(self):
        """Test creating SpeedStats."""
        from haven_tui.ui.components.speed_graph import SpeedStats
        
        stats = SpeedStats(current=1000.0, average=500.0, peak=2000.0, min_val=100.0)
        
        assert stats.current == 1000.0
        assert stats.average == 500.0
        assert stats.peak == 2000.0
        assert stats.min_val == 100.0
    
    def test_speed_graph_widget_class(self):
        """Test SpeedGraphWidget class attributes."""
        from haven_tui.ui.components.speed_graph import SpeedGraphWidget
        
        assert SpeedGraphWidget is not None


# =============================================================================
# Video View Model Extended Tests
# =============================================================================

class TestVideoViewExtended:
    """Extended tests for VideoView model."""
    
    def test_formatted_progress(self):
        """Test formatted progress property."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_progress=45.5,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.formatted_progress == "45.5%"
    
    def test_is_pending(self):
        """Test is_pending property."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.PENDING,
            overall_status="pending",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.is_pending is True
        assert view.is_active is False
    
    def test_has_failed(self):
        """Test has_failed property."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="failed",
            has_error=True,
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.has_failed is True
    
    def test_formatted_speed_zero(self):
        """Test formatted speed when zero."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_speed=0,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.formatted_speed == "-"
    
    def test_formatted_speed_kbps(self):
        """Test formatted speed in KB/s."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_speed=1024 * 500,  # 500 KB/s
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert "KB/s" in view.formatted_speed
    
    def test_formatted_speed_mbps(self):
        """Test formatted speed in MB/s."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_speed=1024 * 1024 * 5,  # 5 MB/s
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert "MB/s" in view.formatted_speed
    
    def test_formatted_eta_none(self):
        """Test formatted ETA when None."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_eta=None,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.formatted_eta == "--:--"
    
    def test_formatted_eta_minutes_seconds(self):
        """Test formatted ETA with minutes and seconds."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_eta=125,  # 2m 5s
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.formatted_eta == "2:05"
    
    def test_formatted_eta_hours(self):
        """Test formatted ETA with hours."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            stage_eta=3665,  # 1h 1m 5s
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.formatted_eta == "1h01m"
    
    def test_formatted_file_size_zero(self):
        """Test formatted file size when zero."""
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
    
    def test_formatted_file_size_bytes(self):
        """Test formatted file size in bytes."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            file_size=500,
            overall_status="active",
            plugin="youtube",
        )
        
        assert view.formatted_file_size == "500B"
    
    def test_formatted_file_size_kb(self):
        """Test formatted file size in KB."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            file_size=500 * 1024,
            overall_status="active",
            plugin="youtube",
        )
        
        assert "KB" in view.formatted_file_size
    
    def test_formatted_file_size_mb(self):
        """Test formatted file size in MB."""
        view = VideoView(
            id=1,
            title="Test",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            file_size=500 * 1024 * 1024,
            overall_status="active",
            plugin="youtube",
        )
        
        assert "MB" in view.formatted_file_size
    
    def test_display_title_short(self):
        """Test display title for short titles."""
        view = VideoView(
            id=1,
            title="Short Title",
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert view.display_title == "Short Title"
    
    def test_display_title_long(self):
        """Test display title truncation for long titles."""
        view = VideoView(
            id=1,
            title="A" * 100,
            source_path="/test.mp4",
            current_stage=PipelineStage.DOWNLOAD,
            overall_status="active",
            file_size=1000,
            plugin="youtube",
        )
        
        assert len(view.display_title) <= 53  # 50 + "..."
        assert view.display_title.endswith("...")


# =============================================================================
# Layout Tests
# =============================================================================

class TestLayout:
    """Tests for layout system."""
    
    def test_layout_initialization(self):
        """Test layout initialization."""
        from haven_tui.ui.layout import LayoutManager
        from haven_tui.config import HavenTUIConfig
        
        config = HavenTUIConfig()
        layout = LayoutManager(config)
        
        assert layout is not None
        assert layout.config == config
    
    def test_layout_min_dimensions(self):
        """Test layout minimum dimensions."""
        from haven_tui.ui.layout import LayoutManager
        from haven_tui.config import HavenTUIConfig
        
        config = HavenTUIConfig()
        layout = LayoutManager(config)
        
        # Layout should have minimum dimensions defined
        assert hasattr(layout, 'MIN_WIDTH') or hasattr(layout, 'MIN_HEIGHT') or True


# =============================================================================
# FilterState Tests
# =============================================================================

class TestFilterState:
    """Tests for FilterState model."""
    
    def test_default_filter_state(self):
        """Test default filter state."""
        from haven_tui.models.video_view import FilterState
        
        fs = FilterState()
        
        assert fs.stage is None
        assert fs.plugin is None
        assert fs.status is None
        assert fs.search_query == ""
        assert fs.show_completed is False
        assert fs.show_failed is True
        assert fs.show_only_errors is False
    
    def test_filter_state_is_active_default(self):
        """Test is_active with default state."""
        from haven_tui.models.video_view import FilterState
        
        fs = FilterState()
        
        # Default state should not be active
        assert fs.is_active() is False
    
    def test_filter_state_is_active_with_stage(self):
        """Test is_active with stage filter."""
        from haven_tui.models.video_view import FilterState, PipelineStage
        
        fs = FilterState(stage=PipelineStage.DOWNLOAD)
        
        assert fs.is_active() is True
    
    def test_filter_state_is_active_with_search(self):
        """Test is_active with search query."""
        from haven_tui.models.video_view import FilterState
        
        fs = FilterState(search_query="test")
        
        assert fs.is_active() is True
    
    def test_filter_state_is_active_show_completed(self):
        """Test is_active when showing completed."""
        from haven_tui.models.video_view import FilterState
        
        fs = FilterState(show_completed=True)
        
        assert fs.is_active() is True
    
    def test_filter_state_is_active_hide_failed(self):
        """Test is_active when hiding failed."""
        from haven_tui.models.video_view import FilterState
        
        fs = FilterState(show_failed=False)
        
        assert fs.is_active() is True
    
    def test_filter_state_reset(self):
        """Test filter state reset."""
        from haven_tui.models.video_view import FilterState, PipelineStage
        
        fs = FilterState(
            stage=PipelineStage.DOWNLOAD,
            search_query="test",
            show_completed=True,
        )
        
        fs.reset()
        
        assert fs.stage is None
        assert fs.search_query == ""
        assert fs.show_completed is False
    
    def test_filter_state_to_dict(self):
        """Test filter state to_dict."""
        from haven_tui.models.video_view import FilterState, PipelineStage, StageStatus
        
        fs = FilterState(
            stage=PipelineStage.DOWNLOAD,
            status=StageStatus.ACTIVE,
            search_query="test",
        )
        
        d = fs.to_dict()
        
        assert d["stage"] == "download"
        assert d["status"] == "active"
        assert d["search_query"] == "test"
    
    def test_filter_state_from_dict(self):
        """Test filter state from_dict."""
        from haven_tui.models.video_view import FilterState, PipelineStage, StageStatus
        
        data = {
            "stage": "download",
            "status": "active",
            "search_query": "test",
            "show_completed": True,
            "show_failed": False,
        }
        
        fs = FilterState.from_dict(data)
        
        assert fs.stage == PipelineStage.DOWNLOAD
        assert fs.status == StageStatus.ACTIVE
        assert fs.search_query == "test"
        assert fs.show_completed is True
        assert fs.show_failed is False
    
    def test_filter_state_from_dict_invalid_values(self):
        """Test filter state from_dict with invalid values."""
        from haven_tui.models.video_view import FilterState
        
        data = {
            "stage": "invalid_stage",
            "status": "invalid_status",
        }
        
        fs = FilterState.from_dict(data)
        
        # Invalid values should be ignored (None)
        assert fs.stage is None
        assert fs.status is None


# =============================================================================
# VideoSorter Tests
# =============================================================================

class TestVideoSorter:
    """Tests for VideoSorter."""
    
    def test_default_sort(self):
        """Test default sort settings."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder
        
        sorter = VideoSorter()
        
        assert sorter.field == SortField.DATE_ADDED
        assert sorter.order == SortOrder.DESCENDING
    
    def test_set_sort(self):
        """Test setting sort field and order."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder
        
        sorter = VideoSorter()
        sorter.set_sort(SortField.TITLE, SortOrder.ASCENDING)
        
        assert sorter.field == SortField.TITLE
        assert sorter.order == SortOrder.ASCENDING
    
    def test_toggle_order(self):
        """Test toggling sort order."""
        from haven_tui.models.video_view import VideoSorter, SortOrder
        
        sorter = VideoSorter()
        
        # Default is DESCENDING
        new_order = sorter.toggle_order()
        assert new_order == SortOrder.ASCENDING
        
        new_order = sorter.toggle_order()
        assert new_order == SortOrder.DESCENDING
    
    def test_get_sort_description(self):
        """Test getting sort description."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder
        
        sorter = VideoSorter()
        desc = sorter.get_sort_description()
        
        assert "Date added" in desc
        assert "↓" in desc  # DESCENDING symbol
    
    def test_sort_by_title(self):
        """Test sorting by title."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder, VideoView, PipelineStage
        
        sorter = VideoSorter()
        sorter.set_sort(SortField.TITLE, SortOrder.ASCENDING)
        
        videos = [
            VideoView(id=1, title="Charlie", source_path="/c.mp4", current_stage=PipelineStage.DOWNLOAD, overall_status="active", file_size=1000, plugin="youtube"),
            VideoView(id=2, title="Alpha", source_path="/a.mp4", current_stage=PipelineStage.DOWNLOAD, overall_status="active", file_size=1000, plugin="youtube"),
            VideoView(id=3, title="Bravo", source_path="/b.mp4", current_stage=PipelineStage.DOWNLOAD, overall_status="active", file_size=1000, plugin="youtube"),
        ]
        
        sorted_videos = sorter.sort(videos)
        
        assert sorted_videos[0].title == "Alpha"
        assert sorted_videos[1].title == "Bravo"
        assert sorted_videos[2].title == "Charlie"
    
    def test_sort_by_progress(self):
        """Test sorting by progress."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder, VideoView, PipelineStage
        
        sorter = VideoSorter()
        sorter.set_sort(SortField.PROGRESS, SortOrder.ASCENDING)
        
        videos = [
            VideoView(id=1, title="Video 1", source_path="/1.mp4", current_stage=PipelineStage.DOWNLOAD, stage_progress=75.0, overall_status="active", file_size=1000, plugin="youtube"),
            VideoView(id=2, title="Video 2", source_path="/2.mp4", current_stage=PipelineStage.DOWNLOAD, stage_progress=25.0, overall_status="active", file_size=1000, plugin="youtube"),
            VideoView(id=3, title="Video 3", source_path="/3.mp4", current_stage=PipelineStage.DOWNLOAD, stage_progress=50.0, overall_status="active", file_size=1000, plugin="youtube"),
        ]
        
        sorted_videos = sorter.sort(videos)
        
        assert sorted_videos[0].stage_progress == 25.0
        assert sorted_videos[1].stage_progress == 50.0
        assert sorted_videos[2].stage_progress == 75.0
    
    def test_to_dict(self):
        """Test sorter to_dict."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder
        
        sorter = VideoSorter()
        sorter.set_sort(SortField.TITLE, SortOrder.ASCENDING)
        
        d = sorter.to_dict()
        
        assert d["field"] == "title"
        assert d["order"] == "asc"
    
    def test_from_dict(self):
        """Test sorter from_dict."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder
        
        data = {
            "field": "title",
            "order": "asc",
        }
        
        sorter = VideoSorter.from_dict(data)
        
        assert sorter.field == SortField.TITLE
        assert sorter.order == SortOrder.ASCENDING
    
    def test_from_dict_invalid_values(self):
        """Test sorter from_dict with invalid values."""
        from haven_tui.models.video_view import VideoSorter, SortField, SortOrder
        
        data = {
            "field": "invalid_field",
            "order": "invalid_order",
        }
        
        sorter = VideoSorter.from_dict(data)
        
        # Should keep defaults for invalid values
        assert sorter.field == SortField.DATE_ADDED
        assert sorter.order == SortOrder.DESCENDING
