"""Tests for Haven TUI Configuration System.

This module tests the configuration loading, saving, validation,
and environment variable overrides.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from haven_tui.config import (
    AdvancedConfig,
    ColumnsConfig,
    DatabaseConfig,
    DisplayConfig,
    FiltersConfig,
    HavenTUIConfig,
    KeysConfig,
    clear_config_cache,
    get_config,
    get_default_config_path,
    set_config,
)


class TestDatabaseConfig:
    """Tests for DatabaseConfig."""
    
    def test_default_values(self):
        """Test default database configuration values."""
        config = DatabaseConfig()
        assert config.auto_discover is True
        assert "haven.db" in str(config.path)
    
    def test_path_expansion(self):
        """Test that paths are expanded correctly."""
        config = DatabaseConfig(path="~/test/haven.db")
        assert str(config.path).startswith(str(Path.home()))
        assert "~" not in str(config.path)
    
    def test_custom_values(self):
        """Test custom database configuration values."""
        config = DatabaseConfig(
            path=Path("/custom/path.db"),
            auto_discover=False,
        )
        assert str(config.path) == "/custom/path.db"
        assert config.auto_discover is False


class TestDisplayConfig:
    """Tests for DisplayConfig."""
    
    def test_default_values(self):
        """Test default display configuration values."""
        config = DisplayConfig()
        assert config.refresh_rate == 2.0
        assert config.theme == "default"
        assert config.show_speed_graphs is True
        assert config.graph_history_seconds == 60
    
    def test_custom_values(self):
        """Test custom display configuration values."""
        config = DisplayConfig(
            refresh_rate=5.0,
            theme="dark",
            show_speed_graphs=False,
            graph_history_seconds=120,
        )
        assert config.refresh_rate == 5.0
        assert config.theme == "dark"
        assert config.show_speed_graphs is False
        assert config.graph_history_seconds == 120


class TestColumnsConfig:
    """Tests for ColumnsConfig."""
    
    def test_default_values(self):
        """Test default columns configuration values."""
        config = ColumnsConfig()
        assert "title" in config.visible
        assert "stage" in config.visible
        assert "progress" in config.visible
        assert config.widths["title"] == 40
        assert config.widths["stage"] == 12
        assert config.widths["progress"] == 10
    
    def test_custom_values(self):
        """Test custom columns configuration values."""
        config = ColumnsConfig(
            visible=["title", "size"],
            widths={"title": 50, "size": 20},
        )
        assert config.visible == ["title", "size"]
        assert config.widths["title"] == 50
        assert config.widths["size"] == 20


class TestFiltersConfig:
    """Tests for FiltersConfig."""
    
    def test_default_values(self):
        """Test default filters configuration values."""
        config = FiltersConfig()
        assert config.show_completed is True
        assert config.show_failed is True
        assert config.plugin_filter == "all"
    
    def test_custom_values(self):
        """Test custom filters configuration values."""
        config = FiltersConfig(
            show_completed=True,
            show_failed=False,
            plugin_filter="youtube",
        )
        assert config.show_completed is True
        assert config.show_failed is False
        assert config.plugin_filter == "youtube"


class TestKeysConfig:
    """Tests for KeysConfig."""
    
    def test_default_values(self):
        """Test default key binding configuration values."""
        config = KeysConfig()
        assert config.quit == "q"
        assert config.refresh == "r"
        assert config.toggle_auto_refresh == "a"
        assert config.show_help == "?"
        assert config.toggle_graph_pane == "g"
        assert config.filter_completed == "h"
        assert config.view_details == "enter"
    
    def test_custom_values(self):
        """Test custom key binding configuration values."""
        config = KeysConfig(
            quit="esc",
            refresh="f5",
            show_help="f1",
        )
        assert config.quit == "esc"
        assert config.refresh == "f5"
        assert config.show_help == "f1"


class TestAdvancedConfig:
    """Tests for AdvancedConfig."""
    
    def test_default_values(self):
        """Test default advanced configuration values."""
        config = AdvancedConfig()
        assert config.max_videos_in_list == 1000
        assert config.event_buffer_size == 1000
        assert config.speed_calculation_window == 5
    
    def test_custom_values(self):
        """Test custom advanced configuration values."""
        config = AdvancedConfig(
            max_videos_in_list=500,
            event_buffer_size=2000,
            speed_calculation_window=10,
        )
        assert config.max_videos_in_list == 500
        assert config.event_buffer_size == 2000
        assert config.speed_calculation_window == 10


class TestHavenTUIConfig:
    """Tests for HavenTUIConfig main class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = HavenTUIConfig()
        assert isinstance(config.database, DatabaseConfig)
        assert isinstance(config.display, DisplayConfig)
        assert isinstance(config.columns, ColumnsConfig)
        assert isinstance(config.filters, FiltersConfig)
        assert isinstance(config.keys, KeysConfig)
        assert isinstance(config.advanced, AdvancedConfig)
    
    def test_config_path_expansion(self):
        """Test that config path is expanded correctly."""
        config = HavenTUIConfig(config_path="~/.config/test/config.toml")
        assert "~" not in str(config.config_path)
        assert str(config.config_path).startswith(str(Path.home()))


