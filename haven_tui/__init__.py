"""Haven TUI - Terminal User Interface for Haven Video Pipeline."""

__version__ = "0.1.0"

# Core components
from .core.pipeline_interface import PipelineInterface
from .core.state_manager import StateManager, VideoState
from .core.metrics import MetricsCollector

# Configuration
from .config import (
    HavenTUIConfig,
    DatabaseConfig,
    DisplayConfig,
    ColumnsConfig,
    FiltersConfig,
    KeysConfig,
    AdvancedConfig,
    get_config,
    set_config,
    clear_config_cache,
    get_default_config_path,
)
from .config_editor import ConfigEditor, ConfigField, create_default_editor

# UI Components
from .ui.views.video_list import VideoListView, VideoListScreen

__all__ = [
    # Core components
    "PipelineInterface",
    "StateManager",
    "VideoState",
    "MetricsCollector",
    # Configuration
    "HavenTUIConfig",
    "DatabaseConfig",
    "DisplayConfig",
    "ColumnsConfig",
    "FiltersConfig",
    "KeysConfig",
    "AdvancedConfig",
    "get_config",
    "set_config",
    "clear_config_cache",
    "get_default_config_path",
    # Config Editor
    "ConfigEditor",
    "ConfigField",
    "create_default_editor",
    # UI Components
    "VideoListView",
    "VideoListScreen",
]
