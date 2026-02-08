# Task 1: Setup haven_tui Package Structure

## Overview
Create the foundational package structure for the TUI layer. This is the entry point for all TUI development.

## Requirements

### Directory Structure
```
haven_tui/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── pipeline_interface.py    # Task 2
│   ├── state_manager.py         # Task 3
│   └── metrics.py               # Task 4
└── pyproject.toml (or update root pyproject.toml)
```

### Deliverables
- [ ] Create `haven_tui/` directory at project root
- [ ] Create `haven_tui/__init__.py` with package exports
- [ ] Create `haven_tui/core/__init__.py`
- [ ] Update root `pyproject.toml` to include the new package
- [ ] Verify package can be imported: `from haven_tui import PipelineInterface`

## Technical Details

### Package Exports (haven_tui/__init__.py)
```python
"""Haven TUI - Terminal User Interface for Haven Video Pipeline."""

__version__ = "0.1.0"

# These will be implemented in subsequent tasks
from .core.pipeline_interface import PipelineInterface
from .core.state_manager import StateManager, VideoState
from .core.metrics import MetricsCollector

__all__ = [
    "PipelineInterface",
    "StateManager",
    "VideoState",
    "MetricsCollector",
]
```

### pyproject.toml Update
Add to `[tool.setuptools.packages.find]` or similar section to ensure the package is included in the distribution.

## Dependencies
- None (this is the foundation task)

## Estimated Effort
0.5 days

## Acceptance Criteria
- [ ] Package structure exists as specified
- [ ] Can import from haven_tui without errors
- [ ] All modules are importable (even if empty/stubs)
- [ ] Tests can import from haven_tui

## Related
- Parent: Sprint 01 - Foundation
- Next: Task 2 (Pipeline Interface)
- Gap Analysis: Section "Phase 1: Foundation"
