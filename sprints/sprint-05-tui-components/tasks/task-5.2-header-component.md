# Task 5.2: Header Component

**Priority:** High
**Estimated Effort:** 1 day

**Description:**
Create header bar showing app info, current view, and aggregate stats.

**Visual:**
```
│ haven-tui v0.1.0 │ Pipeline View │ ↓ 12.5 MiB/s ↑ 3.2 MiB/s │ 5 active │
```

**Implementation:**
```python
class HeaderPanel(TUIPanel):
    """Header bar with status information."""
    
    def __init__(self, stdscr):
        super().__init__(stdscr)
        self.version = "0.1.0"
        self.view_name = "Pipeline"
        
    def render(self, y: int, x: int, height: int, width: int):
        # Build header string
        parts = [
            f"haven-tui v{self.version}",
            f"│ {self.view_name}",
            f"│ ↓ {self._format_speed(self.download_speed)}",
            f"↑ {self._format_speed(self.upload_speed)}",
            f"│ {self.active_count} active",
        ]
        
        line = " ".join(parts)[:width-1]
        self.stdscr.addstr(y, x, line.ljust(width-1), curses.A_REVERSE)
```

**Acceptance Criteria:**
- [ ] Displays app version
- [ ] Shows current view name
- [ ] Shows download/upload speeds
- [ ] Shows active video count
- [ ] Styled with reversed colors
