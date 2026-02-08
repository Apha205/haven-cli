"""Magnet link sources for BitTorrent plugin.

This module provides the abstract base class for magnet link sources
and several built-in implementations.
"""

from haven_cli.plugins.builtin.bittorrent.sources.base import (
    MagnetSource,
    MagnetLink,
    SourceConfig,
    SourceHealth,
    SourceHealthStatus,
)
from haven_cli.plugins.builtin.bittorrent.sources.extraction import (
    ExtractionContext,
    ExtractionPipeline,
    ExtractionStep,
    ForEachElement,
    ConditionalStep,
)
from haven_cli.plugins.builtin.bittorrent.sources.scraper import WebScraperSource

__all__ = [
    # Base classes
    "MagnetSource",
    "MagnetLink",
    "SourceConfig",
    "SourceHealth",
    "SourceHealthStatus",
    # Extraction pipeline
    "ExtractionContext",
    "ExtractionPipeline",
    "ExtractionStep",
    "ForEachElement",
    "ConditionalStep",
    # Concrete source
    "WebScraperSource",
]
