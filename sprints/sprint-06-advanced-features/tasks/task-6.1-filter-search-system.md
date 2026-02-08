# Task 6.1: Filter and Search System

**Priority:** High
**Estimated Effort:** 3 days

**Description:**
Add filtering and search capabilities to the video list.

**Features:**
- Filter by stage (Download, Ingest, Encrypt, etc.)
- Filter by plugin (YouTube, BitTorrent, etc.)
- Filter by status (Active, Completed, Failed)
- Text search (title, URI, CID)
- Quick filters (Show/Hide completed, Show errors only)

**Implementation:**
```python
class FilterState:
    """Current filter configuration."""
    stage: Optional[PipelineStage] = None
    plugin: Optional[str] = None
    status: Optional[StageStatus] = None
    search_query: str = ""
    show_completed: bool = False
    show_failed: bool = True

class VideoListController:
    """Controller for video list with filtering."""
    
    def get_filtered_videos(self, filter: FilterState) -> List[VideoView]:
        """Apply filters to video list."""
        videos = self.state.get_all_videos()
        
        if filter.stage:
            videos = [v for v in videos if v.current_stage == filter.stage]
        
        if filter.plugin:
            videos = [v for v in videos if v.plugin == filter.plugin]
        
        if filter.status:
            videos = [v for v in videos 
                     if v.current_stage_info.status == filter.status]
        
        if not filter.show_completed:
            videos = [v for v in videos if not v.is_complete]
        
        if filter.search_query:
            videos = self._search_videos(videos, filter.search_query)
        
        return videos
    
    def _search_videos(self, videos: List[VideoView], query: str) -> List[VideoView]:
        """Text search across video fields and job tables."""
        query = query.lower()
        results = []
        
        for v in videos:
            # Basic fields
            if query in v.title.lower():
                results.append(v)
                continue
            if hasattr(v, 'source_uri') and query in v.source_uri.lower():
                results.append(v)
                continue
            
            # Search in upload_jobs table for CID
            cid = self.job_repo.get_latest_cid(v.id)
            if cid and query in cid.lower():
                results.append(v)
                continue
        
        return results
```

**UI for Filters:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Filters: [All Stages ▼] [All Plugins ▼] [Active] [✓ Completed]  │
│ Search: /big buck bunny                                        │
└─────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Filter by stage works
- [ ] Filter by plugin works
- [ ] Filter by status works
- [ ] Text search works across title, URI, CID
- [ ] Quick filter toggles work
- [ ] Filters can be combined
