"""Layout System for Haven TUI.

This module provides a layout system for organizing TUI screens with
header, main content, footer, and an optional right pane for speed graphs.
Adapted for Textual framework.

Example:
    >>> from haven_tui.ui.layout import LayoutManager
    >>> layout = LayoutManager(config)
    >>> await self.view.dock(layout.header, edge="top", size=3)
    >>> await self.view.dock(layout.footer, edge="bottom", size=1)
    >>> await self.view.dock(layout.right_pane, edge="right", size=35)
    >>> await self.view.dock(layout.main)
"""

from __future__ import annotations

from typing import Optional, Any, Tuple
from abc import ABC, abstractmethod

from textual.widgets import Static
from textual.reactive import reactive
from textual.containers import Container, Horizontal

from haven_tui.config import HavenTUIConfig
from haven_tui.ui.components.speed_graph import SpeedGraphComponent
from haven_tui.core.state_manager import StateManager


class TUIPanel(Static):
    """Base class for TUI panels/sections.
    
    This abstract base class defines the interface for all panels in the
    TUI layout system. Panels are responsible for rendering content within
    their allocated space and handling user input.
    
    Attributes:
        visible: Whether the panel should be rendered
    """
    
    DEFAULT_CSS = """
    TUIPanel {
        width: 100%;
        height: 100%;
    }
    """
    
    def __init__(self, **kwargs: Any) -> None:
        """Initialize the panel.
        
        Args:
            **kwargs: Additional arguments passed to Static
        """
        super().__init__(**kwargs)
        self._visible = True
    
    @property
    def panel_visible(self) -> bool:
        """Get panel visibility."""
        return self._visible
    
    @panel_visible.setter
    def panel_visible(self, value: bool) -> None:
        """Set panel visibility."""
        self._visible = value
        self.display = value
    
    def render_content(self) -> str:
        """Render panel content.
        
        Returns:
            The content to display in the panel
        """
        raise NotImplementedError("Subclasses must implement render_content()")
    
    def handle_key(self, key: str) -> bool:
        """Handle key press.
        
        Args:
            key: The key that was pressed
            
        Returns:
            True if the key was handled, False otherwise
        """
        return False
    
    def on_resize(self, event: Any) -> None:
        """Handle resize events."""
        self.refresh()


class HeaderPanel(TUIPanel):
    """Header bar with status information.
    
    Displays the application name, version, current view name,
    download/upload speeds, and active video count.
    Styled with reversed colors for visibility.
    
    Visual:
        │ haven-tui v0.1.0 │ Pipeline View │ ↓ 12.5 MiB/s ↑ 3.2 MiB/s │ 5 active │
    """
    
    DEFAULT_CSS = """
    HeaderPanel {
        height: 1;
        background: $text;
        color: $background;
        text-style: bold;
        dock: top;
    }
    """
    
    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        speed_aggregator: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the header panel.
        
        Args:
            state_manager: StateManager for accessing video state
            speed_aggregator: SpeedAggregator for download/upload speeds
            **kwargs: Additional arguments passed to TUIPanel
        """
        super().__init__(**kwargs)
        self.state_manager = state_manager
        self.speed_aggregator = speed_aggregator
        self.version = "0.1.0"
        self.view_name = "Pipeline"
    
    def render_content(self) -> str:
        """Render the header content with app info and stats."""
        # Get active video count
        active_count = self._get_active_count()
        
        # Get download/upload speeds
        download_speed, upload_speed = self._get_speeds()
        
        # Build header parts
        parts = [
            f"haven-tui v{self.version}",
            f"│ {self.view_name} View",
            f"│ ↓ {self._format_speed(download_speed)} ↑ {self._format_speed(upload_speed)}",
            f"│ {active_count} active",
        ]
        
        return " ".join(parts)
    
    def _get_active_count(self) -> int:
        """Get the count of active videos."""
        if self.state_manager is None:
            return 0
        
        videos = self.state_manager.get_all_videos()
        if videos is None:
            return 0
        
        return len([v for v in videos if getattr(v, 'is_active', False)])
    
    def _get_speeds(self) -> Tuple[float, float]:
        """Get current download and upload speeds in bytes/sec.
        
        Returns:
            Tuple of (download_speed, upload_speed) in bytes/sec
        """
        if self.speed_aggregator is not None:
            try:
                return self.speed_aggregator.get_current_speeds()
            except Exception:
                pass
        
        return (0.0, 0.0)
    
    def _format_speed(self, speed: float) -> str:
        """Format speed in human-readable form.
        
        Args:
            speed: Speed in bytes per second
            
        Returns:
            Formatted speed string (e.g., "12.5 MiB/s")
        """
        if speed == 0:
            return "-"
        
        # Convert to human readable
        size = float(speed)
        if size < 1024:
            return f"{size:.0f} B/s"
        size /= 1024
        if size < 1024:
            return f"{size:.1f} KiB/s"
        size /= 1024
        if size < 1024:
            return f"{size:.1f} MiB/s"
        size /= 1024
        return f"{size:.1f} GiB/s"
    
    def compose(self) -> None:
        """Set up the header content."""
        self.update(self.render_content())
    
    def refresh_header(self) -> None:
        """Refresh the header content."""
        self.update(self.render_content())
    
    def set_view_name(self, view_name: str) -> None:
        """Set the current view name.
        
        Args:
            view_name: The view name to display
        """
        self.view_name = view_name
        self.refresh_header()
    
    def set_speed_aggregator(self, aggregator: Any) -> None:
        """Set the speed aggregator for speed display.
        
        Args:
            aggregator: SpeedAggregator instance
        """
        self.speed_aggregator = aggregator


class MainPanel(TUIPanel):
    """Main content panel for the video list.
    
    Contains the primary content of the TUI - the scrollable
    video list showing pipeline status and progress.
    """
    
    DEFAULT_CSS = """
    MainPanel {
        width: 100%;
        height: 1fr;
        padding: 0;
    }
    """
    
    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        config: Optional[HavenTUIConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the main panel.
        
        Args:
            state_manager: StateManager for accessing video state
            config: TUI configuration
            **kwargs: Additional arguments passed to TUIPanel
        """
        super().__init__(**kwargs)
        self.state_manager = state_manager
        self.config = config
        self._content_widget: Optional[Any] = None
    
    def render_content(self) -> str:
        """Render main panel content."""
        return ""  # Main panel uses child widgets
    
    def set_content(self, widget: Any) -> None:
        """Set the main content widget.
        
        Args:
            widget: The widget to display in the main panel
        """
        self._content_widget = widget


