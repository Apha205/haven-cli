# BitTorrent Plugin Implementation

## Overview

The BitTorrent plugin for Haven CLI provides a flexible, composable system for discovering and downloading magnet links from various web sources. The key innovation is the **extraction pipeline abstraction** that allows different websites to be supported through configuration rather than code changes.

## Architecture

### Core Components

1. **Extraction Pipeline** (`extraction.py`)
   - `ExtractionContext`: Data container that flows through the pipeline
   - `ExtractionStep`: Abstract base class for transformation steps
   - `ExtractionPipeline`: Composes multiple steps together
   - `ForEachElement`: Iterates over selected elements and runs sub-steps
   - `ConditionalStep`: Executes steps based on conditions

2. **Extraction Steps** (`steps.py`)
   - `FetchHtmlStep`: Fetches HTML from a URL template
   - `SelectElementsStep`: Selects elements using CSS selectors
   - `ExtractAttributeStep`: Extracts element attributes
   - `ExtractTextStep`: Extracts text content
   - `RegexStep`: Applies regex patterns to extract data
   - `TransformStep`: Applies custom transformation functions
   - `SetVariableStep`: Sets pipeline variables
   - `BuildMagnetLinkStep`: Builds MagnetLink objects from extracted data
   - `FilterStep`: Filters magnet links by criteria
   - `LimitStep`: Limits number of results
   - `SortStep`: Sorts magnet links
   - `ParseSizeStep`: Parses human-readable size strings
   - `UrlJoinStep`: Joins relative URLs with base URL

3. **Source Abstraction** (`base.py`, `scraper.py`)
   - `MagnetSource`: Abstract base class for magnet link sources
   - `MagnetLink`: Dataclass representing a discovered magnet link
   - `SourceConfig`: Configuration for a source
   - `SourceHealth`: Health check result
   - `WebScraperSource`: Concrete source using extraction pipeline

4. **Plugin** (`plugin.py`)
   - `BitTorrentPlugin`: Main plugin class
   - `BitTorrentConfig`: Plugin configuration

## Usage Example

### Creating a Pipeline for a Website

```python
from haven_cli.plugins.builtin.bittorrent.sources.steps import (
    FetchHtmlStep,
    SelectElementsStep,
    ForEachElement,
    ExtractAttributeStep,
    ExtractTextStep,
    RegexStep,
    BuildMagnetLinkStep,
)
from haven_cli.plugins.builtin.bittorrent.sources.extraction import ExtractionPipeline

# Define a pipeline for a hypothetical torrent site
pipeline = ExtractionPipeline([
    # Fetch search results page
    FetchHtmlStep(url_template="https://example.com/search?q={query}"),
    
    # Select all torrent items
    SelectElementsStep(selector=".torrent-item"),
    
    # For each torrent item, extract data
    ForEachElement([
        # Extract magnet URI
        ExtractAttributeStep(attribute="href", output_key="uri"),
        
        # Extract title
        ExtractTextStep(selector=".title", output_key="title"),
        
        # Extract infohash from magnet URI
        RegexStep(
            pattern=r"btih:([a-fA-F0-9]{40})",
            input_key="uri",
            output_key="infohash",
        ),
        
        # Extract size text
        ExtractTextStep(selector=".size", output_key="size_text"),
        
        # Parse size to bytes
        ParseSizeStep(input_key="size_text", output_key="size"),
        
        # Extract seeders
        ExtractTextStep(selector=".seeders", output_key="seeders_text"),
        TransformStep(
            input_key="seeders_text",
            output_key="seeders",
            transform=int,
            default=0,
        ),
        
        # Build the magnet link
        BuildMagnetLinkStep(source_name="example"),
    ]),
    
    # Sort by seeders (descending)
    SortStep(by="seeders", reverse=True),
    
    # Limit to top 10 results
    LimitStep(limit=10),
])

# Create the source
from haven_cli.plugins.builtin.bittorrent.sources.base import SourceConfig
from haven_cli.plugins.builtin.bittorrent.sources.scraper import WebScraperSource

config = SourceConfig(
    name="example",
    url="https://example.com",
    enabled=True,
    max_results=10,
)

source = WebScraperSource(config=config, pipeline=pipeline)

# Search for magnet links
links = await source.search("python tutorial")

for link in links:
    print(f"{link.title} - {link.size / (1024**3):.2f} GB - {link.seeders} seeders")
```

### Using the Plugin

```python
from haven_cli.plugins.builtin.bittorrent import BitTorrentPlugin, BitTorrentConfig

# Create plugin with configuration
config = BitTorrentConfig(
    download_dir="downloads/bittorrent",
    max_concurrent_downloads=3,
    sources=[
        {
            "name": "example",
            "url": "https://example.com",
            "enabled": True,
            # Pipeline configuration would go here
        },
    ],
)

plugin = BitTorrentPlugin(config=config)
await plugin.initialize()

# Discover sources
sources = await plugin.discover_sources(query="python tutorial", limit=10)

# Archive a source
result = await plugin.archive(sources[0])
if result.success:
    print(f"Downloaded to: {result.output_path}")
```

