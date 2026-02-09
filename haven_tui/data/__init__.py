"""Data access layer for Haven TUI.

Repository pattern implementation for querying pipeline data,
event consumer for real-time state updates, and refresh strategy
for data synchronization.
"""

from haven_tui.data.repositories import (
    PipelineSnapshotRepository,
    DownloadRepository,
    JobHistoryRepository,
    SpeedHistoryRepository,
    AnalyticsRepository,
)
from haven_tui.data.event_consumer import (
    TUIEventConsumer,
    TUIStateManager,
)
from haven_tui.data.refresher import (
    DataRefresher,
    RefreshMode,
)
from haven_tui.data.download_tracker import (
    DownloadStatus,
    DownloadProgress,
    DownloadProgressTracker,
    YouTubeProgressAdapter,
    BitTorrentProgressAdapter,
    get_download_tracker,
    reset_download_tracker,
    format_bytes,
    format_duration,
)
from haven_tui.data.torrent_bridge import (
    BitTorrentProgressBridge,
)
from haven_tui.data.speed_aggregator import (
    SpeedAggregator,
    SpeedSample,
    SpeedAggregate,
)

__all__ = [
    "PipelineSnapshotRepository",
    "DownloadRepository",
    "JobHistoryRepository",
    "SpeedHistoryRepository",
    "AnalyticsRepository",
    "TUIEventConsumer",
    "TUIStateManager",
    "DataRefresher",
    "RefreshMode",
    "DownloadStatus",
    "DownloadProgress",
    "DownloadProgressTracker",
    "YouTubeProgressAdapter",
    "BitTorrentProgressAdapter",
    "BitTorrentProgressBridge",
    "get_download_tracker",
    "reset_download_tracker",
    "format_bytes",
    "format_duration",
    "SpeedAggregator",
    "SpeedSample",
    "SpeedAggregate",
]
