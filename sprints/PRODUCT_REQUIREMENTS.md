# Haven TUI - Product Requirements Document

## Overview

**Haven TUI** is a terminal user interface for visualizing the Haven video archival pipeline. Inspired by aria2tui but designed specifically for multi-stage pipeline visualization rather than download management.

## Key Principles

1. **Visualization-First:** Focus on observing pipeline state, not controlling it
2. **Plugin-Agnostic:** Unified view regardless of video source (YouTube, BitTorrent, etc.)
3. **Real-Time:** Live updates via EventBus integration
4. **Terminal-Native:** Efficient curses-based UI for remote/server environments

## User Personas

### Primary: Archive Operator
- Monitors active video archival operations
- Needs to identify bottlenecks and failures
- Wants quick overview of throughput and queue state

### Secondary: Developer/Debugging
- Inspects pipeline state for troubleshooting
- Views detailed logs and event streams
- Analyzes performance metrics

## Core Features

### MVP (Sprints 1-5)
1. **Pipeline Dashboard:** Real-time view of videos in pipeline
2. **Stage Visualization:** Visual progress through Ingest → Analysis → Encrypt → Upload → Sync
3. **Plugin-Agnostic Downloads:** Unified download progress (YouTube + BitTorrent)
4. **Speed Graphs:** Real-time and historical speed visualization
5. **Video Detail View:** Complete pipeline state for individual videos

### Post-MVP (Sprints 6-7)
1. **Filtering/Search:** Find videos by stage, plugin, status, or text search
2. **Batch Operations:** Multi-select and retry failed operations
3. **Analytics Dashboard:** Historical performance metrics
4. **Event Log:** Real-time pipeline event stream

## UI Design Principles

### Layout (inspired by aria2tui)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ haven-tui v0.1.0 │ Pipeline │ ↓ 12.5 MiB/s ↑ 3.2 MiB/s │ 5 active      │ <- Header
├──────────────────────────────────────────────────────────────────────────┤
│ # │ Title                 │ Stage  │ Progress │ Speed    │ Plugin      │ <- Column headers
├──────────────────────────────────────────────────────────────────────────┤
│ 1 │ ubuntu-22.04.iso      │ DL     │ ████░░░░ │ 2.4MB/s  │ torrent     │ <- Video list
│ 2 │ Big Buck Bunny        │ UL     │ ███████░ │ 1.1MB/s  │ youtube     │
│ 3 │ Creative Commons Mix  │ ENC    │ ███░░░░░ │ 5.6MB/s  │ youtube     │
├──────────────────────────────────────────────────────────────────────────┤
│ [q Quit] [r Refresh] [a Auto] [d Detail] [g Graph] [f Filter] [? Help]  │ <- Footer
└──────────────────────────────────────────────────────────────────────────┘
```

### Stage Indicators
- **Download (DL):** Shows progress bar, speed, ETA
  - BitTorrent: Also shows peers/seeds
  - YouTube: Shows connection count
- **Ingest (I):** pHash calculation progress
- **Analysis (A):** VLM frame processing progress
- **Encrypt (ENC):** Encrypted bytes vs original size
- **Upload (UL):** Filecoin upload progress with sub-stages
- **Sync (S):** Arkiv blockchain sync status

### Color Scheme
```python
STAGE_COLORS = {
    "download": curses.COLOR_BLUE,
    "ingest": curses.COLOR_CYAN,
    "analysis": curses.COLOR_YELLOW,
    "encrypt": curses.COLOR_MAGENTA,
    "upload": curses.COLOR_GREEN,
    "sync": curses.COLOR_WHITE,
    "complete": curses.COLOR_GREEN,
    "error": curses.COLOR_RED,
}
```

## Technical Requirements

### Performance
- List refresh: < 100ms for 1000 videos
- Event processing: < 50ms latency
- Graph rendering: < 20ms
- Startup time: < 2 seconds

### Compatibility
- Terminal: 80x24 minimum, 120x40 recommended
- Python: 3.9+
- Platforms: Linux, macOS, WSL
- Terminal emulators: xterm, gnome-terminal, iTerm2, Windows Terminal

### Dependencies
- Core: curses (stdlib), sqlalchemy, pydantic
- TUI Framework: listpick (same as aria2tui) or textual
- Graphing: plotille

### Deployment Model
**Option: Integrated with haven-cli (recommended)**

The TUI is part of the haven-cli repository, installed as an optional extra:

```bash
# Install haven-cli with TUI support
pip install haven-cli[tui]