class TestConfigLoading:
    """Tests for configuration loading from TOML files."""
    
    def test_load_from_nonexistent_file_creates_default(self, tmp_path):
        """Test that loading from non-existent file creates default config."""
        config_path = tmp_path / "nonexistent" / "config.toml"
        config = HavenTUIConfig.load(config_path)
        
        assert isinstance(config, HavenTUIConfig)
        assert config_path.exists()  # Should create default
    
    def test_load_from_toml_file(self, tmp_path):
        """Test loading configuration from TOML file."""
        config_path = tmp_path / "config.toml"
        
        # Create a TOML config file
        toml_content = """
[database]
path = "/custom/db.sqlite"
auto_discover = false

[display]
refresh_rate = 5.0
theme = "dark"
show_speed_graphs = false
graph_history_seconds = 120

[filters]
show_completed = true
show_failed = false
plugin_filter = "youtube"

[advanced]
max_videos_in_list = 500
"""
        config_path.write_text(toml_content)
        
        config = HavenTUIConfig.load(config_path)
        
        assert str(config.database.path) == "/custom/db.sqlite"
        assert config.database.auto_discover is False
        assert config.display.refresh_rate == 5.0
        assert config.display.theme == "dark"
        assert config.display.show_speed_graphs is False
        assert config.display.graph_history_seconds == 120
        assert config.filters.show_completed is True
        assert config.filters.show_failed is False
        assert config.filters.plugin_filter == "youtube"
        assert config.advanced.max_videos_in_list == 500
    
    def test_load_keys_from_toml(self, tmp_path):
        """Test loading key bindings from TOML file."""
        config_path = tmp_path / "config.toml"
        
        toml_content = """
[keys]
quit = "esc"
refresh = "f5"
toggle_auto_refresh = "space"
show_help = "f1"
toggle_graph_pane = "tab"
filter_completed = "c"
view_details = "d"
"""
        config_path.write_text(toml_content)
        
        config = HavenTUIConfig.load(config_path)
        
        assert config.keys.quit == "esc"
        assert config.keys.refresh == "f5"
        assert config.keys.toggle_auto_refresh == "space"
        assert config.keys.show_help == "f1"
        assert config.keys.toggle_graph_pane == "tab"
        assert config.keys.filter_completed == "c"
        assert config.keys.view_details == "d"
    
    def test_load_columns_from_toml(self, tmp_path):
        """Test loading columns configuration from TOML file."""
        config_path = tmp_path / "config.toml"
        
        toml_content = """
[columns]
visible = ["title", "progress", "speed"]

[columns.widths]
title = 50
progress = 15
speed = 12
"""
        config_path.write_text(toml_content)
        
        config = HavenTUIConfig.load(config_path)
        
        assert config.columns.visible == ["title", "progress", "speed"]
        assert config.columns.widths["title"] == 50
        assert config.columns.widths["progress"] == 15
        assert config.columns.widths["speed"] == 12


