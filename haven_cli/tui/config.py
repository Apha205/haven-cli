"""TUI configuration management.

This module handles configuration specific to the TUI component,
separate from the main CLI configuration.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import tomli


@dataclass
class TUIConfig:
    """Configuration for the Haven TUI.
    
    Attributes:
        refresh_interval: UI refresh interval in seconds.
        max_history_points: Maximum number of data points to keep for charts.
        theme: UI theme name (dark, light).
        show_completed: Whether to show completed videos by default.
        auto_scroll: Whether to auto-scroll to active videos.
        log_level: Logging level for TUI messages.
        database_url: Optional override for database URL.
    """
    
    refresh_interval: float = 1.0
    max_history_points: int = 100
    theme: str = "dark"
    show_completed: bool = True
    auto_scroll: bool = True
    log_level: str = "INFO"
    database_url: Optional[str] = None
    
    # UI customization
    show_speed_graphs: bool = True
    show_progress_bars: bool = True
    compact_mode: bool = False
    
    # Keyboard shortcuts
    keybindings: dict[str, str] = field(default_factory=lambda: {
        "quit": "q",
        "refresh": "r",
        "help": "?",
        "toggle_completed": "c",
        "details": "d",
        "logs": "l",
    })
    
    def load_from_file(self, path: Path) -> None:
        """Load configuration from a TOML file.
        
        Args:
            path: Path to the configuration file.
            
        Example:
            config = TUIConfig()
            config.load_from_file(Path("~/.config/haven/tui.toml"))
        """
        if not path.exists():
            return
        
        try:
            with open(path, "rb") as f:
                data = tomli.load(f)
            
            # Update config from file
            tui_section = data.get("tui", {})
            for key, value in tui_section.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                    
        except Exception as e:
            # Log error but continue with defaults
            print(f"Warning: Could not load config from {path}: {e}")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration.
        """
        return {
            "refresh_interval": self.refresh_interval,
            "max_history_points": self.max_history_points,
            "theme": self.theme,
            "show_completed": self.show_completed,
            "auto_scroll": self.auto_scroll,
            "log_level": self.log_level,
            "database_url": self.database_url,
            "show_speed_graphs": self.show_speed_graphs,
            "show_progress_bars": self.show_progress_bars,
            "compact_mode": self.compact_mode,
            "keybindings": self.keybindings,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TUIConfig":
        """Create configuration from dictionary.
        
        Args:
            data: Dictionary containing configuration values.
            
        Returns:
            New TUIConfig instance.
        """
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


def get_default_config_path() -> Path:
    """Get the default configuration file path.
    
    Returns:
        Path to the default configuration file.
        
    The path is determined in the following order:
    1. $XDG_CONFIG_HOME/haven/tui.toml
    2. ~/.config/haven/tui.toml
    """
    xdg_config = Path.home() / ".config"
    if "XDG_CONFIG_HOME" in __import__("os").environ:
        xdg_config = Path(__import__("os").environ["XDG_CONFIG_HOME"])
    
    return xdg_config / "haven" / "tui.toml"
