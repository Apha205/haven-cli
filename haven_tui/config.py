"""Haven TUI Configuration System.

This module provides a comprehensive configuration system for Haven TUI,
inspired by aria2tui's config but tailored for pipeline visualization.

Configuration is loaded from:
1. Default values (lowest priority)
2. TOML config file (~/.config/haven-tui/config.toml)
3. Environment variables (highest priority)

Example:
    >>> from haven_tui.config import HavenTUIConfig
    >>> config = HavenTUIConfig.load()
    >>> print(config.display.refresh_rate)
    2.0
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# Try to import tomllib (Python 3.11+) or tomli as fallback
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

# Try to import tomli_w for writing TOML
try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore


# Default configuration paths
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "haven-tui"
DEFAULT_CONFIG_FILE = "config.toml"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / DEFAULT_CONFIG_FILE
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "haven"


@dataclass
class DatabaseConfig:
    """Database configuration for Haven TUI.
    
    Attributes:
        path: Path to the SQLite database file.
        auto_discover: Whether to auto-discover database from haven-cli config.
    """
    
    path: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "haven.db")
    auto_discover: bool = True
    
    def __post_init__(self) -> None:
        """Expand user home directory in path."""
        if isinstance(self.path, str):
            self.path = Path(self.path).expanduser()
        else:
            self.path = self.path.expanduser()


@dataclass
class DisplayConfig:
    """Display/TUI appearance configuration.
    
    Attributes:
        refresh_rate: Seconds between UI refresh.
        theme: Color theme name (default, dark, light).
        show_speed_graphs: Whether to show speed history graphs.
        graph_history_seconds: How much history to show in graphs.
    """
    
    refresh_rate: float = 2.0
    theme: str = "default"
    show_speed_graphs: bool = True
    graph_history_seconds: int = 60


@dataclass
class ColumnsConfig:
    """Column display configuration for the video list.
    
    Attributes:
        visible: List of visible column names.
        widths: Dictionary mapping column names to their widths.
    """
    
    visible: list[str] = field(default_factory=lambda: [
        "title",
        "stage",
        "progress",
        "speed",
        "plugin",
        "size",
    ])
    widths: dict[str, int] = field(default_factory=lambda: {
        "title": 40,
        "stage": 12,
        "progress": 10,
    })


@dataclass
class FiltersConfig:
    """Default filter configuration.
    
    Attributes:
        show_completed: Whether to show completed videos by default.
        show_failed: Whether to show failed videos.
        plugin_filter: Filter by plugin ("all", "youtube", "bittorrent", etc.).
    """
    
    show_completed: bool = False
    show_failed: bool = True
    plugin_filter: str = "all"


@dataclass
class KeysConfig:
    """Key bindings configuration (vim-style by default).
    
    Attributes:
        quit: Key to quit the application.
        refresh: Key to manually refresh the display.
        toggle_auto_refresh: Key to toggle auto-refresh.
        show_help: Key to show help.
        toggle_graph_pane: Key to toggle graph pane visibility.
        filter_completed: Key to toggle completed videos filter.
        view_details: Key to view video details.
    """
    
    quit: str = "q"
    refresh: str = "r"
    toggle_auto_refresh: str = "a"
    show_help: str = "?"
    toggle_graph_pane: str = "g"
    filter_completed: str = "h"
    view_details: str = "enter"


@dataclass
class AdvancedConfig:
    """Advanced/performance tuning configuration.
    
    Attributes:
        max_videos_in_list: Maximum number of videos to display in list.
        event_buffer_size: Size of the event ring buffer.
        speed_calculation_window: Seconds for speed averaging window.
    """
    
    max_videos_in_list: int = 1000
    event_buffer_size: int = 1000
    speed_calculation_window: int = 5


@dataclass
class HavenTUIConfig:
    """Main configuration container for Haven TUI.
    
    This class holds all configuration sections and provides methods for
    loading, saving, and managing the configuration.
    
    Example:
        >>> config = HavenTUIConfig.load()
        >>> print(config.database.path)
        >>> print(config.display.theme)
        >>> config.display.theme = "dark"
        >>> config.save()
    
    Attributes:
        database: Database configuration section.
        display: Display/appearance configuration section.
        columns: Column display configuration section.
        filters: Filter configuration section.
        keys: Key bindings configuration section.
        advanced: Advanced settings configuration section.
        config_path: Path to the configuration file.
    """
    
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    columns: ColumnsConfig = field(default_factory=ColumnsConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    keys: KeysConfig = field(default_factory=KeysConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    config_path: Path = field(default_factory=lambda: DEFAULT_CONFIG_PATH)
    
    def __post_init__(self) -> None:
        """Ensure config_path is a Path object."""
        if isinstance(self.config_path, str):
            self.config_path = Path(self.config_path).expanduser()
        else:
            self.config_path = self.config_path.expanduser()
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "HavenTUIConfig":
        """Load configuration from file or create default.
        
        This method loads configuration from a TOML file if it exists,
        otherwise creates a default configuration and saves it.
        
        Environment variables can override config file values.
        Format: HAVEN_TUI_<SECTION>_<KEY> (e.g., HAVEN_TUI_DISPLAY_THEME)
        
        Args:
            config_path: Path to config file. Defaults to ~/.config/haven-tui/config.toml
            
        Returns:
            Loaded or default configuration.
            
        Example:
            >>> config = HavenTUIConfig.load()
            >>> config = HavenTUIConfig.load(Path("/custom/path/config.toml"))
        """
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH
        else:
            config_path = config_path.expanduser()
        
        # Check if config file exists
        if config_path.exists() and tomllib is not None:
            config = cls._from_toml(config_path)
        else:
            # Create default config and save it
            config = cls(config_path=config_path)
            config._create_default(config_path)
        
        # Apply environment variable overrides
        config._load_from_env()
        
        return config
    
    @classmethod
    def _from_toml(cls, path: Path) -> "HavenTUIConfig":
        """Load configuration from a TOML file.
        
        Args:
            path: Path to the TOML file.
            
        Returns:
            Loaded configuration.
        """
        config = cls(config_path=path)
        
        if tomllib is None:
            return config
        
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            
            # Load database section
            if "database" in data:
                db_data = data["database"]
                if "path" in db_data:
                    config.database.path = Path(db_data["path"]).expanduser()
                if "auto_discover" in db_data:
                    config.database.auto_discover = db_data["auto_discover"]
            
            # Load display section
            if "display" in data:
                disp_data = data["display"]
                if "refresh_rate" in disp_data:
                    config.display.refresh_rate = float(disp_data["refresh_rate"])
                if "theme" in disp_data:
                    config.display.theme = disp_data["theme"]
                if "show_speed_graphs" in disp_data:
                    config.display.show_speed_graphs = disp_data["show_speed_graphs"]
                if "graph_history_seconds" in disp_data:
                    config.display.graph_history_seconds = int(disp_data["graph_history_seconds"])
            
            # Load columns section
            if "columns" in data:
                col_data = data["columns"]
                if "visible" in col_data:
                    config.columns.visible = list(col_data["visible"])
                if "widths" in col_data:
                    config.columns.widths = dict(col_data["widths"])
            
            # Load filters section
            if "filters" in data:
                filt_data = data["filters"]
                if "show_completed" in filt_data:
                    config.filters.show_completed = filt_data["show_completed"]
                if "show_failed" in filt_data:
                    config.filters.show_failed = filt_data["show_failed"]
                if "plugin_filter" in filt_data:
                    config.filters.plugin_filter = filt_data["plugin_filter"]
            
            # Load keys section
            if "keys" in data:
                keys_data = data["keys"]
                if "quit" in keys_data:
                    config.keys.quit = keys_data["quit"]
                if "refresh" in keys_data:
                    config.keys.refresh = keys_data["refresh"]
                if "toggle_auto_refresh" in keys_data:
                    config.keys.toggle_auto_refresh = keys_data["toggle_auto_refresh"]
                if "show_help" in keys_data:
                    config.keys.show_help = keys_data["show_help"]
                if "toggle_graph_pane" in keys_data:
                    config.keys.toggle_graph_pane = keys_data["toggle_graph_pane"]
                if "filter_completed" in keys_data:
                    config.keys.filter_completed = keys_data["filter_completed"]
                if "view_details" in keys_data:
                    config.keys.view_details = keys_data["view_details"]
            
            # Load advanced section
            if "advanced" in data:
                adv_data = data["advanced"]
                if "max_videos_in_list" in adv_data:
                    config.advanced.max_videos_in_list = int(adv_data["max_videos_in_list"])
                if "event_buffer_size" in adv_data:
                    config.advanced.event_buffer_size = int(adv_data["event_buffer_size"])
                if "speed_calculation_window" in adv_data:
                    config.advanced.speed_calculation_window = int(adv_data["speed_calculation_window"])
            
        except Exception as e:
            # Log warning and return default config
            print(f"Warning: Failed to load config from {path}: {e}")
        
        return config
    
    def _load_from_env(self) -> None:
        """Load configuration overrides from environment variables.
        
        Environment variable format: HAVEN_TUI_<SECTION>_<KEY>
        
        Examples:
            HAVEN_TUI_DATABASE_PATH
            HAVEN_TUI_DISPLAY_THEME
            HAVEN_TUI_DISPLAY_REFRESH_RATE
        """
        prefix = "HAVEN_TUI_"
        
        # Database overrides
        if env_val := os.environ.get(f"{prefix}DATABASE_PATH"):
            self.database.path = Path(env_val).expanduser()
        if env_val := os.environ.get(f"{prefix}DATABASE_AUTO_DISCOVER"):
            self.database.auto_discover = env_val.lower() in ("true", "1", "yes")
        
        # Display overrides
        if env_val := os.environ.get(f"{prefix}DISPLAY_REFRESH_RATE"):
            try:
                self.display.refresh_rate = float(env_val)
            except ValueError:
                pass
        if env_val := os.environ.get(f"{prefix}DISPLAY_THEME"):
            self.display.theme = env_val
        if env_val := os.environ.get(f"{prefix}DISPLAY_SHOW_SPEED_GRAPHS"):
            self.display.show_speed_graphs = env_val.lower() in ("true", "1", "yes")
        if env_val := os.environ.get(f"{prefix}DISPLAY_GRAPH_HISTORY_SECONDS"):
            try:
                self.display.graph_history_seconds = int(env_val)
            except ValueError:
                pass
        
        # Filters overrides
        if env_val := os.environ.get(f"{prefix}FILTERS_SHOW_COMPLETED"):
            self.filters.show_completed = env_val.lower() in ("true", "1", "yes")
        if env_val := os.environ.get(f"{prefix}FILTERS_SHOW_FAILED"):
            self.filters.show_failed = env_val.lower() in ("true", "1", "yes")
        if env_val := os.environ.get(f"{prefix}FILTERS_PLUGIN_FILTER"):
            self.filters.plugin_filter = env_val
        
        # Advanced overrides
        if env_val := os.environ.get(f"{prefix}ADVANCED_MAX_VIDEOS_IN_LIST"):
            try:
                self.advanced.max_videos_in_list = int(env_val)
            except ValueError:
                pass
        if env_val := os.environ.get(f"{prefix}ADVANCED_EVENT_BUFFER_SIZE"):
            try:
                self.advanced.event_buffer_size = int(env_val)
            except ValueError:
                pass
        if env_val := os.environ.get(f"{prefix}ADVANCED_SPEED_CALCULATION_WINDOW"):
            try:
                self.advanced.speed_calculation_window = int(env_val)
            except ValueError:
                pass
    
    def _create_default(self, path: Path) -> None:
        """Create default configuration file.
        
        Args:
            path: Path where the default config should be saved.
        """
        self.save(path)
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to a TOML file.
        
        Args:
            path: Path to save to. Defaults to self.config_path.
        """
        if path is None:
            path = self.config_path
        else:
            path = path.expanduser()
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build TOML content manually for better control
        lines = [
            "# Haven TUI Configuration",
            "# This is the configuration file for Haven TUI (Terminal User Interface)",
            "# For more information, see: https://github.com/haven/haven-cli",
            "",
            "[database]",
            f'path = "{self.database.path}"',
            f"auto_discover = {str(self.database.auto_discover).lower()}",
            "",
            "[display]",
            f"refresh_rate = {self.display.refresh_rate}",
            f'theme = "{self.display.theme}"',
            f"show_speed_graphs = {str(self.display.show_speed_graphs).lower()}",
            f"graph_history_seconds = {self.display.graph_history_seconds}",
            "",
            "[columns]",
            f"visible = {self.columns.visible}",
            "",
            "[columns.widths]",
        ]
        
        for key, value in self.columns.widths.items():
            lines.append(f"{key} = {value}")
        
        lines.extend([
            "",
            "[filters]",
            f"show_completed = {str(self.filters.show_completed).lower()}",
            f"show_failed = {str(self.filters.show_failed).lower()}",
            f'plugin_filter = "{self.filters.plugin_filter}"',
            "",
            "[keys]",
            f'quit = "{self.keys.quit}"',
            f'refresh = "{self.keys.refresh}"',
            f'toggle_auto_refresh = "{self.keys.toggle_auto_refresh}"',
            f'show_help = "{self.keys.show_help}"',
            f'toggle_graph_pane = "{self.keys.toggle_graph_pane}"',
            f'filter_completed = "{self.keys.filter_completed}"',
            f'view_details = "{self.keys.view_details}"',
            "",
            "[advanced]",
            f"max_videos_in_list = {self.advanced.max_videos_in_list}",
            f"event_buffer_size = {self.advanced.event_buffer_size}",
            f"speed_calculation_window = {self.advanced.speed_calculation_window}",
        ])
        
        with open(path, "w") as f:
            f.write("\n".join(lines))
    
    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration.
        """
        return {
            "database": {
                "path": str(self.database.path),
                "auto_discover": self.database.auto_discover,
            },
            "display": {
                "refresh_rate": self.display.refresh_rate,
                "theme": self.display.theme,
                "show_speed_graphs": self.display.show_speed_graphs,
                "graph_history_seconds": self.display.graph_history_seconds,
            },
            "columns": {
                "visible": self.columns.visible,
                "widths": self.columns.widths,
            },
            "filters": {
                "show_completed": self.filters.show_completed,
                "show_failed": self.filters.show_failed,
                "plugin_filter": self.filters.plugin_filter,
            },
            "keys": {
                "quit": self.keys.quit,
                "refresh": self.keys.refresh,
                "toggle_auto_refresh": self.keys.toggle_auto_refresh,
                "show_help": self.keys.show_help,
                "toggle_graph_pane": self.keys.toggle_graph_pane,
                "filter_completed": self.keys.filter_completed,
                "view_details": self.keys.view_details,
            },
            "advanced": {
                "max_videos_in_list": self.advanced.max_videos_in_list,
                "event_buffer_size": self.advanced.event_buffer_size,
                "speed_calculation_window": self.advanced.speed_calculation_window,
            },
        }
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to default values."""
        self.database = DatabaseConfig()
        self.display = DisplayConfig()
        self.columns = ColumnsConfig()
        self.filters = FiltersConfig()
        self.keys = KeysConfig()
        self.advanced = AdvancedConfig()


