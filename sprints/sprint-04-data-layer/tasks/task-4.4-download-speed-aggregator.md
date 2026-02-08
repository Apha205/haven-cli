# Task 4.4: Create Download Speed Aggregator

**Priority:** P1 (High)  
**Owner:** Engineer  
**Effort:** 2 days

**Description:**
Create service that aggregates download speeds from the `downloads` table and `speed_history` table for TUI display.

**Implementation:**

```python
# src/haven_tui/data/speed_aggregator.py

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional
import time
from sqlalchemy import func

@dataclass
class SpeedSample:
    """Single speed measurement."""
    timestamp: float
    video_id: int
    stage: str
    download_rate: float
    upload_rate: float

class SpeedAggregator:
    """
    Aggregates download/upload speeds from downloads and speed_history tables.
    
    Maintains rolling window of samples for graphing and averaging.
    """
    
    def __init__(self, db_session_factory, window_seconds: int = 60):
        self.db_session_factory = db_session_factory
        self.window_seconds = window_seconds
        self._samples: deque[SpeedSample] = deque()
        self._lock = threading.RLock()
    
    def sample_from_downloads_table(self):
        """Sample current speeds from downloads table."""
        with self.db_session_factory() as session:
            active = session.query(Download).filter(
                Download.status == "downloading"
            ).all()
            
            for download in active:
                self.add_sample(
                    video_id=download.video_id,
                    stage="download",
                    download_rate=download.download_rate or 0,
                    upload_rate=download.upload_rate or 0
                )
    
    def add_sample(self, video_id: int, stage: str, 
                   download_rate: float, upload_rate: float = 0):
        """Add a speed sample from a source."""
        with self._lock:
            sample = SpeedSample(
                timestamp=time.time(),
                video_id=video_id,
                stage=stage,
                download_rate=download_rate,
                upload_rate=upload_rate
            )
            
            self._samples.append(sample)
            self._cleanup_old_samples()
    
    def _cleanup_old_samples(self):
        """Remove samples older than window."""
        cutoff = time.time() - self.window_seconds
        while self._samples and self._samples[0].timestamp < cutoff:
            self._samples.popleft()
    
    def get_current_speeds(self) -> tuple[float, float]:
        """Get current aggregate download and upload speeds."""
        # Query downloads table for most recent
        with self.db_session_factory() as session:
            result = session.query(
                func.sum(Download.download_rate),
                func.sum(Download.upload_rate)
            ).filter(
                Download.status == "downloading"
            ).first()
            
            return (result[0] or 0.0, result[1] or 0.0)
    
    def get_average_speeds(self, window_seconds: int = None) -> tuple[float, float]:
        """Get average speeds from speed_history table."""
        from datetime import datetime, timedelta
        
        since = datetime.now() - timedelta(
            seconds=window_seconds or self.window_seconds
        )
        
        with self.db_session_factory() as session:
            result = session.query(
                func.avg(SpeedHistory.speed)
            ).filter(
                SpeedHistory.timestamp >= since,
                SpeedHistory.stage == "download"
            ).scalar()
            
            return (result or 0.0, 0.0)
    
    def get_speed_history(self, video_id: Optional[int] = None,
                          resolution_seconds: int = 1) -> List[tuple[float, float, float]]:
        """
        Get speed history for graphing from speed_history table.
        
        Returns: List of (timestamp, download_rate, upload_rate)
        """
        from datetime import datetime, timedelta
        
        since = datetime.now() - timedelta(seconds=self.window_seconds)
        
        with self.db_session_factory() as session:
            query = session.query(SpeedHistory).filter(
                SpeedHistory.timestamp >= since
            )
            
            if video_id:
                query = query.filter(SpeedHistory.video_id == video_id)
            
            samples = query.order_by(SpeedHistory.timestamp).all()
            
            # Transform to (timestamp, speed, 0) format
            return [
                (s.timestamp.timestamp(), s.speed, 0) 
                for s in samples
            ]
```

**Integration with TUI:**
```python
# In TUI main loop or refresh handler

async def update_speed_display(self):
    """Update speed graph and totals."""
    # Sample from downloads table
    self.speed_aggregator.sample_from_downloads_table()
    
    # Get history for graph from speed_history table
    history = self.speed_aggregator.get_speed_history(
        video_id=self.selected_video_id,
        resolution_seconds=1
    )
    
    # Update UI
    self.speed_graph.set_data(history)
    
    # Update totals display from downloads table
    total_down, total_up = self.speed_aggregator.get_current_speeds()
    self.header.set_speeds(total_down, total_up)
```

**Acceptance Criteria:**
- [ ] Aggregates speeds from `downloads` table
- [ ] Writes samples to `speed_history` table
- [ ] Rolling window of configurable duration
- [ ] Provides data in format suitable for graphing
- [ ] Thread-safe for concurrent updates
