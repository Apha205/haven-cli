"""Built-in plugins for Haven CLI.

This module contains the built-in plugin implementations that ship with Haven CLI.
"""

from haven_cli.plugins.builtin.youtube import YouTubePlugin
from haven_cli.plugins.builtin.bittorrent import BitTorrentPlugin

__all__ = ["YouTubePlugin", "BitTorrentPlugin"]
