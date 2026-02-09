"""Entry point for `python -m haven_tui`.

This module allows running the Haven TUI application using:
    python -m haven_tui

It serves as the main entry point when the package is executed as a module.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from haven_tui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
