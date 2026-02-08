"""Tests for the TUI Layout System.

This module tests the LayoutManager, TUIPanel, and panel implementations
to ensure they meet the acceptance criteria.
"""

import pytest
from unittest.mock import MagicMock, Mock

import sys
sys.path.insert(0, '/home/tower/Documents/workspace/haven-cli')

from haven_tui.config import HavenTUIConfig, DisplayConfig, KeysConfig
from haven_tui.ui.layout import (
    TUIPanel,
    HeaderPanel,
    MainPanel,
    FooterPanel,
    SpeedGraphPanel,
    LayoutManager,
    ResizableLayout,
)
from haven_tui.core.state_manager import StateManager, VideoState


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create a test configuration."""
    return HavenTUIConfig(
        display=DisplayConfig(
            show_speed_graphs=True,
            graph_history_seconds=60,
        ),
        keys=KeysConfig(
            quit="q",
            refresh="r",
            toggle_auto_refresh="a",
            toggle_graph_pane="g",
            filter_completed="h",
            view_details="enter",
            show_help="?",
        ),
    )


@pytest.fixture
def config_no_graphs():
    """Create a test configuration without speed graphs."""
    return HavenTUIConfig(
        display=DisplayConfig(
            show_speed_graphs=False,
            graph_history_seconds=60,
        ),
    )


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager."""
    mock = MagicMock(spec=StateManager)
    
    # Create mock video states
    video1 = MagicMock(spec=VideoState)
    video1.is_active = True
    video1.is_completed = False
    video1.has_failed = False
    
    video2 = MagicMock(spec=VideoState)
    video2.is_active = False
    video2.is_completed = True
    video2.has_failed = False
    
    video3 = MagicMock(spec=VideoState)
    video3.is_active = False
    video3.is_completed = False
    video3.has_failed = True
    
    mock.get_all_videos.return_value = [video1, video2, video3]
    return mock


@pytest.fixture
def layout_manager(config, mock_state_manager):
    """Create a LayoutManager with default config."""
    return LayoutManager(config=config, state_manager=mock_state_manager)


@pytest.fixture
def layout_manager_no_graphs(config_no_graphs, mock_state_manager):
    """Create a LayoutManager without right pane."""
    return LayoutManager(config=config_no_graphs, state_manager=mock_state_manager)


# =============================================================================
# TUIPanel Base Class Tests
# =============================================================================

class TestTUIPanel:
    """Tests for the TUIPanel base class."""
    
    def test_tui_panel_requires_render_content(self):
        """Test that TUIPanel requires render_content to be implemented."""
        panel = TUIPanel()
        # render_content should raise NotImplementedError
        with pytest.raises(NotImplementedError):
            panel.render_content()
    
    def test_tui_panel_visibility(self):
        """Test panel visibility property."""
        # Create a concrete subclass for testing
        class TestPanel(TUIPanel):
            def render_content(self):
                return "test"
        
        panel = TestPanel()
        assert panel.panel_visible is True
        
        panel.panel_visible = False
        assert panel.panel_visible is False


# =============================================================================
# HeaderPanel Tests
# =============================================================================

