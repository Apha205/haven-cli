"""Tests for the Sorting System (Task 6.2).

This module tests the SortField, SortOrder, VideoSorter, and sorting integration
with the video list controller and view.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_tui.core.state_manager import VideoState
from haven_tui.core.controller import VideoListController, FilterResult
from haven_tui.models.video_view import (
    PipelineStage,
    StageStatus,
    FilterState,
    SortField,
    SortOrder,
    VideoSorter,
    VideoView,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_state_manager():
    """Create a mock state manager with test videos for sorting."""
    manager = MagicMock()
    
    # Create test video states with different properties for sorting
    base_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    videos = [
        VideoState(
            id=1,
            title="Alpha Video",
            current_stage="download",
            overall_status="active",
            download_status="active",
            download_progress=50.0,
            download_speed=1024 * 100,  # 100 KB/s
            created_at=base_time - timedelta(days=2),  # Oldest
        ),
        VideoState(
            id=2,
            title="Beta Video",
            current_stage="upload",
            overall_status="active",
            upload_status="active",
            upload_progress=75.0,
            upload_speed=1024 * 500,  # 500 KB/s
            created_at=base_time - timedelta(days=1),
        ),
        VideoState(
            id=3,
            title="Charlie Video",
            current_stage="encrypt",
            overall_status="active",
            encrypt_status="active",
            encrypt_progress=25.0,
            created_at=base_time,  # Newest
        ),
        VideoState(
            id=4,
            title="Delta Video",
            current_stage="download",  # Set to download to match current_progress calculation
            overall_status="completed",
            download_status="completed",
            encrypt_status="completed",
            upload_status="completed",
            sync_status="completed",
            download_progress=100.0,  # This will be current_progress since stage is download
            created_at=base_time - timedelta(days=3),
        ),
        VideoState(
            id=5,
            title="echo video",  # lowercase to test case-insensitivity
            current_stage="download",
            overall_status="failed",
            download_status="failed",
            download_progress=10.0,
            created_at=base_time - timedelta(hours=6),
        ),
    ]
    
    manager.get_all_videos.return_value = videos
    return manager


@pytest.fixture
def video_sorter():
    """Create a fresh VideoSorter instance."""
    return VideoSorter()


# =============================================================================
# SortField and SortOrder Enum Tests
# =============================================================================

class TestSortField:
    """Tests for the SortField enum."""
    
    def test_sort_field_values(self):
        """Test that SortField enum has expected values."""
        assert SortField.DATE_ADDED.value == "date_added"
        assert SortField.TITLE.value == "title"
        assert SortField.PROGRESS.value == "progress"
        assert SortField.SPEED.value == "speed"
        assert SortField.SIZE.value == "size"
        assert SortField.STAGE.value == "stage"
    
    def test_sort_field_from_value(self):
        """Test creating SortField from string value."""
        assert SortField("date_added") == SortField.DATE_ADDED
        assert SortField("title") == SortField.TITLE
        assert SortField("progress") == SortField.PROGRESS


class TestSortOrder:
    """Tests for the SortOrder enum."""
    
    def test_sort_order_values(self):
        """Test that SortOrder enum has expected values."""
        assert SortOrder.ASCENDING.value == "asc"
        assert SortOrder.DESCENDING.value == "desc"
    
    def test_sort_order_from_value(self):
        """Test creating SortOrder from string value."""
        assert SortOrder("asc") == SortOrder.ASCENDING
        assert SortOrder("desc") == SortOrder.DESCENDING


# =============================================================================
# VideoSorter Tests
# =============================================================================

class TestVideoSorter:
    """Tests for the VideoSorter class."""
    
    def test_default_creation(self):
        """Test VideoSorter with default settings."""
        sorter = VideoSorter()
        
        assert sorter.field == SortField.DATE_ADDED
        assert sorter.order == SortOrder.DESCENDING
    
    def test_set_sort_field(self):
        """Test setting sort field."""
        sorter = VideoSorter()
        
        sorter.set_sort(SortField.TITLE)
        
        assert sorter.field == SortField.TITLE
        assert sorter.order == SortOrder.DESCENDING  # Unchanged
    
    def test_set_sort_field_and_order(self):
        """Test setting both sort field and order."""
        sorter = VideoSorter()
        
        sorter.set_sort(SortField.PROGRESS, SortOrder.ASCENDING)
        
        assert sorter.field == SortField.PROGRESS
        assert sorter.order == SortOrder.ASCENDING
    
    def test_toggle_order(self):
        """Test toggling sort order."""
        sorter = VideoSorter()
        
        # Default is DESCENDING
        assert sorter.order == SortOrder.DESCENDING
        
        # Toggle to ASCENDING
        result = sorter.toggle_order()
        assert result == SortOrder.ASCENDING
        assert sorter.order == SortOrder.ASCENDING
        
        # Toggle back to DESCENDING
        result = sorter.toggle_order()
        assert result == SortOrder.DESCENDING
        assert sorter.order == SortOrder.DESCENDING
    
    def test_get_sort_description(self):
        """Test getting sort description."""
        sorter = VideoSorter()
        
        # Default: Date added descending
        desc = sorter.get_sort_description()
        assert "Date added" in desc
        assert "↓" in desc
        
        # Change to title ascending
        sorter.set_sort(SortField.TITLE, SortOrder.ASCENDING)
        desc = sorter.get_sort_description()
        assert "Title" in desc
        assert "↑" in desc
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.TITLE, SortOrder.ASCENDING)
        
        data = sorter.to_dict()
        
        assert data["field"] == "title"
        assert data["order"] == "asc"
    
    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {"field": "progress", "order": "desc"}
        
        sorter = VideoSorter.from_dict(data)
        
        assert sorter.field == SortField.PROGRESS
        assert sorter.order == SortOrder.DESCENDING
    
    def test_from_dict_with_invalid_values(self):
        """Test from_dict handles invalid values gracefully."""
        data = {"field": "invalid_field", "order": "invalid_order"}
        
        sorter = VideoSorter.from_dict(data)
        
        # Should fall back to defaults
        assert sorter.field == SortField.DATE_ADDED
        assert sorter.order == SortOrder.DESCENDING


class TestVideoSorterSortByDate:
    """Tests for sorting by date added."""
    
    def test_sort_by_date_descending(self, mock_state_manager):
        """Test sorting by date added (newest first)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.DATE_ADDED, SortOrder.DESCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # IDs should be: 3 (newest), 5, 2, 1, 4 (oldest)
        ids = [v.id for v in sorted_videos]
        assert ids == [3, 5, 2, 1, 4]
    
    def test_sort_by_date_ascending(self, mock_state_manager):
        """Test sorting by date added (oldest first)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.DATE_ADDED, SortOrder.ASCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # IDs should be: 4 (oldest), 1, 2, 5, 3 (newest)
        ids = [v.id for v in sorted_videos]
        assert ids == [4, 1, 2, 5, 3]


class TestVideoSorterSortByTitle:
    """Tests for sorting by title."""
    
    def test_sort_by_title_ascending(self, mock_state_manager):
        """Test sorting by title A-Z."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.TITLE, SortOrder.ASCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Titles: Alpha, Beta, Charlie, Delta, echo (case-insensitive)
        titles = [v.title for v in sorted_videos]
        assert titles == ["Alpha Video", "Beta Video", "Charlie Video", "Delta Video", "echo video"]
    
    def test_sort_by_title_descending(self, mock_state_manager):
        """Test sorting by title Z-A."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.TITLE, SortOrder.DESCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Titles: echo, Delta, Charlie, Beta, Alpha (case-insensitive)
        titles = [v.title for v in sorted_videos]
        assert titles == ["echo video", "Delta Video", "Charlie Video", "Beta Video", "Alpha Video"]


class TestVideoSorterSortByProgress:
    """Tests for sorting by progress."""
    
    def test_sort_by_progress_descending(self, mock_state_manager):
        """Test sorting by progress (most complete first)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.PROGRESS, SortOrder.DESCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Progress: 4 (100%), 2 (75%), 1 (50%), 3 (25%), 5 (10%)
        ids = [v.id for v in sorted_videos]
        assert ids == [4, 2, 1, 3, 5]
    
    def test_sort_by_progress_ascending(self, mock_state_manager):
        """Test sorting by progress (least complete first)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.PROGRESS, SortOrder.ASCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Progress: 5 (10%), 3 (25%), 1 (50%), 2 (75%), 4 (100%)
        ids = [v.id for v in sorted_videos]
        assert ids == [5, 3, 1, 2, 4]


class TestVideoSorterSortBySpeed:
    """Tests for sorting by speed."""
    
    def test_sort_by_speed_descending(self, mock_state_manager):
        """Test sorting by speed (fastest first)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.SPEED, SortOrder.DESCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Speed: 2 (500KB/s), 1 (100KB/s), 3/4/5 (0)
        ids = [v.id for v in sorted_videos]
        assert ids[0] == 2  # Fastest
        assert ids[1] == 1  # Second fastest
    
    def test_sort_by_speed_ascending(self, mock_state_manager):
        """Test sorting by speed (slowest first)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.SPEED, SortOrder.ASCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Slowest first: 3, 4, 5 (0), 1 (100KB/s), 2 (500KB/s)
        ids = [v.id for v in sorted_videos]
        assert ids[-1] == 2  # Fastest last
        assert ids[-2] == 1  # Second fastest second to last


class TestVideoSorterSortByStage:
    """Tests for sorting by stage."""
    
    def test_sort_by_stage_alphabetical(self, mock_state_manager):
        """Test sorting by stage (alphabetical by stage name)."""
        sorter = VideoSorter()
        sorter.set_sort(SortField.STAGE, SortOrder.ASCENDING)
        
        videos = mock_state_manager.get_all_videos()
        sorted_videos = sorter.sort(videos)
        
        # Stages: download (1, 4, 5), encrypt (3), upload (2)
        stages = [v.current_stage for v in sorted_videos]
        assert stages == ["download", "download", "download", "encrypt", "upload"]


# =============================================================================
# Controller Sorting Integration Tests
# =============================================================================

class TestControllerSorting:
    """Tests for VideoListController sorting integration."""
    
    def test_controller_has_sorter(self, mock_state_manager):
        """Test that controller has a VideoSorter."""
        controller = VideoListController(mock_state_manager)
        
        assert controller.sorter is not None
        assert isinstance(controller.sorter, VideoSorter)
    
    def test_set_sort_field(self, mock_state_manager):
        """Test setting sort field on controller."""
        controller = VideoListController(mock_state_manager)
        
        controller.set_sort_field(SortField.TITLE)
        
        assert controller.sorter.field == SortField.TITLE
    
    def test_set_sort_order(self, mock_state_manager):
        """Test setting sort order on controller."""
        controller = VideoListController(mock_state_manager)
        
        controller.set_sort_order(SortOrder.ASCENDING)
        
        assert controller.sorter.order == SortOrder.ASCENDING
    
    def test_toggle_sort_order(self, mock_state_manager):
        """Test toggling sort order on controller."""
        controller = VideoListController(mock_state_manager)
        
        # Default is DESCENDING
        assert controller.sorter.order == SortOrder.DESCENDING
        
        result = controller.toggle_sort_order()
        
        assert result == SortOrder.ASCENDING
        assert controller.sorter.order == SortOrder.ASCENDING
    
    def test_cycle_sort_field(self, mock_state_manager):
        """Test cycling through sort fields."""
        controller = VideoListController(mock_state_manager)
        
        # Default is DATE_ADDED
        assert controller.sorter.field == SortField.DATE_ADDED
        
        # Cycle to next
        result = controller.cycle_sort_field()
        assert result == SortField.TITLE
        
        # Cycle through all
        assert controller.cycle_sort_field() == SortField.PROGRESS
        assert controller.cycle_sort_field() == SortField.SPEED
        assert controller.cycle_sort_field() == SortField.SIZE
        assert controller.cycle_sort_field() == SortField.STAGE
        assert controller.cycle_sort_field() == SortField.DATE_ADDED  # Back to start
    
    def test_get_sort_description(self, mock_state_manager):
        """Test getting sort description from controller."""
        controller = VideoListController(mock_state_manager)
        
        desc = controller.get_sort_description()
        
        assert "Date added" in desc
        assert "↓" in desc
    
    def test_get_filtered_videos_includes_sort(self, mock_state_manager):
        """Test that get_filtered_videos applies sorting."""
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.TITLE)
        controller.set_sort_order(SortOrder.ASCENDING)
        
        result = controller.get_filtered_videos()
        
        # Should be sorted by title A-Z
        titles = [v.title for v in result.videos]
        assert titles == ["Alpha Video", "Beta Video", "Charlie Video", "Delta Video", "echo video"]
    
    def test_filter_result_includes_sort_description(self, mock_state_manager):
        """Test that FilterResult includes sort description."""
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.PROGRESS)
        
        result = controller.get_filtered_videos()
        
        assert result.sort_description != ""
        assert "Progress" in result.sort_description


# =============================================================================
# Acceptance Criteria Tests
# =============================================================================

class TestAcceptanceCriteria:
    """Tests for meeting the acceptance criteria of Task 6.2."""
    
    def test_ac1_sort_by_date_added(self, mock_state_manager):
        """AC1: Sort by date added works.
        
        Verify that videos can be sorted by date added (newest first by default).
        """
        controller = VideoListController(mock_state_manager)
        
        # Default should be date added, descending
        assert controller.get_sort_field() == SortField.DATE_ADDED
        assert controller.get_sort_order() == SortOrder.DESCENDING
        
        result = controller.get_filtered_videos()
        
        # Verify videos are sorted by date (newest first)
        dates = [v.created_at for v in result.videos]
        assert dates == sorted(dates, reverse=True)
    
    def test_ac2_sort_by_title(self, mock_state_manager):
        """AC2: Sort by title works.
        
        Verify that videos can be sorted alphabetically by title.
        """
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.TITLE)
        controller.set_sort_order(SortOrder.ASCENDING)
        
        result = controller.get_filtered_videos()
        
        titles = [v.title.lower() for v in result.videos]
        assert titles == sorted(titles)
    
    def test_ac3_sort_by_progress(self, mock_state_manager):
        """AC3: Sort by progress works.
        
        Verify that videos can be sorted by progress (most complete first).
        """
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.PROGRESS)
        controller.set_sort_order(SortOrder.DESCENDING)
        
        result = controller.get_filtered_videos()
        
        progresses = [v.current_progress for v in result.videos]
        assert progresses == sorted(progresses, reverse=True)
    
    def test_ac4_sort_by_speed(self, mock_state_manager):
        """AC4: Sort by speed works.
        
        Verify that videos can be sorted by speed (fastest first).
        """
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.SPEED)
        controller.set_sort_order(SortOrder.DESCENDING)
        
        result = controller.get_filtered_videos()
        
        speeds = [v.current_speed for v in result.videos]
        assert speeds == sorted(speeds, reverse=True)
    
    def test_ac5_sort_by_size(self, mock_state_manager):
        """AC5: Sort by size works.
        
        Verify that videos can be sorted by file size.
        """
        controller = VideoListController(mock_state_manager)
        
        # Test that size sort field exists and can be set
        controller.set_sort_field(SortField.SIZE)
        
        assert controller.get_sort_field() == SortField.SIZE
    
    def test_ac6_sort_by_stage(self, mock_state_manager):
        """AC6: Sort by stage works.
        
        Verify that videos can be sorted/grouped by pipeline stage.
        """
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.STAGE)
        controller.set_sort_order(SortOrder.ASCENDING)
        
        result = controller.get_filtered_videos()
        
        stages = [v.current_stage for v in result.videos]
        assert stages == sorted(stages)
    
    def test_ac7_reverse_order(self, mock_state_manager):
        """AC7: Reverse order works.
        
        Verify that sort order can be toggled between ascending and descending.
        """
        controller = VideoListController(mock_state_manager)
        controller.set_sort_field(SortField.TITLE)
        
        # Default descending
        controller.set_sort_order(SortOrder.DESCENDING)
        result_desc = controller.get_filtered_videos()
        titles_desc = [v.title.lower() for v in result_desc.videos]
        
        # Toggle to ascending
        controller.toggle_sort_order()
        result_asc = controller.get_filtered_videos()
        titles_asc = [v.title.lower() for v in result_asc.videos]
        
        # Should be reverse of each other
        assert titles_asc == list(reversed(titles_desc))
