"""Form-based configuration editor for Haven TUI.

This module provides a TUI form interface for editing Haven TUI configuration,
inspired by aria2tui's config editor. It allows users to modify configuration
values through an interactive text-based interface.

Example:
    >>> from haven_tui.config_editor import ConfigEditor
    >>> from haven_tui.config import HavenTUIConfig
    >>> config = HavenTUIConfig.load()
    >>> editor = ConfigEditor(config)
    >>> # Run within a textual app
    >>> await editor.edit_async()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


@dataclass
class ConfigField:
    """Represents a single configuration field in the editor.
    
    Attributes:
        name: Internal field name (e.g., "display.theme").
        label: Display label for the field (e.g., "Theme").
        value: Current value of the field.
        default: Default value for the field.
        field_type: Type of field (str, int, float, bool, choice, path).
        help_text: Help text describing the field.
        choices: Available choices for choice fields.
        min_value: Minimum value for numeric fields.
        max_value: Maximum value for numeric fields.
        section: Configuration section this field belongs to.
        key: Configuration key within the section.
    """
    
    name: str
    label: str
    value: Any
    default: Any = None
    field_type: str = "str"  # str, int, float, bool, choice, path
    help_text: str = ""
    choices: List[str] = field(default_factory=list)
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    section: str = ""
    key: str = ""
    
    def validate(self, new_value: Any) -> Tuple[bool, str]:
        """Validate a new value for this field.
        
        Args:
            new_value: The value to validate.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        try:
            if self.field_type == "int":
                val = int(new_value)
                if self.min_value is not None and val < self.min_value:
                    return False, f"Value must be >= {self.min_value}"
                if self.max_value is not None and val > self.max_value:
                    return False, f"Value must be <= {self.max_value}"
            elif self.field_type == "float":
                val = float(new_value)
                if self.min_value is not None and val < self.min_value:
                    return False, f"Value must be >= {self.min_value}"
                if self.max_value is not None and val > self.max_value:
                    return False, f"Value must be <= {self.max_value}"
            elif self.field_type == "bool":
                if isinstance(new_value, str):
                    if new_value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                        return False, "Value must be true/false, yes/no, or 1/0"
            elif self.field_type == "choice":
                if new_value not in self.choices:
                    return False, f"Value must be one of: {', '.join(self.choices)}"
            elif self.field_type == "path":
                # Basic path validation - just ensure it's a string
                if not isinstance(new_value, (str, Path)):
                    return False, "Value must be a valid path"
            return True, ""
        except (ValueError, TypeError) as e:
            return False, f"Invalid value: {e}"
    
    def parse_value(self, value: Any) -> Any:
        """Parse a value according to field type.
        
        Args:
            value: The value to parse.
            
        Returns:
            Parsed value of the correct type.
        """
        if self.field_type == "int":
            return int(value)
        elif self.field_type == "float":
            return float(value)
        elif self.field_type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        elif self.field_type == "path":
            return Path(value).expanduser()
        return value


