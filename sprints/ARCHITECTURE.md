# Haven TUI Architecture

## High-Level Design

**Deployment:** TUI is an optional module within haven-cli (`haven_cli/tui/`)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         haven-cli Package                           │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     haven_cli.tui                              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │ Video List  │  │ Detail View │  │ Speed Graph Panel   │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │  │
│  │         └─────────────────┴────────────────────┘              │  │
│  │                            │                                  │  │
│  │  ┌─────────────────────────┴─────────────────────────┐        │  │
│  │  │              State Manager (in-memory)            │        │  │
│  │  └─────────────────────────┬─────────────────────────┘        │  │
│  │                            │                                  │  │
│  │  ┌─────────────────────────┴─────────────────────────┐        │  │
│  │  │  Repositories (query downloads, snapshots, etc.)  │        │  │
│  │  └─────────────────────────┬─────────────────────────┘        │  │
│  └────────────────────────────┼──────────────────────────────────┘  │
│                               │                                     │
│  ┌────────────────────────────┼──────────────────────────────────┐  │
│  │                            ▼                                   │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │              haven_cli.pipeline (existing)               │  │  │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │  │  │
│  │  │  │Event Bus │  │ Pipeline │  │   Download/Encrypt/  │   │  │  │
│  │  │  │          │  │ Manager  │  │   Upload Steps       │   │  │  │
│  │  │  └──────────┘  └──────────┘  └──────────────────────┘   │  │  │
│  │  └────────────────────────────┬─────────────────────────────┘  │  │
│  │                               │                                 │  │
│  │  ┌────────────────────────────┼──────────────────────────────┐ │  │
│  │  │                            ▼                              │ │  │
│  │  │  ┌─────────────────────────────────────────────────────┐  │ │  │
│  │  │  │         haven_cli.database (existing)               │  │ │  │
│  │  │  │  ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │  │ │  │
│  │  │  │  │ downloads   │ │ encryption_ │ │ pipeline_     │  │  │ │  │
│  │  │  │  │             │ │ jobs        │ │ snapshots     │  │  │ │  │
│  │  │  │  └─────────────┘ └─────────────┘ └───────────────┘  │  │ │  │
│  │  │  │  ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │  │ │  │
│  │  │  │  │ upload_jobs │ │ analysis_   │ │ speed_history │  │  │ │  │
│  │  │  │  │             │ │ jobs        │ │               │  │  │ │  │
│  │  │  │  └─────────────┘ └─────────────┘ └───────────────┘  │  │ │  │
│  │  │  └─────────────────────────────────────────────────────┘  │ │  │
│  │  └───────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘

$ haven tui          # Entry point launches the TUI module
```

## Key Components

### 1. Pipeline Interface (`haven_tui/core/pipeline_interface.py`)

**Purpose:** Direct interface to Haven pipeline core, completely bypassing the CLI.

**Responsibilities:**
- Connect to EventBus for real-time updates
- Query database for state
- Provide unified view across plugins
- Offer TUI-specific operations (per-stage retry)

**Key Methods:**
- `get_active_videos()` - All videos currently in pipeline
- `get_active_downloads()` - Unified download view (YouTube + BitTorrent)
- `on_event()` - Subscribe to pipeline events
- `retry_video()` - Retry failed stages

### 2. State Manager (`haven_tui/core/state_manager.py`)

**Purpose:** Thread-safe, in-memory state cache optimized for UI rendering.

**Responsibilities:**
- Load initial state from database
- Update state from events in real-time
- Provide synchronous access for UI
- Maintain speed history for graphing

**Key Features:**
- Lock-protected for thread safety
- Change notifications for UI updates
- VideoState dataclass with all pipeline fields
- Automatic path-to-ID mapping

### 3. Metrics Collector (`haven_tui/core/metrics.py`)

**Purpose:** Collect and aggregate speed metrics for visualization.

**Responsibilities:**
- Record speed samples per video/stage
- Maintain rolling window of history
- Calculate aggregate speeds
- Format for graphing

### 4. UI Components

#### Main View (`haven_tui/ui/views/video_list.py`)
- Scrollable list of videos
- Stage icons and progress bars
- Speed and ETA display
- Multi-select support

#### Detail View (`haven_tui/ui/views/video_detail.py`)
- Pipeline stage diagram
- Per-stage progress
- Timing information
- Error messages

#### Speed Graph Panel (`haven_tui/ui/panels/speed_graph.py`)
- ASCII/Unicode graph
- 60-second rolling history
- Current/average/peak speeds

## Data Flow

### Initialization Flow

```
1. TUI starts
2. Load configuration
3. Connect to database
4. Initialize StateManager
5. Load initial state from database
6. Subscribe to EventBus
7. Start refresh loop
```

### Real-Time Update Flow

```
Pipeline Event
      │
      ▼
