# Haven TUI - Sprint Planning

This directory contains the sprint planning for Haven TUI, a terminal user interface for visualizing the Haven video archival pipeline.

## Project Overview

**Haven TUI** is inspired by [aria2tui](https://github.com/grimandgreedy/aria2tui) but designed specifically for the Haven video archival pipeline. It provides real-time visualization of videos flowing through multiple pipeline stages (Download → Ingest → Analysis → Encrypt → Upload → Sync) from various source plugins (YouTube, BitTorrent, etc.).

## Sprint Structure

| Sprint | Name | Duration | Focus |
|--------|------|----------|-------|
| Sprint 1 | Foundation & Prerequisites | 2-3 weeks | Enhance haven-cli's data layer for observability |
| Sprint 2 | Core Architecture | 2 weeks | TUI framework, database client, event integration |
| Sprint 3 | Pipeline Visualization | 2 weeks | Main views, speed graphs, video details |
| Sprint 4 | Plugin-Agnostic Data Layer | 1.5 weeks | Normalize YouTube + BitTorrent progress |
| Sprint 5 | TUI Components | 1.5 weeks | Layout system, header, footer, right pane |
| Sprint 6 | Advanced Features | 1 week | Filtering, search, batch operations, analytics |
| Sprint 7 | Polish & Release | 1 week | Testing, documentation, packaging |

**Total Duration:** ~11-12 weeks

## Directory Contents

This sprint planning is for work done **within the haven-cli repository**:

```
# Sprint documentation (this directory)
sprints/
├── README.md                          # This file
├── PRODUCT_REQUIREMENTS.md            # Detailed PRD
├── ARCHITECTURE.md                    # Technical architecture
│
├── 01-prerequisites/                  # Database table creation in haven-cli
│   └── TASKS.md
│
├── sprint-02-architecture/            # Core TUI framework → haven_cli/tui/
│   └── TASKS.md
│
├── sprint-03-pipeline-viz/            # Views → haven_cli/tui/ui/
│   └── TASKS.md
│
├── sprint-04-data-layer/              # Plugin updates in haven-cli
│   └── TASKS.md
│
├── sprint-05-tui-components/          # UI → haven_cli/tui/ui/
│   └── TASKS.md
│
├── sprint-06-advanced-features/       # Advanced TUI features
│   └── TASKS.md
│
└── sprint-07-polish-release/          # Testing & release
    └── TASKS.md

# Code location in haven-cli repo:
haven-cli/src/haven_cli/
├── cli.py                    # Add 'haven tui' command
├── pipeline/                 # Update steps to write to tables
│   └── steps/
├── database/
│   └── models.py             # Add Download, EncryptionJob, etc.
└── tui/                      # NEW: All TUI code here
    ├── __init__.py
    ├── __main__.py
    ├── app.py
    ├── config.py
    ├── models/
    ├── ui/
    ├── data/
    └── utils/
```

## Key Design Decisions

### 1. Deployment: TUI as haven-cli Module
The TUI is **part of the haven-cli repository**, not a separate project:

```
haven-cli/src/haven_cli/
├── __init__.py
├── cli.py              # Existing CLI
├── pipeline/           # Existing pipeline
├── database/           # Existing database models
│   └── models.py       # Video, Download, etc.
└── tui/                # NEW: TUI module
    ├── __init__.py
    ├── app.py
    └── ...
```

**Usage:**
```bash
pip install haven-cli[tui]   # Install with TUI dependencies
haven tui                     # Launch TUI
```

**Rationale:**
- TUI shares database models directly (same Python process)
- Uses haven-cli's EventBus (tight coupling)
- Single release cycle is appropriate
- Simpler for users (one package)

### 2. Table-Based Database Design
Instead of adding nullable columns to the `videos` table, we create dedicated tables:

- **downloads** - Download progress for YouTube, BitTorrent, etc.
- **encryption_jobs** - Lit Protocol encryption progress
- **upload_jobs** - IPFS/Arkiv upload progress
- **analysis_jobs** - VLM/LLM analysis progress
- **sync_jobs** - Blockchain sync progress
- **pipeline_snapshots** - Read-optimized view for TUI queries
- **speed_history** - Time-series data for graphing

This provides clean separation, job history, and efficient querying.

### 2. Plugin-Agnostic View
YouTube downloads and BitTorrent downloads appear identically in the main list:
- Same progress indicators
- Same speed display
- Unified download speed graph

Plugin-specific details (peers/seeds) shown in detail view only.

### 3. Stage-Based Progress
Unlike download managers that show single progress, Haven TUI shows:
- Current pipeline stage
- Stage-specific progress
- Overall pipeline position

### 4. TUI Framework
Options:
- **listpick** (like aria2tui) - battle-tested, curses-based
- **textual** - modern Python TUI framework
- **rich** - terminal formatting, could be base for custom TUI

Recommendation: Start with listpick for familiarity with aria2tui patterns.

## Getting Started

### Prerequisites
1. haven-cli repository cloned
2. Python 3.9+
3. Terminal with curses support

### Installation

The TUI is part of haven-cli, installed as an optional extra:

```bash
# Clone haven-cli
git clone <haven-cli-repo>
cd haven-cli

# Install with TUI support
pip install -e ".[tui]"

# Or install with all optional features
pip install -e ".[all]"
```

### Development Setup
```bash
# Install development dependencies
pip install -e ".[tui,dev]"

# Run TUI tests
pytest tests/tui/

# Run TUI
haven tui

# Or directly
python -m haven_cli.tui
```

## Sprint Execution

### Sprint Planning
Each sprint follows this structure:
1. **Task Review** - Review TASKS.md with team
2. **Estimation** - Assign effort estimates
3. **Assignment** - Assign tasks to developers
4. **Definition of Done** - Clarify acceptance criteria

### Daily Standups
- What did you complete yesterday?
- What are you working on today?
- Any blockers?

### Sprint Review
- Demo completed features
- Gather feedback
- Update product backlog

### Sprint Retrospective
- What went well?
- What could be improved?
- Action items for next sprint

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Haven TUI                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ UI Layer    │  │ State Layer │  │ Data Layer          │  │
│  │             │  │             │  │                     │  │
│  │ - VideoList │  │ - StateMgr  │  │ - PipelineInterface │  │
│  │ - DetailView│  │ - Metrics   │  │ - EventConsumer     │  │
│  │ - SpeedGraph│  │ - Filters   │  │ - Repositories      │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────┘  │
│         │                │                     │            │
│         └────────────────┼─────────────────────┘            │
│                          ▼                                  │
│  ┌────────────────────────────────────────────────────────┐│
│  │                  haven-cli Core                        ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   ││
│  │  │ EventBus    │  │ Pipeline    │  │ Database      │   ││
│  │  │             │  │ Manager     │  │ (SQLite)      │   ││
│  │  └─────────────┘  └─────────────┘  └───────────────┘   ││
│  └────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Monitoring & Debugging

### Logging
```python
import structlog

logger = structlog.get_logger()
logger.info("pipeline_event_received", event_type="upload_progress", video_id=123)
```

### Metrics
- Event processing latency
- Database query times
- UI render times
- Memory usage

### Debug Mode
```bash
HAVEN_TUI_DEBUG=1 python -m haven_tui
```

## Contributing

### Code Style
- Black formatter
- isort imports
- mypy type checking
- flake8 linting

### Testing
- Unit tests: `pytest tests/unit/`
- Integration tests: `pytest tests/integration/`
- UI tests: `pytest tests/ui/` (using pytest-curses)

### Documentation
- Docstrings in Google style
- Architecture Decision Records (ADRs) in `docs/adr/`
- User guide in `docs/user-guide/`

## Resources

### Haven Ecosystem
- **haven-cli** - Command-line interface (this repo)
- **haven-tui** - Terminal UI (this project)
- **haven-backend** - Web API (separate repo)
- **haven-player** - Video player (separate repo)

### External References
- [aria2tui](https://github.com/grimandgreedy/aria2tui) - Inspiration
- [listpick](https://github.com/grimandgreedy/listpick) - TUI framework
- [textual](https://textual.textualize.io/) - Alternative TUI framework
- [rich](https://rich.readthedocs.io/) - Terminal formatting

## Contact

- **Product Owner:** [Name]
- **Tech Lead:** [Name]
- **Slack:** #haven-tui
- **Issues:** GitHub Issues

## License

MIT License - See LICENSE file
