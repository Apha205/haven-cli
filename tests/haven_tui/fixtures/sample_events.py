"""Sample event fixtures for testing.

This module provides factory functions for creating test events.
"""

from typing import Optional, Dict, Any

from haven_cli.pipeline.events import Event, EventType


def create_download_progress_event(
    video_id: int,
    progress: float = 50.0,
    speed: float = 1024000.0,
    eta: int = 120,
    bytes_downloaded: int = 50 * 1024 * 1024,
    bytes_total: int = 100 * 1024 * 1024,
) -> Event:
    """Create a download progress event.
    
    Args:
        video_id: Video ID
        progress: Download progress (0-100)
        speed: Download speed in bytes/sec
        eta: Estimated time remaining in seconds
        bytes_downloaded: Bytes downloaded so far
        bytes_total: Total bytes to download
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.DOWNLOAD_PROGRESS,
        payload={
            "video_id": video_id,
            "progress_percent": progress,
            "download_rate": speed,
            "eta_seconds": eta,
            "bytes_downloaded": bytes_downloaded,
            "bytes_total": bytes_total,
        },
    )


def create_upload_progress_event(
    video_id: int,
    progress: float = 50.0,
    speed: float = 512000.0,
    job_id: int = 1,
) -> Event:
    """Create an upload progress event.
    
    Args:
        video_id: Video ID
        progress: Upload progress (0-100)
        speed: Upload speed in bytes/sec
        job_id: Upload job ID
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.UPLOAD_PROGRESS,
        payload={
            "video_id": video_id,
            "progress": progress,
            "upload_speed": speed,
            "job_id": job_id,
        },
    )


def create_encrypt_progress_event(
    video_id: int,
    progress: float = 50.0,
    encrypt_speed: float = 0.0,
    job_id: int = 1,
    bytes_processed: int = 50 * 1024 * 1024,
) -> Event:
    """Create an encrypt progress event.
    
    Args:
        video_id: Video ID
        progress: Encryption progress (0-100)
        encrypt_speed: Encryption speed in bytes/sec
        job_id: Encryption job ID
        bytes_processed: Bytes processed so far
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.ENCRYPT_PROGRESS,
        payload={
            "video_id": video_id,
            "progress": progress,
            "encrypt_speed": encrypt_speed,
            "job_id": job_id,
            "bytes_processed": bytes_processed,
        },
    )


def create_completion_event(
    video_id: int,
    event_type: EventType = EventType.UPLOAD_COMPLETE,
) -> Event:
    """Create a completion event.
    
    Args:
        video_id: Video ID
        event_type: Type of completion event
        
    Returns:
        Event object
    """
    return Event(
        event_type=event_type,
        payload={"video_id": video_id},
    )


def create_failure_event(
    video_id: int,
    stage: str = "download",
    error: str = "Unknown error",
    event_type: EventType = EventType.PIPELINE_FAILED,
) -> Event:
    """Create a failure event.
    
    Args:
        video_id: Video ID
        stage: Stage that failed
        error: Error message
        event_type: Type of failure event
        
    Returns:
        Event object
    """
    return Event(
        event_type=event_type,
        payload={
            "video_id": video_id,
            "stage": stage,
            "error": error,
        },
    )


def create_step_started_event(
    video_id: int,
    stage: str = "download",
) -> Event:
    """Create a step started event.
    
    Args:
        video_id: Video ID
        stage: Stage that started
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.STEP_STARTED,
        payload={
            "video_id": video_id,
            "stage": stage,
        },
    )


def create_step_complete_event(
    video_id: int,
    stage: str = "download",
) -> Event:
    """Create a step complete event.
    
    Args:
        video_id: Video ID
        stage: Stage that completed
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.STEP_COMPLETE,
        payload={
            "video_id": video_id,
            "stage": stage,
        },
    )


def create_video_ingested_event(
    video_id: int,
) -> Event:
    """Create a video ingested event.
    
    Args:
        video_id: Video ID
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.VIDEO_INGESTED,
        payload={"video_id": video_id},
    )


def create_pipeline_started_event(
    video_id: int,
) -> Event:
    """Create a pipeline started event.
    
    Args:
        video_id: Video ID
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.PIPELINE_STARTED,
        payload={"video_id": video_id},
    )


def create_pipeline_complete_event(
    video_id: int,
) -> Event:
    """Create a pipeline complete event.
    
    Args:
        video_id: Video ID
        
    Returns:
        Event object
    """
    return Event(
        event_type=EventType.PIPELINE_COMPLETE,
        payload={"video_id": video_id},
    )


# Event sequences for testing complex scenarios
DOWNLOAD_FLOW_EVENTS = [
    create_pipeline_started_event(1),
    create_step_started_event(1, "download"),
    create_download_progress_event(1, progress=25.0),
    create_download_progress_event(1, progress=50.0),
    create_download_progress_event(1, progress=75.0),
    create_step_complete_event(1, "download"),
    create_step_started_event(1, "encrypt"),
    create_encrypt_progress_event(1, progress=50.0),
    create_encrypt_progress_event(1, progress=100.0),
    create_completion_event(1, EventType.ENCRYPT_COMPLETE),
    create_step_started_event(1, "upload"),
    create_upload_progress_event(1, progress=50.0),
    create_upload_progress_event(1, progress=100.0),
    create_completion_event(1, EventType.UPLOAD_COMPLETE),
    create_step_complete_event(1, "upload"),
    create_completion_event(1, EventType.SYNC_COMPLETE),
    create_pipeline_complete_event(1),
]

FAILED_DOWNLOAD_EVENTS = [
    create_pipeline_started_event(2),
    create_step_started_event(2, "download"),
    create_download_progress_event(2, progress=25.0),
    create_download_progress_event(2, progress=50.0),
    create_failure_event(2, stage="download", error="Network timeout"),
]

RETRY_FLOW_EVENTS = [
    create_pipeline_started_event(3),
    create_step_started_event(3, "download"),
    create_download_progress_event(3, progress=50.0),
    create_failure_event(3, stage="download", error="Connection reset"),
    create_step_started_event(3, "download"),  # Retry
    create_download_progress_event(3, progress=25.0),
    create_download_progress_event(3, progress=75.0),
    create_step_complete_event(3, "download"),
    create_pipeline_complete_event(3),
]