# Global configuration instance (lazy-loaded)
_global_config: Optional[HavenTUIConfig] = None


def get_config() -> HavenTUIConfig:
    """Get the global configuration instance.
    
    This function provides a singleton-like access to the configuration,
    loading it on first call.
    
    Returns:
        The global HavenTUIConfig instance.
        
    Example:
        >>> from haven_tui.config import get_config
        >>> config = get_config()
        >>> print(config.display.theme)
    """
    global _global_config
    if _global_config is None:
        _global_config = HavenTUIConfig.load()
    return _global_config


def set_config(config: HavenTUIConfig) -> None:
    """Set the global configuration instance.
    
    Args:
        config: The configuration to set as global.
    """
    global _global_config
    _global_config = config


def clear_config_cache() -> None:
    """Clear the global configuration cache.
    
    This forces the next call to get_config() to reload the configuration.
    """
    global _global_config
    _global_config = None


def get_default_config_path() -> Path:
    """Get the default configuration file path.
    
    Returns:
        Path to the default configuration file.
        
    The path is determined in the following order:
    1. $XDG_CONFIG_HOME/haven-tui/config.toml
    2. ~/.config/haven-tui/config.toml
    """
    xdg_config = Path.home() / ".config"
    if "XDG_CONFIG_HOME" in os.environ:
        xdg_config = Path(os.environ["XDG_CONFIG_HOME"])
    
    return xdg_config / "haven-tui" / "config.toml"
