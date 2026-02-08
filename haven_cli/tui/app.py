"""Main TUI application for Haven.

This module provides the main TUI application using Textual.
"""

from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static

from haven_cli.tui.config import TUIConfig


class TUIApp(App[None]):
    """Main TUI application for Haven video pipeline monitoring.
    
    This application provides a terminal-based interface for:
    - Monitoring pipeline progress
    - Viewing video status
    - Controlling downloads, encryption, uploads
    - Viewing metrics and logs
    
    Example:
        app = TUIApp(config_file="tui.toml")
        app.run()
    """
    
    CSS = """
    Screen {
        align: center middle;
    }
    
    #main-container {
        width: 100%;
        height: 100%;
        padding: 1;
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
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("?", "help", "Help"),
    ]
    
    def __init__(self, config_file: Optional[str] = None) -> None:
        """Initialize the TUI application.
        
        Args:
            config_file: Optional path to TUI configuration file.
        """
        super().__init__()
        self.config = TUIConfig()
        self.config_path: Optional[Path] = Path(config_file) if config_file else None
        
        # Load config if provided
        if self.config_path and self.config_path.exists():
            self.config.load_from_file(self.config_path)
    
    def compose(self) -> ComposeResult:
        """Compose the UI layout.
        
        Yields:
            UI components for the application.
        """
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            yield Static(
                "[bold blue]Welcome to Haven TUI[/bold blue]\n\n"
                "The Terminal User Interface for Haven video pipeline.\n\n"
                "[dim]Press 'q' to quit, '?' for help[/dim]",
                classes="welcome",
            )
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Handle application mount event."""
        self.title = "Haven TUI"
        self.sub_title = "Video Pipeline Monitor"
    
    def action_refresh(self) -> None:
        """Refresh the display."""
        self.refresh()
    
    def action_help(self) -> None:
        """Show help information."""
        self.notify(
            "Haven TUI Help:\n"
            "  q - Quit\n"
            "  r - Refresh\n"
            "  ? - Show this help",
            title="Help",
            timeout=5.0,
        )
