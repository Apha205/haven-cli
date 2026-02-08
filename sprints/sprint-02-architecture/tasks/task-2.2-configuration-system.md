# Task 2.2: Configuration System

**Priority:** Critical
**Estimated Effort:** 2 days

**Description:**
Create a configuration system for haven-tui, inspired by aria2tui's config but tailored for pipeline visualization.

**Configuration Schema:**
```toml
# ~/.config/haven-tui/config.toml

[database]
# SQLite database path (from haven-cli)
path = "~/.local/share/haven/haven.db"
# Or use haven-cli config discovery
auto_discover = true

[display]
# TUI appearance
refresh_rate = 2.0           # Seconds between refresh
theme = "default"            # Color theme
show_speed_graphs = true     # Show speed history graphs
graph_history_seconds = 60   # How much history to show

[columns]
# Which columns to display in video list
visible = [
    "title",
    "stage",
    "progress",
    "speed",
    "plugin",
    "size"
]
widths = { title = 40, stage = 12, progress = 10 }

[filters]
# Default filters
show_completed = false       # Hide completed videos by default
show_failed = true           # Show failed videos
plugin_filter = "all"        # Filter by plugin: "all", "youtube", "bittorrent"

[keys]
# Key bindings (vim-style by default)
quit = "q"
refresh = "r"
toggle_auto_refresh = "a"
show_help = "?"
toggle_graph_pane = "g"
filter_completed = "h"
view_details = "enter"

[advanced]
# Performance tuning
max_videos_in_list = 1000    # Limit for large databases
event_buffer_size = 1000     # Event ring buffer size
speed_calculation_window = 5 # Seconds for speed averaging
```

**Implementation:**
```python
# src/haven_tui/config.py
from pydantic import BaseSettings, Field
from pathlib import Path

class HavenTUIConfig(BaseSettings):
    """Haven TUI configuration."""
    
    database_path: Path = Field(default=Path("~/.local/share/haven/haven.db"))
    auto_discover_db: bool = True
    refresh_rate: float = 2.0
    theme: str = "default"
    show_speed_graphs: bool = True
    graph_history_seconds: int = 60
    max_videos_in_list: int = 1000
    
    class Config:
        env_prefix = "HAVEN_TUI_"
        config_file = "~/.config/haven-tui/config.toml"
    
    @classmethod
    def load(cls) -> "HavenTUIConfig":
        """Load config from file or create default."""
        config_path = Path(cls.Config.config_file).expanduser()
        if config_path.exists():
            return cls._from_toml(config_path)
        return cls._create_default(config_path)
```

**Acceptance Criteria:**
- [ ] Config loads from TOML file
- [ ] Environment variable overrides work
- [ ] Default config created on first run
- [ ] Form-based config editor (like aria2tui)
