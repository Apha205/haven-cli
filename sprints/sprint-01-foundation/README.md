# Sprint 01: Foundation

## Overview
This sprint establishes the foundational TUI layer by creating the core integration components between the TUI and the existing `haven-cli` pipeline.

## Sprint Goals
1. Create the `haven_tui` package structure
2. Implement the `PipelineInterface` for core pipeline access
3. Build the `StateManager` for real-time state tracking
4. Create the `MetricsCollector` for speed history visualization
5. Implement unified download views and retry logic
6. Comprehensive integration testing

## Tasks

| Task | Title | Effort | Dependencies |
|------|-------|--------|--------------|
| 1 | [Setup haven_tui Package](./tasks/task-01-setup-haven-tui-package.md) | 0.5d | - |
| 2 | [Pipeline Core Interface](./tasks/task-02-pipeline-interface.md) | 2d | Task 1 |
| 3 | [Real-Time State Manager](./tasks/task-03-state-manager.md) | 2d | Task 1, 2 |
| 4 | [Metrics Collector](./tasks/task-04-metrics-collector.md) | 0.5d | Task 1, 3 |
| 5 | [Unified Downloads & Retry](./tasks/task-05-unified-downloads-and-retry.md) | 1d | Task 2, 3 |
| 6 | [Integration Testing](./tasks/task-06-integration-testing.md) | 1d | Task 1-5 |

## Total Effort
**7 days** (revised from original 9 days based on gap analysis)

## Key Components

### PipelineInterface (`haven_tui/core/pipeline_interface.py`)
The primary bridge between TUI and pipeline core. Provides:
- Database query access
- Event subscription management
- Unified download view
- TUI-first operations (retry, cancel, pause)

### StateManager (`haven_tui/core/state_manager.py`)
Thread-safe state management for real-time UI updates:
- In-memory state cache
- Event-driven state updates
- Change notification callbacks
- Speed history tracking per video

### MetricsCollector (`haven_tui/core/metrics.py`)
TUI-facing metrics wrapper:
- Speed history queries
- Aggregate speed calculations
- Chart data formatting

## Existing Foundation (No Work Needed)

The following components are already implemented in `haven-cli`:

| Component | Location | Status |
|-----------|----------|--------|
| Event Bus | `haven_cli/pipeline/events.py` | ✅ Ready |
| Pipeline Manager | `haven_cli/pipeline/manager.py` | ✅ Ready |
| Plugin Manager | `haven_cli/plugins/manager.py` | ✅ Ready |
| Database Models | `haven_cli/database/models.py` | ✅ Ready |
| Repositories | `haven_cli/database/repositories.py` | ✅ Ready |
| Speed History Service | `haven_cli/services/speed_history.py` | ✅ Ready |

## Database Schema Compatibility

The existing database schema fully supports TUI requirements:
- `PipelineSnapshot` table for fast queries
- `SpeedHistory` table for time-series data
- Job tables for all pipeline stages

✅ **No schema changes needed**

## Event System Compatibility

All required event types already exist:
- `DOWNLOAD_PROGRESS`, `ENCRYPT_PROGRESS`, `UPLOAD_PROGRESS`
- `*_COMPLETE`, `*_FAILED` events for all stages
- `PIPELINE_STARTED`, `PIPELINE_COMPLETE`

✅ **No new events needed**

## Success Criteria

- [ ] All 6 tasks completed
- [ ] `haven_tui` package importable and functional
- [ ] Integration tests passing (>80% coverage)
- [ ] Performance test: 100+ videos handled concurrently
- [ ] Documentation complete

## Next Sprint

**Sprint 02: Architecture** - Plugin system, job queue, and core infrastructure.

## References

- [Gap Analysis](../../docs/TUI_GAP_ANALYSIS.md)
- [Architecture Document](../ARCHITECTURE.md)
- [Product Requirements](../PRODUCT_REQUIREMENTS.md)
