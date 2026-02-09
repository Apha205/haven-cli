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
from pathlib import Path

# Import from haven_tui package
from haven_tui.config import HavenTUIConfig, get_config, get_default_config_path
from haven_tui.core.state_manager import StateManager
from haven_tui.core.pipeline_interface import PipelineInterface
from haven_tui.data.event_consumer import TUIEventConsumer as EventConsumer
from haven_tui.data.refresher import DataRefresher as Refresher
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
    
    # Note: video_detail screen is created dynamically with video_id
    SCREENS = {
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
            self.config = HavenTUIConfig.load(Path(config_path))
        else:
            default_path = get_default_config_path()
            if default_path.exists():
                self.config = HavenTUIConfig.load(default_path)
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
        # Get database URL from config
        db_url = self.config.database.connection_string
        
        # Initialize pipeline interface with database path
        # The PipelineInterface needs a database path to connect to the Haven database
        self.pipeline_interface = PipelineInterface(
            database_path=db_url.replace("sqlite:///", ""),
        )
        
        # Enter the async context to initialize the database session
        await self.pipeline_interface.__aenter__()
        
        # Initialize state manager with pipeline interface
        # StateManager uses pipeline_interface as its data source
        self.state_manager = StateManager(pipeline=self.pipeline_interface)
        await self.state_manager.initialize()
        
        # Initialize speed history repository
        self.speed_history_repo = SpeedHistoryRepository(
            db_url=db_url,
            max_history_seconds=self.config.display.graph_history_seconds,
        )
        
        # Initialize event consumer - skip for now as it requires EventBus
        # The StateManager already handles events directly from PipelineInterface
        self.event_consumer = None
        
        # Initialize refresher - skip for now as it requires full setup
        # The VideoListScreen has its own refresh mechanism
        self.refresher = None
        
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
        
        # Note: video_detail screen is created dynamically with video_id
        # Other screens are defined in SCREENS class attribute
    
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
            await self.refresher.stop()
        
        if self.event_consumer:
            await self.event_consumer.stop()
        
        # Shutdown state manager
        if self.state_manager:
            await self.state_manager.shutdown()
        
        # Exit pipeline interface context
        if self.pipeline_interface:
            await self.pipeline_interface.__aexit__(None, None, None)


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
