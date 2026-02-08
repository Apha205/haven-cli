"""Main Video List View for Haven TUI.

This module provides the primary view for the TUI - a scrollable list of videos
showing their current pipeline stage and progress, inspired by aria2tui's download list.
"""

from __future__ import annotations

from typing import Callable, ClassVar, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from textual.widgets import DataTable, Static, Header, Footer
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.coordinate import Coordinate

from haven_tui.core.state_manager import StateManager, VideoState
from haven_tui.config import HavenTUIConfig
from haven_tui.models.video_view import PipelineStage
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
        ("title", "Title", 35, True),
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
        **kwargs: Any,
    ) -> None:
        """Initialize the video list widget.
        
        Args:
            state_manager: The StateManager for accessing video state
            config: The TUI configuration
            on_select: Callback when a video is selected (single click)
            on_multi_select: Callback for multi-selection changes
            **kwargs: Additional arguments passed to DataTable
        """
        super().__init__(**kwargs)
        self.state_manager = state_manager
        self.config = config or HavenTUIConfig()
        self.on_select_callback = on_select
        self.on_multi_select_callback = on_multi_select
        self._video_rows: List[VideoRow] = []
        self._selected_video_ids: set[int] = set()
        self._last_refresh: Optional[datetime] = None
        
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
        
        This method fetches the current video states from the state manager
        and updates the table display.
        """
        if self.state_manager is None:
            return
        
        # Get all videos from state manager
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
    
    def _update_table(self) -> None:
        """Update the table with current video rows."""
        # Clear existing rows
        self.clear()
        
        # Add rows
        for row in self._video_rows:
            progress_bar = self._format_progress_bar(row.progress)
            
            # Apply styling based on stage and status
            stage_style = self._get_stage_style(row.stage, row.status)
            
            cells = [
                str(row.index),
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
    
    def get_selected_video_ids(self) -> List[int]:
        """Get IDs of all selected videos (for multi-select).
        
        Returns:
            List of video IDs
        """
        return list(self._selected_video_ids)
    
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
        
        if video_id in self._selected_video_ids:
            self._selected_video_ids.remove(video_id)
        else:
            self._selected_video_ids.add(video_id)
        
        if self.on_multi_select_callback:
            self.on_multi_select_callback(list(self._selected_video_ids))
    
    def clear_selection(self) -> None:
        """Clear all selections."""
        self._selected_video_ids.clear()
        if self.on_multi_select_callback:
            self.on_multi_select_callback([])


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
    
    def __init__(self, show_graph: bool = False, **kwargs: Any) -> None:
        """Initialize the footer.
        
        Args:
            show_graph: Whether the speed graph is currently visible
            **kwargs: Additional arguments passed to Static
        """
        super().__init__(**kwargs)
        self._show_graph = show_graph
    
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
    
    def _update_content(self) -> None:
        """Update the footer content."""
        graph_indicator = "ON" if self._show_graph else "OFF"
        self.update(
            f"[q] Quit  [r] Refresh  [a] Auto-refresh  [d] Details  "
            f"[g] Graph ({graph_indicator})  [f] Filter  [s] Sort  [?] Help"
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
        ("s", "sort", "Sort"),
        ("?", "help", "Help"),
        ("space", "toggle_select", "Select"),
    ]
    
    auto_refresh: reactive[bool] = reactive(True)
    show_graph: reactive[bool] = reactive(False)
    
    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        config: Optional[HavenTUIConfig] = None,
        on_show_details: Optional[Callable[[int], None]] = None,
        speed_history_repo: Optional[SpeedHistoryRepository] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the video list screen.
        
        Args:
            state_manager: The StateManager for accessing video state
            config: The TUI configuration
            on_show_details: Optional callback when user requests to view video details
            speed_history_repo: Optional repository for speed history data
            **kwargs: Additional arguments passed to Screen
        """
        super().__init__(**kwargs)
        self.state_manager = state_manager
        self.config = config or HavenTUIConfig()
        self.auto_refresh = True
        self.show_graph = config.display.show_speed_graphs if config else False
        self._refresh_timer: Optional[Any] = None
        self.on_show_details_callback = on_show_details
        self._speed_history_repo = speed_history_repo
        self._selected_video_id: Optional[int] = None
        self._selected_stage: str = "download"
    
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
                yield VideoListFooter(show_graph=self.show_graph)
    
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
        """Open filter dialog."""
        self.app.notify("Filter dialog (not implemented)", timeout=2.0)
    
    def action_sort(self) -> None:
        """Cycle through sort options."""
        self.app.notify("Sort options (not implemented)", timeout=2.0)
    
    def action_help(self) -> None:
        """Show help dialog."""
        help_text = (
            "Keyboard Shortcuts:\n"
            "  q - Quit application\n"
            "  r - Refresh data\n"
            "  a - Toggle auto-refresh\n"
            "  d - View details\n"
            "  g - Toggle speed graph\n"
            "  f - Filter videos\n"
            "  s - Sort videos\n"
            "  Space - Select/deselect video\n"
            "  ? - Show this help"
        )
        self.app.notify(help_text, title="Help", timeout=10.0)
    
    def action_toggle_select(self) -> None:
        """Toggle selection of current video."""
        video_list = self.query_one(VideoListWidget)
        video_list.toggle_selection()


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
    """
    
    def __init__(
        self,
        state_manager: StateManager,
        config: HavenTUIConfig,
        on_show_details: Optional[Callable[[int], None]] = None,
        speed_history_repo: Optional[SpeedHistoryRepository] = None,
    ) -> None:
        """Initialize the video list view.
        
        Args:
            state_manager: The StateManager for accessing video state
            config: The TUI configuration
            on_show_details: Optional callback when user requests to view video details
            speed_history_repo: Optional repository for speed history data
        """
        self.state_manager = state_manager
        self.config = config
        self.on_show_details = on_show_details
        self.speed_history_repo = speed_history_repo
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