class TestHeaderPanel:
    """Tests for the HeaderPanel."""
    
    def test_header_panel_creation(self):
        """Test HeaderPanel can be created."""
        panel = HeaderPanel()
        assert panel is not None
        assert panel.panel_visible is True
    
    def test_header_panel_displays_app_version(self):
        """AC: Displays app version."""
        panel = HeaderPanel()
        content = panel.render_content()
        
        assert "haven-tui v0.1.0" in content
    
    def test_header_panel_displays_view_name(self):
        """AC: Shows current view name."""
        panel = HeaderPanel()
        content = panel.render_content()
        
        assert "Pipeline View" in content
    
    def test_header_panel_displays_speeds(self):
        """AC: Shows download/upload speeds."""
        panel = HeaderPanel()
        content = panel.render_content()
        
        # Should show download/upload indicators
        assert "↓" in content
        assert "↑" in content
    
    def test_header_panel_displays_active_count(self):
        """AC: Shows active video count."""
        mock_sm = MagicMock()
        video1 = MagicMock()
        video1.is_active = True
        video2 = MagicMock()
        video2.is_active = False
        mock_sm.get_all_videos.return_value = [video1, video2]
        
        panel = HeaderPanel(state_manager=mock_sm)
        content = panel.render_content()
        
        assert "1 active" in content
    
    def test_header_panel_with_state_manager(self, mock_state_manager):
        """Test HeaderPanel with state manager shows stats."""
        panel = HeaderPanel(state_manager=mock_state_manager)
        content = panel.render_content()
        
        assert "haven-tui v0.1.0" in content
        assert "1 active" in content
    
    def test_header_panel_without_state_manager(self):
        """Test HeaderPanel without state manager shows default."""
        panel = HeaderPanel()
        content = panel.render_content()
        
        assert "haven-tui v0.1.0" in content
        assert "0 active" in content
    
    def test_header_panel_set_view_name(self):
        """Test HeaderPanel view name can be changed."""
        panel = HeaderPanel()
        panel.set_view_name("Settings")
        content = panel.render_content()
        
        assert "Settings View" in content
    
    def test_header_panel_no_videos(self):
        """Test HeaderPanel shows '0 active' when empty."""
        mock_sm = MagicMock()
        mock_sm.get_all_videos.return_value = []
        
        panel = HeaderPanel(state_manager=mock_sm)
        content = panel.render_content()
        
        assert "0 active" in content
    
    def test_header_panel_with_speed_aggregator(self):
        """Test HeaderPanel with speed aggregator shows speeds."""
        mock_aggregator = MagicMock()
        mock_aggregator.get_current_speeds.return_value = (
            13107200,  # 12.5 MiB/s
            3358720,   # 3.2 MiB/s
        )
        
        panel = HeaderPanel(speed_aggregator=mock_aggregator)
        content = panel.render_content()
        
        assert "12.5 MiB/s" in content or "13.1 MiB/s" in content
        assert "3.2 MiB/s" in content or "3.4 MiB/s" in content
    
    def test_header_panel_format_speed_bytes(self):
        """Test speed formatting for bytes."""
        panel = HeaderPanel()
        assert panel._format_speed(500) == "500 B/s"
    
    def test_header_panel_format_speed_kib(self):
        """Test speed formatting for KiB."""
        panel = HeaderPanel()
        assert panel._format_speed(1536) == "1.5 KiB/s"
    
    def test_header_panel_format_speed_mib(self):
        """Test speed formatting for MiB."""
        panel = HeaderPanel()
        assert panel._format_speed(13107200) == "12.5 MiB/s"
    
    def test_header_panel_format_speed_gib(self):
        """Test speed formatting for GiB."""
        panel = HeaderPanel()
        assert panel._format_speed(1073741824) == "1.0 GiB/s"
    
    def test_header_panel_format_speed_zero(self):
        """Test speed formatting for zero."""
        panel = HeaderPanel()
        assert panel._format_speed(0) == "-"


# =============================================================================
# MainPanel Tests
# =============================================================================

class TestMainPanel:
    """Tests for the MainPanel."""
    
    def test_main_panel_creation(self):
        """Test MainPanel can be created."""
        panel = MainPanel()
        assert panel is not None
        assert panel.panel_visible is True
    
    def test_main_panel_with_state_manager(self, mock_state_manager):
        """Test MainPanel with state manager."""
        panel = MainPanel(state_manager=mock_state_manager)
        assert panel.state_manager == mock_state_manager
    
    def test_main_panel_set_content(self):
        """Test MainPanel can have content set."""
        panel = MainPanel()
        mock_widget = MagicMock()
        
        panel.set_content(mock_widget)
        assert panel._content_widget == mock_widget


# =============================================================================
# FooterPanel Tests
# =============================================================================

