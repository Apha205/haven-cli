"""Tests for Haven TUI Configuration Editor.

This module tests the form-based configuration editor functionality.
"""

from __future__ import annotations

import pytest

from haven_tui.config import HavenTUIConfig
from haven_tui.config_editor import (
    ConfigEditor,
    ConfigField,
    ConfigFormBuilder,
    create_default_editor,
    quick_edit_field,
)


class TestConfigField:
    """Tests for ConfigField dataclass."""
    
    def test_string_field_validation(self):
        """Test string field validation."""
        field = ConfigField(
            name="test.string",
            label="Test String",
            value="default",
            field_type="str",
        )
        
        is_valid, error = field.validate("new value")
        assert is_valid is True
        assert error == ""
    
    def test_int_field_validation(self):
        """Test integer field validation."""
        field = ConfigField(
            name="test.int",
            label="Test Int",
            value=10,
            field_type="int",
            min_value=0,
            max_value=100,
        )
        
        # Valid value
        is_valid, error = field.validate("50")
        assert is_valid is True
        
        # Below minimum
        is_valid, error = field.validate("-1")
        assert is_valid is False
        assert "0" in error
        
        # Above maximum
        is_valid, error = field.validate("101")
        assert is_valid is False
        assert "100" in error
        
        # Invalid type
        is_valid, error = field.validate("not a number")
        assert is_valid is False
    
    def test_float_field_validation(self):
        """Test float field validation."""
        field = ConfigField(
            name="test.float",
            label="Test Float",
            value=1.5,
            field_type="float",
            min_value=0.1,
            max_value=10.0,
        )
        
        # Valid value
        is_valid, error = field.validate("5.5")
        assert is_valid is True
        
        # Below minimum
        is_valid, error = field.validate("0.05")
        assert is_valid is False
        
        # Above maximum
        is_valid, error = field.validate("10.1")
        assert is_valid is False
    
    def test_bool_field_validation(self):
        """Test boolean field validation."""
        field = ConfigField(
            name="test.bool",
            label="Test Bool",
            value=True,
            field_type="bool",
        )
        
        # Valid values
        for val in ["true", "false", "1", "0", "yes", "no"]:
            is_valid, error = field.validate(val)
            assert is_valid is True, f"Failed for: {val}"
        
        # Invalid value
        is_valid, error = field.validate("maybe")
        assert is_valid is False
    
    def test_choice_field_validation(self):
        """Test choice field validation."""
        field = ConfigField(
            name="test.choice",
            label="Test Choice",
            value="option1",
            field_type="choice",
            choices=["option1", "option2", "option3"],
        )
        
        # Valid choice
        is_valid, error = field.validate("option2")
        assert is_valid is True
        
        # Invalid choice
        is_valid, error = field.validate("option4")
        assert is_valid is False
        assert "option1" in error
        assert "option2" in error
        assert "option3" in error
    
    def test_path_field_validation(self):
        """Test path field validation."""
        field = ConfigField(
            name="test.path",
            label="Test Path",
            value="/default/path",
            field_type="path",
        )
        
        # Valid path
        is_valid, error = field.validate("/new/path")
        assert is_valid is True
        
        # Invalid type
        is_valid, error = field.validate(123)
        assert is_valid is False
    
    def test_parse_value_int(self):
        """Test parsing integer values."""
        field = ConfigField(
            name="test.int",
            label="Test",
            value=0,
            field_type="int",
        )
        
        assert field.parse_value("42") == 42
        assert field.parse_value(42) == 42
    
    def test_parse_value_float(self):
        """Test parsing float values."""
        field = ConfigField(
            name="test.float",
            label="Test",
            value=0.0,
            field_type="float",
        )
        
        assert field.parse_value("3.14") == 3.14
        assert field.parse_value(3.14) == 3.14
    
    def test_parse_value_bool(self):
        """Test parsing boolean values."""
        field = ConfigField(
            name="test.bool",
            label="Test",
            value=False,
            field_type="bool",
        )
        
        assert field.parse_value(True) is True
        assert field.parse_value(False) is False
        assert field.parse_value("true") is True
        assert field.parse_value("false") is False
        assert field.parse_value("1") is True
        assert field.parse_value("0") is False
        assert field.parse_value("yes") is True
        assert field.parse_value("no") is False


