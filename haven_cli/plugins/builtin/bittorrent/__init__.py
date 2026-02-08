"""BitTorrent archiver plugin for Haven CLI.

This plugin provides BitTorrent downloading capabilities with support
for multiple magnet link sources through a pluggable source interface.
"""

from haven_cli.plugins.builtin.bittorrent.plugin import BitTorrentPlugin, BitTorrentConfig
from haven_cli.plugins.builtin.bittorrent.sources.base import (
    MagnetSource,
    MagnetLink,
    SourceConfig,
)
from haven_cli.plugins.builtin.bittorrent.sources.extraction import (
    ExtractionContext,
    ExtractionPipeline,
    ExtractionStep,
)
from haven_cli.plugins.builtin.bittorrent.sources.scraper import WebScraperSource
from haven_cli.plugins.builtin.bittorrent.sources.forum import (
    ForumScraperSource,
    ForumSourceConfig,
)

__all__ = [
    "BitTorrentPlugin",
    "BitTorrentConfig",
    "MagnetSource",
    "MagnetLink",
    "SourceConfig",
    "ExtractionContext",
    "ExtractionPipeline",
    "ExtractionStep",
    "WebScraperSource",
    "ForumScraperSource",
    "ForumSourceConfig",
]
