# Task 4: Metrics Collector Wrapper

## Overview
Implement the `MetricsCollector` class - a thin TUI-facing wrapper around the existing `SpeedHistoryService`. This provides a simplified interface for the TUI to access speed history and aggregate metrics.

## Requirements

### MetricsCollector Class
```python
from typing import Dict, List, Optional, Tuple
from datetime import datetime

class MetricsCollector:
    """TUI-facing metrics collector.
    
    Thin wrapper around SpeedHistoryService that provides
    simplified access for visualization components.
    """
    
    def __init__(self, service: SpeedHistoryService, max_history_seconds: int = 300)
    
    # Recording (typically called by StateManager)
    def record_speed(video_id: int, stage: str, speed: float, progress: float = 0)
    
    # Per-video queries
    def get_speed_history(
        video_id: int, 
        stage: str, 
        seconds: int = 60
    ) -> List[Tuple[datetime, float]]
    """Get speed history for a specific video and stage.
    
    Returns: List of (timestamp, speed_bps) tuples
    """
    
    def get_current_speed(video_id: int, stage: str) -> Optional[float]
    """Get most recent speed for video/stage."""
    
    # Aggregate queries
    def get_aggregate_speeds(seconds: int = 60) -> Dict[str, float]
    """Get aggregate speeds across all videos.
    
    Returns: {
        'download': float,  # bytes/sec
        'encrypt': float,
        'upload': float,
        'total': float
    }
    """
    
    def get_active_stages(seconds: int = 60) -> Dict[str, int]
    """Get count of videos in each active stage.
    
    Returns: {
        'download': int,
        'encrypt': int,
        'upload': int,
        'total_active': int
    }
    """
    
    # Visualization helpers
    def get_speed_data_for_chart(
        video_id: Optional[int] = None,
        stage: Optional[str] = None,
        seconds: int = 60,
        bucket_size: int = 5  # seconds per bucket
    ) -> Dict
    """Get formatted data for charting libraries.
    
    Returns: {
        'timestamps': List[datetime],
        'speeds': List[float],
        'avg_speed': float,
        'peak_speed': float
    }
    """
    
    # Maintenance
    def cleanup_old_data(hours: int = 24)
    """Clean up old metrics data."""
```

### Deliverables
- [ ] Implement `MetricsCollector` class
- [ ] Implement speed recording method
- [ ] Implement per-video speed history queries
- [ ] Implement aggregate speed queries
- [ ] Implement visualization helpers
- [ ] Write unit tests

## Technical Details

### Wrapper Implementation
```python
from haven_cli.services.speed_history import SpeedHistoryService

class MetricsCollector:
    def __init__(self, service: SpeedHistoryService, max_history_seconds: int = 300):
        self._service = service
        self._max_history = max_history_seconds
        
    def record_speed(self, video_id: int, stage: str, speed: float, progress: float = 0):
        """Record speed sample - delegates to service."""
        self._service.record_sample(
            video_id=video_id,
            stage=stage,
            speed=int(speed),
            progress=progress,
            bytes_processed=0  # Can be calculated if needed
        )
```

### Data Transformation
```python
def get_speed_history(
    self, 
    video_id: int, 
    stage: str, 
    seconds: int = 60
) -> List[Tuple[datetime, float]]:
    """Transform service output to TUI format."""
    minutes = max(1, seconds // 60)
    records = self._service.get_speed_history(video_id, stage, minutes)
    
    return [(r.timestamp, float(r.speed)) for r in records]

def get_aggregate_speeds(self, seconds: int = 60) -> Dict[str, float]:
    """Get aggregate speeds from all stages."""
    minutes = max(1, seconds // 60)
    
    aggregates = {
        'download': 0.0,
        'encrypt': 0.0,
        'upload': 0.0,
        'total': 0.0
    }
    
    for stage in ['download', 'encrypt', 'upload']:
        stage_data = self._service.get_aggregate_speeds(stage, minutes)
        # Calculate average from bucketed data
        if stage_data:
            avg_speed = sum(d['avg_speed'] for d in stage_data) / len(stage_data)
            aggregates[stage] = avg_speed
            aggregates['total'] += avg_speed
    
    return aggregates
```

### Chart Data Formatting
```python
def get_speed_data_for_chart(
    self,
    video_id: Optional[int] = None,
    stage: Optional[str] = None,
    seconds: int = 60,
    bucket_size: int = 5
) -> Dict:
    """Format speed data for chart rendering."""
    if video_id and stage:
        data = self.get_speed_history(video_id, stage, seconds)
    else:
        # Aggregate data across all videos
        data = self._get_aggregate_history(seconds)
    
    timestamps = [d[0] for d in data]
    speeds = [d[1] for d in data]
    
    return {
        'timestamps': timestamps,
        'speeds': speeds,
        'avg_speed': sum(speeds) / len(speeds) if speeds else 0,
        'peak_speed': max(speeds) if speeds else 0,
        'current_speed': speeds[-1] if speeds else 0
    }
```

## Dependencies
- Task 1: Setup haven_tui Package Structure
- Task 3: State Manager (for integration, though can be developed independently)

## Estimated Effort
0.5 days

## Acceptance Criteria
- [ ] MetricsCollector wraps SpeedHistoryService
- [ ] Speed history queries return correct time range
- [ ] Aggregate speeds calculate correctly across all stages
- [ ] Chart data formatted for easy rendering
- [ ] Unit tests cover all query methods
- [ ] Integration test shows metrics flow from events to collector

## Related
- Parent: Sprint 01 - Foundation
- Previous: Task 3 (State Manager)
- Next: Task 5 (Unified Downloads & Retry Logic)
- Gap Analysis: Section "Task 13: Speed History & Metrics"
