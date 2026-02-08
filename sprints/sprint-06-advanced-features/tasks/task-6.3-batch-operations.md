# Task 6.3: Batch Operations

**Priority:** Medium
**Estimated Effort:** 2 days

**Description:**
Allow multi-selecting videos and performing batch operations (like aria2tui's multi-select).

**Operations:**
- Retry failed stages
- Remove from queue
- Force re-process
- Export list

**Implementation:**
```python
class BatchOperations:
    """Handles multi-select and batch operations on videos."""
    
    def __init__(self, state_manager: StateManager, api_client: APIClient):
        self.state = state_manager
        self.api = api_client
        self.selected: Set[int] = set()
    
    def toggle_selection(self, video_id: int):
        """Toggle video selection."""
        if video_id in self.selected:
            self.selected.remove(video_id)
        else:
            self.selected.add(video_id)
    
    def select_all(self, videos: List[VideoView]):
        """Select all visible videos."""
        self.selected = {v.id for v in videos}
    
    def clear_selection(self):
        """Clear all selections."""
        self.selected.clear()
    
    def get_selected(self) -> List[int]:
        """Get list of selected video IDs."""
        return list(self.selected)
    
    async def retry_failed(self) -> BatchResult:
        """Retry failed stages for selected videos."""
        results = BatchResult()
        
        for video_id in self.selected:
            video = self.state.get_video(video_id)
            if video and video.has_error:
                try:
                    await self.api.retry_video(video_id)
                    results.success.append(video_id)
                except Exception as e:
                    results.failed.append((video_id, str(e)))
        
        return results
    
    async def remove_from_queue(self) -> BatchResult:
        """Remove selected videos from pipeline."""
        results = BatchResult()
        
        for video_id in self.selected:
            try:
                await self.api.remove_video(video_id)
                results.success.append(video_id)
            except Exception as e:
                results.failed.append((video_id, str(e)))
        
        self.selected.clear()
        return results
    
    async def force_reprocess(self, stage: PipelineStage = None) -> BatchResult:
        """Force re-process selected videos from given stage."""
        results = BatchResult()
        
        for video_id in self.selected:
            try:
                await self.api.reprocess_video(video_id, from_stage=stage)
                results.success.append(video_id)
            except Exception as e:
                results.failed.append((video_id, str(e)))
        
        return results
    
    def export_list(self, filepath: str):
        """Export selected videos to file."""
        import json
        
        videos = [self.state.get_video(vid) for vid in self.selected]
        data = [
            {
                "id": v.id,
                "title": v.title,
                "stage": v.current_stage.value,
                "progress": v.stage_progress,
                "plugin": v.plugin,
            }
            for v in videos if v
        ]
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

@dataclass
class BatchResult:
    """Result of batch operation."""
    success: List[int] = field(default_factory=list)
    failed: List[tuple[int, str]] = field(default_factory=list)
    
    @property
    def all_succeeded(self) -> bool:
        return len(self.failed) == 0
```

**UI for Batch Operations:**
```
# Multi-select mode indicator
┌─────────────────────────────────────────────────────────────────┐
│ Batch Mode: 5 selected │ [a All] [c Clear] [r Retry] [x Remove] │
├────┬───────────────────────┬──────────┬──────────┬──────────────┤
│ ✓  │ Big Buck Bunny        │ upload   │ ████░░░░ │ ...          │
│ ✓  │ Creative Commons Mix  │ failed   │ ✗ Error  │ ...          │
│    │ Linux Kernel Talk     │ analysis │ ██░░░░░░ │ ...          │
│ ✓  │ Archive Mirror        │ download │ ████████ │ ...          │
└────┴───────────────────────┴──────────┴──────────┴──────────────┘
```

**Acceptance Criteria:**
- [ ] Multi-select works with space key
- [ ] Select all / clear selection works
- [ ] Retry failed works for selected videos
- [ ] Remove from queue works
- [ ] Force re-process works
- [ ] Export list to JSON works
- [ ] Confirmation dialogs for destructive operations
