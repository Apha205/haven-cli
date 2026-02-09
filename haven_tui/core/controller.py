"""Video List Controller for Haven TUI.

Provides filtering and search capabilities for the video list,
integrating with the StateManager and repositories.
"""

from typing import List, Optional, Callable, Any
from dataclasses import dataclass, field

from haven_tui.core.state_manager import StateManager, VideoState
from haven_tui.models.video_view import (
    VideoView,
    PipelineStage,
    StageStatus,
    FilterState,
    SortField,
    SortOrder,
    VideoSorter,
)


@dataclass
class FilterResult:
    """Result of applying filters and sorting to video list.
    
    Attributes:
        videos: Filtered and sorted list of videos
        total_count: Total number of videos before filtering
        filtered_count: Number of videos after filtering
        active_filters: List of active filter descriptions
        sort_description: Human-readable description of current sort
    """
    videos: List[VideoState]
    total_count: int
    filtered_count: int
    active_filters: List[str]
    sort_description: str = ""


class VideoListController:
    """Controller for video list with filtering, sorting, and search capabilities.
    
    This controller manages the video list state and provides filtering
    by stage, plugin, status, text search across video fields, and
    sorting by various criteria.
    
    Attributes:
        state_manager: The StateManager for accessing video state
        filter_state: Current filter configuration
        sorter: VideoSorter for sorting videos
        _change_callbacks: List of callbacks to notify on filter changes
    
    Example:
        >>> controller = VideoListController(state_manager)
        >>> controller.set_filter_stage(PipelineStage.DOWNLOAD)
        >>> controller.set_sort_field(SortField.DATE_ADDED)
        >>> result = controller.get_filtered_videos()
        >>> print(f"Showing {result.filtered_count} of {result.total_count} videos")
    """
    
    def __init__(
        self,
        state_manager: StateManager,
        filter_state: Optional[FilterState] = None,
        sorter: Optional[VideoSorter] = None,
    ) -> None:
        """Initialize the video list controller.
        
        Args:
            state_manager: The StateManager for accessing video state
            filter_state: Initial filter configuration (optional)
            sorter: Initial video sorter (optional)
        """
        self.state_manager = state_manager
        self.filter_state = filter_state or FilterState()
        self.sorter = sorter or VideoSorter()
        self._change_callbacks: List[Callable[[FilterState], None]] = []
    
    def on_filter_change(self, callback: Callable[[FilterState], None]) -> None:
        """Register callback for filter state changes.
        
        Args:
            callback: Function to call when filters change
        """
        self._change_callbacks.append(callback)
    
    def off_filter_change(self, callback: Callable[[FilterState], None]) -> bool:
        """Unregister a filter change callback.
        
        Args:
            callback: The callback to remove
            
        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._change_callbacks.remove(callback)
            return True
        except ValueError:
            return False
    
    def _notify_filter_change(self) -> None:
        """Notify all registered callbacks of filter change."""
        for callback in self._change_callbacks:
            try:
                callback(self.filter_state)
            except Exception as e:
                # Log error but don't break other callbacks
                import logging
                logging.getLogger(__name__).error(f"Filter change callback error: {e}")
    
    def get_filtered_videos(self, filter_state: Optional[FilterState] = None) -> FilterResult:
        """Apply filters and sorting to video list and return result.
        
        Args:
            filter_state: Optional filter state to use (defaults to self.filter_state)
            
        Returns:
            FilterResult containing filtered and sorted videos and metadata
        """
        filt = filter_state or self.filter_state
        
        # Get all videos from state manager
        videos = self.state_manager.get_all_videos()
        total_count = len(videos)
        
        # Track active filters for display
        active_filters: List[str] = []
        
        # Filter by stage
        if filt.stage:
            videos = [v for v in videos if v.current_stage == filt.stage.value]
            active_filters.append(f"stage={filt.stage.value}")
        
        # Filter by status (overall_status)
        if filt.status:
            status_map = {
                StageStatus.PENDING: "pending",
                StageStatus.ACTIVE: "active",
                StageStatus.COMPLETED: "completed",
                StageStatus.FAILED: "failed",
            }
            target_status = status_map.get(filt.status)
            if target_status:
                videos = [v for v in videos if v.overall_status == target_status]
                active_filters.append(f"status={filt.status.value}")
        
        # Filter by show_completed
        if not filt.show_completed:
            videos = [v for v in videos if not v.is_completed]
            active_filters.append("hide_completed")
        
        # Filter by show_failed
        if not filt.show_failed:
            videos = [v for v in videos if not v.has_failed]
            active_filters.append("hide_failed")
        
        # Filter by show_only_errors
        if filt.show_only_errors:
            videos = [v for v in videos if v.has_failed]
            active_filters.append("errors_only")
        
        # Text search
        if filt.search_query:
            videos = self._search_videos(videos, filt.search_query)
            active_filters.append(f"search='{filt.search_query}'")
        
        # Apply sorting
        videos = self.sorter.sort(videos)
        
        return FilterResult(
            videos=videos,
            total_count=total_count,
            filtered_count=len(videos),
            active_filters=active_filters,
            sort_description=self.sorter.get_sort_description(),
        )
    
    def _search_videos(
        self,
        videos: List[VideoState],
        query: str,
    ) -> List[VideoState]:
        """Text search across video fields.
        
        Searches across:
        - Video title (case-insensitive)
        - Video ID (exact match if query is numeric)
        
        Args:
            videos: List of videos to search
            query: Search query string
            
        Returns:
            List of videos matching the search query
        """
        query = query.lower().strip()
        if not query:
            return videos
        
        results = []
        
        # Check if query is a numeric ID search
        is_numeric_query = query.isdigit()
        query_id = int(query) if is_numeric_query else None
        
        for v in videos:
            # Search by ID (exact match for numeric queries)
            if is_numeric_query and v.id == query_id:
                results.append(v)
                continue
            
            # Search in title
            if query in v.title.lower():
                results.append(v)
                continue
        
        return results
    
    # Filter setters that notify on change
    
    def set_filter_stage(self, stage: Optional[PipelineStage]) -> None:
        """Set stage filter.
        
        Args:
            stage: Pipeline stage to filter by, or None to clear
        """
        if self.filter_state.stage != stage:
            self.filter_state.stage = stage
            self._notify_filter_change()
    
    def set_filter_plugin(self, plugin: Optional[str]) -> None:
        """Set plugin filter.
        
        Args:
            plugin: Plugin name to filter by, or None to clear
        """
        if self.filter_state.plugin != plugin:
            self.filter_state.plugin = plugin
            self._notify_filter_change()
    
    def set_filter_status(self, status: Optional[StageStatus]) -> None:
        """Set status filter.
        
        Args:
            status: Stage status to filter by, or None to clear
        """
        if self.filter_state.status != status:
            self.filter_state.status = status
            self._notify_filter_change()
    
    def set_search_query(self, query: str) -> None:
        """Set search query.
        
        Args:
            query: Search string
        """
        if self.filter_state.search_query != query:
            self.filter_state.search_query = query
            self._notify_filter_change()
    
    def set_show_completed(self, show: bool) -> None:
        """Set whether to show completed videos.
        
        Args:
            show: True to show completed videos
        """
        if self.filter_state.show_completed != show:
            self.filter_state.show_completed = show
            self._notify_filter_change()
    
    def set_show_failed(self, show: bool) -> None:
        """Set whether to show failed videos.
        
        Args:
            show: True to show failed videos
        """
        if self.filter_state.show_failed != show:
            self.filter_state.show_failed = show
            self._notify_filter_change()
    
    def set_show_only_errors(self, show: bool) -> None:
        """Set whether to show only videos with errors.
        
        Args:
            show: True to show only error videos
        """
        if self.filter_state.show_only_errors != show:
            self.filter_state.show_only_errors = show
            self._notify_filter_change()
    
    def clear_all_filters(self) -> None:
        """Reset all filters to default values."""
        if self.filter_state.is_active():
            self.filter_state.reset()
            self._notify_filter_change()
    
    def toggle_show_completed(self) -> bool:
        """Toggle show_completed filter.
        
        Returns:
            New value of show_completed
        """
        self.filter_state.show_completed = not self.filter_state.show_completed
        self._notify_filter_change()
        return self.filter_state.show_completed
    
    def toggle_show_failed(self) -> bool:
        """Toggle show_failed filter.
        
        Returns:
            New value of show_failed
        """
        self.filter_state.show_failed = not self.filter_state.show_failed
        self._notify_filter_change()
        return self.filter_state.show_failed
    
    def toggle_show_only_errors(self) -> bool:
        """Toggle show_only_errors filter.
        
        Returns:
            New value of show_only_errors
        """
        self.filter_state.show_only_errors = not self.filter_state.show_only_errors
        self._notify_filter_change()
        return self.filter_state.show_only_errors
    
    def get_active_filter_descriptions(self) -> List[str]:
        """Get human-readable descriptions of active filters.
        
        Returns:
            List of filter descriptions
        """
        result = self.get_filtered_videos()
        return result.active_filters
    
    def has_active_filters(self) -> bool:
        """Check if any filters are currently active.
        
        Returns:
            True if filters are active
        """
        return self.filter_state.is_active()

    
    # Sorting methods
    
    def set_sort_field(self, field: SortField) -> None:
        """Set the sort field.
        
        Args:
            field: The field to sort by
        """
        self.sorter.set_sort(field)
    
    def set_sort_order(self, order: SortOrder) -> None:
        """Set the sort order.
        
        Args:
            order: ASCENDING or DESCENDING
        """
        self.sorter.order = order
    
    def toggle_sort_order(self) -> SortOrder:
        """Toggle between ascending and descending sort order.
        
        Returns:
            The new sort order
        """
        return self.sorter.toggle_order()
    
    def cycle_sort_field(self) -> SortField:
        """Cycle to the next sort field.
        
        Cycles through: DATE_ADDED -> TITLE -> PROGRESS -> SPEED -> SIZE -> STAGE -> DATE_ADDED
        
        Returns:
            The new sort field
        """
        field_order = [
            SortField.DATE_ADDED,
            SortField.TITLE,
            SortField.PROGRESS,
            SortField.SPEED,
            SortField.SIZE,
            SortField.STAGE,
        ]
        
        current_index = field_order.index(self.sorter.field)
        next_index = (current_index + 1) % len(field_order)
        next_field = field_order[next_index]
        
        self.sorter.set_sort(next_field)
        return next_field
    
    def get_sort_description(self) -> str:
        """Get a human-readable description of the current sort.
        
        Returns:
            String describing the current sort
        """
        return self.sorter.get_sort_description()
    
    def get_sort_field(self) -> SortField:
        """Get the current sort field.
        
        Returns:
            Current sort field
        """
        return self.sorter.field
    
    def get_sort_order(self) -> SortOrder:
        """Get the current sort order.
        
        Returns:
            Current sort order
        """
        return self.sorter.order