class TestFooterPanel:
    """Tests for the FooterPanel."""
    
    def test_footer_panel_creation(self):
        """Test FooterPanel can be created."""
        panel = FooterPanel()
        assert panel is not None
        assert panel.panel_visible is True
    
    def test_footer_panel_default_bindings(self):
        """AC: Displays key bindings - Test FooterPanel shows default key bindings."""
        panel = FooterPanel()
        content = panel.render_content()
        
        assert "[q Quit]" in content
        assert "[r Refresh]" in content
        assert "[↑/↓ Navigate]" in content
        assert "[Enter Details]" in content
        assert "[g Toggle Graph]" in content
        assert "[? Help]" in content
    
    def test_footer_panel_custom_bindings(self, config):
        """Test FooterPanel works with custom config."""
        panel = FooterPanel(config=config)
        content = panel.render_content()
        
        # Should show default bindings even with config
        assert "[q Quit]" in content
        assert "[r Refresh]" in content
    
    def test_footer_panel_shows_status_message(self):
        """AC: Shows status messages - Test status message display."""
        panel = FooterPanel()
        
        # Set a status message
        panel.set_status("Download complete!")
        content = panel.render_content()
        
        assert "Download complete!" in content
        # Status should take precedence over key bindings
        assert "[q Quit]" not in content
    
    def test_footer_panel_status_message_expires(self):
        """Test status message expires after duration."""
        import time
        panel = FooterPanel()
        
        # Set a status message with short duration
        panel.set_status("Test message", duration=0.01)
        content = panel.render_content()
        assert "Test message" in content
        
        # Wait for expiration
        time.sleep(0.02)
        content = panel.render_content()
        
        # Should show key bindings again
        assert "Test message" not in content
        assert "[q Quit]" in content
    
    def test_footer_panel_clear_status(self):
        """Test clearing status message immediately."""
        panel = FooterPanel()
        
        # Set a status message
        panel.set_status("Test message")
        content = panel.render_content()
        assert "Test message" in content
        
        # Clear status
        panel.clear_status()
        content = panel.render_content()
        
        assert "Test message" not in content
        assert "[q Quit]" in content
    
    def test_footer_panel_context_pipeline(self):
        """AC: Updates dynamically based on context - Test pipeline context."""
        panel = FooterPanel()
        panel.set_view_context("pipeline")
        content = panel.render_content()
        
        assert "[q Quit]" in content
        assert "[↑/↓ Navigate]" in content
        assert "[Enter Details]" in content
        assert "[g Toggle Graph]" in content
    
    def test_footer_panel_context_detail(self):
        """AC: Updates dynamically based on context - Test detail context."""
        panel = FooterPanel()
        panel.set_view_context("detail")
        content = panel.render_content()
        
        assert "[q Quit]" in content
        assert "[Esc Back]" in content
        assert "[r Refresh]" in content
        assert "[g Toggle Graph]" in content
        # Should not show navigation keys from pipeline
        assert "Navigate" not in content
    
    def test_footer_panel_context_help(self):
        """AC: Updates dynamically based on context - Test help context."""
        panel = FooterPanel()
        panel.set_view_context("help")
        content = panel.render_content()
        
        assert "[q Quit]" in content
        assert "[Esc Close]" in content
        assert "[? Back]" in content
    
    def test_footer_panel_show_help_keys(self):
        """Test show_help_keys switches to help context."""
        panel = FooterPanel()
        panel.set_view_context("pipeline")
        
        # Switch to help context
        panel.show_help_keys()
        content = panel.render_content()
        
        assert panel.view_context == "help"
        assert "[Esc Close]" in content
    
    def test_footer_panel_get_current_bindings(self):
        """Test getting current key bindings."""
        panel = FooterPanel()
        bindings = panel.get_current_bindings()
        
        # Should return list of tuples
        assert isinstance(bindings, list)
        assert len(bindings) > 0
        assert all(isinstance(b, tuple) and len(b) == 2 for b in bindings)
        
        # Check for expected bindings
        keys = [b[0] for b in bindings]
        assert "q" in keys
        assert "r" in keys
    
    def test_footer_panel_styled_consistently_with_header(self):
        """AC: Styled consistently with header - Test styling matches header.
        
        Footer should use same reversed colors as header (background: $text, 
        color: $background, text-style: bold).
        """
        panel = FooterPanel()
        
        # Check CSS properties match header styling
        assert "background: $text" in panel.DEFAULT_CSS
        assert "color: $background" in panel.DEFAULT_CSS
        assert "text-style: bold" in panel.DEFAULT_CSS
    
    def test_footer_panel_status_with_duration(self):
        """Test status message with custom duration."""
        import time
        panel = FooterPanel()
        
        # Set a status message with longer duration
        panel.set_status("Long message", duration=5.0)
        
        # Check timeout is set correctly
        assert panel.status_timeout is not None
        assert panel.status_message == "Long message"
    
    def test_footer_panel_invalid_context_fallback(self):
        """Test fallback to pipeline bindings for invalid context."""
        panel = FooterPanel()
        panel.set_view_context("invalid_context")
        
        # Should fallback to pipeline bindings
        content = panel.render_content()
        assert "[q Quit]" in content
        assert "[↑/↓ Navigate]" in content


