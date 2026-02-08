# Task 5.1: Layout System

**Priority:** Critical
**Estimated Effort:** 2 days

**Description:**
Create layout system for organizing TUI screens (header, main content, footer, optional right pane).

**Implementation:**
```python
# src/haven_tui/ui/layout.py

class TUIPanel:
    """Base class for TUI panels/sections."""
    
    def __init__(self, stdscr: curses.window):
        self.stdscr = stdscr
        self.visible = True
    
    def render(self, y: int, x: int, height: int, width: int):
        """Render panel at position with given dimensions."""
        raise NotImplementedError
    
    def handle_key(self, key: int) -> bool:
        """Handle key press, return True if handled."""
        return False

class LayoutManager:
    """Manages TUI layout with header, main, footer, optional side pane."""
    
    def __init__(self, stdscr: curses.window, config: TUIConfig):
        self.stdscr = stdscr
        self.config = config
        self.show_right_pane = config.show_speed_graphs
        self.header = HeaderPanel(stdscr)
        self.main = MainPanel(stdscr)
        self.footer = FooterPanel(stdscr)
        self.right_pane = SpeedGraphPanel(stdscr) if self.show_right_pane else None
        
    def render(self):
        """Render complete layout."""
        max_y, max_x = self.stdscr.getmaxyx()
        
        # Calculate regions
        header_height = 1
        footer_height = 1
        right_pane_width = 35 if self.show_right_pane and max_x > 100 else 0
        
        main_height = max_y - header_height - footer_height
        main_width = max_x - right_pane_width
        
        # Render panels
        self.header.render(0, 0, header_height, max_x)
        self.main.render(header_height, 0, main_height, main_width)
        self.footer.render(max_y - footer_height, 0, footer_height, max_x)
        
        if self.right_pane:
            self.right_pane.render(
                header_height, main_width, 
                main_height, right_pane_width
            )
    
    def toggle_right_pane(self):
        """Toggle speed graph visibility (like aria2tui)."""
        self.show_right_pane = not self.show_right_pane
        self.right_pane = SpeedGraphPanel(self.stdscr) if self.show_right_pane else None
```

**Acceptance Criteria:**
- [ ] Panels render within allocated space
- [ ] Right pane can be toggled
- [ ] Resizes correctly with terminal
- [ ] No overlapping content
