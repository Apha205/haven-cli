# Task 5.4: Right Pane (Speed Graph)

**Priority:** Medium
**Estimated Effort:** 2 days

**Description:**
Create optional right pane showing speed graph for selected video (like aria2tui's detail pane).

**Visual:**
```
┌───────────────────────────────────┐
│ Speed History                     │
│                                   │
│  5.0 ┤                        ╭╮  │
│  2.5 ┤        ╭──╮           ╯╯  │
│  0.0 ┼──────────────────────────  │
│     60s  45s  30s  15s  now      │
│                                   │
│ Current: 3.2 MiB/s                │
│ Average: 2.1 MiB/s                │
│ Peak: 5.8 MiB/s                   │
└───────────────────────────────────┘
```

**Implementation:**
```python
class SpeedGraphPanel(TUIPanel):
    """Right pane showing speed graph."""
    
    def __init__(self, stdscr, state_manager: StateManager):
        super().__init__(stdscr)
        self.state = state_manager
        self.selected_video_id = None
        self.width = 35
        self.height = 20
    
    def render(self, y: int, x: int, height: int, width: int):
        # Border
        self._draw_border(y, x, height, width, "Speed History")
        
        # Get speed data for selected video
        history = self.state.get_speed_history(
            self.selected_video_id, 
            seconds=60
        )
        
        # Render graph
        if len(history) > 2:
            graph = self._render_ascii_graph(
                history, 
                width - 4, 
                height - 8
            )
            for i, line in enumerate(graph):
                self.stdscr.addstr(y + 2 + i, x + 2, line)
        
        # Stats at bottom
        stats_y = y + height - 5
        self.stdscr.addstr(stats_y, x + 2, f"Current: {self.current_speed}")
        self.stdscr.addstr(stats_y + 1, x + 2, f"Average: {self.avg_speed}")
        self.stdscr.addstr(stats_y + 2, x + 2, f"Peak: {self.peak_speed}")
    
    def set_selected_video(self, video_id: int):
        """Update selected video for graph."""
        self.selected_video_id = video_id
    
    def _draw_border(self, y: int, x: int, height: int, width: int, title: str):
        """Draw panel border with title."""
        # Top border
        self.stdscr.addstr(y, x, "┌" + "─" * (width - 2) + "┐")
        # Title
        self.stdscr.addstr(y, x + 2, f" {title} ")
        # Side borders
        for i in range(1, height - 1):
            self.stdscr.addstr(y + i, x, "│")
            self.stdscr.addstr(y + i, x + width - 1, "│")
        # Bottom border
        self.stdscr.addstr(y + height - 1, x, "└" + "─" * (width - 2) + "┘")
    
    def _render_ascii_graph(self, history: list, width: int, height: int) -> list[str]:
        """Render ASCII graph from history data."""
        # Use plotille or custom rendering
        pass
```

**Acceptance Criteria:**
- [ ] Shows speed history graph
- [ ] Updates when video selection changes
- [ ] Shows current, average, peak speeds
- [ ] Toggle visibility with 'g' key
- [ ] Resizes correctly with terminal