## Key Design Decisions

### 1. Composable Pipeline (Not RSS-Based)

The user explicitly requested **NOT** to use RSS feeds. Instead, the system uses HTML scraping with composable extraction steps. This provides:

- **Flexibility**: Different websites can be supported by configuring different pipelines
- **Reusability**: Steps can be mixed and matched
- **Testability**: Each step can be tested independently
- **Extensibility**: New steps can be added without modifying existing code

### 2. Extraction Context

The `ExtractionContext` dataclass holds all state as it flows through the pipeline:

- `raw_html`: Fetched HTML content
- `soup`: BeautifulSoup parsed HTML (lazy)
- `elements`: Selected elements
- `current_element`: Current element being processed
- `current_data`: Data extracted for current element
- `magnet_links`: Final list of magnet links
- `variables`: Pipeline-level variables
- `errors`: List of errors encountered

### 3. Step-Based Architecture

Each step is a stateless transformation:

```python
@dataclass
class FetchHtmlStep(ExtractionStep):
    url_template: str
    timeout: int = 30
    
    @property
    def name(self) -> str:
        return "fetch_html"
    
    async def execute(self, context: ExtractionContext) -> ExtractionContext:
        # Fetch HTML and update context
        url = self.url_template.format(query=context.query)
        response = await httpx.get(url)
        context.raw_html = response.text
        return context
```

### 4. MagnetLink Dataclass

Standardized representation of discovered magnet links:

```python
@dataclass
class MagnetLink:
    infohash: str  # 40-character hex string
    uri: str  # Full magnet URI
    title: str
    size: int  # Bytes
    seeders: int
    leechers: int
    category: str
    discovered_at: datetime
    source_name: str
    metadata: Dict[str, Any]
```

## File Structure

```
haven_cli/plugins/builtin/bittorrent/
├── __init__.py              # Plugin exports
├── plugin.py                # Main BitTorrentPlugin class
└── sources/
    ├── __init__.py           # Source exports
    ├── base.py               # MagnetSource, MagnetLink, SourceConfig
    ├── extraction.py         # ExtractionPipeline, ExtractionContext, ExtractionStep
    ├── scraper.py            # WebScraperSource implementation
    └── steps.py              # Concrete extraction steps
```

## Testing

Tests are in `tests/plugins/test_bittorrent_extraction.py`:

- `TestExtractionContext`: Context creation, variables, cloning
- `TestSetVariableStep`: Setting pipeline variables
- `TestBuildMagnetLinkStep`: Building magnet links from data
- `TestRegexStep`: Regex extraction
- `TestExtractAttributeStep`: Attribute extraction
- `TestExtractTextStep`: Text extraction
- `TestMagnetLink`: MagnetLink creation, validation, URI parsing
- `TestExtractionPipeline`: Pipeline execution
- `TestForEachElement`: Iterating over elements

All 20 tests pass.

## Future Work

### 1. libtorrent Integration

The `archive()` method currently returns a placeholder. Full implementation would:

1. Create libtorrent session
2. Add magnet link to session
3. Download torrent metadata
4. Select video files based on extensions
5. Download content
6. Apply speed limits and seeding rules

### 2. Pipeline Configuration

Add support for defining pipelines from configuration files (YAML/JSON):

```yaml
sources:
  - name: example
    url: https://example.com
    pipeline:
      - type: fetch_html
        url_template: "https://example.com/search?q={query}"
      - type: select_elements
        selector: ".torrent-item"
      - type: for_each
        steps:
          - type: extract_attribute
            attribute: href
            output_key: uri
          - type: extract_text
            selector: .title
            output_key: title
          - type: regex
            pattern: "btih:([a-fA-F0-9]{40})"
            input_key: uri
            output_key: infohash
          - type: build_magnet_link
            source_name: example
```

### 3. Built-in Sources

Create pre-configured pipelines for popular torrent sites:

- `1337x.py`
- `ThePirateBay.py`
- `RARBG.py`
- `YTS.py`

### 4. State Persistence

Track seen infohashes and archived torrents in the database to avoid duplicates.

### 5. Job Scheduling

Integrate with the scheduler to periodically check sources for new content.

## Dependencies

- `beautifulsoup4==4.13.3`: HTML parsing
- `httpx==0.28.1`: Async HTTP client (already in dependencies)
- `libtorrent==2.0.11`: BitTorrent library (already in dependencies)

## Summary

The BitTorrent plugin provides a highly flexible, composable system for discovering magnet links from web sources. The extraction pipeline abstraction allows different websites to be supported through configuration rather than code changes, making the system easy to extend and maintain.
