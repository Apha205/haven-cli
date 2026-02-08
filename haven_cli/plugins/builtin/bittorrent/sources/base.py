"""Abstract base class for magnet link sources.

This module defines the interface that all magnet link sources must implement.
Sources can be RSS feeds, web scrapers, APIs, or any other source of magnet links.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from urllib.parse import unquote



class SourceHealthStatus(Enum):
    """Health status of a magnet source."""
    
    HEALTHY = auto()       # Source is working properly
    DEGRADED = auto()      # Source is working but with issues
    UNHEALTHY = auto()     # Source is not working
    UNKNOWN = auto()       # Health status could not be determined


@dataclass
class MagnetLink:
    """Represents a discovered magnet link.
    
    Attributes:
        infohash: The BTIH infohash (40-character hex string)
        uri: The full magnet URI
        title: Title/name of the torrent content
        size: Size in bytes (if known)
        seeders: Number of seeders (if known)
        leechers: Number of leechers (if known)
        category: Content category (e.g., "video", "audio", "software")
        discovered_at: When this link was discovered
        source_name: Name of the source that provided this link
        metadata: Additional source-specific metadata
    """
    
    infohash: str
    uri: str
    title: str = ""
    size: int = 0
    seeders: int = 0
    leechers: int = 0
    category: str = "unknown"
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    source_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate and normalize the magnet link."""
        # Ensure infohash is lowercase
        self.infohash = self.infohash.lower()
        
        # Validate infohash format (40 hex characters)
        if not len(self.infohash) == 40:
            raise ValueError(f"Invalid infohash length: {len(self.infohash)} (expected 40)")
        
        try:
            int(self.infohash, 16)
        except ValueError:
            raise ValueError(f"Invalid infohash format: {self.infohash} (expected hex)")
    
    @classmethod
    def from_magnet_uri(cls, uri: str, **kwargs: Any) -> "MagnetLink":
        """Create a MagnetLink from a magnet URI.
        
        Args:
            uri: The magnet URI (magnet:?xt=urn:btih:...)
            **kwargs: Additional attributes to set
            
        Returns:
            MagnetLink instance
            
        Raises:
            ValueError: If URI is not a valid magnet link
        """
        if not uri.startswith("magnet:"):
            raise ValueError(f"Not a magnet URI: {uri}")
        
        # Parse infohash from URI
        infohash = None
        for param in uri.split("&"):
            if param.startswith("xt=urn:btih:"):
                infohash = param.split(":")[-1]
                break
            elif param.startswith("magnet:?xt=urn:btih:"):
                infohash = param.split(":")[-1]
                break
        
        if not infohash:
            raise ValueError(f"Could not extract infohash from magnet URI: {uri}")
        
        # Parse display name if present
        title = kwargs.pop("title", "")
        if not title:
            for param in uri.split("&"):
                if param.startswith("dn="):
                    
                    title = unquote(param[3:])
                    break
        
        return cls(
            infohash=infohash,
            uri=uri,
            title=title,
            **kwargs,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "infohash": self.infohash,
            "uri": self.uri,
            "title": self.title,
            "size": self.size,
            "seeders": self.seeders,
            "leechers": self.leechers,
            "category": self.category,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None,
            "source_name": self.source_name,
            "metadata": self.metadata,
        }


@dataclass
class SourceHealth:
    """Health check result for a magnet source.
    
    Attributes:
        status: Overall health status
        message: Human-readable status message
        last_check: When the health check was performed
        details: Additional health check details
    """
    
    status: SourceHealthStatus
    message: str = ""
    last_check: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_healthy(self) -> bool:
        """Check if source is healthy or degraded."""
        return self.status in (SourceHealthStatus.HEALTHY, SourceHealthStatus.DEGRADED)


@dataclass
class SourceConfig:
    """Configuration for a magnet source.
    
    Attributes:
        name: Unique name for this source
        enabled: Whether this source is enabled
        url: URL or endpoint for the source
        filter_type: Content type filter (e.g., "video", "audio", "all")
        max_results: Maximum results to return per query
        timeout: Request timeout in seconds
        extra: Additional source-specific configuration
    """
    
    name: str
    enabled: bool = True
    url: str = ""
    filter_type: str = "video"
    max_results: int = 10
    timeout: int = 30
    extra: Dict[str, Any] = field(default_factory=dict)


class MagnetSource(ABC):
    """Abstract base class for magnet link sources.
    
    A MagnetSource is responsible for discovering magnet links from
    a specific source (RSS feed, website, API, etc.). Sources are
    configured with search terms and return matching magnet links.
    
    Example:
        class MySource(MagnetSource):
            async def search(self, query: str) -> List[MagnetLink]:
                # Implement search logic
                ...
            
            async def health_check(self) -> SourceHealth:
                # Implement health check
                ...
        
        source = MySource(config=SourceConfig(name="my_source", url="https://..."))
        links = await source.search("python tutorial")
    """
    
    def __init__(self, config: SourceConfig) -> None:
        """Initialize the magnet source.
        
        Args:
            config: Source configuration
        """
        self._config = config
        self._initialized = False
    
    @property
    def name(self) -> str:
        """Get the source name."""
        return self._config.name
    
    @property
    def config(self) -> SourceConfig:
        """Get the source configuration."""
        return self._config
    
    @property
    def enabled(self) -> bool:
        """Check if source is enabled."""
        return self._config.enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable the source."""
        self._config.enabled = value
    
    async def initialize(self) -> bool:
        """Initialize the source.
        
        Override this method to perform setup tasks like
        validating credentials, checking connectivity, etc.
        
        Returns:
            True if initialization succeeded
        """
        self._initialized = True
        return True
    
    async def shutdown(self) -> None:
        """Shutdown the source.
        
        Override this method to perform cleanup tasks.
        """
        self._initialized = False
    
    @abstractmethod
    async def search(self, query: str) -> List[MagnetLink]:
        """Search for magnet links matching a query.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching magnet links
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> SourceHealth:
        """Check the health of this source.
        
        Returns:
            SourceHealth with status and details
        """
        pass
    
    async def get_trending(self, category: str = "all", limit: int = 10) -> List[MagnetLink]:
        """Get trending/popular magnet links.
        
        Override this method if the source supports trending content.
        
        Args:
            category: Content category filter
            limit: Maximum number of results
            
        Returns:
            List of trending magnet links (empty by default)
        """
        return []
    
    def validate_config(self) -> List[str]:
        """Validate the source configuration.
        
        Override this method to implement configuration validation.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not self._config.name:
            errors.append("Source name is required")
        
        return errors
    
    def __repr__(self) -> str:
        """String representation of the source."""
        return f"{self.__class__.__name__}(name={self.name!r}, enabled={self.enabled})"
