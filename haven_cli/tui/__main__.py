"""Entry point for `python -m haven_cli.tui`."""

import sys
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from haven_cli.tui import check_tui_available


def main() -> int:
    """Main entry point for the TUI.
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    # Check if TUI dependencies are available
    if not check_tui_available():
        print(
            "Error: TUI dependencies not installed.\n"
            "Install with: pip install 'haven-cli[tui]'",
            file=sys.stderr,
        )
        return 1
    
    # Import and run the TUI app
    from haven_cli.tui.app import TUIApp
    
    app = TUIApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
