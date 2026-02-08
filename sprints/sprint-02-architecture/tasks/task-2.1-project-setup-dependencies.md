# Task 2.1: Project Setup and Dependencies

**Sprint:** 2 - TUI Core Architecture  
**Priority:** Critical  
**Estimated Effort:** 1 day

---

## Description
Set up the TUI as part of the haven-cli repository. The TUI is an optional component that shares the same database and models.

## Location within haven-cli repo:
```
haven-cli/
├── src/
│   └── haven_cli/
│       ├── __init__.py
│       ├── cli.py             # Existing CLI commands
│       ├── pipeline/          # Existing pipeline code
│       ├── database/          # Existing database models
│       │   └── models.py      # Video, Download, etc.
│       └── tui/               # NEW: TUI module
│           ├── __init__.py
│           ├── __main__.py    # Entry point: python -m haven_cli.tui
│           ├── app.py         # Main TUI application
│           ├── config.py      # TUI configuration
│           ├── models/        # TUI view models
│           ├── ui/            # UI components
│           ├── data/          # Repositories, event consumers
│           └── utils/         # Utilities
├── pyproject.toml
└── tests/
    └── tui/                   # TUI tests
```

## pyproject.toml changes:
```toml
[project.optional-dependencies]
tui = [
    "listpick >= 1.0.0",       # TUI picker framework
    "plotille >= 4.0.0",       # ASCII graphs
    "textual >= 0.40.0",       # Alternative: modern TUI framework
]
all = ["haven-cli[tui]"]

[project.scripts]
haven = "haven_cli.cli:main"

# Entry point for: python -m haven_cli.tui
```

## CLI Integration:
Add to existing haven CLI:
```python
# src/haven_cli/cli.py

@click.group()
def cli():
    """Haven video archival pipeline."""
    pass

# Existing commands...
@cli.command()
@click.option('--config', '-c', help='TUI config file')
def tui(config):
    """Launch the Terminal User Interface."""
    from haven_cli.tui.app import TUIApp
    app = TUIApp(config_file=config)
    app.run()
```

## Acceptance Criteria:
- [ ] TUI module created at `haven_cli/tui/`
- [ ] `pip install -e ".[tui]"` installs TUI dependencies
- [ ] `haven tui` command launches the TUI
- [ ] `python -m haven_cli.tui` also works
- [ ] Imports work: `from haven_cli.database.models import Download`
- [ ] Basic config loading functional
