# Task 6: Integration Testing & Validation

## Overview
Create comprehensive integration tests for the TUI foundation layer. Ensure all components work together correctly and handle edge cases properly.

## Requirements

### Test Categories

#### 1. PipelineInterface Integration Tests
```python
class TestPipelineInterfaceIntegration:
    """Integration tests for PipelineInterface."""
    
    async def test_context_manager_initializes_resources()
    async def test_context_manager_cleans_up_on_exit()
    async def test_get_active_videos_returns_videos()
    async def test_search_videos_filters_correctly()
    async def test_unified_downloads_combines_sources()
    async def test_retry_video_resets_stages()
    async def test_cancel_video_stops_operations()
    async def test_event_subscription_works()
```

#### 2. StateManager Integration Tests
```python
class TestStateManagerIntegration:
    """Integration tests for StateManager."""
    
    async def test_initializes_from_database()
    async def test_updates_state_on_progress_event()
    async def test_notifies_on_state_change()
    async def test_handles_multiple_simultaneous_updates()
    async def test_cleanup_unsubscribes_events()
    async def test_handles_missing_video_gracefully()
```

#### 3. MetricsCollector Integration Tests
```python
class TestMetricsCollectorIntegration:
    """Integration tests for MetricsCollector."""
    
    async def test_records_speed_from_events()
    async def test_get_speed_history_returns_correct_range()
    async def test_aggregate_speeds_calculate_correctly()
    async def test_chart_data_formatted_correctly()
```

#### 4. End-to-End Tests
```python
class TestTuiFoundationE2E:
    """End-to-end tests for the complete foundation layer."""
    
    async def test_full_video_lifecycle()
    """Test: Video ingested -> download -> encrypt -> upload.
    Verify state updates at each stage.
    """
    
    async def test_retry_flow()
    """Test: Video fails at encrypt -> retry from encrypt -> completes.
    Verify state resets and re-updates correctly.
    """
    
    async def test_concurrent_videos()
    """Test: 50 videos processing simultaneously.
    Verify state manager handles load without errors.
    """
```

### Deliverables
- [ ] Create `tests/tui/` directory for TUI-specific tests
- [ ] Implement integration tests for PipelineInterface
- [ ] Implement integration tests for StateManager
- [ ] Implement integration tests for MetricsCollector
- [ ] Implement end-to-end lifecycle tests
- [ ] Add performance test for concurrent videos
- [ ] Document test fixtures and helpers
- [ ] Ensure all tests pass in CI

## Technical Details

### Test Fixtures
```python
@pytest.fixture
async def pipeline_interface(tmp_db_path):
    """Create a PipelineInterface with test database."""
    interface = PipelineInterface(database_path=tmp_db_path)
    async with interface:
        yield interface

@pytest.fixture
async def state_manager(pipeline_interface):
    """Create an initialized StateManager."""
    manager = StateManager(pipeline_interface)
    await manager.initialize()
    yield manager
    await manager.shutdown()

@pytest.fixture
def mock_event_bus():
    """Create a mock event bus for testing."""
    return MockEventBus()
```

### Mock Event Bus for Testing
```python
class MockEventBus:
    """Mock event bus for testing without full pipeline."""
    
    def __init__(self):
        self._subscribers = defaultdict(list)
        self._history = []
    
    def subscribe(self, event_type, handler):
        self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type, handler):
        self._subscribers[event_type].remove(handler)
    
    async def publish(self, event):
        self._history.append(event)
        for handler in self._subscribers.get(event.type, []):
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
    
    def simulate_download_progress(self, video_id, progress, speed):
        """Helper to simulate download progress events."""
        event = Event(
            type=EventType.DOWNLOAD_PROGRESS,
            video_id=video_id,
            progress=progress,
            speed=speed
        )
        asyncio.create_task(self.publish(event))
```

### Performance Test
```python
async def test_concurrent_videos_performance():
    """Test state manager with many concurrent videos."""
    import time
    
    interface = PipelineInterface(...)
    state_manager = StateManager(interface)
    await state_manager.initialize()
    
    # Create 100 videos
    video_ids = []
    for i in range(100):
        video_id = await create_test_video(f"Video {i}")
        video_ids.append(video_id)
    
    # Simulate rapid events
    start = time.time()
    for video_id in video_ids:
        await event_bus.publish(DownloadProgressEvent(
            video_id=video_id,
            progress=50.0,
            speed=1000000
        ))
    
    # All updates should complete quickly
    elapsed = time.time() - start
    assert elapsed < 1.0, f"State updates too slow: {elapsed}s"
    
    # Verify all states updated
    for video_id in video_ids:
        state = state_manager.get_video(video_id)
        assert state.download_progress == 50.0
```

### Test Helpers
```python
async def create_test_video(title: str, status: str = "pending") -> int:
    """Helper to create a test video in the database."""
    # Implementation

async def create_test_download(video_id: int, source_type: str = "youtube") -> int:
    """Helper to create a test download job."""
    # Implementation

def wait_for_state_change(callback_mock, timeout: float = 1.0):
    """Helper to wait for state change callback."""
    # Implementation
```

## Dependencies
- Task 1-5: All foundation components

## Estimated Effort
1 day

## Acceptance Criteria
- [ ] Integration tests cover all public methods
- [ ] End-to-end tests verify complete workflows
- [ ] Performance test validates concurrent video handling
- [ ] Test coverage > 80% for TUI core modules
- [ ] All tests pass in CI environment
- [ ] Tests run in < 30 seconds total
- [ ] Documentation for running tests

## Related
- Parent: Sprint 01 - Foundation
- Previous: Task 5 (Unified Downloads & Retry)
- Gap Analysis: Section "Phase 4: Testing & Polish"