# =============================================================================
# SpeedGraphPanel Tests
# =============================================================================

class TestSpeedGraphPanel:
    """Tests for the SpeedGraphPanel."""
    
    def test_speed_graph_panel_creation(self):
        """Test SpeedGraphPanel can be created."""
        panel = SpeedGraphPanel()
        assert panel is not None
        assert panel.panel_visible is True
    
    def test_speed_graph_panel_with_video(self):
        """Test SpeedGraphPanel with video ID."""
        panel = SpeedGraphPanel(video_id=123)
        assert panel.video_id == 123
    
    def test_speed_graph_panel_set_video(self):
        """Test SpeedGraphPanel video can be changed."""
        panel = SpeedGraphPanel()
        panel.set_video(456, "download")
        assert panel.video_id == 456


# =============================================================================
# LayoutManager Tests
# =============================================================================

class TestLayoutManager:
    """Tests for the LayoutManager."""
    
    def test_layout_manager_creation(self, config, mock_state_manager):
        """Test LayoutManager can be created."""
        layout = LayoutManager(config=config, state_manager=mock_state_manager)
        
        assert layout.config == config
        assert layout.state_manager == mock_state_manager
        assert layout.show_right_pane is True
    
    def test_layout_manager_creates_panels(self, layout_manager):
        """Test LayoutManager creates all panels."""
        assert layout_manager.header is not None
        assert isinstance(layout_manager.header, HeaderPanel)
        
        assert layout_manager.main is not None
        assert isinstance(layout_manager.main, MainPanel)
        
        assert layout_manager.footer is not None
        assert isinstance(layout_manager.footer, FooterPanel)
        
        assert layout_manager.right_pane is not None
        assert isinstance(layout_manager.right_pane, SpeedGraphPanel)
    
    def test_layout_manager_no_graphs(self, layout_manager_no_graphs):
        """Test LayoutManager without speed graphs."""
        assert layout_manager_no_graphs.show_right_pane is False
        assert layout_manager_no_graphs.right_pane is None


class TestLayoutManagerToggle:
    """Tests for LayoutManager toggle functionality."""
    
    def test_toggle_right_pane_on_to_off(self, layout_manager):
        """Test toggling right pane from on to off."""
        assert layout_manager.show_right_pane is True
        assert layout_manager.right_pane is not None
        
        result = layout_manager.toggle_right_pane()
        
        assert result is False
        assert layout_manager.show_right_pane is False
        assert layout_manager.right_pane is None
    
    def test_toggle_right_pane_off_to_on(self, layout_manager_no_graphs):
        """Test toggling right pane from off to on."""
        assert layout_manager_no_graphs.show_right_pane is False
        assert layout_manager_no_graphs.right_pane is None
        
        result = layout_manager_no_graphs.toggle_right_pane()
        
        assert result is True
        assert layout_manager_no_graphs.show_right_pane is True
        assert layout_manager_no_graphs.right_pane is not None
    
    def test_toggle_right_pane_returns_state(self, layout_manager):
        """Test toggle_right_pane returns current visibility state."""
        # Toggle off
        result = layout_manager.toggle_right_pane()
        assert result is False
        
        # Toggle on
        result = layout_manager.toggle_right_pane()
        assert result is True