class ConfigEditor:
    """Form-based configuration editor for Haven TUI.
    
    This class provides methods to create and manage configuration forms,
    allowing users to edit configuration values interactively.
    
    Example:
        >>> from haven_tui.config import HavenTUIConfig
        >>> from haven_tui.config_editor import ConfigEditor
        >>> config = HavenTUIConfig.load()
        >>> editor = ConfigEditor(config)
        >>> # In a textual app:
        >>> form = editor.create_form()
    
    Attributes:
        config: The configuration being edited.
        fields: List of ConfigField objects for the form.
        on_save: Optional callback when configuration is saved.
        on_cancel: Optional callback when editing is cancelled.
    """
    
    # Field definitions for the configuration editor
    FIELD_DEFINITIONS: List[Dict[str, Any]] = [
        # Database section
        {
            "name": "database.path",
            "label": "Database Path",
            "section": "database",
            "key": "path",
            "type": "path",
            "help_text": "Path to the SQLite database file",
        },
        {
            "name": "database.auto_discover",
            "label": "Auto-discover Database",
            "section": "database",
            "key": "auto_discover",
            "type": "bool",
            "help_text": "Automatically discover database from haven-cli config",
        },
        # Display section
        {
            "name": "display.refresh_rate",
            "label": "Refresh Rate (seconds)",
            "section": "display",
            "key": "refresh_rate",
            "type": "float",
            "min": 0.1,
            "max": 60.0,
            "help_text": "Seconds between UI refresh cycles",
        },
        {
            "name": "display.theme",
            "label": "Theme",
            "section": "display",
            "key": "theme",
            "type": "choice",
            "choices": ["default", "dark", "light"],
            "help_text": "Color theme for the TUI",
        },
        {
            "name": "display.show_speed_graphs",
            "label": "Show Speed Graphs",
            "section": "display",
            "key": "show_speed_graphs",
            "type": "bool",
            "help_text": "Display speed history graphs",
        },
        {
            "name": "display.graph_history_seconds",
            "label": "Graph History (seconds)",
            "section": "display",
            "key": "graph_history_seconds",
            "type": "int",
            "min": 10,
            "max": 3600,
            "help_text": "How much history to show in graphs",
        },
        # Filters section
        {
            "name": "filters.show_completed",
            "label": "Show Completed Videos",
            "section": "filters",
            "key": "show_completed",
            "type": "bool",
            "help_text": "Show completed videos in the list by default",
        },
        {
            "name": "filters.show_failed",
            "label": "Show Failed Videos",
            "section": "filters",
            "key": "show_failed",
            "type": "bool",
            "help_text": "Show failed videos in the list",
        },
        {
            "name": "filters.plugin_filter",
            "label": "Default Plugin Filter",
            "section": "filters",
            "key": "plugin_filter",
            "type": "str",
            "help_text": "Default plugin filter ('all' or specific plugin name)",
        },
        # Keys section
        {
            "name": "keys.quit",
            "label": "Quit Key",
            "section": "keys",
            "key": "quit",
            "type": "str",
            "help_text": "Key to quit the application",
        },
        {
            "name": "keys.refresh",
            "label": "Refresh Key",
            "section": "keys",
            "key": "refresh",
            "type": "str",
            "help_text": "Key to manually refresh the display",
        },
        {
            "name": "keys.toggle_auto_refresh",
            "label": "Toggle Auto-refresh Key",
            "section": "keys",
            "key": "toggle_auto_refresh",
            "type": "str",
            "help_text": "Key to toggle auto-refresh",
        },
        {
            "name": "keys.show_help",
            "label": "Help Key",
            "section": "keys",
            "key": "show_help",
            "type": "str",
            "help_text": "Key to show help",
        },
        {
            "name": "keys.toggle_graph_pane",
            "label": "Toggle Graph Pane Key",
            "section": "keys",
            "key": "toggle_graph_pane",
            "type": "str",
            "help_text": "Key to toggle graph pane visibility",
        },
        {
            "name": "keys.filter_completed",
            "label": "Filter Completed Key",
            "section": "keys",
            "key": "filter_completed",
            "type": "str",
            "help_text": "Key to toggle completed videos filter",
        },
        {
            "name": "keys.view_details",
            "label": "View Details Key",
            "section": "keys",
            "key": "view_details",
            "type": "str",
            "help_text": "Key to view video details",
        },
        # Advanced section
        {
            "name": "advanced.max_videos_in_list",
            "label": "Max Videos in List",
            "section": "advanced",
            "key": "max_videos_in_list",
            "type": "int",
            "min": 10,
            "max": 10000,
            "help_text": "Maximum number of videos to display in list",
        },
        {
            "name": "advanced.event_buffer_size",
            "label": "Event Buffer Size",
            "section": "advanced",
            "key": "event_buffer_size",
            "type": "int",
            "min": 100,
            "max": 10000,
            "help_text": "Size of the event ring buffer",
        },
        {
            "name": "advanced.speed_calculation_window",
            "label": "Speed Calculation Window (seconds)",
            "section": "advanced",
            "key": "speed_calculation_window",
            "type": "int",
            "min": 1,
            "max": 60,
            "help_text": "Seconds for speed averaging window",
        },
    ]
    
    def __init__(
        self,
        config: "HavenTUIConfig",
        on_save: Optional[Callable[["HavenTUIConfig"], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        """Initialize the configuration editor.
        
        Args:
            config: The configuration to edit.
            on_save: Optional callback when configuration is saved.
            on_cancel: Optional callback when editing is cancelled.
        """
        self.config = config
        self.on_save = on_save
        self.on_cancel = on_cancel
        self.fields: List[ConfigField] = []
        self._build_fields()
    
    def _build_fields(self) -> None:
        """Build the list of ConfigField objects from config."""
        self.fields = []
        
        for field_def in self.FIELD_DEFINITIONS:
            section = field_def["section"]
            key = field_def["key"]
            
            # Get current value from config
            section_obj = getattr(self.config, section)
            current_value = getattr(section_obj, key)
            
            # Create ConfigField
            field = ConfigField(
                name=field_def["name"],
                label=field_def["label"],
                value=current_value,
                default=current_value,
                field_type=field_def["type"],
                help_text=field_def.get("help_text", ""),
                choices=field_def.get("choices", []),
                min_value=field_def.get("min"),
                max_value=field_def.get("max"),
                section=section,
                key=key,
            )
            self.fields.append(field)
    
    def get_field(self, name: str) -> Optional[ConfigField]:
        """Get a field by name.
        
        Args:
            name: The field name (e.g., "display.theme").
            
        Returns:
            The ConfigField if found, None otherwise.
        """
        for field in self.fields:
            if field.name == name:
                return field
        return None
    
    def update_field(self, name: str, value: Any) -> Tuple[bool, str]:
        """Update a field value after validation.
        
        Args:
            name: The field name to update.
            value: The new value.
            
        Returns:
            Tuple of (success, error_message).
        """
        field = self.get_field(name)
        if field is None:
            return False, f"Field '{name}' not found"
        
        # Validate the value
        is_valid, error = field.validate(value)
        if not is_valid:
            return False, error
        
        # Parse and update
        field.value = field.parse_value(value)
        return True, ""
    
    def apply_changes(self) -> None:
        """Apply all field values to the configuration."""
        for field in self.fields:
            section_obj = getattr(self.config, field.section)
            setattr(section_obj, field.key, field.value)
    
    def save(self) -> None:
        """Save the configuration to file."""
        self.apply_changes()
        self.config.save()
        if self.on_save:
            self.on_save(self.config)
    
    def cancel(self) -> None:
        """Cancel editing and restore original values."""
        self._build_fields()  # Rebuild to restore defaults
        if self.on_cancel:
            self.on_cancel()
    
    def get_fields_by_section(self) -> Dict[str, List[ConfigField]]:
        """Get fields grouped by section.
        
        Returns:
            Dictionary mapping section names to lists of fields.
        """
        sections: Dict[str, List[ConfigField]] = {}
        for field in self.fields:
            if field.section not in sections:
                sections[field.section] = []
            sections[field.section].append(field)
        return sections
    
    def get_field_value(self, name: str) -> Any:
        """Get the current value of a field.
        
        Args:
            name: The field name.
            
        Returns:
            The field value, or None if not found.
        """
        field = self.get_field(name)
        return field.value if field else None
    
    def reset_to_defaults(self) -> None:
        """Reset all fields to their default values."""
        for field in self.fields:
            field.value = field.default
    
    def get_changed_fields(self) -> List[ConfigField]:
        """Get list of fields that have been changed from their defaults.
        
        Returns:
            List of changed ConfigField objects.
        """
        return [f for f in self.fields if f.value != f.default]
    
    def validate_all(self) -> List[Tuple[str, str]]:
        """Validate all field values.
        
        Returns:
            List of (field_name, error_message) tuples for invalid fields.
        """
        errors = []
        for field in self.fields:
            is_valid, error = field.validate(field.value)
            if not is_valid:
                errors.append((field.name, error))
        return errors


class ConfigFormBuilder:
    """Builder for creating configuration forms.
    
    This class provides a fluent interface for building configuration forms
    programmatically.
    
    Example:
        >>> from haven_tui.config_editor import ConfigFormBuilder
        >>> builder = ConfigFormBuilder()
        >>> form = (builder
        ...     .section("Display")
        ...     .field("theme", "Theme", "choice", choices=["dark", "light"])
        ...     .field("refresh_rate", "Refresh Rate", "float", min=0.1, max=60)
        ...     .build())
    """
    
    def __init__(self):
        """Initialize the form builder."""
        self.fields: List[Dict[str, Any]] = []
        self.current_section: str = ""
    
    def section(self, name: str) -> "ConfigFormBuilder":
        """Start a new section.
        
        Args:
            name: The section name.
            
        Returns:
            Self for method chaining.
        """
        self.current_section = name.lower()
        return self
    
    def field(
        self,
        key: str,
        label: str,
        field_type: str = "str",
        default: Any = None,
        help_text: str = "",
        choices: Optional[List[str]] = None,
        min: Optional[Union[int, float]] = None,
        max: Optional[Union[int, float]] = None,
    ) -> "ConfigFormBuilder":
        """Add a field to the current section.
        
        Args:
            key: The field key within the section.
            label: Display label for the field.
            field_type: Type of field (str, int, float, bool, choice, path).
            default: Default value.
            help_text: Help text for the field.
            choices: Available choices for choice fields.
            min_value: Minimum value for numeric fields.
            max_value: Maximum value for numeric fields.
            
        Returns:
            Self for method chaining.
        """
        field_def = {
            "name": f"{self.current_section}.{key}",
            "label": label,
            "section": self.current_section,
            "key": key,
            "type": field_type,
            "default": default,
            "help_text": help_text,
            "choices": choices or [],
            "min": min,
            "max": max,
        }
        self.fields.append(field_def)
        return self
    
    def build(self) -> List[Dict[str, Any]]:
        """Build and return the field definitions.
        
        Returns:
            List of field definition dictionaries.
        """
        return self.fields


def create_default_editor(
    config: Optional["HavenTUIConfig"] = None,
    on_save: Optional[Callable[["HavenTUIConfig"], None]] = None,
) -> ConfigEditor:
    """Create a default configuration editor.
    
    Args:
        config: The configuration to edit. If None, loads default config.
        on_save: Optional callback when configuration is saved.
        
    Returns:
        Configured ConfigEditor instance.
    """
    if config is None:
        from haven_tui.config import HavenTUIConfig
        config = HavenTUIConfig.load()
    
    return ConfigEditor(config, on_save=on_save)


def quick_edit_field(config: "HavenTUIConfig", field_path: str, value: Any) -> Tuple[bool, str]:
    """Quickly edit a single configuration field.
    
    Args:
        config: The configuration to edit.
        field_path: Path to the field (e.g., "display.theme").
        value: The new value.
        
    Returns:
        Tuple of (success, error_message).
    """
    editor = ConfigEditor(config)
    success, error = editor.update_field(field_path, value)
    if success:
        editor.apply_changes()
    return success, error
