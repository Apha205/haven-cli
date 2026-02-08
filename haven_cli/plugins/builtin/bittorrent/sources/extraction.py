"""Composable extraction pipeline for web scraping magnet links.

This module provides a flexible, composable pipeline for extracting magnet links
from web pages. Each step in the pipeline transforms data, allowing different
websites to be supported through different pipeline configurations.

Example:
    pipeline = ExtractionPipeline([
        FetchHtmlStep(url_template="https://example.com/search?q={query}"),
        SelectElementsStep(selector=".torrent-item"),
        ExtractAttributeStep(attribute="href", output_key="magnet_uri"),
        RegexStep(pattern=r"btih:([a-fA-F0-9]{40})", input_key="magnet_uri", output_key="infohash"),
        BuildMagnetLinkStep(),
    ])
    
    source = WebScraperSource(config=config, pipeline=pipeline)
    links = await source.search("python tutorial")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from haven_cli.plugins.builtin.bittorrent.sources.base import MagnetLink


@dataclass
class ExtractionContext:
    """Context that flows through the extraction pipeline.
    
    Each step in the pipeline reads from and writes to this context.
    The context accumulates data as it flows through the pipeline.
    
    Attributes:
        query: The original search query (if any)
        raw_html: The raw HTML content fetched
        soup: BeautifulSoup parsed HTML (lazy)
        current_element: Current element being processed (for iteration)
        elements: List of selected elements
        extracted_data: List of dicts with extracted data per element
        current_data: Current data dict being built (for single item processing)
        magnet_links: Final list of extracted magnet links
        variables: Pipeline-level variables (can be set/read by steps)
        errors: List of errors encountered during extraction
        metadata: Additional metadata about the extraction
    """
    
    query: str = ""
    raw_html: str = ""
    _soup: Optional[BeautifulSoup] = field(default=None, repr=False)
    current_element: Any = None
    elements: List[Any] = field(default_factory=list)
    extracted_data: List[Dict[str, Any]] = field(default_factory=list)
    current_data: Dict[str, Any] = field(default_factory=dict)
    magnet_links: List[MagnetLink] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def soup(self) -> BeautifulSoup:
        """Get BeautifulSoup instance (lazy initialization)."""
        if self._soup is None and self.raw_html:
            self._soup = BeautifulSoup(self.raw_html, "html.parser")
        return self._soup
    
    def clone(self, **updates: Any) -> "ExtractionContext":
        """Create a copy of this context with optional updates."""
        new_ctx = ExtractionContext(
            query=self.query,
            raw_html=self.raw_html,
            _soup=self._soup,
            current_element=self.current_element,
            elements=self.elements.copy(),
            extracted_data=self.extracted_data.copy(),
            current_data=self.current_data.copy(),
            magnet_links=self.magnet_links.copy(),
            variables=self.variables.copy(),
            errors=self.errors.copy(),
            metadata=self.metadata.copy(),
        )
        for key, value in updates.items():
            setattr(new_ctx, key, value)
        return new_ctx
    
    def add_error(self, error: str) -> None:
        """Add an error message to the context."""
        self.errors.append(error)
    
    def set_variable(self, key: str, value: Any) -> None:
        """Set a pipeline variable."""
        self.variables[key] = value
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a pipeline variable."""
        return self.variables.get(key, default)


class ExtractionStep(ABC):
    """Abstract base class for extraction pipeline steps.
    
    Each step transforms the ExtractionContext in some way. Steps can:
    - Fetch HTML from a URL
    - Select elements using CSS selectors
    - Extract attributes or text from elements
    - Apply regex transformations
    - Build final MagnetLink objects
    
    Steps should be stateless and reusable across different pipelines.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the step name for logging/debugging."""
        pass
    
    @abstractmethod
    async def execute(self, context: ExtractionContext) -> ExtractionContext:
        """Execute this step, transforming the context.
        
        Args:
            context: The current extraction context
            
        Returns:
            Updated extraction context
        """
        pass
    
    def __repr__(self) -> str:
        """String representation of the step."""
        return f"{self.__class__.__name__}()"