class TestLayoutManagerRegions:
    """Tests for LayoutManager region calculations."""
    
    def test_get_layout_regions_basic(self, layout_manager):
        """Test basic layout region calculation."""
        regions = layout_manager.get_layout_regions(120, 40)
        
        assert regions["header"] is not None
        assert regions["main"] is not None
        assert regions["footer"] is not None
        assert regions["right_pane"] is not None
    
    def test_get_layout_regions_header_position(self, layout_manager):
        """Test header is at top."""
        regions = layout_manager.get_layout_regions(120, 40)
        
        header = regions["header"]
        assert header["y"] == 0
        assert header["x"] == 0
        assert header["height"] == 3
        assert header["width"] == 120
    
    def test_get_layout_regions_footer_position(self, layout_manager):
        """Test footer is at bottom."""
        regions = layout_manager.get_layout_regions(120, 40)
        
        footer = regions["footer"]
        assert footer["y"] == 39  # 40 - 1
        assert footer["x"] == 0
        assert footer["height"] == 1
        assert footer["width"] == 120
    
    def test_get_layout_regions_main_dimensions(self, layout_manager):
        """Test main panel dimensions."""
        regions = layout_manager.get_layout_regions(120, 40)
        
        main = regions["main"]
        assert main["y"] == 3  # After header
        assert main["x"] == 0
        assert main["height"] == 36  # 40 - 3 - 1
        assert main["width"] == 85  # 120 - 35
    
    def test_get_layout_regions_right_pane_dimensions(self, layout_manager):
        """Test right pane dimensions."""
        regions = layout_manager.get_layout_regions(120, 40)
        
        right = regions["right_pane"]
        assert right["y"] == 3  # After header
        assert right["x"] == 85  # After main
        assert right["height"] == 36
        assert right["width"] == 35
    
    def test_get_layout_regions_no_right_pane_when_narrow(self, layout_manager):
        """Test right pane is hidden when terminal is narrow."""
        regions = layout_manager.get_layout_regions(80, 40)
        
        # Terminal too narrow, right pane should be None
        assert regions["right_pane"] is None
        
        # Main should use full width
        main = regions["main"]
        assert main["width"] == 80
    
    def test_get_layout_regions_no_right_pane_when_disabled(self, layout_manager_no_graphs):
        """Test right pane is hidden when disabled in config."""
        regions = layout_manager_no_graphs.get_layout_regions(120, 40)
        
        # Right pane disabled in config
        assert regions["right_pane"] is None
    
    def test_get_layout_regions_small_terminal(self, layout_manager):
        """Test layout with small terminal."""
        regions = layout_manager.get_layout_regions(60, 20)
        
        # Right pane should be hidden
        assert regions["right_pane"] is None
        
        # Main should use full width
        assert regions["main"]["width"] == 60


class TestLayoutManagerResize:
    """Tests for LayoutManager resize handling."""
    
    def test_handle_resize_updates_visibility(self, layout_manager):
        """Test resize updates right pane visibility."""
        # Initially visible with wide terminal
        assert layout_manager.show_right_pane is True
        
        # Resize to narrow terminal
        layout_manager.handle_resize(80, 40)
        
        # Right pane should be hidden (but show_right_pane flag remains True)
        # The panel's display property would be updated in a real Textual context
        assert layout_manager.show_right_pane is True  # Config unchanged
    
    def test_handle_resize_large_terminal(self, layout_manager):
        """Test resize with large terminal."""
        layout_manager.handle_resize(150, 50)
        
        regions = layout_manager.get_layout_regions(150, 50)
        assert regions["right_pane"] is not None


