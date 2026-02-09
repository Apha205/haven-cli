"""Sample video fixtures for testing.

This module provides sample VideoView objects and factory functions
for creating test video data.
"""

from datetime import datetime, timezone
from typing import List

from haven_tui.models.video_view import VideoView, PipelineStage


# Pre-defined sample video views for quick testing
SAMPLE_VIEWS = {
    "pending": VideoView(
        id=1,
        title="Pending Video",
        source_path="/downloads/pending.mp4",
        current_stage=PipelineStage.PENDING,
        stage_progress=0.0,
        stage_speed=0,
        overall_status="pending",
        has_error=False,
        error_message=None,
        file_size=0,
        plugin="youtube",
    ),
    "downloading": VideoView(
        id=2,
        title="Downloading Video",
        source_path="/downloads/active.mp4",
        current_stage=PipelineStage.DOWNLOAD,
        stage_progress=45.5,
        stage_speed=1024000,  # 1 MB/s
        stage_eta=120,
        overall_status="active",
        has_error=False,
        error_message=None,
        file_size=100 * 1024 * 1024,  # 100 MB
        plugin="youtube",
    ),
    "encrypting": VideoView(
        id=3,
        title="Encrypting Video",
        source_path="/downloads/encrypt.mp4",
        current_stage=PipelineStage.ENCRYPT,
        stage_progress=75.0,
        stage_speed=0,
        overall_status="active",
        has_error=False,
        error_message=None,
        file_size=50 * 1024 * 1024,  # 50 MB
        plugin="bittorrent",
    ),
    "uploading": VideoView(
        id=4,
        title="Uploading Video",
        source_path="/downloads/upload.mp4",
        current_stage=PipelineStage.UPLOAD,
        stage_progress=30.0,
        stage_speed=512000,  # 500 KB/s
        stage_eta=300,
        overall_status="active",
        has_error=False,
        error_message=None,
        file_size=200 * 1024 * 1024,  # 200 MB
        plugin="youtube",
    ),
    "syncing": VideoView(
        id=5,
        title="Syncing Video",
        source_path="/downloads/sync.mp4",
        current_stage=PipelineStage.SYNC,
        stage_progress=60.0,
        stage_speed=0,
        overall_status="active",
        has_error=False,
        error_message=None,
        file_size=150 * 1024 * 1024,  # 150 MB
        plugin="youtube",
    ),
    "analyzing": VideoView(
        id=6,
        title="Analyzing Video",
        source_path="/downloads/analyze.mp4",
        current_stage=PipelineStage.ANALYSIS,
        stage_progress=80.0,
        stage_speed=0,
        overall_status="active",
        has_error=False,
        error_message=None,
        file_size=75 * 1024 * 1024,  # 75 MB
        plugin="youtube",
    ),
    "completed": VideoView(
        id=7,
        title="Completed Video",
        source_path="/downloads/complete.mp4",
        current_stage=PipelineStage.COMPLETE,
        stage_progress=100.0,
        stage_speed=0,
        overall_status="completed",
        has_error=False,
        error_message=None,
        file_size=100 * 1024 * 1024,
        plugin="youtube",
    ),
    "failed": VideoView(
        id=8,
        title="Failed Video",
        source_path="/downloads/failed.mp4",
        current_stage=PipelineStage.DOWNLOAD,
        stage_progress=25.0,
        stage_speed=0,
        overall_status="failed",
        has_error=True,
        error_message="Network timeout",
        file_size=0,
        plugin="bittorrent",
    ),
}


def create_sample_video(
    video_id: int = 1,
    title: str = "Sample Video",
    stage: PipelineStage = PipelineStage.DOWNLOAD,
    progress: float = 50.0,
    speed: int = 1024000,
    status: str = "active",
    plugin: str = "youtube",
    file_size: int = 100 * 1024 * 1024,
    has_error: bool = False,
    error_message: str = None,
) -> VideoView:
    """Create a sample video view with customizable properties.
    
    Args:
        video_id: Video ID
        title: Video title
        stage: Current pipeline stage
        progress: Stage progress (0-100)
        speed: Current speed in bytes/sec
        status: Overall status
        plugin: Plugin name
        file_size: File size in bytes
        has_error: Whether video has error
        error_message: Error message
        
    Returns:
        VideoView object
    """
    return VideoView(
        id=video_id,
        title=title,
        source_path=f"/downloads/video_{video_id}.mp4",
        current_stage=stage,
        stage_progress=progress,
        stage_speed=speed,
        overall_status=status,
        has_error=has_error,
        error_message=error_message,
        file_size=file_size,
        plugin=plugin,
    )


def create_sample_videos(count: int = 10) -> List[VideoView]:
    """Create a list of sample videos in various stages.
    
    Args:
        count: Number of videos to create
        
    Returns:
        List of VideoView objects
    """
    videos = []
    stages = [
        (PipelineStage.DOWNLOAD, "active", 1024000),
        (PipelineStage.ENCRYPT, "active", 0),
        (PipelineStage.UPLOAD, "active", 512000),
        (PipelineStage.SYNC, "active", 0),
        (PipelineStage.ANALYSIS, "active", 0),
        (PipelineStage.PENDING, "pending", 0),
        (PipelineStage.COMPLETE, "completed", 0),
    ]
    plugins = ["youtube", "bittorrent"]
    
    for i in range(count):
        stage_idx = i % len(stages)
        stage, status, speed = stages[stage_idx]
        plugin = plugins[i % len(plugins)]
        progress = (i * 10) % 100
        
        video = create_sample_video(
            video_id=i + 1,
            title=f"Sample Video {i + 1}",
            stage=stage,
            progress=progress,
            speed=speed,
            status=status,
            plugin=plugin,
        )
        videos.append(video)
    
    return videos


def create_large_video_list(count: int = 100) -> List[VideoView]:
    """Create a large list of videos for performance testing.
    
    Args:
        count: Number of videos to create
        
    Returns:
        List of VideoView objects
    """
    return create_sample_videos(count)
