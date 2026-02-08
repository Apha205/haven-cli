"""Haven TUI - Terminal User Interface for Haven Video Pipeline.

This module provides a TUI for monitoring and controlling the Haven video pipeline.
It is an optional component that can be installed with `pip install haven-cli[tui]`.

Example:
    Launch TUI via CLI:
        $ haven tui
    
    Launch TUI via module:
        $ python -m haven_cli.tui
"""

__version__ = "0.1.0"

# Check if TUI dependencies are available
try:
    from textual.app import App  # noqa: F401
    _TUI_AVAILABLE = True
except ImportError:
    _TUI_AVAILABLE = False

__all__ = [
    "_TUI_AVAILABLE",
]


def check_tui_available() -> bool:
    """Check if TUI dependencies are installed.
    
    Returns:
        True if TUI dependencies are available, False otherwise.
    """
    return _TUI_AVAILABLE