class TestLayoutManagerIntegration:
    """Integration tests for LayoutManager."""
    
    def test_set_right_pane_video(self, layout_manager):
        """Test setting video for right pane."""
        layout_manager.set_right_pane_video(123, "download")
        assert layout_manager.right_pane.video_id == 123
    
    def test_set_right_pane_video_no_pane(self, layout_manager_no_graphs):
        """Test setting video when right pane is disabled."""
        # Should not raise error
        layout_manager_no_graphs.set_right_pane_video(123, "download")
        assert layout_manager_no_graphs.right_pane is None
    
    def test_refresh_header(self, layout_manager, mock_state_manager):
        """Test refresh_header calls header refresh."""
        # Mock the header's refresh_header method
        layout_manager.header.refresh_header = MagicMock()
        
        layout_manager.refresh_header()
        layout_manager.header.refresh_header.assert_called_once()
    
    def test_refresh_footer(self, layout_manager):
        """Test refresh_footer calls footer refresh."""
        layout_manager.footer.refresh_footer = MagicMock()
        
        layout_manager.refresh_footer()
        layout_manager.footer.refresh_footer.assert_called_once()
    
    def test_get_panels(self, layout_manager):
        """Test get_panels returns all panels."""
        panels = layout_manager.get_panels()
        
        assert "header" in panels
        assert "main" in panels
        assert "footer" in panels
        assert "right_pane" in panels
        
        assert panels["header"] == layout_manager.header
        assert panels["main"] == layout_manager.main
        assert panels["footer"] == layout_manager.footer
        assert panels["right_pane"] == layout_manager.right_pane


# =============================================================================
# Acceptance Criteria Tests
# =============================================================================

class TestAcceptanceCriteria:
    """Tests for meeting the acceptance criteria."""
    
    def test_panels_render_within_allocated_space(self, layout_manager):
        """AC1: Panels render within allocated space.
        
        Verify that header, main, footer, and right pane have
        calculated regions that don't overlap.
        """
        regions = layout_manager.get_layout_regions(120, 40)
        
        header = regions["header"]
        main = regions["main"]
        footer = regions["footer"]
        right_pane = regions["right_pane"]
        
        # Header at top (rows 0-2)
        assert header["y"] == 0
        assert header["height"] == 3
        
        # Main below header (rows 3-38)
        assert main["y"] == 3
        assert main["height"] == 36
        
        # Footer at bottom (row 39)
        assert footer["y"] == 39
        assert footer["height"] == 1
        
        # Right pane next to main
        assert right_pane["x"] == main["width"]
        assert right_pane["y"] == main["y"]
        assert right_pane["height"] == main["height"]
        
        # Verify no vertical overlap between header, main, footer
        assert header["y"] + header["height"] <= main["y"]
        assert main["y"] + main["height"] <= footer["y"]
    
    def test_right_pane_can_be_toggled(self, layout_manager):
        """AC2: Right pane can be toggled.
        
        Verify that the right pane can be shown/hidden
        using the toggle_right_pane method.
        """
        # Initially visible
        assert layout_manager.show_right_pane is True
        assert layout_manager.right_pane is not None
        
        # Toggle off
        result = layout_manager.toggle_right_pane()
        assert result is False
        assert layout_manager.show_right_pane is False
        assert layout_manager.right_pane is None
        
        # Toggle on
        result = layout_manager.toggle_right_pane()
        assert result is True
        assert layout_manager.show_right_pane is True
        assert layout_manager.right_pane is not None
    
    def test_resizes_correctly_with_terminal(self, layout_manager):
        """AC3: Resizes correctly with terminal.
        
        Verify that layout regions are recalculated when
        terminal size changes.
        """
        # Large terminal
        large = layout_manager.get_layout_regions(120, 40)
        assert large["right_pane"] is not None
        assert large["main"]["width"] == 85
        
        # Small terminal
        small = layout_manager.get_layout_regions(80, 40)
        assert small["right_pane"] is None
        assert small["main"]["width"] == 80
        
        # Very small terminal
        very_small = layout_manager.get_layout_regions(60, 20)
        assert very_small["right_pane"] is None
        assert very_small["main"]["width"] == 60
    
    def test_no_overlapping_content(self, layout_manager):
        """AC4: No overlapping content.
        
        Verify that all panels have distinct regions
        without overlapping each other.
        """
        regions = layout_manager.get_layout_regions(120, 40)
        
        def regions_overlap(r1, r2):
            """Check if two regions overlap."""
            # Vertical overlap
            v_overlap = not (r1["y"] + r1["height"] <= r2["y"] or 
                            r2["y"] + r2["height"] <= r1["y"])
            # Horizontal overlap
            h_overlap = not (r1["x"] + r1["width"] <= r2["x"] or 
                            r2["x"] + r2["width"] <= r1["x"])
            return v_overlap and h_overlap
        
        header = regions["header"]
        main = regions["main"]
        footer = regions["footer"]
        right_pane = regions["right_pane"]
        
        # Header and footer should not overlap with anything
        assert not regions_overlap(header, main)
        assert not regions_overlap(header, footer)
        assert not regions_overlap(main, footer)
        
        # Right pane should not overlap with main (they're side by side)
        # But they share the same vertical space
        assert right_pane["x"] == main["x"] + main["width"]
        assert right_pane["y"] == main["y"]