class FooterPanel(TUIPanel):
    """Footer bar with key bindings and status messages.
    
    Displays available keyboard shortcuts and their functions,
    similar to aria2tui's footer. Styled consistently with header
    using reverse video (bold, inverted colors).
    
    Visual:
        │ [q Quit] [r Refresh] [←/→ Navigate] [Enter Details] [g Toggle Graph] │
    
    Attributes:
        status_message: Temporary status message to display
        view_context: Current view context for dynamic key binding updates
        status_timeout: Time when status message should clear
    """
    
    DEFAULT_CSS = """
    FooterPanel {
        height: 1;
        background: $text;
        color: $background;
        text-style: bold;
        dock: bottom;
    }
    """
    
    # Context-specific key bindings
    CONTEXT_BINDINGS = {
        "pipeline": [
            ("q", "Quit"),
            ("r", "Refresh"),
            ("↑/↓", "Navigate"),
            ("Enter", "Details"),
            ("g", "Toggle Graph"),
            ("?", "Help"),
        ],
        "detail": [
            ("q", "Quit"),
            ("Esc", "Back"),
            ("r", "Refresh"),
            ("g", "Toggle Graph"),
            ("?", "Help"),
        ],
        "help": [
            ("q", "Quit"),
            ("Esc", "Close"),
            ("?", "Back"),
        ],
    }
    
    def __init__(
        self,
        config: Optional[HavenTUIConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the footer panel.
        
        Args:
            config: TUI configuration for key bindings
            **kwargs: Additional arguments passed to TUIPanel
        """
        super().__init__(**kwargs)
        self.config = config
        self.status_message: str = ""
        self.status_timeout: Optional[float] = None
        self.view_context: str = "pipeline"
        self._key_bindings: list[tuple[str, str]] = []
        self._update_key_bindings()
    
    def _update_key_bindings(self) -> None:
        """Update key bindings based on current view context."""
        if self.view_context in self.CONTEXT_BINDINGS:
            self._key_bindings = self.CONTEXT_BINDINGS[self.view_context].copy()
        else:
            # Default bindings if context not found
            self._key_bindings = self.CONTEXT_BINDINGS["pipeline"].copy()
    
    def render_content(self) -> str:
        """Render footer content with key bindings or status message.
        
        If a status message is set and not expired, it will be displayed.
        Otherwise, the current context's key bindings are shown.
        
        Returns:
            Formatted footer content string
        """
        import time
        
        # Check if status message has expired
        if self.status_timeout and time.time() > self.status_timeout:
            self.status_message = ""
            self.status_timeout = None
        
        # Show status message if present
        if self.status_message:
            return f" {self.status_message}"
        
        # Build key binding string
        parts = [f"[{key} {label}]" for key, label in self._key_bindings]
        return " " + " ".join(parts)
    
    def compose(self) -> None:
        """Set up the footer content."""
        self.update(self.render_content())
    
    def refresh_footer(self) -> None:
        """Refresh the footer content."""
        self.update(self.render_content())
    
    def set_status(self, message: str, duration: float = 3.0) -> None:
        """Set temporary status message.
        
        The status message will be displayed instead of key bindings
        for the specified duration.
        
        Args:
            message: The status message to display
            duration: How long to show the message in seconds (default: 3.0)
        """
        import time
        self.status_message = message
        self.status_timeout = time.time() + duration
        self.refresh_footer()
    
    def clear_status(self) -> None:
        """Clear the current status message immediately."""
        self.status_message = ""
        self.status_timeout = None
        self.refresh_footer()
    
    def set_view_context(self, context: str) -> None:
        """Set the current view context for dynamic key binding updates.
        
        Args:
            context: The view context ("pipeline", "detail", "help", etc.)
        """
        if context != self.view_context:
            self.view_context = context
            self._update_key_bindings()
            self.refresh_footer()
    
    def get_current_bindings(self) -> list[tuple[str, str]]:
        """Get the current key bindings.
        
        Returns:
            List of (key, label) tuples for the current context
        """
        return self._key_bindings.copy()
    
    def show_help_keys(self) -> None:
        """Show help key overlay - switches to help context."""
        self.set_view_context("help")


class SpeedGraphPanel(TUIPanel):
    """Right panel displaying speed history graphs.
    
    Shows real-time speed graphs for the selected video's
    pipeline stages. Can be toggled on/off.
    """
    
    DEFAULT_CSS = """
    SpeedGraphPanel {
        width: 35;
        height: 100%;
        border: solid $primary;
        padding: 1;
        dock: right;
    }
    """
    
    def __init__(
        self,
        video_id: Optional[int] = None,
        config: Optional[HavenTUIConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the speed graph panel.
        
        Args:
            video_id: ID of video to show graph for
            config: TUI configuration for graph settings
            **kwargs: Additional arguments passed to TUIPanel
        """
        super().__init__(**kwargs)
        self.video_id = video_id
        self.config = config
        self._graph_component: Optional[SpeedGraphComponent] = None
    
    def render_content(self) -> str:
        """Render speed graph panel content."""
        return ""  # Panel uses SpeedGraphComponent child widget
    
    def compose(self) -> None:
        """Set up the speed graph component."""
        history_seconds = 60
        if self.config:
            history_seconds = self.config.display.graph_history_seconds
        
        self._graph_component = SpeedGraphComponent(
            width=30,
            height=15,
            history_seconds=history_seconds,
        )
        yield self._graph_component
    
    def set_video(self, video_id: int, stage: str = "download") -> None:
        """Set the video to display graph for.
        
        Args:
            video_id: ID of the video
            stage: Pipeline stage to display
        """
        self.video_id = video_id
        if self._graph_component:
            self._graph_component.set_video(video_id, stage)
    
    def set_repository(self, repo: Any) -> None:
        """Set the speed history repository.
        
        Args:
            repo: SpeedHistoryRepository instance
        """
        if self._graph_component:
            self._graph_component.set_repository(repo)


class LayoutManager:
    """Manages TUI layout with header, main, footer, optional side pane.
    
    This class coordinates the layout of all panels in the TUI,
    handling their creation, visibility, and resize behavior.
    
    Attributes:
        config: The TUI configuration
        header: Header panel widget
        main: Main content panel widget
        footer: Footer panel widget
        right_pane: Optional right pane widget (speed graphs)
        show_right_pane: Whether right pane is currently visible
    
    Example:
        >>> layout = LayoutManager(config, state_manager)
        >>> # In Textual app compose():
        >>> yield layout.header
        >>> with Horizontal():
        >>>     yield layout.main
        >>>     yield layout.right_pane
        >>> yield layout.footer
    """
    
    def __init__(
        self,
        config: HavenTUIConfig,
        state_manager: Optional[StateManager] = None,
        speed_aggregator: Optional[Any] = None,
    ) -> None:
        """Initialize the layout manager.
        
        Args:
            config: The TUI configuration
            state_manager: Optional StateManager for data access
            speed_aggregator: Optional SpeedAggregator for header speed display
        """
        self.config = config
        self.state_manager = state_manager
        self.speed_aggregator = speed_aggregator
        self.show_right_pane = config.display.show_speed_graphs
        
        # Create panels
        self.header = HeaderPanel(
            state_manager=state_manager,
            speed_aggregator=speed_aggregator
        )
        self.main = MainPanel(state_manager=state_manager, config=config)
        self.footer = FooterPanel(config=config)
        self.right_pane: Optional[SpeedGraphPanel] = None
        
        if self.show_right_pane:
            self.right_pane = self._create_right_pane()
    
    def _create_right_pane(self) -> SpeedGraphPanel:
        """Create the right pane widget."""
        return SpeedGraphPanel(config=self.config)
    
    def toggle_right_pane(self) -> bool:
        """Toggle speed graph visibility (like aria2tui).
        
        Returns:
            True if right pane is now visible, False otherwise
        """
        self.show_right_pane = not self.show_right_pane
        
        if self.show_right_pane:
            self.right_pane = self._create_right_pane()
        else:
            self.right_pane = None
        
        return self.show_right_pane
    
    def set_right_pane_video(self, video_id: int, stage: str = "download") -> None:
        """Set the video to display in the right pane.
        
        Args:
            video_id: ID of the video to display
            stage: Pipeline stage to show
        """
        if self.right_pane:
            self.right_pane.set_video(video_id, stage)
    
    def refresh_header(self) -> None:
        """Refresh the header panel content."""
        self.header.refresh_header()
    
    def refresh_footer(self) -> None:
        """Refresh the footer panel content."""
        self.footer.refresh_footer()
    
    def get_layout_regions(self, total_width: int, total_height: int) -> dict:
        """Calculate layout regions based on available space.
        
        This method calculates the position and dimensions for each panel
        based on the available terminal size.
        
        Args:
            total_width: Total available width
            total_height: Total available height
            
        Returns:
            Dictionary with region specifications for each panel
        """
        # Fixed heights
        header_height = 3
        footer_height = 1
        
        # Right pane width (35 chars if visible and terminal is wide enough)
        right_pane_width = 0
        if self.show_right_pane and total_width > 100:
            right_pane_width = 35
        
        # Calculate main content area
        main_height = total_height - header_height - footer_height
        main_width = total_width - right_pane_width
        
        return {
            "header": {
                "y": 0,
                "x": 0,
                "height": header_height,
                "width": total_width,
            },
            "main": {
                "y": header_height,
                "x": 0,
                "height": main_height,
                "width": main_width,
            },
            "footer": {
                "y": total_height - footer_height,
                "x": 0,
                "height": footer_height,
                "width": total_width,
            },
            "right_pane": {
                "y": header_height,
                "x": main_width,
                "height": main_height,
                "width": right_pane_width,
            } if right_pane_width > 0 else None,
        }
    
    def handle_resize(self, width: int, height: int) -> None:
        """Handle terminal resize events.
        
        Recalculates layout regions and updates panel visibility
        based on new terminal dimensions.
        
        Args:
            width: New terminal width
            height: New terminal height
        """
        regions = self.get_layout_regions(width, height)
        
        # Update right pane visibility based on space
        if self.right_pane:
            right_region = regions.get("right_pane")
            if right_region:
                self.right_pane.panel_visible = True
            else:
                self.right_pane.panel_visible = False
    
    def get_panels(self) -> dict[str, Optional[TUIPanel]]:
        """Get all panels as a dictionary.
        
        Returns:
            Dictionary mapping panel names to panel instances
        """
        return {
            "header": self.header,
            "main": self.main,
            "footer": self.footer,
            "right_pane": self.right_pane,
        }


class ResizableLayout(Container):
    """A Textual container that manages resizable layout regions.
    
    This container automatically handles terminal resize events and
    ensures panels render within their allocated space without overlapping.
    """
    
    DEFAULT_CSS = """
    ResizableLayout {
        width: 100%;
        height: 100%;
        layout: vertical;
    }
    """
    
    def __init__(
        self,
        layout_manager: LayoutManager,
        **kwargs: Any,
    ) -> None:
        """Initialize the resizable layout container.
        
        Args:
            layout_manager: The layout manager controlling panel placement
            **kwargs: Additional arguments passed to Container
        """
        super().__init__(**kwargs)
        self.layout_manager = layout_manager
    
    def compose(self) -> None:
        """Compose the layout with all panels."""
        # Header at top
        yield self.layout_manager.header
        
        # Middle section: main content + optional right pane
        with Horizontal():
            yield self.layout_manager.main
            if self.layout_manager.right_pane:
                yield self.layout_manager.right_pane
        
        # Footer at bottom
        yield self.layout_manager.footer
    
    def on_resize(self, event: Any) -> None:
        """Handle resize events."""
        # Notify layout manager of resize
        self.layout_manager.handle_resize(event.size.width, event.size.height)
