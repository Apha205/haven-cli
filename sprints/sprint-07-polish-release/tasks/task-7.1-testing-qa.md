# Task 7.1: Testing & QA

**Priority:** Critical
**Estimated Effort:** 3 days

**Description:**
Comprehensive testing and quality assurance before release.

## Unit Tests

- [ ] Test all repositories (>80% coverage)
  - PipelineSnapshotRepository
  - DownloadRepository
  - JobHistoryRepository
  - SpeedHistoryRepository

- [ ] Test event consumer
  - Event subscription/unsubscription
  - State updates
  - Thread safety

- [ ] Test configuration system
  - Config loading
  - Default creation
  - Environment overrides

## Integration Tests

- [ ] Test with haven-cli
  - Database integration
  - Event bus integration
  - Plugin communication

- [ ] End-to-end pipeline scenarios
  - YouTube download flow
  - BitTorrent download flow
  - Encryption flow
  - Upload flow

## Manual Testing

- [ ] Terminal sizes
  - Minimum 80x24
  - Standard 100x30
  - Large 150x40
  - Resizing behavior

- [ ] Performance testing
  - 100 videos in pipeline
  - 1000 videos in pipeline
  - Graph rendering performance
  - Memory usage

## Test Files Structure

```
tests/
├── unit/
│   ├── test_repositories.py
│   ├── test_event_consumer.py
│   ├── test_state_manager.py
│   ├── test_config.py
│   └── test_ui_components.py
├── integration/
│   ├── test_database_integration.py
│   ├── test_event_bus.py
│   └── test_end_to_end.py
└── fixtures/
    ├── sample_videos.py
    └── sample_events.py
```

## Acceptance Criteria:
- [ ] Unit test coverage >80%
- [ ] All integration tests pass
- [ ] Manual testing completed on different terminals
- [ ] Performance benchmarks met
- [ ] No critical or high severity bugs