class TestConfigEditor:
    """Tests for ConfigEditor class."""
    
    def test_editor_initialization(self):
        """Test ConfigEditor initialization."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        assert editor.config is config
        assert len(editor.fields) > 0
    
    def test_get_field(self):
        """Test getting fields by name."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        field = editor.get_field("display.theme")
        assert field is not None
        assert field.section == "display"
        assert field.key == "theme"
        
        # Non-existent field
        field = editor.get_field("nonexistent.field")
        assert field is None
    
    def test_update_field_valid(self):
        """Test updating a field with valid value."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        success, error = editor.update_field("display.theme", "dark")
        
        assert success is True
        assert error == ""
        
        field = editor.get_field("display.theme")
        assert field.value == "dark"
    
    def test_update_field_invalid(self):
        """Test updating a field with invalid value."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        # Invalid float value
        success, error = editor.update_field("display.refresh_rate", "not a number")
        
        assert success is False
        assert error != ""
    
    def test_update_field_nonexistent(self):
        """Test updating a non-existent field."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        success, error = editor.update_field("nonexistent.field", "value")
        
        assert success is False
        assert "not found" in error
    
    def test_apply_changes(self):
        """Test applying changes to configuration."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        # Update fields in editor
        editor.update_field("display.theme", "dark")
        editor.update_field("display.refresh_rate", "5.0")
        
        # Apply changes
        editor.apply_changes()
        
        # Verify config was updated
        assert config.display.theme == "dark"
        assert config.display.refresh_rate == 5.0
    
    def test_save(self, tmp_path):
        """Test saving configuration."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig(config_path=config_path)
        editor = ConfigEditor(config)
        
        # Modify and save
        editor.update_field("display.theme", "dark")
        editor.save()
        
        # Reload and verify
        config2 = HavenTUIConfig.load(config_path)
        assert config2.display.theme == "dark"
    
    def test_cancel(self):
        """Test canceling edits."""
        config = HavenTUIConfig()
        config.display.theme = "original"
        editor = ConfigEditor(config)
        
        # Modify in editor
        editor.update_field("display.theme", "changed")
        
        # Cancel
        editor.cancel()
        
        # Verify original values restored
        field = editor.get_field("display.theme")
        assert field.value == "original"
    
    def test_get_fields_by_section(self):
        """Test getting fields grouped by section."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        sections = editor.get_fields_by_section()
        
        assert "database" in sections
        assert "display" in sections
        assert "filters" in sections
        assert "keys" in sections
        assert "advanced" in sections
        
        # Each section should have fields
        for section_fields in sections.values():
            assert len(section_fields) > 0
    
    def test_get_field_value(self):
        """Test getting field value."""
        config = HavenTUIConfig()
        config.display.theme = "custom"
        editor = ConfigEditor(config)
        
        value = editor.get_field_value("display.theme")
        assert value == "custom"
        
        # Non-existent field
        value = editor.get_field_value("nonexistent")
        assert value is None
    
    def test_reset_to_defaults(self):
        """Test resetting all fields to defaults."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        # Get original theme value
        original_theme = editor.get_field("display.theme").value
        
        # Modify fields
        editor.update_field("display.theme", "changed")
        
        # Reset
        editor.reset_to_defaults()
        
        # Verify restored
        assert editor.get_field("display.theme").value == original_theme
    
    def test_get_changed_fields(self):
        """Test getting changed fields."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        # Initially no changes
        changed = editor.get_changed_fields()
        assert len(changed) == 0
        
        # Modify a field
        editor.update_field("display.theme", "dark")
        
        # Should have one changed field
        changed = editor.get_changed_fields()
        assert len(changed) == 1
        assert changed[0].name == "display.theme"
    
    def test_validate_all_valid(self):
        """Test validating all fields with valid values."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        errors = editor.validate_all()
        assert len(errors) == 0
    
    def test_validate_all_invalid(self):
        """Test validating all fields with invalid values."""
        config = HavenTUIConfig()
        editor = ConfigEditor(config)
        
        # Manually set an invalid value
        field = editor.get_field("display.refresh_rate")
        field.value = "invalid"
        
        errors = editor.validate_all()
        assert len(errors) > 0


class TestConfigFormBuilder:
    """Tests for ConfigFormBuilder class."""
    
    def test_builder_chain(self):
        """Test builder method chaining."""
        builder = ConfigFormBuilder()
        
        result = (builder
            .section("Display")
            .field("theme", "Theme", "choice", choices=["dark", "light"])
            .field("refresh", "Refresh", "float", min=0.1, max=60))
        
        assert result is builder
    
    def test_builder_creates_fields(self):
        """Test that builder creates field definitions."""
        builder = ConfigFormBuilder()
        
        fields = (builder
            .section("Display")
            .field("theme", "Theme", "choice", default="dark", choices=["dark", "light"])
            .field("refresh", "Refresh Rate", "float", default=2.0, min=0.1, max=60.0)
            .section("Database")
            .field("path", "Database Path", "path", default="~/db.sqlite")
            .build())
        
        assert len(fields) == 3
        
        # Check display fields
        assert fields[0]["name"] == "display.theme"
        assert fields[0]["section"] == "display"
        assert fields[0]["choices"] == ["dark", "light"]
        
        assert fields[1]["name"] == "display.refresh"
        assert fields[1]["min"] == 0.1
        assert fields[1]["max"] == 60.0
        
        # Check database field
        assert fields[2]["name"] == "database.path"
        assert fields[2]["section"] == "database"


class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_create_default_editor(self, tmp_path):
        """Test creating default editor."""
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig(config_path=config_path)
        
        editor = create_default_editor(config)
        
        assert isinstance(editor, ConfigEditor)
        assert editor.config is config
    
    def test_create_default_editor_without_config(self, tmp_path, monkeypatch):
        """Test creating default editor without providing config."""
        config_path = tmp_path / "config.toml"
        monkeypatch.setattr(
            "haven_tui.config.DEFAULT_CONFIG_PATH",
            config_path
        )
        
        editor = create_default_editor()
        
        assert isinstance(editor, ConfigEditor)
        assert isinstance(editor.config, HavenTUIConfig)
    
    def test_quick_edit_field_success(self):
        """Test successful quick field edit."""
        config = HavenTUIConfig()
        
        success, error = quick_edit_field(config, "display.theme", "dark")
        
        assert success is True
        assert error == ""
        assert config.display.theme == "dark"
    
    def test_quick_edit_field_failure(self):
        """Test failed quick field edit."""
        config = HavenTUIConfig()
        
        success, error = quick_edit_field(config, "display.refresh_rate", "invalid")
        
        assert success is False
        assert error != ""
    
    def test_quick_edit_field_nonexistent(self):
        """Test quick edit of non-existent field."""
        config = HavenTUIConfig()
        
        success, error = quick_edit_field(config, "nonexistent.field", "value")
        
        assert success is False
        assert "not found" in error


class TestConfigEditorCallbacks:
    """Tests for ConfigEditor callbacks."""
    
    def test_on_save_callback(self, tmp_path):
        """Test on_save callback is called."""
        saved_config = None
        
        def on_save(config):
            nonlocal saved_config
            saved_config = config
        
        config_path = tmp_path / "config.toml"
        config = HavenTUIConfig(config_path=config_path)
        editor = ConfigEditor(config, on_save=on_save)
        
        editor.save()
        
        assert saved_config is config
    
    def test_on_cancel_callback(self):
        """Test on_cancel callback is called."""
        cancelled = False
        
        def on_cancel():
            nonlocal cancelled
            cancelled = True
        
        config = HavenTUIConfig()
        editor = ConfigEditor(config, on_cancel=on_cancel)
        
        editor.cancel()
        
        assert cancelled is True