EventBus.publish()
      │
      ▼
PipelineInterface (subscription)
      │
      ▼
StateManager._on_*_handler()
      │
      ▼
Update VideoState
      │
      ▼
Notify UI callbacks
      │
      ▼
Trigger screen refresh
```

### Polling Fallback Flow

```
Timer (5s)
   │
   ▼
Query database for active videos
   │
   ▼
Merge with current state
   │
   ▼
Add missing videos
Update stale entries
   │
   ▼
Notify UI if changes
```

## Threading Model

### Main Thread
- Curses UI rendering
- Keyboard input handling
- Screen updates

### Event Thread (asyncio)
- EventBus subscriptions
- Event handlers
- State updates

### Background Thread (optional)
- Database polling fallback
- Metrics aggregation

### Synchronization
- StateManager uses threading.RLock
- All state access is lock-protected
- Event handlers are async-safe

## Database Schema (Table-Based Design)

Rather than adding nullable columns to the `videos` table, we use dedicated tables for each pipeline stage. This provides:
- Clean separation of concerns
- Efficient querying per stage
- History of job attempts
- Optimized read path via `pipeline_snapshots`

### Core Tables

#### 1. `downloads` - Download progress for any source
```python
class Download(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    source_type: Mapped[str]  # "youtube" | "torrent"
    status: Mapped[str]  # "pending" | "downloading" | "completed" | "failed"
    progress_percent: Mapped[Optional[float]]
    bytes_downloaded: Mapped[Optional[int]]
    bytes_total: Mapped[Optional[int]]
    download_rate: Mapped[Optional[int]]  # bytes/sec
    eta_seconds: Mapped[Optional[int]]
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
    failed_at: Mapped[Optional[datetime]]
    error_message: Mapped[Optional[str]]
    source_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

#### 2. `encryption_jobs` - Lit Protocol encryption tracking
```python
class EncryptionJob(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    status: Mapped[str]
    progress_percent: Mapped[Optional[float]]
    bytes_processed: Mapped[Optional[int]]
    bytes_total: Mapped[Optional[int]]
    encrypt_speed: Mapped[Optional[int]]
    lit_cid: Mapped[Optional[str]]
    access_control_conditions: Mapped[Optional[dict]] = mapped_column(JSON)
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
    error_message: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

#### 3. `upload_jobs` - IPFS/Arkiv upload tracking
```python
class UploadJob(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    status: Mapped[str]
    target: Mapped[str]  # "ipfs" | "arkiv" | "s3"
    progress_percent: Mapped[Optional[float]]
    bytes_uploaded: Mapped[Optional[int]]
    bytes_total: Mapped[Optional[int]]
    upload_speed: Mapped[Optional[int]]
    remote_cid: Mapped[Optional[str]]
    remote_url: Mapped[Optional[str]]
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
    error_message: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

#### 4. `analysis_jobs` - VLM/LLM analysis tracking
```python
class AnalysisJob(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    status: Mapped[str]
    frames_processed: Mapped[Optional[int]]
    frames_total: Mapped[Optional[int]]
    progress_percent: Mapped[Optional[float]]
    analysis_type: Mapped[str]  # "vlm" | "llm"
    model_name: Mapped[Optional[str]]
    output_file: Mapped[Optional[str]]
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
    error_message: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

#### 5. `sync_jobs` - Blockchain sync tracking
```python
class SyncJob(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    status: Mapped[str]
    tx_hash: Mapped[Optional[str]]
    block_number: Mapped[Optional[int]]
    gas_used: Mapped[Optional[int]]
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
    error_message: Mapped[Optional[str]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

#### 6. `pipeline_snapshots` - Read-optimized view for TUI
```python
class PipelineSnapshot(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), unique=True, index=True)
    current_stage: Mapped[str]  # "download" | "ingest" | "analyze" | "encrypt" | "upload" | "sync"
    overall_status: Mapped[str]  # "pending" | "active" | "completed" | "failed"
    stage_progress_percent: Mapped[Optional[float]]
    stage_speed: Mapped[Optional[int]]
    stage_eta: Mapped[Optional[int]]
    total_bytes: Mapped[Optional[int]]
    downloaded_bytes: Mapped[Optional[int]]
    encrypted_bytes: Mapped[Optional[int]]
    uploaded_bytes: Mapped[Optional[int]]
    has_error: Mapped[bool] = mapped_column(default=False)
    error_stage: Mapped[Optional[str]]
    error_message: Mapped[Optional[str]]
    stage_started_at: Mapped[Optional[datetime]]
    pipeline_started_at: Mapped[Optional[datetime]]
    pipeline_completed_at: Mapped[Optional[datetime]]
    updated_at: Mapped[datetime]
```

#### 7. `speed_history` - Time-series for graphing
```python
class SpeedHistory(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    stage: Mapped[str]
    timestamp: Mapped[datetime] = mapped_column(index=True)
    speed: Mapped[int]  # bytes/sec
    progress: Mapped[float]
    bytes_processed: Mapped[int]
    
    __table_args__ = (
        Index('idx_speed_history_video_time', 'video_id', 'stage', 'timestamp'),
    )
```

### Query Patterns

| TUI View | Query | Tables |
|----------|-------|--------|
| Main list | `SELECT * FROM pipeline_snapshots WHERE overall_status IN ('active', 'pending') ORDER BY stage_started_at DESC` | `pipeline_snapshots` |
| Header stats | `SELECT SUM(stage_speed), COUNT(*) FROM pipeline_snapshots WHERE overall_status = 'active'` | `pipeline_snapshots` |
| Download details | `SELECT * FROM downloads WHERE video_id = ? ORDER BY created_at DESC LIMIT 1` | `downloads` |
| Speed graph | `SELECT * FROM speed_history WHERE video_id = ? AND stage = ? AND timestamp > NOW() - INTERVAL '5 minutes' ORDER BY timestamp` | `speed_history` |
| Detail view | Join with all job tables | `downloads`, `analysis_jobs`, `encryption_jobs`, `upload_jobs`, `sync_jobs` |
| Failed jobs | Union across job tables with `status = 'failed'` | All job tables |
| CID lookup | `SELECT remote_cid FROM upload_jobs WHERE video_id = ? AND status = 'completed' ORDER BY completed_at DESC LIMIT 1` | `upload_jobs` |

## Event Types Used

### Input Events (from Pipeline)
- `DOWNLOAD_STARTED/PROGRESS/COMPLETE/FAILED`
- `VIDEO_INGESTED`
- `ANALYSIS_REQUESTED/PROGRESS/COMPLETE/FAILED`
- `ENCRYPT_REQUESTED/PROGRESS/COMPLETE/FAILED`
- `UPLOAD_REQUESTED/PROGRESS/COMPLETE/FAILED`
- `PIPELINE_STARTED/COMPLETE/FAILED/CANCELLED`

### Output Events (from TUI - optional)
- `VIDEO_RETRY` - Retry failed stages
- `VIDEO_CANCEL` - Cancel processing

## Configuration

```toml
# ~/.config/haven-tui/config.toml

[database]
path = "~/.local/share/haven/haven.db"

[display]
refresh_rate = 1.0           # seconds
show_speed_graph = true
graph_history_seconds = 60
theme = "dark"               # dark, light, minimal

[ui]
show_completed = false
show_failed = true
max_videos_in_list = 1000
```

## Performance Considerations

1. **State Caching:** All state in memory, no DB queries during render
2. **Lazy Loading:** Detail view queries on-demand
3. **Batched Updates:** Event handlers batch UI notifications
4. **Pagination:** Video list limited to N most recent
5. **Graph Downsampling:** Speed history aggregated for display

## Security

- Read-only database access by default
- Optional write access for retry/cancel operations
- No credential storage in TUI
- Uses existing haven-cli configuration

## Dependencies

- `haven-cli` - Core pipeline (reused)
- `curses` - Terminal UI (stdlib)
- `listpick` - TUI framework (aria2tui's picker)
- `plotille` - ASCII graphs
- `sqlalchemy` - Database ORM (reused from haven-cli)
- `pydantic` - Config validation
- `toml` - Config files
