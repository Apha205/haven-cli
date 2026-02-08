# Task 3.1: Main Video List View (Pipeline Overview)

**Priority:** Critical
**Estimated Effort:** 4 days

**Description:**
Create the primary view - a scrollable list of videos showing their current pipeline stage and progress, inspired by aria2tui's download list. Queries from `PipelineSnapshot` and `downloads` tables.

**Design Reference (from aria2tui):**
- aria2tui shows: GID, Name, Status, Progress, Speed, Size, Connections
- For haven-tui: Title, Current Stage, Stage Progress, Speed, Plugin, Size

**Implementation:**
```python
# src/haven_tui/ui/views/video_list.py
from listpick.listpick_app import Picker
from listpick.utils.picker_state import DynamicPickerState

class VideoListView:
    """Main video list view - the primary TUI screen."""
    
    def __init__(self, state_manager: StateManager, config: HavenTUIConfig):
        self.state = state_manager
        self.config = config
        self._setup_picker()
    
    def _setup_picker(self):
        """Configure listpick Picker for video list."""
        self.picker = Picker(
            stdscr=None,  # Set at render time
            title="Haven Pipeline",
            header=self._build_header(),
            items=[],  # Populated dynamically
            
            # Dynamic data function (like aria2tui's downloads_data)
            refresh_function=self._get_video_data,
            auto_refresh=True,
            timer=self.config.refresh_rate,
            
            # Display configuration
            colour_theme_number=0,
            number_columns=True,
            max_selected=100,  # Multi-select for batch operations
        )
    
    def _build_header(self) -> list[str]:
        """Build column headers."""
        return ["#", "Title", "Stage", "Progress", "Speed", "Plugin", "Size", "ETA"]
    
    def _get_video_data(self, *args) -> tuple[list[list[str]], list[str]]:
        """Fetch and format video data for display from state manager."""
        videos = self.state.get_videos(
            filter_fn=lambda v: not v.is_complete or self.config.show_completed
        )
        
        items = []
        for i, video in enumerate(videos, 1):
            row = [
                str(i),
                self._truncate(video.title, 35),
                video.current_stage.value,
                self._format_progress(video.stage_progress),
                video.formatted_speed,
                video.plugin[:10],
                self._format_size(video.file_size),
                video.formatted_eta
            ]
            items.append(row)
        
        return items, self._build_header()
    
    def _format_progress(self, progress: float) -> str:
        """Format progress bar like aria2tui."""
        if progress == 0:
            return "░░░░░░░░░░ 0%"
        elif progress >= 100:
            return "██████████ 100%"
        else:
            # Animated progress bar
            filled = int(progress / 10)
            bar = "█" * filled + "░" * (10 - filled)
            return f"{bar} {progress:.1f}%"
    
    def _format_speed(self, speed: int) -> str:
        """Format speed in human-readable form."""
        if speed == 0:
            return "-"
        return self._human_readable_bytes(speed) + "/s"
    
    def render(self, stdscr):
        """Render the video list."""
        self.picker.stdscr = stdscr
        selected, _, _ = self.picker.run()
        return selected
```

**Visual Design (ASCII Mockup):**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Haven Pipeline - 12 active videos                                    [? Help]│
├────┬───────────────────────┬──────────┬──────────┬────────┬─────────┬───────┤
│ #  │ Title                 │ Stage    │ Progress │ Speed  │ Plugin  │ Size  │
├────┼───────────────────────┼──────────┼──────────┼────────┼─────────┼───────┤
│ 1  │ ubuntu-22.04.iso      │ download │ █████░░░░░ 45%  │ 2.4MB/s│ torrent │ 3.2GB │
│ 2  │ Big Buck Bunny        │ upload   │ ███████░░░ 68%  │ 1.1MB/s│ youtube │ 450MB │
│ 3  │ Creative Commons Mix  │ encrypt  │ ████░░░░░░ 38%  │ 5.6MB/s│ youtube │ 1.1GB │
│ 4  │ Linux Kernel Talk     │ analysis │ ██░░░░░░░░ 15%  │ -      │ youtube │ 280MB │
│ 5  │ Archive Mirror        │ download │ █████████░ 92%  │ 890KB/s│ torrent │ 8.4GB │
│ 6  │ Blender Tutorial      │ ingest   │ ██████████ 100% │ -      │ youtube │ 120MB │
└────┴───────────────────────┴──────────┴──────────┴────────┴─────────┴───────┘
 [q Quit] [r Refresh] [a Auto-refresh: ON] [d Details] [f Filter] [s Sort]
```

**Acceptance Criteria:**
- [ ] List displays all active videos from PipelineSnapshot table
- [ ] Columns: #, Title, Stage, Progress, Speed, Plugin, Size, ETA
- [ ] Progress bar shows visual progress per stage
- [ ] Auto-refresh updates every N seconds
- [ ] Supports multi-selection (like aria2tui)
- [ ] Color coding for different stages