class TestConfigSaving:
    """Tests for configuration saving to TOML files."""
    
    def test_save_creates_file(self, tmp_path):
        """Test that save creates the config file."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig(config_path=config_path)
        
        config.save()
        
        assert config_path.exists()
        content = config_path.read_text()
        assert "[database]" in content
        assert "[display]" in content
        assert "[filters]" in content
    
    def test_save_and_reload(self, tmp_path):
        """Test that saved config can be reloaded correctly."""
        config_path = tmp_path / "config.toml"
        
        # Create and customize config
        config1 = HavenTUIConfig(config_path=config_path)
        config1.display.theme = "dark"
        config1.display.refresh_rate = 3.5
        config1.filters.show_completed = True
        config1.keys.quit = "esc"
        
        config1.save()
        
        # Reload and verify
        config2 = HavenTUIConfig.load(config_path)
        assert config2.display.theme == "dark"
        assert config2.display.refresh_rate == 3.5
        assert config2.filters.show_completed is True
        assert config2.keys.quit == "esc"
    
    def test_save_creates_directory(self, tmp_path):
        """Test that save creates parent directories if needed."""
        config_path = tmp_path / "nested" / "deep" / "config.toml"
        config = HavenTUIConfig(config_path=config_path)
        
        config.save()
        
        assert config_path.exists()


class TestEnvironmentVariables:
    """Tests for environment variable configuration overrides."""
    
    def test_database_env_vars(self, tmp_path, monkeypatch):
        """Test database environment variable overrides."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig.load(config_path)
        
        # Set environment variables
        monkeypatch.setenv("HAVEN_TUI_DATABASE_PATH", "/env/db.sqlite")
        monkeypatch.setenv("HAVEN_TUI_DATABASE_AUTO_DISCOVER", "false")
        
        config._load_from_env()
        
        assert str(config.database.path) == "/env/db.sqlite"
        assert config.database.auto_discover is False
    
    def test_display_env_vars(self, tmp_path, monkeypatch):
        """Test display environment variable overrides."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig.load(config_path)
        
        monkeypatch.setenv("HAVEN_TUI_DISPLAY_REFRESH_RATE", "3.5")
        monkeypatch.setenv("HAVEN_TUI_DISPLAY_THEME", "light")
        monkeypatch.setenv("HAVEN_TUI_DISPLAY_SHOW_SPEED_GRAPHS", "false")
        monkeypatch.setenv("HAVEN_TUI_DISPLAY_GRAPH_HISTORY_SECONDS", "180")
        
        config._load_from_env()
        
        assert config.display.refresh_rate == 3.5
        assert config.display.theme == "light"
        assert config.display.show_speed_graphs is False
        assert config.display.graph_history_seconds == 180
    
    def test_filters_env_vars(self, tmp_path, monkeypatch):
        """Test filters environment variable overrides."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig.load(config_path)
        
        monkeypatch.setenv("HAVEN_TUI_FILTERS_SHOW_COMPLETED", "true")
        monkeypatch.setenv("HAVEN_TUI_FILTERS_SHOW_FAILED", "false")
        monkeypatch.setenv("HAVEN_TUI_FILTERS_PLUGIN_FILTER", "bittorrent")
        
        config._load_from_env()
        
        assert config.filters.show_completed is True
        assert config.filters.show_failed is False
        assert config.filters.plugin_filter == "bittorrent"
    
    def test_advanced_env_vars(self, tmp_path, monkeypatch):
        """Test advanced environment variable overrides."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig.load(config_path)
        
        monkeypatch.setenv("HAVEN_TUI_ADVANCED_MAX_VIDEOS_IN_LIST", "500")
        monkeypatch.setenv("HAVEN_TUI_ADVANCED_EVENT_BUFFER_SIZE", "2000")
        monkeypatch.setenv("HAVEN_TUI_ADVANCED_SPEED_CALCULATION_WINDOW", "10")
        
        config._load_from_env()
        
        assert config.advanced.max_videos_in_list == 500
        assert config.advanced.event_buffer_size == 2000
        assert config.advanced.speed_calculation_window == 10
    
    def test_env_var_override_precedence(self, tmp_path, monkeypatch):
        """Test that environment variables override file config."""
        config_path = tmp_path / "config.toml"
        
        # Create config file
        toml_content = """
