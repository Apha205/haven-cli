# Task 6.4: Pipeline Analytics Dashboard

**Priority:** Low
**Estimated Effort:** 3 days

**Description:**
Analytics view showing pipeline performance over time.

**Metrics:**
- Videos processed per day/week
- Average time per stage
- Success/failure rates
- Throughput trends
- Plugin usage distribution

**Implementation:**
```python
# src/haven_tui/ui/views/analytics.py

class AnalyticsDashboard:
    """Analytics view showing pipeline performance metrics."""
    
    def __init__(self, analytics_repo: AnalyticsRepository):
        self.repo = analytics_repo
    
    def render(self, stdscr):
        """Render analytics dashboard."""
        max_y, max_x = stdscr.getmaxyx()
        
        # Header
        stdscr.addstr(1, 2, "Pipeline Analytics", curses.A_BOLD)
        
        # Processed videos per day
        y = 3
        daily = self.repo.get_videos_per_day(days=7)
        self._render_bar_chart(stdscr, y, 2, "Videos Processed (Last 7 Days)", daily)
        
        # Average time per stage
        y = 12
        stage_times = self.repo.get_avg_time_per_stage()
        self._render_stage_timing(stdscr, y, 2, stage_times)
        
        # Success/failure rates
        y = 20
        rates = self.repo.get_success_rates()
        self._render_rates(stdscr, y, 2, rates)

class AnalyticsRepository:
    """Repository for analytics queries."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    def get_videos_per_day(self, days: int = 7) -> Dict[str, int]:
        """Get count of videos processed per day."""
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        since = datetime.now() - timedelta(days=days)
        
        with self.session_factory() as session:
            results = session.query(
                func.date(Video.created_at).label('date'),
                func.count().label('count')
            ).filter(
                Video.created_at >= since
            ).group_by(
                func.date(Video.created_at)
            ).all()
            
            return {str(r.date): r.count for r in results}
    
    def get_avg_time_per_stage(self) -> Dict[str, float]:
        """Get average time spent in each stage."""
        from sqlalchemy import func
        
        stages = {}
        
        with self.session_factory() as session:
            # Download stage
            dl_avg = session.query(
                func.avg(func.julianday(Download.completed_at) - 
                        func.julianday(Download.started_at))
            ).filter(
                Download.status == "completed",
                Download.completed_at != None
            ).scalar()
            stages["download"] = dl_avg or 0
            
            # Encrypt stage
            enc_avg = session.query(
                func.avg(func.julianday(EncryptionJob.completed_at) - 
                        func.julianday(EncryptionJob.started_at))
            ).filter(
                EncryptionJob.status == "completed"
            ).scalar()
            stages["encrypt"] = enc_avg or 0
            
            # Upload stage
            up_avg = session.query(
                func.avg(func.julianday(UploadJob.completed_at) - 
                        func.julianday(UploadJob.started_at))
            ).filter(
                UploadJob.status == "completed"
            ).scalar()
            stages["upload"] = up_avg or 0
        
        return stages
    
    def get_success_rates(self) -> Dict[str, float]:
        """Get success/failure rates by stage."""
        from sqlalchemy import func, case
        
        with self.session_factory() as session:
            results = {}
            
            for table, name in [(Download, "download"), 
                               (EncryptionJob, "encrypt"),
                               (UploadJob, "upload")]:
                total = session.query(func.count()).select_from(table).scalar()
                success = session.query(func.count()).filter(
                    table.status == "completed"
                ).scalar()
                
                if total > 0:
                    results[name] = (success / total) * 100
                else:
                    results[name] = 0
            
            return results
```

**Visual Design:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Pipeline Analytics                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ Videos Processed (Last 7 Days)                                          │
│ Mon ████████ 12   Tue ██████████████ 24   Wed ██████████ 15            │
│ Thu ████████████████ 30   Fri ██████ 9   Sat ████████████ 18           │
│ Sun ██████ 8                                                             │
│                                                                          │
│ Average Time Per Stage                                                   │
│   Download:  ████████████████████ 4m 32s                                │
│   Encrypt:   ██████████ 2m 15s                                          │
│   Upload:    ████████████████ 3m 45s                                    │
│                                                                          │
│ Success Rates                                                            │
│   Download:  ████████████████████ 95%                                   │
│   Encrypt:   ██████████████████ 92%                                     │
│   Upload:    ████████████████████ 96%                                   │
│                                                                          │
│ Plugin Usage                                                             │
│   YouTube:   ████████████████████████████ 78%                           │
│   BitTorrent: ██████████ 22%                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria:**
- [ ] Shows videos processed per day
- [ ] Shows average time per stage
- [ ] Shows success/failure rates
- [ ] Shows plugin usage distribution
- [ ] Visual bar charts rendered in ASCII
- [ ] Data updates on refresh
