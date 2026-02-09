"""Tests for Batch Operations functionality.

This module tests the BatchOperations class and its integration
with the video list view.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import MagicMock, Mock, AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_cli.database.models import (
    Base,
    Video,
    Download,
    PipelineSnapshot,
)
from haven_cli.pipeline.events import (
    Event,
    EventType,
    EventBus,
    get_event_bus,
    reset_event_bus,
)

from haven_tui.core.state_manager import StateManager, VideoState
from haven_tui.core.pipeline_interface import (
    PipelineInterface,
    BatchOperations,
    BatchResult,
)
from haven_tui.config import HavenTUIConfig, FiltersConfig, DisplayConfig


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def database_engine(temp_db_path):
    """Create a database engine with all tables."""
    engine = create_engine(f"sqlite:///{temp_db_path}")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(database_engine) -> Session:
    """Create a fresh database session for each test."""
    SessionLocal = sessionmaker(bind=database_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def event_bus():
    """Get a fresh event bus for testing."""
    reset_event_bus()
    bus = get_event_bus()
    yield bus
    reset_event_bus()


@pytest.fixture
def config():
    """Create a test configuration."""
    return HavenTUIConfig(
        filters=FiltersConfig(
            show_completed=True,
            show_failed=True,
        ),
        display=DisplayConfig(
            refresh_rate=1.0,
        ),
    )


@pytest.fixture
async def pipeline_interface(database_engine, temp_db_path, event_bus):
    """Create a PipelineInterface with test database."""
    interface = PipelineInterface(
        database_path=temp_db_path,
        event_bus=event_bus,
    )
    
    SessionLocal = sessionmaker(bind=database_engine)
    session = SessionLocal()
    interface._db_session = session
    interface._plugin_manager = None
    
    yield interface
    
    session.close()
    reset_event_bus()


@pytest.fixture
async def state_manager(pipeline_interface):
    """Create an initialized StateManager."""
    manager = StateManager(pipeline_interface)
    await manager.initialize()
    yield manager
    await manager.shutdown()


@pytest.fixture
def batch_operations(state_manager, pipeline_interface):
    """Create a BatchOperations instance."""
    return BatchOperations(state_manager, pipeline_interface)


# =============================================================================
# Test Data Helpers
# =============================================================================

def create_mock_video_state(
    video_id: int,
    title: str,
    stage: str = "download",
    progress: float = 0.0,
    status: str = "pending",
    has_failed: bool = False,
) -> VideoState:
    """Helper to create a mock VideoState."""
    state = VideoState(
        id=video_id,
        title=title,
        current_stage=stage,
        overall_status=status,
    )
    
    if stage == "download":
        state.download_status = "failed" if has_failed else status
        state.download_progress = progress
    elif stage == "upload":
        state.upload_status = "failed" if has_failed else status
        state.upload_progress = progress
    
    return state


# =============================================================================
# Unit Tests for BatchResult
# =============================================================================

class TestBatchResult:
    """Tests for the BatchResult dataclass."""
    
    def test_batch_result_creation(self):
        """Test creating a BatchResult."""
        result = BatchResult()
        
        assert result.success == []
        assert result.failed == []
        assert result.all_succeeded is True
        assert result.total_count == 0
    
    def test_batch_result_with_data(self):
        """Test BatchResult with success and failures."""
        result = BatchResult(
            success=[1, 2, 3],
            failed=[(4, "Error message"), (5, "Another error")]
        )
        
        assert result.success_count == 3
        assert result.failed_count == 2
        assert result.total_count == 5
        assert result.all_succeeded is False
    
    def test_batch_result_to_dict(self):
        """Test converting BatchResult to dictionary."""
        result = BatchResult(
            success=[1, 2],
            failed=[(3, "Error")]
        )
        
        data = result.to_dict()
        
        assert data["success"] == [1, 2]
        assert data["success_count"] == 2
        assert data["failed_count"] == 1
        assert data["all_succeeded"] is False
        assert len(data["failed"]) == 1


# =============================================================================
# Unit Tests for BatchOperations
# =============================================================================

class TestBatchOperationsSelection:
    """Tests for BatchOperations selection functionality."""
    
    def test_toggle_selection_adds_video(self, batch_operations):
        """Test toggle_selection adds video to selection."""
        result = batch_operations.toggle_selection(1)
        
        assert result is True
        assert batch_operations.is_selected(1)
        assert batch_operations.get_selected() == [1]
    
    def test_toggle_selection_removes_video(self, batch_operations):
        """Test toggle_selection removes video when already selected."""
        batch_operations.toggle_selection(1)
        result = batch_operations.toggle_selection(1)
        
        assert result is False
        assert not batch_operations.is_selected(1)
        assert batch_operations.get_selected() == []
    
    def test_select_all(self, batch_operations):
        """Test select_all selects all provided videos."""
        videos = [
            VideoState(id=1, title="Video 1"),
            VideoState(id=2, title="Video 2"),
            VideoState(id=3, title="Video 3"),
        ]
        
        count = batch_operations.select_all(videos)
        
        assert count == 3
        assert batch_operations.get_selected_count() == 3
        assert batch_operations.has_selection() is True
        assert set(batch_operations.get_selected()) == {1, 2, 3}
    
    def test_clear_selection(self, batch_operations):
        """Test clear_selection removes all selections."""
        batch_operations.toggle_selection(1)
        batch_operations.toggle_selection(2)
        
        batch_operations.clear_selection()
        
        assert batch_operations.get_selected() == []
        assert batch_operations.has_selection() is False
    
    def test_get_selected_videos_info(self, batch_operations):
        """Test getting info about selected videos."""
        # Add mock videos to state manager
        batch_operations.state_manager._state[1] = VideoState(
            id=1,
            title="Test Video 1",
            current_stage="download",
            overall_status="active",
        )
        batch_operations.state_manager._state[2] = VideoState(
            id=2,
            title="Test Video 2",
            current_stage="upload",
            overall_status="completed",
        )
        
        batch_operations.toggle_selection(1)
        batch_operations.toggle_selection(2)
        
        info = batch_operations.get_selected_videos_info()
        
        assert len(info) == 2
        assert info[0]["id"] == 1
        assert info[0]["title"] == "Test Video 1"
        assert info[1]["id"] == 2
        assert info[1]["stage"] == "upload"


class TestBatchOperationsExport:
    """Tests for BatchOperations export functionality."""
    
    def test_export_list(self, batch_operations, tmp_path):
        """Test exporting selected videos to JSON."""
        # Add mock videos to state manager
        batch_operations.state_manager._state[1] = VideoState(
            id=1,
            title="Test Video 1",
            current_stage="download",
            overall_status="active",
        )
        batch_operations.state_manager._state[2] = VideoState(
            id=2,
            title="Test Video 2",
            current_stage="upload",
            overall_status="completed",
        )
        
        batch_operations.toggle_selection(1)
        batch_operations.toggle_selection(2)
        
        filepath = str(tmp_path / "export.json")
        result = batch_operations.export_list(filepath)
        
        assert result["success"] is True
        assert result["exported_count"] == 2
        assert result["filepath"] == filepath
        assert os.path.exists(filepath)
        
        # Verify file contents
        with open(filepath, 'r') as f:
            data = json.load(f)
            assert data["exported_count"] == 2
            assert len(data["videos"]) == 2
    
    def test_export_list_no_selection(self, batch_operations, tmp_path):
        """Test exporting with no selection."""
        filepath = str(tmp_path / "export.json")
        result = batch_operations.export_list(filepath)
        
        assert result["success"] is True
        assert result["exported_count"] == 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestBatchOperationsIntegration:
    """Integration tests for BatchOperations."""
    
    @pytest.mark.asyncio
    async def test_batch_operations_initialization(self, state_manager, pipeline_interface):
        """Test BatchOperations can be initialized."""
        batch_ops = BatchOperations(state_manager, pipeline_interface)
        
        assert batch_ops.state_manager == state_manager
        assert batch_ops.pipeline == pipeline_interface
        assert batch_ops.get_selected() == []
    
    @pytest.mark.asyncio
    async def test_batch_operations_with_state_manager(self, state_manager, pipeline_interface):
        """Test BatchOperations integration with StateManager."""
        # Add videos to state manager
        state_manager._state[1] = create_mock_video_state(
            1, "Video 1", "download", 50.0, "active"
        )
        state_manager._state[2] = create_mock_video_state(
            2, "Video 2", "upload", 75.0, "failed", has_failed=True
        )
        
        batch_ops = BatchOperations(state_manager, pipeline_interface)
        
        # Select all from state manager
        all_videos = state_manager.get_all_videos()
        count = batch_ops.select_all(all_videos)
        
        assert count == 2
        assert batch_ops.has_selection() is True


# =============================================================================
# Acceptance Criteria Tests
# =============================================================================

class TestAcceptanceCriteria:
    """Tests for meeting the acceptance criteria."""
    
    def test_multi_select_with_space(self, batch_operations):
        """AC1: Multi-select works with space key.
        
        The space key toggles selection of the current video.
        """
        # Toggle selection (simulating space key)
        batch_operations.toggle_selection(1)
        assert batch_operations.is_selected(1) is True
        
        # Toggle again
        batch_operations.toggle_selection(1)
        assert batch_operations.is_selected(1) is False
    
    def test_select_all(self, batch_operations):
        """AC2: Select all works.
        
        Can select all visible videos at once.
        """
        videos = [
            VideoState(id=1, title="Video 1"),
            VideoState(id=2, title="Video 2"),
            VideoState(id=3, title="Video 3"),
        ]
        
        count = batch_operations.select_all(videos)
        
        assert count == 3
        assert set(batch_operations.get_selected()) == {1, 2, 3}
    
    def test_clear_selection(self, batch_operations):
        """AC3: Clear selection works.
        
        Can clear all selections at once.
        """
        batch_operations.toggle_selection(1)
        batch_operations.toggle_selection(2)
        batch_operations.toggle_selection(3)
        
        assert batch_operations.get_selected_count() == 3
        
        batch_operations.clear_selection()
        
        assert batch_operations.get_selected_count() == 0
        assert batch_operations.has_selection() is False
    
    def test_retry_failed_interface(self, batch_operations):
        """AC4: Retry failed interface exists.
        
        The BatchOperations class has a retry_failed method.
        """
        assert hasattr(batch_operations, 'retry_failed')
        assert asyncio.iscoroutinefunction(batch_operations.retry_failed)
    
    def test_remove_from_queue_interface(self, batch_operations):
        """AC5: Remove from queue interface exists.
        
        The BatchOperations class has a remove_from_queue method.
        """
        assert hasattr(batch_operations, 'remove_from_queue')
        assert asyncio.iscoroutinefunction(batch_operations.remove_from_queue)
    
    def test_force_reprocess_interface(self, batch_operations):
        """AC6: Force re-process interface exists.
        
        The BatchOperations class has a force_reprocess method.
        """
        assert hasattr(batch_operations, 'force_reprocess')
        assert asyncio.iscoroutinefunction(batch_operations.force_reprocess)
    
    def test_export_list_to_json(self, batch_operations, tmp_path):
        """AC7: Export list to JSON works.
        
        Can export selected videos to a JSON file.
        """
        # Add video to state manager
        batch_operations.state_manager._state[1] = VideoState(
            id=1,
            title="Test Video",
            current_stage="download",
            overall_status="active",
        )
        
        batch_operations.toggle_selection(1)
        
        filepath = str(tmp_path / "export.json")
        result = batch_operations.export_list(filepath)
        
        assert result["success"] is True
        assert os.path.exists(filepath)
        
        # Verify JSON content
        with open(filepath, 'r') as f:
            data = json.load(f)
            assert "videos" in data
            assert data["exported_count"] == 1
            assert data["videos"][0]["id"] == 1
            assert data["videos"][0]["title"] == "Test Video"


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in batch operations."""
    
    def test_export_list_invalid_path(self, batch_operations):
        """Test export handles invalid file path."""
        batch_operations.state_manager._state[1] = VideoState(
            id=1,
            title="Test Video",
            current_stage="download",
            overall_status="active",
        )
        batch_operations.toggle_selection(1)
        
        # Try to export to invalid path
        result = batch_operations.export_list("/nonexistent/path/export.json")
        
        assert result["success"] is False
        assert "error" in result
    
    def test_batch_result_with_mixed_results(self):
        """Test BatchResult handles mixed success/failure."""
        result = BatchResult(
            success=[1, 2],
            failed=[(3, "Error 1"), (4, "Error 2")]
        )
        
        assert result.success_count == 2
        assert result.failed_count == 2
        assert result.all_succeeded is False
        assert result.total_count == 4


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Performance tests for batch operations."""
    
    def test_toggle_selection_performance(self, batch_operations):
        """Test toggle selection performance with many videos."""
        import time
        
        start = time.time()
        for i in range(1000):
            batch_operations.toggle_selection(i)
        elapsed = time.time() - start
        
        # Should handle 1000 selections in less than 1 second
        assert elapsed < 1.0
        assert batch_operations.get_selected_count() == 1000
    
    def test_select_all_performance(self, batch_operations):
        """Test select all performance with many videos."""
        import time
        
        # Create many videos
        videos = [VideoState(id=i, title=f"Video {i}") for i in range(1000)]
        
        start = time.time()
        count = batch_operations.select_all(videos)
        elapsed = time.time() - start
        
        # Should handle 1000 videos in less than 1 second
        assert elapsed < 1.0
        assert count == 1000
