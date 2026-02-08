# Task 3.3: Speed Graph Component (from aria2tui)

**Priority:** High
**Estimated Effort:** 3 days

**Description:**
Adapt aria2tui's speed graph for haven-tui, showing speed history from `speed_history` table for the selected video.

**Implementation:**
```python
# src/haven_tui/ui/components/speed_graph.py
from plotille import Figure

class SpeedGraphComponent:
    """ASCII speed graph using data from speed_history table."""
    
    def __init__(self, width: int = 60, height: int = 15):
        self.width = width
        self.height = height
        self.history_seconds = 60
    
    def render(self, stdscr, y: int, x: int, video_id: int):
        """Render speed graph for video from speed_history table."""
        # Get speed history from database
        speed_data = self.speed_history_repo.get_speed_history(
            video_id=video_id,
            stage="download",  # or current stage
            minutes=5
        )
        
        if not speed_data:
            stdscr.addstr(y, x, "[No speed data available]")
            return
        
        # Create ASCII graph
        fig = Figure()
        fig.width = self.width
        fig.height = self.height
        
        # Extract timestamps and speeds
        times = [s.timestamp.timestamp() for s in speed_data]
        speeds = [s.speed for s in speed_data]
        
        # Normalize timestamps to relative seconds
        now = time.time()
        x_data = [now - t for t in times]
        
        # Convert speeds to MB/s for readability
        y_data = [s / (1024 * 1024) for s in speeds]
        
        fig.plot(x_data, y_data, label="Speed (MB/s)")
        fig.x_label = "Seconds ago"
        fig.y_label = "MB/s"
        
        # Render graph lines
        graph_str = str(fig)
        for i, line in enumerate(graph_str.split('\n')):
            if y + i < stdscr.getmaxyx()[0]:
                stdscr.addstr(y + i, x, line[:self.width])
        
        # Render stats
        stats_y = y + self.height + 1
        current = speeds[-1] if speeds else 0
        avg = sum(speeds) / len(speeds) if speeds else 0
        peak = max(speeds) if speeds else 0
        
        stdscr.addstr(stats_y, x, f"Current: {self._format_speed(current)}")
        stdscr.addstr(stats_y + 1, x, f"Average: {self._format_speed(avg)}")
        stdscr.addstr(stats_y + 2, x, f"Peak: {self._format_speed(peak)}")
    
    def render_multi_stage(self, stdscr, y: int, x: int, video_id: int):
        """Render stacked graph showing all stages' activity from speed_history."""
        fig = Figure()
        fig.width = self.width
        fig.height = self.height
        
        colors = ['red', 'green', 'blue', 'yellow', 'cyan']
        stages = ["download", "encrypt", "upload"]
        
        for i, stage in enumerate(stages):
            stage_history = self.speed_history_repo.get_speed_history(
                video_id=video_id,
                stage=stage,
                minutes=5
            )
            if stage_history:
                times = [s.timestamp.timestamp() for s in stage_history]
                speeds = [s.speed / (1024 * 1024) for s in stage_history]
                x_data = [time.time() - t for t in times]
                
                fig.plot(x_data, speeds, label=stage, lc=colors[i % len(colors)])
        
        graph_str = str(fig)
        for i, line in enumerate(graph_str.split('\n')):
            if y + i < stdscr.getmaxyx()[0]:
                stdscr.addstr(y + i, x, line[:self.width])
```

**Visual Design:**
```
# Right pane showing speed graph (like aria2tui's detail pane)
┌────────────────────────────────────────────────────────────────┐
│ Big Buck Bunny - Speed History                                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  5.0 ┤                                      ╭─╮                │
│  4.0 ┤                              ╭──────╯  ╰──╮             │
│  3.0 ┤           ╭──╮              ╭╯              ╰─╮          │
│  2.0 ┤    ╭──────╯  ╰──────────────╯                 ╰──╮       │
│  1.0 ┤╭───╯                                             ╰────── │
│  0.0 ┼────────────────────────────────────────────────────────  │
│     60s  45s  30s  15s  now                                     │
│                                                                │
│ Current: 2.4 MiB/s  Average: 1.8 MiB/s  Peak: 5.2 MiB/s        │
│                                                                │
│ Stage Timeline:                                                │
│ [Download]████[Ingest]██[Encrypt]████[Upload]███████►          │
└────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Speed graph queries `speed_history` table
- [ ] Shows 60-second rolling history
- [ ] Y-axis in MB/s (human readable)
- [ ] X-axis shows "seconds ago"
- [ ] Shows current, average, and peak speeds
- [ ] Multi-stage timeline below graph