# =============================================================================
# ResizableLayout Tests
# =============================================================================

class TestResizableLayout:
    """Tests for the ResizableLayout container."""
    
    def test_resizable_layout_creation(self, layout_manager):
        """Test ResizableLayout can be created."""
        container = ResizableLayout(layout_manager=layout_manager)
        assert container is not None
        assert container.layout_manager == layout_manager
    
    def test_resizable_layout_handles_resize(self, layout_manager):
        """Test ResizableLayout handles resize events."""
        container = ResizableLayout(layout_manager=layout_manager)
        
        # Create a mock resize event
        mock_event = MagicMock()
        mock_event.size.width = 100
        mock_event.size.height = 40
        
        # Should not raise
        container.on_resize(mock_event)


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_very_small_terminal(self, layout_manager):
        """Test layout with very small terminal."""
        regions = layout_manager.get_layout_regions(40, 10)
        
        # Should still work, right pane hidden
        assert regions["right_pane"] is None
        assert regions["header"]["width"] == 40
        assert regions["footer"]["width"] == 40
    
    def test_minimum_viable_terminal(self, layout_manager):
        """Test layout at minimum viable terminal size."""
        regions = layout_manager.get_layout_regions(20, 5)
        
        # Layout should still calculate
        assert regions["header"] is not None
        assert regions["main"] is not None
        assert regions["footer"] is not None
    
    def test_layout_manager_with_none_config(self, mock_state_manager):
        """Test LayoutManager handles None config gracefully."""
        # Should raise AttributeError since config is required
        with pytest.raises((TypeError, AttributeError)):
            LayoutManager(config=None, state_manager=mock_state_manager)
    
    def test_header_with_none_videos(self):
        """Test header when get_all_videos returns None."""
        mock_sm = MagicMock()
        mock_sm.get_all_videos.return_value = None
        
        panel = HeaderPanel(state_manager=mock_sm)
        # Should handle None gracefully
        content = panel.render_content()
        assert "haven-tui v0.1.0" in content
        assert "0 active" in content
    
    def test_multiple_toggles(self, layout_manager):
        """Test multiple rapid toggles."""
        states = []
        for _ in range(10):
            states.append(layout_manager.toggle_right_pane())
        
        # Should alternate between True and False
        expected = [False, True, False, True, False, True, False, True, False, True]
        assert states == expected
