"""Speed Graph Component for Haven TUI.

ASCII speed graph using data from speed_history table.
Adapted from aria2tui's speed graph for haven-tui.
"""

from __future__ import annotations

import time
from typing import List, Optional, Any
from dataclasses import dataclass

from rich.text import Text
from textual.widgets import Static
from textual.reactive import reactive
from textual.visual import visualize

from haven_tui.data.repositories import SpeedHistoryRepository
from haven_tui.models.video_view import PipelineStage

# Optional plotille import - fallback to simple ASCII if not available
try:
    from plotille import Figure
    PLOTILLE_AVAILABLE = True
except ImportError:
    PLOTILLE_AVAILABLE = False


@dataclass
class SpeedDataPoint:
    """Single speed data point for graphing."""
    timestamp: float  # Unix timestamp
    speed: float  # bytes/sec
    progress: float  # 0-100


@dataclass
class SpeedStats:
    """Statistics for speed data."""
    current: float  # bytes/sec
    average: float  # bytes/sec
    peak: float  # bytes/sec
    min_val: float  # bytes/sec


class SpeedGraphComponent(Static):
    """ASCII speed graph using data from speed_history table.
    
    This widget displays a speed history graph for a selected video,
    showing speed trends over time for different pipeline stages.
    
    Attributes:
        width: Width of the graph in characters
        height: Height of the graph in characters
        history_seconds: How many seconds of history to display
    """
    
    DEFAULT_CSS = """
    SpeedGraphComponent {
        height: auto;
        width: 100%;
        padding: 1;
        border: solid $primary;
    }
    
    SpeedGraphComponent > .graph-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    
    SpeedGraphComponent > .graph-stats {
        margin-top: 1;
        color: $text-muted;
    }
    
    SpeedGraphComponent > .graph-timeline {
        margin-top: 1;
        color: $text;
    }
    """
    
    # Reactive properties for auto-update
    video_id: reactive[Optional[int]] = reactive(None)
    current_stage: reactive[str] = reactive("download")
    
    def __init__(
        self,
        speed_history_repo: Optional[SpeedHistoryRepository] = None,
        width: int = 60,
        height: int = 15,
        history_seconds: int = 60,
        **kwargs: Any,
    ) -> None:
        """Initialize the speed graph component.
        
        Args:
            speed_history_repo: Repository for querying speed history
            width: Width of the graph in characters
            height: Height of the graph in characters
            history_seconds: How many seconds of history to display
            **kwargs: Additional arguments passed to Static
        """
        super().__init__(**kwargs)
        self.speed_history_repo = speed_history_repo
        self.graph_width = width
        self.graph_height = height
        self.history_seconds = history_seconds
        self._speed_data: List[SpeedDataPoint] = []
        self._stats = SpeedStats(0, 0, 0, 0)
    
    def set_repository(self, repo: SpeedHistoryRepository) -> None:
        """Set the speed history repository.
        
        Args:
            repo: SpeedHistoryRepository instance
        """
        self.speed_history_repo = repo
    
    def set_video(self, video_id: int, stage: str = "download") -> None:
        """Set the video to display speed graph for.
        
        Args:
            video_id: Video ID to display
            stage: Pipeline stage to show ("download", "encrypt", "upload")
        """
        self.video_id = video_id
        self.current_stage = stage
        self.refresh_graph()
    
    def refresh_graph(self) -> None:
        """Refresh the graph data from repository."""
        if self.video_id is None or self.speed_history_repo is None:
            self._speed_data = []
            self._update_stats()
            self.update(self._get_empty_text())
            return
        
        # Get speed history from database (last N minutes to ensure coverage)
        minutes = max(1, (self.history_seconds // 60) + 1)
        history = self.speed_history_repo.get_speed_history(
            video_id=self.video_id,
            stage=self.current_stage,
            minutes=minutes,
        )
        
        # Convert to SpeedDataPoint list
        now = time.time()
        cutoff = now - self.history_seconds
        
        self._speed_data = []
        for entry in history:
            ts = entry.timestamp.timestamp()
            if ts >= cutoff:
                self._speed_data.append(SpeedDataPoint(
                    timestamp=ts,
                    speed=float(entry.speed),
                    progress=entry.progress,
                ))
        
        self._update_stats()
        self.update(self._get_text())
    
    def _update_stats(self) -> None:
        """Update speed statistics from current data."""
        if not self._speed_data:
            self._stats = SpeedStats(0, 0, 0, 0)
            return
        
        speeds = [dp.speed for dp in self._speed_data]
        self._stats = SpeedStats(
            current=speeds[-1] if speeds else 0,
            average=sum(speeds) / len(speeds) if speeds else 0,
            peak=max(speeds) if speeds else 0,
            min_val=min(speeds) if speeds else 0,
        )
    
    def _get_empty_text(self) -> Text:
        """Get empty state text when no data available."""
        lines = [
            "┌" + "─" * (self.graph_width - 2) + "┐",
            "│" + "Speed History".center(self.graph_width - 2) + "│",
            "├" + "─" * (self.graph_width - 2) + "┤",
        ]
        
        empty_lines = self.graph_height - 5
        for _ in range(empty_lines // 2):
            lines.append("│" + " " * (self.graph_width - 2) + "│")
        
        lines.append("│" + "[No speed data available]".center(self.graph_width - 2) + "│")
        
        for _ in range(empty_lines // 2):
            lines.append("│" + " " * (self.graph_width - 2) + "│")
        
        lines.append("└" + "─" * (self.graph_width - 2) + "┘")
        return Text("\n".join(lines))
    
    def _get_text(self) -> Text:
        """Get the speed graph text."""
        if not self._speed_data:
            return self._get_empty_text()
        
        lines = []
        
        # Title
        title = f"Speed History - {self.current_stage.title()}"
        lines.append(f"[bold]{title}[/bold]")
        lines.append("")
        
        # Graph
        graph_lines = self._render_graph_lines()
        lines.extend(graph_lines)
        
        # Stats
        lines.append("")
        lines.append(self._render_stats())
        
        return Text("\n".join(lines))
    
    def _render_graph_lines(self) -> List[str]:
        """Render the graph using plotille or fallback."""
        if PLOTILLE_AVAILABLE and len(self._speed_data) > 1:
            return self._render_plotille_graph()
        return self._render_fallback_graph()
    
    def _render_plotille_graph(self) -> List[str]:
        """Render graph using plotille."""
        now = time.time()
        
        # Extract data
        x_data = [now - dp.timestamp for dp in self._speed_data]  # seconds ago
        y_data = [dp.speed / (1024 * 1024) for dp in self._speed_data]  # MB/s
        
        # Create figure
        fig = Figure()
        fig.width = self.graph_width - 10  # Account for y-axis labels
        fig.height = self.graph_height - 3  # Account for x-axis labels
        fig.set_x_limits(min_=0, max_=self.history_seconds)
        fig.set_y_limits(min_=0, max_=max(y_data) * 1.1 if y_data else 10)
        
        # Plot data
        fig.plot(x_data, y_data, label="Speed (MB/s)")
        fig.x_label = "Seconds ago"
        fig.y_label = "MB/s"
        
        # Get graph string and format
        graph_str = str(fig)
        return graph_str.split("\n")
    
    def _render_fallback_graph(self) -> List[str]:
        """Render simple ASCII bar graph when plotille is not available."""
        if not self._speed_data:
            return ["[No data]"]
        
        # Group data into buckets
        num_buckets = min(len(self._speed_data), self.graph_width - 10)
        if num_buckets < 1:
            return ["[Insufficient data]"]
        
        # Calculate bucket size
        bucket_size = len(self._speed_data) / num_buckets
        max_speed = max(dp.speed for dp in self._speed_data) or 1
        
        # Build bars
        bars = []
        for i in range(num_buckets):
            start_idx = int(i * bucket_size)
            end_idx = int((i + 1) * bucket_size)
            bucket_data = self._speed_data[start_idx:end_idx]
            
            if bucket_data:
                avg_speed = sum(dp.speed for dp in bucket_data) / len(bucket_data)
                bar_height = int((avg_speed / max_speed) * (self.graph_height - 3))
                bars.append(bar_height)
            else:
                bars.append(0)
        
        # Render graph lines from top to bottom
        lines = []
        graph_height = self.graph_height - 3
        max_label = f"{max_speed / (1024 * 1024):.1f}"
        
        for row in range(graph_height, 0, -1):
            line_parts = []
            if row == graph_height:
                line_parts.append(f"{max_label:>4} ┤")
            elif row == graph_height // 2:
                line_parts.append(f"{float(max_label) / 2:.1f}:>4 ┤")
            elif row == 1:
                line_parts.append("   0 ┤")
            else:
                line_parts.append("     │")
            
            for bar in bars:
                if bar >= row:
                    line_parts.append("█")
                else:
                    line_parts.append(" ")
            
            lines.append("".join(line_parts))
        
        # X-axis
        lines.append("     └" + "─" * len(bars))
        lines.append(f"       {self.history_seconds}s ago".ljust(len(bars)) + "now")
        
        return lines
    
    def _render_stats(self) -> str:
        """Render statistics line."""
        return (
            f"Current: [accent]{self._format_speed(self._stats.current)}[/accent]  "
            f"Average: [text]{self._format_speed(self._stats.average)}[/text]  "
            f"Peak: [success]{self._format_speed(self._stats.peak)}[/success]"
        )
    
    def _format_speed(self, speed: float) -> str:
        """Format speed in human-readable form.
        
        Args:
            speed: Speed in bytes per second
            
        Returns:
            Formatted speed string (e.g., "2.4 MiB/s")
        """
        if speed == 0:
            return "-"
        
        # Convert to human readable
        size = float(speed)
        if size < 1024:
            return f"{size:.0f} B/s"
        size /= 1024
        if size < 1024:
            return f"{size:.1f} KiB/s"
        size /= 1024
        if size < 1024:
            return f"{size:.1f} MiB/s"
        size /= 1024
        return f"{size:.1f} GiB/s"
    
    def get_multi_stage_text(
        self,
        stages: Optional[List[str]] = None,
    ) -> Text:
        """Get multi-stage speed comparison graph text.
        
        Args:
            stages: List of stages to display (default: download, encrypt, upload)
            
        Returns:
            Rendered graph as Rich Text
        """
        if stages is None:
            stages = ["download", "encrypt", "upload"]
        
        if self.video_id is None or self.speed_history_repo is None:
            return self._get_empty_text()
        
        minutes = max(1, (self.history_seconds // 60) + 1)
        now = time.time()
        
        # Collect data for all stages
        stage_data: dict[str, List[SpeedDataPoint]] = {}
        for stage in stages:
            history = self.speed_history_repo.get_speed_history(
                video_id=self.video_id,
                stage=stage,
                minutes=minutes,
            )
            
            cutoff = now - self.history_seconds
            points = []
            for entry in history:
                ts = entry.timestamp.timestamp()
                if ts >= cutoff:
                    points.append(SpeedDataPoint(
                        timestamp=ts,
                        speed=float(entry.speed),
                        progress=entry.progress,
                    ))
            
            if points:
                stage_data[stage] = points
        
        if not stage_data:
            return self._get_empty_text()
        
        lines = []
        lines.append("[bold]Multi-Stage Speed History[/bold]")
        lines.append("")
        
        # Render multi-stage graph
        if PLOTILLE_AVAILABLE:
            graph_lines = self._render_multi_stage_plotille(stage_data)
            lines.extend(graph_lines)
        else:
            lines.append("[Multi-stage graph requires plotille]")
        
        # Stage legend
        lines.append("")
        lines.append(self._render_stage_timeline(stage_data))
        
        return Text("\n".join(lines))
    
    def _render_multi_stage_plotille(
        self,
        stage_data: dict[str, List[SpeedDataPoint]],
    ) -> List[str]:
        """Render multi-stage graph using plotille."""
        colors = ["red", "green", "blue", "yellow", "cyan"]
        now = time.time()
        
        fig = Figure()
        fig.width = self.graph_width - 10
        fig.height = self.graph_height - 3
        fig.set_x_limits(min_=0, max_=self.history_seconds)
        
        all_speeds: List[float] = []
        for i, (stage, points) in enumerate(stage_data.items()):
            if not points:
                continue
            
            x_data = [now - dp.timestamp for dp in points]
            y_data = [dp.speed / (1024 * 1024) for dp in points]
            all_speeds.extend(y_data)
            
            color = colors[i % len(colors)]
            fig.plot(x_data, y_data, label=stage, lc=color)
        
        if all_speeds:
            fig.set_y_limits(min_=0, max_=max(all_speeds) * 1.1)
        
        fig.x_label = "Seconds ago"
        fig.y_label = "MB/s"
        
        return str(fig).split("\n")
    
    def _render_stage_timeline(
        self,
        stage_data: dict[str, List[SpeedDataPoint]],
    ) -> str:
        """Render stage activity timeline below graph.
        
        Args:
            stage_data: Dictionary mapping stage name to speed data points
            
        Returns:
            Timeline string
        """
        parts = []
        stages = ["download", "ingest", "encrypt", "upload"]
        
        for stage in stages:
            if stage in stage_data and stage_data[stage]:
                points = stage_data[stage]
                duration = len(points)  # Approximate based on data points
                bar = "█" * min(duration, 10)
                parts.append(f"[{stage.title()}]{bar}")
            else:
                parts.append(f"[{stage.title()}]░░")
        
        return " → ".join(parts) + "►"
    
    def watch_video_id(self, video_id: Optional[int]) -> None:
        """Watch for video_id changes and refresh."""
        if video_id is not None:
            self.refresh_graph()
    
    def watch_current_stage(self, stage: str) -> None:
        """Watch for stage changes and refresh."""
        if self.video_id is not None:
            self.refresh_graph()


class SpeedGraphWidget(Static):
    """Full-featured speed graph widget with timeline.
    
    This widget provides a complete speed visualization including:
    - Speed history graph
    - Current, average, and peak statistics
    - Multi-stage timeline
    """
    
    DEFAULT_CSS = """
    SpeedGraphWidget {
        height: auto;
        width: 100%;
        padding: 1;
        border: solid $primary;
    }
    """
    
    def __init__(
        self,
        speed_history_repo: Optional[SpeedHistoryRepository] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the speed graph widget.
        
        Args:
            speed_history_repo: Repository for querying speed history
            **kwargs: Additional arguments passed to Static
        """
        super().__init__(**kwargs)
        self._graph_component = SpeedGraphComponent(speed_history_repo)
    
    def compose(self) -> None:
        """Compose the widget layout."""
        yield self._graph_component
    
    def set_video(self, video_id: int, stage: str = "download") -> None:
        """Set the video to display.
        
        Args:
            video_id: Video ID to display
            stage: Pipeline stage to show
        """
        self._graph_component.set_video(video_id, stage)
    
    def set_repository(self, repo: SpeedHistoryRepository) -> None:
        """Set the speed history repository.
        
        Args:
            repo: SpeedHistoryRepository instance
        """
        self._graph_component.set_repository(repo)
