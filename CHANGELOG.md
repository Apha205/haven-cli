# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-02-08

### Features

#### TUI (Terminal User Interface)
- Real-time pipeline visualization with live updates
- Support for YouTube and BitTorrent downloads
- Stage-specific progress indicators (download, analyze, encrypt, upload, sync)
- ASCII speed graphs showing download/upload speeds over time
- Video detail view with full pipeline history
- Filter and search capabilities for videos
- Batch operations (retry, remove, export)
- Pipeline analytics dashboard with statistics
- Event log viewer for monitoring system events
- Vim-style keyboard navigation (j/k, g/G, / for search, etc.)

#### Core Functionality
- Event-driven real-time updates using SSE
- Unified download progress interface
- Repository pattern for data access
- Table-based database design
- Thread-safe state management
- Metrics collection and aggregation

### Technical

#### Architecture
- Modular plugin system for archivers
- Configuration system with TOML support
- Repository pattern for database access
- Event-driven architecture for real-time updates
- Refresh strategy with configurable intervals

#### Database
- SQLAlchemy ORM for database operations
- Repository pattern implementation
- Support for SQLite and PostgreSQL

#### Testing
- Comprehensive test suite with pytest
- Unit tests for all core components
- Integration tests for TUI components
- E2E tests for critical user flows

### Dependencies
- Python 3.11+
- Textual >= 0.40.0 (TUI framework)
- Plotille >= 4.0.0 (ASCII graphs)
- Typer >= 0.21.0 (CLI framework)
- Rich >= 14.0.0 (terminal formatting)
- SQLAlchemy >= 2.0.0 (ORM)

---

## Release Notes

### Installation

```bash
pip install haven-cli
```

To use the TUI:
```bash
pip install "haven-cli[tui]"
haven-tui
```

### Documentation

- [User Guide](docs/user-guide.md)
- [TUI User Guide](docs/tui-user-guide.md)
- [Configuration](docs/configuration.md)
- [Keyboard Shortcuts](docs/keyboard-shortcuts.md)
