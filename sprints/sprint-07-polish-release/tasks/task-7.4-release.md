# Task 7.4: Release

**Priority:** Critical
**Estimated Effort:** 1 day

**Description:**
Final release activities and announcement.

## Version 0.1.0 Release

**Release Checklist:**
- [ ] All tests passing
- [ ] Documentation complete
- [ ] CHANGELOG.md updated
- [ ] Version bumped in all files
- [ ] Git tag created
- [ ] GitHub release created
- [ ] PyPI package published

**CHANGELOG.md:**
```markdown
# Changelog

## [0.1.0] - 2024-XX-XX

### Features
- Real-time pipeline visualization
- Support for YouTube and BitTorrent downloads
- Stage-specific progress indicators
- ASCII speed graphs
- Video detail view with full pipeline history
- Filter and search capabilities
- Batch operations (retry, remove, export)
- Pipeline analytics dashboard
- Event log viewer
- Vim-style keyboard navigation

### Technical
- Unified download progress interface
- Repository pattern for data access
- Event-driven real-time updates
- Table-based database design
- Thread-safe state management
```

**Version Bump:**
```bash
# Update version in files
sed -i 's/version = "0.0.1"/version = "0.1.0"/' pyproject.toml
sed -i 's/__version__ = "0.0.1"/__version__ = "0.1.0"/' src/haven_tui/__init__.py
```

## GitHub Release

**Create Git Tag:**
```bash
# Create annotated tag
git tag -a v0.1.0 -m "Release version 0.1.0"

# Push tag
git push origin v0.1.0
```

**Release Notes:**
```markdown
## Haven TUI v0.1.0 - Initial Release

Haven TUI is a terminal user interface for monitoring the Haven video archival pipeline.

### Installation
```bash
pip install haven-tui
```

### Quick Start
```bash
# Start the TUI
haven-tui

# Or use the CLI command
haven tui
```

### Features
- 📊 Real-time pipeline monitoring
- 📈 Speed graphs and statistics
- 🔍 Search and filter videos
- ⚡ Batch operations
- 🎨 Clean terminal UI inspired by aria2tui

### Requirements
- Python 3.9+
- haven-cli (separate installation)

### Links
- [Documentation](https://github.com/haven/haven-tui/blob/main/docs/)
- [Issues](https://github.com/haven/haven-tui/issues)
```

## Announcement

**Channels:**
- [ ] GitHub Discussions
- [ ] Twitter / X
- [ ] Hacker News
- [ ] Reddit (r/python, r/selfhosted)
- [ ] Discord server

**Announcement Template:**
```
🚀 Announcing Haven TUI v0.1.0

A terminal interface for monitoring your video archival pipeline.

Features:
✅ Real-time download progress (YouTube, BitTorrent)
✅ Pipeline stage visualization
✅ ASCII speed graphs
✅ Search and filter
✅ Batch operations

Built with Python and curses, inspired by aria2tui.

pip install haven-tui

https://github.com/haven/haven-tui

#opensource #python #tui
```

## Post-Release

- [ ] Monitor for critical issues
- [ ] Respond to user feedback
- [ ] Plan v0.2.0 features
- [ ] Update roadmap

## Acceptance Criteria:
- [ ] Version 0.1.0 tagged
- [ ] GitHub release created with notes
- [ ] PyPI package published
- [ ] Announcement posted
- [ ] Monitor feedback
