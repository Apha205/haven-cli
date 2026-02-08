# Task 5.3: Footer/Status Bar

**Priority:** High
**Estimated Effort:** 1 day

**Description:**
Create footer with key bindings and status messages.

**Visual:**
```
│ [q Quit] [r Refresh] [←/→ Navigate] [Enter Details] [g Toggle Graph] │
```

**Implementation:**
```python
class FooterPanel(TUIPanel):
    """Footer bar with key bindings and status messages."""
    
    def __init__(self, stdscr, config: TUIConfig):
        super().__init__(stdscr)
        self.config = config
        self.status_message = ""
        self.key_bindings = [
            ("q", "Quit"),
            ("r", "Refresh"),
            ("←/→", "Navigate"),
            ("Enter", "Details"),
            ("g", "Toggle Graph"),
            ("?", "Help"),
        ]
    
    def render(self, y: int, x: int, height: int, width: int):
        """Render footer with key bindings."""
        # Build key binding string
        parts = [f"[{key} {label}]" for key, label in self.key_bindings]
        line = " ".join(parts)[:width-1]
        
        # Render with reverse video
        self.stdscr.addstr(y, x, line.ljust(width-1), curses.A_REVERSE)
    
    def set_status(self, message: str):
        """Set temporary status message."""
        self.status_message = message
    
    def show_help_keys(self):
        """Show help key overlay."""
        pass
```

**Acceptance Criteria:**
- [ ] Displays key bindings
- [ ] Shows status messages
- [ ] Styled consistently with header
- [ ] Updates dynamically based on context
