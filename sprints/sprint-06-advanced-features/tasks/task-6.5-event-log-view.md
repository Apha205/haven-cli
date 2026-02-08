# Task 6.5: Event Log View

**Priority:** Medium
**Estimated Effort:** 2 days

**Description:**
View showing recent pipeline events (like a system log).

**Features:**
- Real-time event stream
- Filter by event type
- Search log messages
- Export logs

**Implementation:**
```python
# src/haven_tui/ui/views/event_log.py

class EventLogView:
    """Real-time event log view."""
    
    def __init__(self, event_bus: EventBus, max_entries: int = 1000):
        self.event_bus = event_bus
        self.max_entries = max_entries
        self.entries: deque[LogEntry] = deque(maxlen=max_entries)
        self.filter: Optional[EventType] = None
        self.search_query: str = ""
        self._unsubscribe = None
    
    def start(self):
        """Start listening to events."""
        self._unsubscribe = self.event_bus.subscribe_all(self._on_event)
    
    def stop(self):
        """Stop listening to events."""
        if self._unsubscribe:
            self._unsubscribe()
    
    def _on_event(self, event: Event):
        """Handle incoming event."""
        entry = LogEntry(
            timestamp=datetime.now(),
            event_type=event.type,
            message=self._format_event(event),
            level=self._get_level(event)
        )
        self.entries.append(entry)
    
    def render(self, stdscr):
        """Render event log."""
        max_y, max_x = stdscr.getmaxyx()
        
        # Header with filter info
        header = f"Event Log [{len(self.entries)} entries]"
        if self.filter:
            header += f" (filtered: {self.filter.value})"
        stdscr.addstr(0, 0, header.ljust(max_x-1), curses.A_REVERSE)
        
        # Filter entries
        entries = self._get_filtered_entries()
        
        # Render entries
        for i, entry in enumerate(entries[-(max_y-2):]):
            y = i + 1
            color = self._get_color(entry.level)
            line = self._format_entry(entry, max_x - 2)
            stdscr.addstr(y, 0, line, color)
    
    def _get_filtered_entries(self) -> List[LogEntry]:
        """Get entries matching current filter."""
        entries = list(self.entries)
        
        if self.filter:
            entries = [e for e in entries if e.event_type == self.filter]
        
        if self.search_query:
            entries = [e for e in entries 
                      if self.search_query.lower() in e.message.lower()]
        
        return entries
    
    def _format_entry(self, entry: LogEntry, max_width: int) -> str:
        """Format log entry for display."""
        time_str = entry.timestamp.strftime("%H:%M:%S")
        type_str = entry.event_type.value[:10].ljust(10)
        msg = entry.message[:max_width - 25]
        return f"{time_str} | {type_str} | {msg}"
    
    def set_filter(self, event_type: Optional[EventType]):
        """Set event type filter."""
        self.filter = event_type
    
    def set_search(self, query: str):
        """Set search query."""
        self.search_query = query
    
    def export(self, filepath: str):
        """Export log to file."""
        with open(filepath, 'w') as f:
            for entry in self.entries:
                f.write(f"{entry.timestamp.isoformat()} | "
                       f"{entry.event_type.value} | "
                       f"{entry.message}\n")

@dataclass
class LogEntry:
    """Single log entry."""
    timestamp: datetime
    event_type: EventType
    message: str
    level: str  # info, warning, error
```

**Visual Design:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Event Log [342 entries] (filtered: DOWNLOAD_PROGRESS)                    │
├─────────────────────────────────────────────────────────────────────────┤
│ 14:23:01 | download_pr | Big Buck Bunny - 45% - 2.4MB/s                │
│ 14:23:02 | download_pr | Creative Commons Mix - 12% - 1.1MB/s          │
│ 14:23:03 | download_pr | Big Buck Bunny - 46% - 2.5MB/s                │
│ 14:23:04 | download_pr | Archive Mirror - 78% - 890KB/s                │
│ 14:23:05 | download_pr | Big Buck Bunny - 48% - 2.4MB/s                │
│ 14:23:06 | download_pr | Creative Commons Mix - 15% - 1.2MB/s          │
│ 14:23:07 | encrypt_pro | Encrypting Linux Kernel Talk - 5%             │
│ 14:23:08 | download_pr | Big Buck Bunny - 50% - 2.3MB/s                │
│ 14:23:09 | upload_prog | Uploading Archive Mirror - 23%                │
│ ...                                                                      │
│                                                                          │
│ [f Filter] [/ Search] [e Export] [c Clear] [q Back]                     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Real-time event stream displays
- [ ] Filter by event type works
- [ ] Search log messages works
- [ ] Export to file works
- [ ] Clear log works
- [ ] Auto-scrolls to latest entries
- [ ] Color-coded by severity
