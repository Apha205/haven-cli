"""Main TUI application for Haven.

This module provides the main entry point for the Haven TUI application
using the Textual framework.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional, Any

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static

# Import from haven_tui package
from haven_tui.config import HavenTUIConfig, get_config, get_default_config_path
from haven_tui.core.state_manager import StateManager
from haven_tui.core.pipeline_interface import PipelineInterface
from haven_tui.data.event_consumer import EventConsumer
from haven_tui.data.refresher import Refresher
from haven_tui.data.repositories import SpeedHistoryRepository
from haven_tui.ui.views.video_list import VideoListScreen
from haven_tui.ui.views.video_detail import VideoDetailScreen
from haven_tui.ui.views.analytics import AnalyticsDashboardScreen
from haven_tui.ui.views.event_log import EventLogScreen


class HavenTUIApp(App[None]):
    """Main TUI application for Haven video pipeline monitoring.
    
    This application provides a terminal-based interface for:
    - Monitoring video pipeline progress
    - Viewing video status and details
    - Controlling downloads, encryption, uploads
    - Viewing metrics and logs
    - Managing filters and search
    
    Example:
        >>> app = HavenTUIApp()
        >>> app.run()
    
    Attributes:
        config: The TUI configuration
        state_manager: Manages application state
        pipeline_interface: Interface to the pipeline
        event_consumer: Consumes events from the pipeline
        refresher: Handles periodic data refresh
        speed_history_repo: Repository for speed history data
    """
    
    CSS = """
    Screen {
        align: center middle;
    }
    
    #main-container {
        width: 100%;
        height: 100%;
        padding: 0;
    }
    
    .welcome {
        width: 100%;
        height: auto;
        content-align: center middle;
        text-align: center;
    }
    
    .welcome-title {
        text-style: bold;
        color: $accent;
    }
    
    .loading {
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-align: center;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("?", "help", "Help"),
    ]
    
    SCREENS = {
        "video_list": VideoListScreen,
        "video_detail": VideoDetailScreen,
        "analytics": AnalyticsDashboardScreen,
        "event_log": EventLogScreen,
    }
    
    def __init__(
        self,
        config: Optional[HavenTUIConfig] = None,
        config_path: Optional[str] = None,
    ) -> None:
        """Initialize the TUI application.
        
        Args:
            config: Optional TUI configuration. If not provided, will load
                from config file or use defaults.
            config_path: Optional path to configuration file.
        """
        super().__init__()
        
        # Load configuration
        if config:
            self.config = config
        elif config_path:
            self.config = get_config(config_path)
        else:
            default_path = get_default_config_path()
            if default_path.exists():
                self.config = get_config(str(default_path))
            else:
                self.config = HavenTUIConfig()
        
        # Initialize core components (will be set up in on_mount)
        self.state_manager: Optional[StateManager] = None
        self.pipeline_interface: Optional[PipelineInterface] = None
        self.event_consumer: Optional[EventConsumer] = None
        self.refresher: Optional[Refresher] = None
        self.speed_history_repo: Optional[SpeedHistoryRepository] = None
        self._init_error: Optional[str] = None
    
    def compose(self) -> ComposeResult:
        """Compose the UI layout.
        
        Yields:
            UI components for the application.
        """
        with Container(id="main-container"):
            if self._init_error:
                yield Static(
                    f"[bold red]Error:[/bold red] {self._init_error}\n\n"
                    "Please check your configuration and try again.",
                    classes="loading",
                )
            else:
                yield Static(
                    "[bold blue]Haven TUI[/bold blue]\n\n"
                    "[dim]Loading...[/dim]",
                    classes="loading",
                )
    
    async def on_mount(self) -> None:
        """Handle application mount event - initialize components."""
        self.title = "Haven TUI"
        self.sub_title = "Video Pipeline Monitor"
        
        try:
            await self._initialize_components()
            
            # Push the main video list screen
            if self.state_manager:
                await self.push_screen("video_list")
        except Exception as e:
            self._init_error = str(e)
            self.refresh()
    
    async def _initialize_components(self) -> None:
        """Initialize all application components."""
        # Initialize state manager
        db_url = self.config.database.connection_string
        self.state_manager = StateManager(db_url=db_url)
        
        # Initialize pipeline interface
        self.pipeline_interface = PipelineInterface(
            base_url=self.config.advanced.api_base_url,
            api_key=self.config.advanced.api_key,
        )
        
        # Initialize speed history repository
        self.speed_history_repo = SpeedHistoryRepository(
            db_url=db_url,
            max_history_seconds=self.config.display.graph_history_seconds,
        )
        
        # Initialize event consumer
        self.event_consumer = EventConsumer(
            pipeline_interface=self.pipeline_interface,
            state_manager=self.state_manager,
        )
        
        # Initialize refresher
        self.refresher = Refresher(
            state_manager=self.state_manager,
            refresh_interval=self.config.display.refresh_rate,
        )
        
        # Start background tasks
        # Note: In a real implementation, these would be proper background tasks
        # For now, we'll set up the screens with the initialized components
        
        # Update screens with initialized components
        self._setup_screens()
    
    def _setup_screens(self) -> None:
        """Set up screens with initialized components."""
        # Create video list screen with all components
        video_list_screen = VideoListScreen(
            state_manager=self.state_manager,
            config=self.config,
            speed_history_repo=self.speed_history_repo,
            pipeline_interface=self.pipeline_interface,
        )
        
        # Install the screen
        self.install_screen(video_list_screen, "video_list")
        
        # Install other screens
        self.install_screen(VideoDetailScreen(), "video_detail")
        self.install_screen(AnalyticsDashboardScreen(), "analytics")
        self.install_screen(EventLogScreen(), "event_log")
    
    def action_refresh(self) -> None:
        """Refresh the display."""
        self.refresh()
    
    def action_help(self) -> None:
        """Show help information."""
        help_text = """
[b]Haven TUI Help[/b]

[b]Global Keys:[/b]
  q - Quit application
  r - Refresh display
  ? - Show this help

[b]Navigation:[/b]
  ↑/↓ - Navigate up/down
  Enter - Select item / View details
  Esc - Go back

[b]Filters:[/b]
  f - Open filter dialog
  c - Toggle completed videos
  e - Show errors only
  x - Clear all filters

[b]Sorting:[/b]
  s - Change sort field
  S - Toggle sort order

[b]View:[/b]
  g - Toggle speed graph
  a - Toggle analytics view
  l - Show event log

[b]Actions:[/b]
  space - Select item (batch mode)
  b - Toggle batch mode
  R - Retry failed items
  X - Cancel selected items
"""
        self.notify(help_text, title="Help", timeout=10.0)
    
    async def on_unmount(self) -> None:
        """Handle application unmount - cleanup resources."""
        # Stop background tasks
        if self.refresher:
            self.refresher.stop()
        
        if self.event_consumer:
            await self.event_consumer.stop()
        
        # Close database connections
        if self.state_manager:
            await self.state_manager.close()


def main(args: Optional[list[str]] = None) -> int:
    """Main entry point for Haven TUI.
    
    Args:
        args: Command line arguments (optional).
        
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    # Check Python version
    if sys.version_info < (3, 9):
        print(
            "Error: Python 3.9 or higher is required.",
            file=sys.stderr,
        )
        return 1
    
    # Parse arguments (simple implementation)
    config_path: Optional[str] = None
    if args:
        for i, arg in enumerate(args):
            if arg in ("-c", "--config") and i + 1 < len(args):
                config_path = args[i + 1]
            elif arg.startswith("--config="):
                config_path = arg.split("=", 1)[1]
            elif arg in ("-h", "--help"):
                print(__doc__ or "Haven TUI - Terminal User Interface for Haven")
                print("\nUsage: haven-tui [OPTIONS]")
                print("\nOptions:")
                print("  -c, --config PATH    Path to configuration file")
                print("  -h, --help          Show this help message")
                print("  -v, --version       Show version information")
                return 0
            elif arg in ("-v", "--version"):
                from haven_tui import __version__
                print(f"haven-tui {__version__}")
                return 0
    
    try:
        # Create and run the app
        app = HavenTUIApp(config_path=config_path)
        app.run()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
