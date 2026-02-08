# Task 6.2: Sorting Options

**Priority:** Medium
**Estimated Effort:** 1 day

**Description:**
Add sorting options for the video list.

**Sort Fields:**
- Date added (default, newest first)
- Title (alphabetical)
- Progress (most complete first)
- Speed (fastest first)
- Size (largest first)
- Stage (group by pipeline stage)

**Implementation:**
```python
from enum import Enum

class SortField(Enum):
    DATE_ADDED = "date_added"
    TITLE = "title"
    PROGRESS = "progress"
    SPEED = "speed"
    SIZE = "size"
    STAGE = "stage"

class SortOrder(Enum):
    ASCENDING = "asc"
    DESCENDING = "desc"

class VideoSorter:
    """Sorts video list by various criteria."""
    
    def __init__(self):
        self.field = SortField.DATE_ADDED
        self.order = SortOrder.DESCENDING
    
    def sort(self, videos: List[VideoView]) -> List[VideoView]:
        """Sort videos by current field and order."""
        reverse = self.order == SortOrder.DESCENDING
        
        if self.field == SortField.DATE_ADDED:
            return sorted(videos, key=lambda v: v.added_at, reverse=reverse)
        elif self.field == SortField.TITLE:
            return sorted(videos, key=lambda v: v.title.lower(), reverse=reverse)
        elif self.field == SortField.PROGRESS:
            return sorted(videos, key=lambda v: v.stage_progress, reverse=reverse)
        elif self.field == SortField.SPEED:
            return sorted(videos, key=lambda v: v.stage_speed, reverse=reverse)
        elif self.field == SortField.SIZE:
            return sorted(videos, key=lambda v: v.file_size, reverse=reverse)
        elif self.field == SortField.STAGE:
            return sorted(videos, key=lambda v: v.current_stage.value, reverse=reverse)
        
        return videos
    
    def set_sort(self, field: SortField, order: SortOrder = None):
        """Set sort field and optionally order."""
        self.field = field
        if order:
            self.order = order
    
    def toggle_order(self):
        """Toggle between ascending/descending."""
        if self.order == SortOrder.ASCENDING:
            self.order = SortOrder.DESCENDING
        else:
            self.order = SortOrder.ASCENDING
```

**UI for Sorting:**
```
# Sort dialog
┌───────────────────────────────────┐
│ Sort by:                          │
│   [d] Date added (newest first)   │
│   [t] Title (A-Z)                 │
│   [p] Progress (most complete)    │
│   [s] Speed (fastest first)       │
│   [z] Size (largest first)        │
│   [g] Stage (grouped)             │
│                                   │
│   [r] Reverse order               │
└───────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Sort by date added works
- [ ] Sort by title works
- [ ] Sort by progress works
- [ ] Sort by speed works
- [ ] Sort by size works
- [ ] Sort by stage works
- [ ] Reverse order works