# Or install all optional features
pip install haven-cli[all]
```

**Rationale:**
- TUI shares database models directly with haven-cli (no API boundary)
- Uses haven-cli's EventBus for real-time updates
- Tight coupling means same release cycle is appropriate
- Simpler installation for users

**Entry point:**
```bash
haven tui              # Launch TUI
haven tui --help       # TUI options
```

**Alternative considered:** Separate repo (`haven-tui` package)
- Rejected due to tight coupling with haven-cli internals
- Would require stable API between components

## Data Flow

### Pipeline → Database → TUI

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   YouTube       │     │   BitTorrent     │     │   Other         │
│   Plugin        │     │   Plugin         │     │   Plugins       │
└────────┬────────┘     └────────┬─────────┘     └────────┬────────┘
         │                       │                        │
         │  progress_hook        │  session alerts        │
         │  (real-time)          │  (real-time)           │
         ▼                       ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│              DownloadProgressTracker (unified)                  │
│                    (writes to downloads table)                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       │ INSERT/UPDATE downloads, encryption_jobs,
                       │ upload_jobs, etc. + pipeline_snapshots
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Database                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ downloads   │ │ encryption_ │ │ pipeline_   │               │
│  │             │ │ jobs        │ │ snapshots   │               │
│  └──────┬──────┘ └─────────────┘ └──────┬──────┘               │
│         │                               │                       │
│         │  ┌─────────────┐ ┌───────────┴───────┐               │
│         └──┤ upload_jobs │ │ speed_history     │               │
│            │             │ │                   │               │
│            └─────────────┘ └───────────────────┘               │
└──────────────┬───────────────────────┬──────────────────────────┘
               │                       │
               │ 1. EventBus           │ 2. Direct Query
               │    (real-time)        │    (polling backup)
               │                       │
               ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Haven TUI                               │
│  ┌─────────────┐  ┌──────────────────────────────────────────┐  │
│  │ Event       │  │ Repository Layer                          │  │
│  │ Consumer    │  │  - PipelineSnapshotRepository (main view) │  │
│  │             │  │  - DownloadRepository (speed totals)      │  │
│  └──────┬──────┘  │  - JobHistoryRepository (detail view)     │  │
│         │         │  - SpeedHistoryRepository (graphs)        │  │
│         │         └───────────────────┬──────────────────────┘  │
│         │                             │                         │
│         └─────────────────────────────┤                         │
│                                       ▼                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                     StateManager                            │ │
│  │  (in-memory cache from pipeline_snapshots + events)        │ │
│  └──────────────────────────┬─────────────────────────────────┘ │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                     UI Views                                 ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ ││
│  │  │ VideoList   │  │ DetailView  │  │ SpeedGraph          │ ││
│  │  │ (main)      │  │ (single)    │  │ (right pane)        │ ││
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Success Metrics

### Technical
- [ ] Renders correctly on 80x24 terminal
- [ ] Handles 1000+ videos without performance degradation
- [ ] Zero crashes during 24-hour continuous operation
- [ ] < 1 second delay between pipeline event and UI update

### User Experience
- [ ] New user can understand pipeline state in < 30 seconds
- [ ] Common operations require < 3 keypresses
- [ ] Help/Documentation accessible from any screen
- [ ] Color-blind friendly (symbol indicators, not just color)

## Release Milestones

### Sprint 1-2: Foundation (3 weeks)
- Database: Create downloads, encryption_jobs, upload_jobs, analysis_jobs, sync_jobs, pipeline_snapshots, speed_history tables
- Pipeline integration: Update steps to write to job tables
- Unified download progress tracking (writes to downloads table)
- Project architecture

### Sprint 3-4: Core Visualization (3 weeks)
- Pipeline dashboard
- Stage-specific progress indicators
- Speed graphs
- Video detail view

### Sprint 5: Polish (1 week)
- UI components
- Themes
- Keyboard shortcuts

### Sprint 6: Advanced (1.5 weeks)
- Filtering and search
- Batch operations
- Analytics

### Sprint 7: Release (1 week)
- Testing and QA
- Documentation
- Packaging and distribution

**Total Timeline:** ~10 weeks to v0.1.0

## Future Enhancements (Post-v0.1.0)

1. **Remote TUI:** Connect to haven-cli running on another machine via WebSocket
2. **Mobile/Responsive:** Adaptive layout for narrow terminals
3. **Plugin Discovery:** Browse and configure plugins from TUI
4. **Job Scheduling:** View and manage recurring jobs
5. **Notifications:** Desktop notifications for completions/failures

## References

- **aria2tui:** github.com/grimandgreedy/aria2tui
- **haven-cli:** /haven-cli directory
- **listpick:** TUI framework used by aria2tui
- **textual:** Alternative modern TUI framework (rich)
