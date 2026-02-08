"""Web scraper source for magnet links.

This module provides WebScraperSource, which uses an ExtractionPipeline
to discover magnet links from web pages. Different websites can be supported
by configuring different pipelines.

Example:
    from haven_cli.plugins.builtin.bittorrent.sources.steps import (
        FetchHtmlStep,
        SelectElementsStep,
        ForEachElement,
        ExtractAttributeStep,
        ExtractTextStep,
        BuildMagnetLinkStep,
    )
    from haven_cli.plugins.builtin.bittorrent.sources.extraction import ExtractionPipeline
    
    # Define a pipeline for a specific site
    pipeline = ExtractionPipeline([
        FetchHtmlStep(url_template="https://example.com/search?q={query}"),
        SelectElementsStep(selector=".torrent-item"),
        ForEachElement([
            ExtractAttributeStep(attribute="href", output_key="uri"),
            ExtractTextStep(selector=".title", output_key="title"),
            BuildMagnetLinkStep(source_name="example"),
        ]),
    ])
    
    # Create the source
    config = SourceConfig(name="example", url="https://example.com")
    source = WebScraperSource(config=config, pipeline=pipeline)
    
    # Search for magnet links
    links = await source.search("python tutorial")
"""

from __future__ import annotations

from typing import List, Optional

from haven_cli.plugins.builtin.bittorrent.sources.base import (
    MagnetLink,
    MagnetSource,
    SourceConfig,
    SourceHealth,
    SourceHealthStatus,
)
from haven_cli.plugins.builtin.bittorrent.sources.extraction import ExtractionPipeline


class WebScraperSource(MagnetSource):
    """Magnet source that uses an extraction pipeline to scrape web pages.
    
    This source is highly flexible - different websites can be supported
    by configuring different extraction pipelines. The pipeline defines
    how to fetch HTML, select elements, extract data, and build magnet links.
    
    Example:
        pipeline = ExtractionPipeline([
            FetchHtmlStep(url_template="https://example.com/search?q={query}"),
            SelectElementsStep(selector=".torrent-item"),
            ForEachElement([
                ExtractAttributeStep(attribute="href", output_key="uri"),
                ExtractTextStep(selector=".title", output_key="title"),
                BuildMagnetLinkStep(source_name="example"),
            ]),
        ])
        
        source = WebScraperSource(
            config=SourceConfig(name="example", url="https://example.com"),
            pipeline=pipeline,
        )
    """
    
    def __init__(
        self,
        config: SourceConfig,
        pipeline: ExtractionPipeline,
        trending_pipeline: Optional[ExtractionPipeline] = None,
    ) -> None:
        """Initialize the web scraper source.
        
        Args:
            config: Source configuration
            pipeline: Pipeline for search queries
            trending_pipeline: Optional pipeline for trending content
        """
        super().__init__(config)
        self._pipeline = pipeline
        self._trending_pipeline = trending_pipeline
    
    @property
    def pipeline(self) -> ExtractionPipeline:
        """Get the search pipeline."""
        return self._pipeline
    
    @property
    def trending_pipeline(self) -> Optional[ExtractionPipeline]:
        """Get the trending pipeline."""
        return self._trending_pipeline
    
    async def search(self, query: str) -> List[MagnetLink]:
        """Search for magnet links matching a query.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching magnet links
        """
        if not self.enabled:
            return []
        
        # Execute the pipeline
        context = await self._pipeline.execute(query=query, source_name=self.name)
        
        # Return magnet links
        return context.magnet_links
    
    async def health_check(self) -> SourceHealth:
        """Check the health of this source.
        
        Performs a simple search to verify the source is working.
        
        Returns:
            SourceHealth with status and details
        """
        if not self.enabled:
            return SourceHealth(
                status=SourceHealthStatus.UNKNOWN,
                message="Source is disabled",
            )
        
        try:
            # Try a simple search
            links = await self.search("")
            
            if links:
                return SourceHealth(
                    status=SourceHealthStatus.HEALTHY,
                    message=f"Found {len(links)} magnet links",
                    details={"link_count": len(links)},
                )
            else:
                return SourceHealth(
                    status=SourceHealthStatus.DEGRADED,
                    message="No magnet links found",
                    details={"link_count": 0},
                )
        except Exception as e:
            return SourceHealth(
                status=SourceHealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                details={"error": str(e)},
            )
    
    async def get_trending(self, category: str = "all", limit: int = 10) -> List[MagnetLink]:
        """Get trending/popular magnet links.
        
        Args:
            category: Content category filter
            limit: Maximum number of results
            
        Returns:
            List of trending magnet links
        """
        if not self.enabled:
            return []
        
        if not self._trending_pipeline:
            # Fall back to search with empty query
            links = await self.search("")
        else:
            # Execute trending pipeline
            context = await self._trending_pipeline.execute(
                query="",
                source_name=self.name,
                category=category,
            )
            links = context.magnet_links
        
        # Apply limit
        return links[:limit]
    
    def validate_config(self) -> List[str]:
        """Validate the source configuration.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = super().validate_config()
        
        # Validate pipeline
        if not self._pipeline:
            errors.append("Pipeline is required")
        
        # Validate URL
        if not self._config.url:
            errors.append("URL is required")
        
        return errors
    
    def __repr__(self) -> str:
        """String representation of the source."""
        return f"WebScraperSource(name={self.name!r}, enabled={self.enabled}, pipeline={self._pipeline.name!r})"