[display]
theme = "dark"
refresh_rate = 2.0
"""
        config_path.write_text(toml_content)
        
        # Set env var
        monkeypatch.setenv("HAVEN_TUI_DISPLAY_THEME", "light")
        
        config = HavenTUIConfig.load(config_path)
        
        # Env var should override file
        assert config.display.theme == "light"
        # File value should remain
        assert config.display.refresh_rate == 2.0
    
    def test_boolean_env_var_variations(self, tmp_path, monkeypatch):
        """Test various boolean environment variable formats."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig(config_path=config_path)
        
        # Test "true", "1", "yes"
        for val in ["true", "1", "yes", "True", "YES"]:
            monkeypatch.setenv("HAVEN_TUI_FILTERS_SHOW_COMPLETED", val)
            config._load_from_env()
            assert config.filters.show_completed is True, f"Failed for value: {val}"
        
        # Test "false", "0", "no"
        for val in ["false", "0", "no", "False", "NO"]:
            monkeypatch.setenv("HAVEN_TUI_FILTERS_SHOW_COMPLETED", val)
            config._load_from_env()
            assert config.filters.show_completed is False, f"Failed for value: {val}"


class TestConfigDictConversion:
    """Tests for configuration to/from dictionary conversion."""
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = HavenTUIConfig()
        config.display.theme = "dark"
        
        d = config.to_dict()
        
        assert "database" in d
        assert "display" in d
        assert "columns" in d
        assert "filters" in d
        assert "keys" in d
        assert "advanced" in d
        
        assert d["display"]["theme"] == "dark"
        assert d["database"]["auto_discover"] is True
    
    def test_dict_contains_all_sections(self):
        """Test that to_dict includes all configuration sections."""
        config = HavenTUIConfig()
        d = config.to_dict()
        
        # Check all expected sections exist
        expected_sections = ["database", "display", "columns", "filters", "keys", "advanced"]
        for section in expected_sections:
            assert section in d, f"Missing section: {section}"


class TestGlobalConfig:
    """Tests for global configuration singleton functions."""
    
    def test_get_config_creates_instance(self, tmp_path, monkeypatch):
        """Test that get_config creates a global instance."""
        # Clear any existing config
        clear_config_cache()
        
        # Use a temp config path
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(
            "haven_tui.config.DEFAULT_CONFIG_PATH",
            config_path
        )
        
        config = get_config()
        assert isinstance(config, HavenTUIConfig)
        
        # Second call should return same instance
        config2 = get_config()
        assert config is config2
    
    def test_set_config(self):
        """Test setting global configuration."""
        clear_config_cache()
        
        config = HavenTUIConfig()
        config.display.theme = "dark"
        
        set_config(config)
        
        retrieved = get_config()
        assert retrieved is config
        assert retrieved.display.theme == "dark"
    
    def test_clear_config_cache(self):
        """Test clearing global configuration cache."""
        # Set up a config
        config = HavenTUIConfig()
        set_config(config)
        
        # Clear cache
        clear_config_cache()
        
        # get_config should create new instance
        # (but since we're using default path, it might load existing)
        # We just verify no error occurs
        config2 = get_config()
        assert isinstance(config2, HavenTUIConfig)


class TestDefaultConfigPath:
    """Tests for default config path function."""
    
    def test_default_path(self):
        """Test default config path function."""
        path = get_default_config_path()
        assert "haven-tui" in str(path)
        assert str(path).endswith("config.toml")
    
    def test_xdg_config_home(self, monkeypatch):
        """Test XDG_CONFIG_HOME environment variable."""
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
        path = get_default_config_path()
        assert "/custom/config/haven-tui/config.toml" in str(path)


class TestConfigReset:
    """Tests for configuration reset functionality."""
    
    def test_reset_to_defaults(self):
        """Test resetting configuration to defaults."""
        config = HavenTUIConfig()
        
        # Modify values
        config.display.theme = "dark"
        config.display.refresh_rate = 5.0
        config.filters.show_completed = True
        
        # Reset
        config.reset_to_defaults()
        
        # Verify defaults restored
        assert config.display.theme == "default"
        assert config.display.refresh_rate == 2.0
        assert config.filters.show_completed is True