class ExtractionPipeline:
    """Composable pipeline for extracting magnet links from web pages.
    
    A pipeline consists of multiple ExtractionSteps that are executed
    in sequence. Each step transforms the context, building up the
    final list of MagnetLinks.
    
    Example:
        pipeline = ExtractionPipeline([
            FetchHtmlStep(url_template="https://example.com/search?q={query}"),
            SelectElementsStep(selector=".torrent-item"),
            ForEachElement([
                ExtractAttributeStep(attribute="href", output_key="uri"),
                ExtractTextStep(selector=".title", output_key="title"),
                BuildMagnetLinkStep(),
            ]),
        ])
    """
    
    def __init__(self, steps: List[ExtractionStep], name: str = "default"):
        """Initialize the pipeline with a list of steps.
        
        Args:
            steps: List of extraction steps to execute in order
            name: Optional name for the pipeline (for logging)
        """
        self.steps = steps
        self.name = name
    
    async def execute(self, initial_context: Optional[ExtractionContext] = None, **kwargs: Any) -> ExtractionContext:
        """Execute the pipeline and return the final context.
        
        Args:
            initial_context: Optional starting context
            **kwargs: Additional context attributes to set
            
        Returns:
            Final extraction context with magnet_links populated
        """
        context = initial_context or ExtractionContext()
        
        # Apply any kwargs to the context
        for key, value in kwargs.items():
            if hasattr(context, key):
                setattr(context, key, value)
        
        # Execute each step in sequence
        for step in self.steps:
            try:
                context = await step.execute(context)
            except Exception as e:
                context.add_error(f"Step '{step.name}' failed: {e}")
                # Continue with remaining steps unless critical
        
        return context
    
    async def extract(self, query: str = "", **kwargs: Any) -> List[MagnetLink]:
        """Execute the pipeline and return extracted magnet links.
        
        This is a convenience method that creates a context, runs the
        pipeline, and returns the magnet_links.
        
        Args:
            query: Search query to use
            **kwargs: Additional context attributes
            
        Returns:
            List of extracted MagnetLink objects
        """
        context = await self.execute(query=query, **kwargs)
        return context.magnet_links
    
    def __repr__(self) -> str:
        """String representation of the pipeline."""
        step_names = [s.name for s in self.steps]
        return f"ExtractionPipeline(name={self.name!r}, steps={step_names})"


class ForEachElement(ExtractionStep):
    """Step that iterates over selected elements and runs sub-steps for each.
    
    This is useful for processing multiple torrent items on a page.
    Each element becomes the current_element, and sub-steps are run
    to extract data from that element.
    """
    
    def __init__(self, steps: List[ExtractionStep], use_elements: bool = True):
        """Initialize the for-each step.
        
        Args:
            steps: Sub-steps to run for each element
            use_elements: If True, iterate over context.elements.
                         If False, iterate over context.extracted_data.
        """
        self.steps = steps
        self.use_elements = use_elements
    
    @property
    def name(self) -> str:
        return "for_each_element"
    
    async def execute(self, context: ExtractionContext) -> ExtractionContext:
        """Execute sub-steps for each element."""
        items = context.elements if self.use_elements else context.extracted_data
        
        for item in items:
            # Create a sub-context for this element
            sub_context = context.clone(
                current_element=item if self.use_elements else None,
                current_data=item.copy() if isinstance(item, dict) else {},
            )
            
            # Run sub-steps
            for step in self.steps:
                try:
                    sub_context = await step.execute(sub_context)
                except Exception as e:
                    sub_context.add_error(f"ForEach sub-step '{step.name}' failed: {e}")
            
            # Merge results back
            context.magnet_links.extend(sub_context.magnet_links)
            context.extracted_data.append(sub_context.current_data)
            context.errors.extend(sub_context.errors)
        
        return context
    
    def __repr__(self) -> str:
        step_names = [s.name for s in self.steps]
        return f"ForEachElement(steps={step_names})"


class ConditionalStep(ExtractionStep):
    """Step that only executes if a condition is met.
    
    The condition is evaluated against the context.
    """
    
    def __init__(
        self,
        step: ExtractionStep,
        condition_key: str,
        condition_value: Any = True,
    ):
        """Initialize the conditional step.
        
        Args:
            step: Step to execute if condition is met
            condition_key: Context variable key to check
            condition_value: Expected value (default: True)
        """
        self.step = step
        self.condition_key = condition_key
        self.condition_value = condition_value
    
    @property
    def name(self) -> str:
        return f"conditional_{self.step.name}"
    
    async def execute(self, context: ExtractionContext) -> ExtractionContext:
        """Execute the step only if condition is met."""
        actual_value = context.get_variable(self.condition_key)
        if actual_value == self.condition_value:
            return await self.step.execute(context)
        return context
