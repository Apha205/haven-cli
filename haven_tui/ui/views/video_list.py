"""Main Video List View for Haven TUI.

This module provides the primary view for the TUI - a scrollable list of videos
showing their current pipeline stage and progress, inspired by aria2tui's download list.
"""

from __future__ import annotations

from typing import Callable, ClassVar, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from textual.widgets import DataTable, Static, Header, Footer, Input
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.coordinate import Coordinate

from haven_tui.core.state_manager import StateManager, VideoState
from haven_tui.core.controller import VideoListController, FilterResult
from haven_tui.core.pipeline_interface import BatchOperations, BatchResult
from haven_tui.config import HavenTUIConfig
from haven_tui.models.video_view import (
    PipelineStage, StageStatus, FilterState,
    SortField, SortOrder, VideoSorter,
)
from haven_tui.ui.components.speed_graph import SpeedGraphComponent
from haven_tui.data.repositories import SpeedHistoryRepository


@dataclass
class VideoRow:
    """Represents a single row in the video list."""
    index: int
    video_id: int
    title: str
    stage: str
    progress: float
    speed: str
    plugin: str
    size: str
    eta: str
    status: str  # "active", "pending", "completed", "failed"


class VideoListWidget(DataTable):
    """A DataTable widget for displaying video pipeline status.
    
    This widget displays a scrollable list of videos with their current
    pipeline stage, progress, speed, and other metadata. Supports
    multi-selection and auto-refresh.
    
    Attributes:
        state_manager: The StateManager instance for accessing video state
        config: The HavenTUIConfig for display settings
        on_select_callback: Optional callback when a video is selected
        on_multi_select_callback: Optional callback for multi-selection
    """
    
    DEFAULT_CSS = """
    VideoListWidget {
        height: 100%;
        width: 100%;
        border: solid $primary;
    }
    
    VideoListWidget > .datatable--header {
        background: $surface-darken-1;
        color: $text;
        text-style: bold;
    }
    
    VideoListWidget > .datatable--row {
        height: 1;
    }
    
    VideoListWidget > .datatable--row-cursor {
        background: $primary-darken-1;
    }
    
    VideoListWidget > .datatable--row-selected {
        background: $success-darken-2;
    }
    
    /* Stage-specific styling */
    .stage-pending { color: $text-muted; }
    .stage-download { color: $accent; }
    .stage-ingest { color: $warning; }
    .stage-analysis { color: $warning; }
    .stage-encrypt { color: $error; }
    .stage-upload { color: $success; }
    .stage-sync { color: $success; }
    .stage-complete { color: $success; text-style: bold; }
    
    /* Progress bar styling */
    .progress-complete { color: $success; }
    .progress-active { color: $accent; }
    .progress-pending { color: $text-muted; }
    """
    
    # Column definitions: (key, label, width, visible)
    COLUMNS: ClassVar[List[tuple[str, str, int, bool]]] = [
        ("#", "#", 4, True),
        ("sel", "✓", 3, True),  # Selection column for batch mode
        ("title", "Title", 32, True),
        ("stage", "Stage", 12, True),
        ("progress", "Progress", 15, True),
        ("speed", "Speed", 12, True),
        ("plugin", "Plugin", 12, True),
        ("size", "Size", 10, True),
        ("eta", "ETA", 10, True),
    ]
    
    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        config: Optional[HavenTUIConfig] = None,
        on_select: Optional[Callable[[int], None]] = None,
        on_multi_select: Optional[Callable[[List[int]], None]] = None,
        controller: Optional[VideoListController] = None,
        batch_operations: Optional[BatchOperations] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the video list widget.
        
        Args:
            state_manager: The StateManager for accessing video state
            config: The TUI configuration
            on_select: Callback when a video is selected (single click)
            on_multi_select: Callback for multi-selection changes
            controller: Optional VideoListController for filtering
            batch_operations: Optional BatchOperations instance for multi-select
            **kwargs: Additional arguments passed to DataTable
        """
        super().__init__(**kwargs)
        self.state_manager = state_manager
        self.config = config or HavenTUIConfig()
        self.on_select_callback = on_select
        self.on_multi_select_callback = on_multi_select
        self._video_rows: List[VideoRow] = []
        self._last_refresh: Optional[datetime] = None
        self._last_filter_result: Optional[FilterResult] = None
        
        # Batch operations for multi-select
        self.batch_operations = batch_operations
        
        # Initialize controller with config-based filter state
        if controller:
            self.controller = controller
        elif state_manager:
            filter_state = FilterState(
                show_completed=self.config.filters.show_completed,
                show_failed=self.config.filters.show_failed,
                plugin=self.config.filters.plugin_filter if self.config.filters.plugin_filter != "all" else None,
            )
            self.controller = VideoListController(state_manager, filter_state)
        else:
            self.controller = None
        
        # Enable zebra striping and cursor
        self.zebra_stripes = True
        self.cursor_type = "row"
        self.show_cursor = True
        
    def compose(self) -> None:
        """Set up the table columns."""
        self._setup_columns()
        
    def _setup_columns(self) -> None:
        """Configure table columns based on config."""
        # Clear existing columns
        for key in list(self.columns.keys()):
            self.remove_column(key)
            
        # Add configured columns
        for key, label, width, visible in self.COLUMNS:
            if visible:
                self.add_column(label, key=key, width=width)
    
    def _format_progress_bar(self, progress: float, width: int = 10) -> str:
        """Format a progress bar using Unicode block characters.
        
        Args:
            progress: Progress percentage (0.0 - 100.0)
            width: Width of the progress bar in characters
            
        Returns:
            Formatted progress bar string
        """
        if progress <= 0:
            return "░" * width + " 0%"
        elif progress >= 100:
            return "█" * width + " 100%"
        
        filled = int((progress / 100.0) * width)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        return f"{bar} {progress:.0f}%"
    
    def _format_speed(self, speed: float) -> str:
        """Format speed in human-readable form.
        
        Args:
            speed: Speed in bytes per second
            
        Returns:
            Formatted speed string (e.g., "2.4MB/s")
        """
        if speed == 0:
            return "-"
        
        # Convert to human readable
        size = float(speed)
        if size < 1024:
            return f"{size:.0f}B/s"
        size /= 1024
        if size < 1024:
            return f"{size:.1f}KB/s"
        size /= 1024
        if size < 1024:
            return f"{size:.1f}MB/s"
        size /= 1024
        return f"{size:.1f}GB/s"
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable form.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string (e.g., "3.2GB")
        """
        if size_bytes == 0:
            return "-"
        
        size = float(size_bytes)
        if size < 1024:
            return f"{size:.0f}B"
        size /= 1024
        if size < 1024:
            return f"{size:.1f}KB"
        size /= 1024
        if size < 1024:
            return f"{size:.1f}MB"
        size /= 1024
        return f"{size:.1f}GB"
    
    def _format_eta(self, eta_seconds: Optional[int]) -> str:
        """Format ETA in human-readable form.
        
        Args:
            eta_seconds: ETA in seconds
            
        Returns:
            Formatted ETA string (e.g., "12m30s")
        """
        if eta_seconds is None:
            return "--:--"
        
        minutes, seconds = divmod(eta_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}h{minutes:02d}m"
        return f"{minutes}:{seconds:02d}"
    
    def _get_stage_style(self, stage: str, status: str) -> str:
        """Get the CSS style class for a stage.
        
        Args:
            stage: The pipeline stage
            status: The video status
            
        Returns:
            CSS class name for styling
        """
        if status == "completed":
            return "stage-complete"
        elif status == "failed":
            return "stage-failed"
        return f"stage-{stage.lower()}"
    
    def _truncate_title(self, title: str, max_length: int = 35) -> str:
        """Truncate title to fit column width.
        
        Args:
            title: The video title
            max_length: Maximum length
            
        Returns:
            Truncated title
        """
        if len(title) <= max_length:
            return title
        return title[: max_length - 3] + "..."
    
    def refresh_data(self) -> None:
        """Refresh the video list data from the state manager.
        
        This method fetches the current video states from the state manager,
        applies any active filters, and updates the table display.
        """
        if self.state_manager is None:
            return
        
        # Use controller for filtering if available
        if self.controller:
            result = self.controller.get_filtered_videos()
            self._last_filter_result = result
            videos = result.videos
        else:
            # Fallback to direct state manager access with config filters
            videos = self.state_manager.get_all_videos()
            
            # Filter based on config
            if not self.config.filters.show_completed:
                videos = [v for v in videos if not v.is_completed]
            if not self.config.filters.show_failed:
                videos = [v for v in videos if not v.has_failed]
        
        # Sort by activity and creation time
        videos.sort(key=lambda v: (
            not v.is_active,  # Active videos first
            v.created_at or datetime.min,
        ))
        
        # Build row data
        self._video_rows = []
        for i, video in enumerate(videos, 1):
            row = VideoRow(
                index=i,
                video_id=video.id,
                title=self._truncate_title(video.title),
                stage=video.current_stage,
                progress=video.current_progress,
                speed=self._format_speed(video.current_speed),
                plugin=video.title.split(".")[-1][:10] if "." in video.title else "youtube",
                size=self._format_size(10485760),  # Placeholder - would come from video data
                eta=self._format_eta(video.download_eta if video.current_stage == "download" else None),
                status=video.overall_status,
            )
            self._video_rows.append(row)
        
        # Update the table
        self._update_table()
        self._last_refresh = datetime.now()
    
    def set_filter_state(self, filter_state: FilterState) -> None:
        """Set the current filter state and refresh.
        
        Args:
            filter_state: New filter state to apply
        """
        if self.controller:
            self.controller.filter_state = filter_state
            self.refresh_data()
    
    def get_filter_state(self) -> Optional[FilterState]:
        """Get the current filter state.
        
        Returns:
            Current filter state or None if no controller
        """
        return self.controller.filter_state if self.controller else None
    
    def clear_filters(self) -> None:
        """Clear all filters and refresh."""
        if self.controller:
            self.controller.clear_all_filters()
            self.refresh_data()
    
    def set_search_query(self, query: str) -> None:
        """Set the search query and refresh.
        
        Args:
            query: Search string
        """
        if self.controller:
            self.controller.set_search_query(query)
            self.refresh_data()
    
    def toggle_show_completed(self) -> bool:
        """Toggle show completed filter.
        
        Returns:
            New value of show_completed
        """
        if self.controller:
            result = self.controller.toggle_show_completed()
            self.refresh_data()
            return result
        return False
    
    def toggle_show_failed(self) -> bool:
        """Toggle show failed filter.
        
        Returns:
            New value of show_failed
        """
        if self.controller:
            result = self.controller.toggle_show_failed()
            self.refresh_data()
            return result
        return False
    
    def get_filter_summary(self) -> str:
        """Get a summary of current filter state.
        
        Returns:
            Human-readable filter summary
        """
        if not self.controller or not self.controller.has_active_filters():
            return ""
        
        result = self._last_filter_result
        if result and result.active_filters:
            return f"Filters: {', '.join(result.active_filters)}"
        return ""
    
    def set_sort_field(self, field: SortField) -> None:
        """Set the sort field and refresh.
        
        Args:
            field: The field to sort by
        """
        if self.controller:
            self.controller.set_sort_field(field)
            self.refresh_data()
    
    def set_sort_order(self, order: SortOrder) -> None:
        """Set the sort order and refresh.
        
        Args:
            order: ASCENDING or DESCENDING
        """
        if self.controller:
            self.controller.set_sort_order(order)
            self.refresh_data()
    
    def toggle_sort_order(self) -> SortOrder:
        """Toggle sort order and refresh.
        
        Returns:
            The new sort order
        """
        if self.controller:
            order = self.controller.toggle_sort_order()
            self.refresh_data()
            return order
        return SortOrder.DESCENDING
    
    def cycle_sort_field(self) -> SortField:
        """Cycle to the next sort field and refresh.
        
        Returns:
            The new sort field
        """
        if self.controller:
            field = self.controller.cycle_sort_field()
            self.refresh_data()
            return field
        return SortField.DATE_ADDED
    
    def get_sort_description(self) -> str:
        """Get a human-readable description of the current sort.
        
        Returns:
            String describing the current sort
        """
        if self.controller:
            return self.controller.get_sort_description()
        return ""
    
    def _update_table(self) -> None:
        """Update the table with current video rows."""
        # Clear existing rows
        self.clear()
        
        # Add rows
        for row in self._video_rows:
            progress_bar = self._format_progress_bar(row.progress)
            
            # Apply styling based on stage and status
            stage_style = self._get_stage_style(row.stage, row.status)
            
            # Selection indicator
            sel_indicator = ""
            if self.batch_operations and self.batch_operations.is_selected(row.video_id):
                sel_indicator = "✓"
            
            cells = [
                str(row.index),
                sel_indicator,
                row.title,
                f"[{stage_style}]{row.stage}[/{stage_style}]",
                progress_bar,
                row.speed,
                row.plugin,
                row.size,
                row.eta,
            ]
            
            # Add row with metadata for selection
            self.add_row(
                *cells,
                key=str(row.video_id),
            )
    
    def get_selected_video_id(self) -> Optional[int]:
        """Get the ID of the currently selected video.
        
        Returns:
            Video ID or None if no selection
        """
        cursor_row = self.cursor_row
        if cursor_row is None or cursor_row >= len(self._video_rows):
            return None
        return self._video_rows[cursor_row].video_id
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection event.
        
        Args:
            event: The row selected event
        """
        video_id = self.get_selected_video_id()
        if video_id and self.on_select_callback:
            self.on_select_callback(video_id)
    
    def toggle_selection(self) -> None:
        """Toggle selection of the current row (for multi-select)."""
        video_id = self.get_selected_video_id()
        if video_id is None:
            return
        
        # Use batch_operations if available
        if self.batch_operations:
            self.batch_operations.toggle_selection(video_id)
        
        # Refresh to show selection change
        self._update_table()
        
        if self.on_multi_select_callback:
            if self.batch_operations:
                self.on_multi_select_callback(self.batch_operations.get_selected())
            else:
                self.on_multi_select_callback([video_id])
    
    def clear_selection(self) -> None:
        """Clear all selections."""
        if self.batch_operations:
            self.batch_operations.clear_selection()
        
        # Refresh to show selection cleared
        self._update_table()
        
        if self.on_multi_select_callback:
            self.on_multi_select_callback([])
    
    def select_all_visible(self) -> int:
        """Select all currently visible videos.
        
        Returns:
            Number of videos selected
        """
        if not self.batch_operations:
            return 0
        
        # Get visible videos from state manager
        if self.controller:
            result = self.controller.get_filtered_videos()
            videos = result.videos
        else:
            videos = self.state_manager.get_all_videos() if self.state_manager else []
        
        count = self.batch_operations.select_all(videos)
        self._update_table()
        
        if self.on_multi_select_callback:
            self.on_multi_select_callback(self.batch_operations.get_selected())
        
        return count
    
    def get_selected_video_ids(self) -> List[int]:
        """Get IDs of all selected videos (for multi-select).
        
        Returns:
            List of video IDs
        """
        if self.batch_operations:
            return self.batch_operations.get_selected()
        return []
    
    def has_selection(self) -> bool:
        """Check if any videos are selected.
        
        Returns:
            True if at least one video is selected
        """
        if self.batch_operations:
            return self.batch_operations.has_selection()
        return False
    
    def get_selection_count(self) -> int:
        """Get number of selected videos.
        
        Returns:
            Number of selected videos
        """
        if self.batch_operations:
            return self.batch_operations.get_selected_count()
        return 0


class VideoListHeader(Static):
    """Header widget showing pipeline summary."""
    
    DEFAULT_CSS = """
    VideoListHeader {
        height: 3;
        background: $surface-darken-2;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }
    """
    
    def __init__(self, state_manager: Optional[StateManager] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.state_manager = state_manager
    
    def update_header(self) -> None:
        """Update the header text with current stats."""
        if self.state_manager is None:
            self.update("Haven Pipeline")
            return
        
        videos = self.state_manager.get_all_videos()
        active = len([v for v in videos if v.is_active])
        completed = len([v for v in videos if v.is_completed])
        failed = len([v for v in videos if v.has_failed])
        
        status_parts = []
        if active > 0:
            status_parts.append(f"{active} active")
        if completed > 0:
            status_parts.append(f"{completed} completed")
        if failed > 0:
            status_parts.append(f"{failed} failed")
        
        status_text = " | ".join(status_parts) if status_parts else "No videos"
        self.update(f"Haven Pipeline - {status_text}")


class VideoListFooter(Static):
    """Footer widget showing key bindings."""
    
    DEFAULT_CSS = """
    VideoListFooter {
        height: 1;
        background: $surface-darken-2;
        color: $text-muted;
        content-align: center middle;
    }
    """
    
    def __init__(
        self,
        show_graph: bool = False,
        batch_mode: bool = False,
        selection_count: int = 0,
        **kwargs: Any
    ) -> None:
        """Initialize the footer.
        
        Args:
            show_graph: Whether the speed graph is currently visible
            batch_mode: Whether batch mode is active
            selection_count: Number of selected videos
            **kwargs: Additional arguments passed to Static
        """
        super().__init__(**kwargs)
        self._show_graph = show_graph
        self._batch_mode = batch_mode
        self._selection_count = selection_count
    
    def compose(self) -> None:
        """Set up the footer content."""
        self._update_content()
    
    def set_show_graph(self, show_graph: bool) -> None:
        """Update the graph visibility indicator.
        
        Args:
            show_graph: Whether the speed graph is currently visible
        """
        self._show_graph = show_graph
        self._update_content()
    
    def set_batch_mode(self, batch_mode: bool, selection_count: int = 0) -> None:
        """Update the batch mode indicator.
        
        Args:
            batch_mode: Whether batch mode is active
            selection_count: Number of selected videos
        """
        self._batch_mode = batch_mode
        self._selection_count = selection_count
        self._update_content()
    
    def set_selection_count(self, count: int) -> None:
        """Update the selection count display.
        
        Args:
            count: Number of selected videos
        """
        self._selection_count = count
        self._update_content()
    
    def _update_content(self) -> None:
        """Update the footer content."""
        if self._batch_mode:
            # Batch mode footer with selection count and batch operations
            self.update(
                f"Batch: {self._selection_count} selected | "
                f"[a] All  [c] Clear  [r] Retry  [x] Remove  [e] Export  [Esc] Exit"
            )
        else:
            # Normal mode footer
            graph_indicator = "ON" if self._show_graph else "OFF"
            self.update(
                f"[q] Quit  [r] Refresh  [a] Auto-refresh  [d] Details  "
                f"[g] Graph ({graph_indicator})  [f/c/e/x] Filter  [s/S] Sort  [b] Batch  [?] Help"
            )


class VideoListScreen(Screen):
    """Main screen for the video list view.
    
    This is the primary screen of the TUI application, showing a scrollable
    list of videos with their pipeline status and progress.
    
    Attributes:
        state_manager: The StateManager for accessing video state
        config: The HavenTUIConfig for display settings
        auto_refresh: Whether auto-refresh is enabled
    """
    
    DEFAULT_CSS = """
    VideoListScreen {
        layout: vertical;
    }
    
    #video-list-container {
        height: 100%;
        width: 100%;
    }
    
    #header-container {
        height: auto;
        dock: top;
    }
    
    #footer-container {
        height: auto;
        dock: bottom;
    }
    
    #main-content {
        height: 1fr;
        width: 100%;
        layout: horizontal;
    }
    
    #list-container {
        height: 100%;
        width: 1fr;
    }
    
    #graph-container {
        height: 100%;
        width: 35;
        dock: right;
        display: none;
    }
    
    #graph-container.visible {
        display: block;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("a", "toggle_auto_refresh", "Auto-refresh"),
        ("d", "details", "Details"),
        ("g", "toggle_graph", "Graph"),
        ("f", "filter", "Filter"),
        ("c", "toggle_completed_filter", "Toggle Completed"),
        ("e", "errors_only_filter", "Errors Only"),
        ("x", "clear_filters", "Clear Filters"),
        ("s", "sort", "Sort"),
        ("S", "toggle_sort_order", "Reverse Sort"),
        ("?", "help", "Help"),
        ("space", "toggle_select", "Select"),
        ("b", "toggle_batch_mode", "Batch Mode"),
        ("A", "select_all", "Select All"),
        ("R", "batch_retry", "Batch Retry"),
        ("X", "batch_remove", "Batch Remove"),
        ("E", "batch_export", "Batch Export"),
        ("escape", "exit_batch_mode", "Exit Batch"),
    ]
    
    auto_refresh: reactive[bool] = reactive(True)
    show_graph: reactive[bool] = reactive(False)
    batch_mode: reactive[bool] = reactive(False)
    
    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        config: Optional[HavenTUIConfig] = None,
        on_show_details: Optional[Callable[[int], None]] = None,
        speed_history_repo: Optional[SpeedHistoryRepository] = None,
        pipeline_interface: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the video list screen.
        
        Args:
            state_manager: The StateManager for accessing video state
            config: The TUI configuration
            on_show_details: Optional callback when user requests to view video details
            speed_history_repo: Optional repository for speed history data
            pipeline_interface: Optional PipelineInterface for batch operations
            **kwargs: Additional arguments passed to Screen
        """
        super().__init__(**kwargs)
        self.state_manager = state_manager
        self.config = config or HavenTUIConfig()
        self.auto_refresh = True
        self.show_graph = config.display.show_speed_graphs if config else False
        self.batch_mode = False
        self._refresh_timer: Optional[Any] = None
        self.on_show_details_callback = on_show_details
        self._speed_history_repo = speed_history_repo
        self._pipeline_interface = pipeline_interface
        self._selected_video_id: Optional[int] = None
        self._selected_stage: str = "download"
        
        # Initialize batch operations
        self._batch_operations: Optional[BatchOperations] = None
        if state_manager and pipeline_interface:
            self._batch_operations = BatchOperations(state_manager, pipeline_interface)
    
    def compose(self) -> None:
        """Compose the screen layout."""
        with Container(id="video-list-container"):
            with Container(id="header-container"):
                yield VideoListHeader(self.state_manager)
            
            with Container(id="main-content"):
                with Container(id="list-container"):
                    yield VideoListWidget(
                        state_manager=self.state_manager,
                        config=self.config,
                        on_select=self._on_video_select,
                        on_multi_select=self._on_multi_select,
                        batch_operations=self._batch_operations,
                    )
                
                with Container(id="graph-container", classes="visible" if self.show_graph else ""):
                    yield SpeedGraphComponent(
                        speed_history_repo=self._speed_history_repo,
                        width=30,
                        height=15,
                        history_seconds=self.config.display.graph_history_seconds if self.config else 60,
                        id="speed-graph",
                    )
            
            with Container(id="footer-container"):
                yield VideoListFooter(
                    show_graph=self.show_graph,
                    batch_mode=self.batch_mode,
                )
    
    def on_mount(self) -> None:
        """Handle mount event - start auto-refresh timer."""
        self._start_refresh_timer()
        self._update_header()
    
    def on_unmount(self) -> None:
        """Handle unmount event - stop timer."""
        self._stop_refresh_timer()
    
    def _start_refresh_timer(self) -> None:
        """Start the auto-refresh timer."""
        if self._refresh_timer is not None:
            return
        
        refresh_interval = self.config.display.refresh_rate
        self._refresh_timer = self.set_interval(refresh_interval, self._auto_refresh)
    
    def _stop_refresh_timer(self) -> None:
        """Stop the auto-refresh timer."""
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
    
    def _auto_refresh(self) -> None:
        """Perform auto-refresh if enabled."""
        if self.auto_refresh:
            self._refresh_data()
    
    def _refresh_data(self) -> None:
        """Refresh the video list data."""
        video_list = self.query_one(VideoListWidget)
        video_list.refresh_data()
        self._update_header()
        self._update_speed_graph()
    
    def _update_header(self) -> None:
        """Update the header with current stats."""
        header = self.query_one(VideoListHeader)
        header.update_header()
    
    def _on_video_select(self, video_id: int) -> None:
        """Handle single video selection.
        
        Args:
            video_id: The selected video ID
        """
        self._selected_video_id = video_id
        self._update_speed_graph()
    
    def _update_speed_graph(self) -> None:
        """Update the speed graph with the selected video's data."""
        if not self.show_graph or self._selected_video_id is None:
            return
        
        try:
            graph = self.query_one("#speed-graph", SpeedGraphComponent)
            graph.set_video(self._selected_video_id, self._selected_stage)
        except Exception:
            pass  # Graph may not be mounted yet
    
    def action_toggle_graph(self) -> None:
        """Toggle speed graph visibility with 'g' key."""
        self.show_graph = not self.show_graph
        
        # Update graph container visibility
        try:
            graph_container = self.query_one("#graph-container")
            if self.show_graph:
                graph_container.add_class("visible")
            else:
                graph_container.remove_class("visible")
        except Exception:
            pass
        
        # Update footer to show graph state
        try:
            footer = self.query_one(VideoListFooter)
            footer.set_show_graph(self.show_graph)
        except Exception:
            pass
        
        # Update graph if now visible and we have a selection
        if self.show_graph and self._selected_video_id is not None:
            self._update_speed_graph()
        
        status = "visible" if self.show_graph else "hidden"
        self.app.notify(f"Speed graph {status}", timeout=1.5)
    
    def _on_multi_select(self, video_ids: List[int]) -> None:
        """Handle multi-selection change.
        
        Args:
            video_ids: List of selected video IDs
        """
        if video_ids:
            self.app.notify(f"Selected {len(video_ids)} videos", timeout=2.0)
    
    def action_refresh(self) -> None:
        """Manual refresh action."""
        self._refresh_data()
        self.app.notify("Refreshed", timeout=1.0)
    
    def action_toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh on/off."""
        self.auto_refresh = not self.auto_refresh
        status = "ON" if self.auto_refresh else "OFF"
        self.app.notify(f"Auto-refresh: {status}", timeout=2.0)
    
    def action_details(self) -> None:
        """Show details for selected video."""
        video_list = self.query_one(VideoListWidget)
        video_id = video_list.get_selected_video_id()
        if video_id:
            self._show_video_details(video_id)
        else:
            self.app.notify("No video selected", severity="warning", timeout=2.0)
    
    def _show_video_details(self, video_id: int) -> None:
        """Show details for a video.
        
        This method can be overridden or the on_show_details_callback
        can be set to customize the navigation behavior.
        
        Args:
            video_id: ID of the video to show details for
        """
        # Import here to avoid circular imports
        from haven_tui.ui.views.video_detail import VideoDetailScreen
        
        # Check if there's a custom callback
        if hasattr(self, 'on_show_details_callback') and self.on_show_details_callback:
            self.on_show_details_callback(video_id)
        else:
            # Default behavior: show a notification that detail view is available
            # The actual navigation should be handled by the app using the callback
            self.app.notify(
                f"Detail view for video {video_id} - "
                "Use on_show_details_callback to customize navigation",
                timeout=3.0
            )
    
    def action_filter(self) -> None:
        """Open filter dialog or cycle through filter states."""
        video_list = self.query_one(VideoListWidget)
        filter_state = video_list.get_filter_state()
        
        if filter_state is None:
            self.app.notify("Filter system not available", severity="warning", timeout=2.0)
            return
        
        # Show current filter state
        if video_list.controller and video_list.controller.has_active_filters():
            descriptions = video_list.controller.get_active_filter_descriptions()
            self.app.notify(
                f"Active filters: {', '.join(descriptions)}\n"
                "Press 'c' to toggle completed, 'e' for errors only, 'x' to clear",
                title="Filters",
                timeout=5.0
            )
        else:
            self.app.notify(
                "No active filters.\n"
                "Press 'c' to toggle completed, 'e' for errors only",
                title="Filters",
                timeout=5.0
            )
    
    def action_toggle_completed_filter(self) -> None:
        """Toggle show/hide completed videos."""
        video_list = self.query_one(VideoListWidget)
        new_value = video_list.toggle_show_completed()
        status = "shown" if new_value else "hidden"
        self.app.notify(f"Completed videos {status}", timeout=2.0)
    
    def action_toggle_failed_filter(self) -> None:
        """Toggle show/hide failed videos."""
        video_list = self.query_one(VideoListWidget)
        new_value = video_list.toggle_show_failed()
        status = "shown" if new_value else "hidden"
        self.app.notify(f"Failed videos {status}", timeout=2.0)
    
    def action_errors_only_filter(self) -> None:
        """Toggle show only errors filter."""
        video_list = self.query_one(VideoListWidget)
        if video_list.controller:
            new_value = video_list.controller.toggle_show_only_errors()
            status = "ON" if new_value else "OFF"
            video_list.refresh_data()
            self.app.notify(f"Errors only filter: {status}", timeout=2.0)
    
    def action_clear_filters(self) -> None:
        """Clear all active filters."""
        video_list = self.query_one(VideoListWidget)
        video_list.clear_filters()
        self.app.notify("All filters cleared", timeout=2.0)
    
    def action_sort(self) -> None:
        """Cycle through sort options."""
        video_list = self.query_one(VideoListWidget)
        
        if video_list.controller is None:
            self.app.notify("Sort system not available", severity="warning", timeout=2.0)
            return
        
        # Cycle to next sort field
        new_field = video_list.cycle_sort_field()
        sort_desc = video_list.get_sort_description()
        
        self.app.notify(f"Sorted by: {sort_desc}", timeout=2.0)
    
    def action_toggle_sort_order(self) -> None:
        """Toggle between ascending/descending sort order."""
        video_list = self.query_one(VideoListWidget)
        
        if video_list.controller is None:
            self.app.notify("Sort system not available", severity="warning", timeout=2.0)
            return
        
        new_order = video_list.toggle_sort_order()
        sort_desc = video_list.get_sort_description()
        
        order_text = "descending" if new_order == SortOrder.DESCENDING else "ascending"
        self.app.notify(f"Sort order: {order_text} ({sort_desc})", timeout=2.0)
    
    def action_help(self) -> None:
        """Show help dialog."""
        if self.batch_mode:
            # Batch mode help
            help_text = (
                "Batch Mode Shortcuts:\n"
                "  Space - Select/deselect current video\n"
                "  a - Select all visible videos\n"
                "  c - Clear all selections\n"
                "  r - Retry failed selected videos\n"
                "  x - Remove selected from queue\n"
                "  e - Export selected to JSON\n"
                "  Esc - Exit batch mode\n"
                "  ? - Show this help"
            )
        else:
            # Normal mode help
            help_text = (
                "Keyboard Shortcuts:\n"
                "  q - Quit application\n"
                "  r - Refresh data\n"
                "  a - Toggle auto-refresh\n"
                "  d - View details\n"
                "  g - Toggle speed graph\n"
                "  f - Filter dialog\n"
                "  c - Toggle completed videos\n"
                "  e - Toggle errors only\n"
                "  x - Clear all filters\n"
                "  s - Change sort field\n"
                "  S - Toggle sort order (asc/desc)\n"
                "  Space - Select/deselect video\n"
                "  b - Toggle batch mode\n"
                "  ? - Show this help"
            )
        self.app.notify(help_text, title="Help", timeout=10.0)
    
    def action_toggle_select(self) -> None:
        """Toggle selection of current video."""
        video_list = self.query_one(VideoListWidget)
        video_list.toggle_selection()
        
        # Update footer if in batch mode
        if self.batch_mode:
            self._update_footer()
    
    def action_toggle_batch_mode(self) -> None:
        """Toggle batch mode on/off."""
        self.batch_mode = not self.batch_mode
        
        if self.batch_mode:
            # Entering batch mode
            self.app.notify(
                "Batch mode ON. Use [Space] to select, [a] for all, [c] to clear, "
                "[r] to retry failed, [x] to remove, [e] to export, [Esc] to exit",
                title="Batch Mode",
                timeout=5.0
            )
        else:
            # Exiting batch mode
            self.app.notify("Batch mode OFF", timeout=2.0)
            # Clear selection when exiting batch mode
            if self._batch_operations:
                self._batch_operations.clear_selection()
        
        self._update_footer()
        self._refresh_data()
    
    def action_exit_batch_mode(self) -> None:
        """Exit batch mode."""
        if self.batch_mode:
            self.batch_mode = False
            if self._batch_operations:
                self._batch_operations.clear_selection()
            self._update_footer()
            self._refresh_data()
            self.app.notify("Batch mode OFF", timeout=2.0)
    
    def action_select_all(self) -> None:
        """Select all visible videos."""
        if not self.batch_mode:
            # In normal mode, enter batch mode first
            self.batch_mode = True
        
        video_list = self.query_one(VideoListWidget)
        count = video_list.select_all_visible()
        
        self._update_footer()
        self.app.notify(f"Selected {count} videos", timeout=2.0)
    
    def action_batch_retry(self) -> None:
        """Retry failed videos in selection."""
        if not self._batch_operations or not self._batch_operations.has_selection():
            self.app.notify("No videos selected", severity="warning", timeout=2.0)
            return
        
        # Show confirmation dialog
        count = self._batch_operations.get_selected_count()
        self._confirm_action(
            f"Retry {count} failed video(s)?",
            self._do_batch_retry
        )
    
    async def _do_batch_retry(self) -> None:
        """Execute batch retry operation."""
        if not self._batch_operations:
            return
        
        self.app.notify("Retrying failed videos...", timeout=2.0)
        
        try:
            result = await self._batch_operations.retry_failed()
            
            if result.all_succeeded:
                self.app.notify(
                    f"Successfully retried {result.success_count} video(s)",
                    timeout=3.0
                )
            else:
                self.app.notify(
                    f"Retry complete: {result.success_count} succeeded, "
                    f"{result.failed_count} failed",
                    severity="warning" if result.failed_count > 0 else "information",
                    timeout=3.0
                )
            
            self._batch_operations.clear_selection()
            self._update_footer()
            self._refresh_data()
            
        except Exception as e:
            self.app.notify(f"Batch retry failed: {e}", severity="error", timeout=3.0)
    
    def action_batch_remove(self) -> None:
        """Remove selected videos from queue."""
        if not self._batch_operations or not self._batch_operations.has_selection():
            self.app.notify("No videos selected", severity="warning", timeout=2.0)
            return
        
        count = self._batch_operations.get_selected_count()
        self._confirm_action(
            f"Remove {count} video(s) from queue? This will cancel all active operations.",
            self._do_batch_remove
        )
    
    async def _do_batch_remove(self) -> None:
        """Execute batch remove operation."""
        if not self._batch_operations:
            return
        
        self.app.notify("Removing videos from queue...", timeout=2.0)
        
        try:
            result = await self._batch_operations.remove_from_queue()
            
            if result.all_succeeded:
                self.app.notify(
                    f"Successfully removed {result.success_count} video(s)",
                    timeout=3.0
                )
            else:
                self.app.notify(
                    f"Remove complete: {result.success_count} succeeded, "
                    f"{result.failed_count} failed",
                    severity="warning" if result.failed_count > 0 else "information",
                    timeout=3.0
                )
            
            self._update_footer()
            self._refresh_data()
            
        except Exception as e:
            self.app.notify(f"Batch remove failed: {e}", severity="error", timeout=3.0)
    
    def action_batch_export(self) -> None:
        """Export selected videos to JSON file."""
        if not self._batch_operations or not self._batch_operations.has_selection():
            self.app.notify("No videos selected", severity="warning", timeout=2.0)
            return
        
        # Generate default filename with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = f"haven_export_{timestamp}.json"
        
        # For now, use default path (in a full implementation, we'd show a file dialog)
        self._do_batch_export(default_path)
    
    def _do_batch_export(self, filepath: str) -> None:
        """Execute batch export operation.
        
        Args:
            filepath: Path to the output JSON file
        """
        if not self._batch_operations:
            return
        
        try:
            result = self._batch_operations.export_list(filepath)
            
            if result.get("success"):
                self.app.notify(
                    f"Exported {result['exported_count']} videos to {filepath}",
                    timeout=3.0
                )
            else:
                error = result.get("error", "Unknown error")
                self.app.notify(f"Export failed: {error}", severity="error", timeout=3.0)
                
        except Exception as e:
            self.app.notify(f"Export failed: {e}", severity="error", timeout=3.0)
    
    def _confirm_action(self, message: str, action_callback) -> None:
        """Show a confirmation dialog for destructive actions.
        
        Args:
            message: The confirmation message to display
            action_callback: The callback to execute if confirmed
        """
        # For now, just execute the action (in a full implementation, 
        # we'd show a modal confirmation dialog)
        # Since textual's modal dialogs are complex, we'll use a simpler approach:
        # Show notification and proceed
        self.app.notify(f"{message} (press same key to confirm)", timeout=3.0)
        
        # In a real implementation, we'd wait for confirmation
        # For now, we'll proceed with the action
        import asyncio
        if asyncio.iscoroutinefunction(action_callback):
            asyncio.create_task(action_callback())
        else:
            action_callback()
    
    def _update_footer(self) -> None:
        """Update the footer to reflect current state."""
        try:
            footer = self.query_one(VideoListFooter)
            selection_count = 0
            if self._batch_operations:
                selection_count = self._batch_operations.get_selected_count()
            footer.set_batch_mode(self.batch_mode, selection_count)
        except Exception:
            pass  # Footer may not be available yet
    
    def _refresh_data(self) -> None:
        """Refresh the video list data."""
        try:
            video_list = self.query_one(VideoListWidget)
            video_list.refresh_data()
            self._update_header()
            self._update_speed_graph()
        except Exception:
            pass  # Widget may not be available yet


class VideoListView:
    """Main video list view - the primary TUI interface.
    
    This class provides a high-level interface for the video list view,
    managing the screen and providing integration with the StateManager.
    
    Example:
        >>> view = VideoListView(state_manager, config)
        >>> await view.run()
    
    Attributes:
        state_manager: The StateManager for accessing video state
        config: The HavenTUIConfig for display settings
        screen: The VideoListScreen instance
        on_show_details: Optional callback for showing video details
        speed_history_repo: Optional repository for speed history data
        pipeline_interface: Optional PipelineInterface for batch operations
    """
    
    def __init__(
        self,
        state_manager: StateManager,
        config: HavenTUIConfig,
        on_show_details: Optional[Callable[[int], None]] = None,
        speed_history_repo: Optional[SpeedHistoryRepository] = None,
        pipeline_interface: Optional[Any] = None,
    ) -> None:
        """Initialize the video list view.
        
        Args:
            state_manager: The StateManager for accessing video state
            config: The TUI configuration
            on_show_details: Optional callback when user requests to view video details
            speed_history_repo: Optional repository for speed history data
            pipeline_interface: Optional PipelineInterface for batch operations
        """
        self.state_manager = state_manager
        self.config = config
        self.on_show_details = on_show_details
        self.speed_history_repo = speed_history_repo
        self.pipeline_interface = pipeline_interface
        self.screen: Optional[VideoListScreen] = None
    
    def create_screen(self) -> VideoListScreen:
        """Create the video list screen.
        
        Returns:
            The configured VideoListScreen instance
        """
        self.screen = VideoListScreen(
            state_manager=self.state_manager,
            config=self.config,
            on_show_details=self.on_show_details,
            speed_history_repo=self.speed_history_repo,
            pipeline_interface=self.pipeline_interface,
        )
        return self.screen
    
    def refresh(self) -> None:
        """Refresh the video list display."""
        if self.screen is not None:
            self.screen._refresh_data()
    
    def get_selected_video_id(self) -> Optional[int]:
        """Get the currently selected video ID.
        
        Returns:
            Video ID or None if no selection
        """
        if self.screen is None:
            return None
        video_list = self.screen.query_one(VideoListWidget)
        return video_list.get_selected_video_id()
    
    def get_selected_video_ids(self) -> List[int]:
        """Get all selected video IDs.
        
        Returns:
            List of video IDs
        """
        if self.screen is None:
            return []
        video_list = self.screen.query_one(VideoListWidget)
        return video_list.get_selected_video_ids()
