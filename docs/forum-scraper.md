# Forum Scraper Source

The `ForumScraperSource` is a magnet link source designed for forum-based torrent sites. It's not opinionated about specific websites - the user configures the domain and forum ID.

## Overview

The forum scraper follows this workflow:

1. **Fetch forum listing page** - Gets the list of threads from a forum category
2. **Extract thread URLs** - Parses  the HTML to find individual thread links
3. **Fetch each thread page** - Visits each thread to extract torrent info
4. **Extract infohash** - Finds the torrent's infohash from the thread content
5. **Build magnet link** - Constructs a magnet URI from the infohash

## Configuration

### Basic Configuration

```python
from haven_cli.plugins.builtin.bittorrent.sources.forum import (
    ForumScraperSource,
    ForumSourceConfig,
)

config = ForumSourceConfig(
    name="sample_forum",
    domain="sample.com",
    forum_id="1",  # Forum category ID
    max_threads=10,  # Maximum threads to fetch
)

source = ForumScraperSource(config=config)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | `forum_{domain}_{forum_id}` | Unique name for this source |
| `domain` | str | required | Forum domain (e.g., "sample.com") |
| `forum_id` | str | required | Forum ID (fid parameter) |
| `max_threads` | int | 10 | Maximum number of threads to fetch |
| `listing_url_template` | str | `"https://{domain}/thread0806.php?fid={forum_id}"` | Template for listing page URL |
| `thread_url_template` | str | `"https://{domain}{thread_path}"` | Template for thread page URL |
| `infohash_pattern` | str | `r"【特徵全碼】：([A-Fa-f0-9]{40})"` | Regex to extract infohash |
| `title_pattern` | str | `r"<title>(.+?)</title>"` | Regex to extract title |
| `size_pattern` | str | `r"【影片大小】：([\d.]+)(GB\|MB\|KB)"` | Regex to extract size |

## Usage Example

### Basic Usage

```python
import asyncio
from haven_cli.plugins.builtin.bittorrent.sources.forum import (
    ForumScraperSource,
    ForumSourceConfig,
)

async def main():
    # Configure the source
    config = ForumSourceConfig(
        name="sample_fid26",
        domain="sample.com",
        forum_id="1",
        max_threads=5,
    )
    
    # Create and initialize the source
    source = ForumScraperSource(config=config)
    await source.initialize()
    
    # Health check
    health = await source.health_check()
    print(f"Health: {health.status.value} - {health.message}")
    
    # Search for magnet links
    magnets = await source.search("")
    
    # Display results
    for magnet in magnets:
        print(f"Title: {magnet.title}")
        print(f"Size: {magnet.size / (1024**3):.2f} GB")
        print(f"Infohash: {magnet.infohash}")
        print(f"URI: {magnet.uri}")
        print()

asyncio.run(main())
```

### Multiple Forums

```python
configs = [
    ForumSourceConfig(
        name="sample_fid1",
        domain="sample.com",
        forum_id="1",
        max_threads=5,
    ),
    ForumSourceConfig(
        name="sample_fid2",
        domain="sample.com",
        forum_id="2",
        max_threads=5,
    ),
]

all_magnets = []
for config in configs:
    source = ForumScraperSource(config=config)
    await source.initialize()
    magnets = await source.search("")
    all_magnets.extend(magnets)

print(f"Total magnets found: {len(all_magnets)}")
```

### Custom Patterns

For forums with different HTML structures, you can customize the regex patterns:

```python
config = ForumSourceConfig(
    name="custom_forum",
    domain="example.com",
    forum_id="1",
    max_threads=10,
    # Custom patterns for different forum formats
    infohash_pattern=r"Infohash:\s*([A-Fa-f0-9]{40})",
    title_pattern=r"<h1>(.+?)</h1>",
    size_pattern=r"Size:\s*([\d.]+)\s*(GB|MB|KB)",
)

source = ForumScraperSource(config=config)
```

## Integration with BitTorrent Plugin

The forum scraper can be integrated with the BitTorrent plugin:

```python
from haven_cli.plugins.builtin.bittorrent import BitTorrentPlugin, BitTorrentConfig

# Configure the BitTorrent plugin with forum sources
config = BitTorrentConfig(
    download_dir="downloads/bittorrent",
    max_concurrent_downloads=3,
    sources=[
        {
            "name": "sample_fid2",
            "type": "forum",
            "domain": "sample.com",
            "forum_id": "1",
            "max_threads": 5,
        },
        {
            "name": "sample_fid1",
            "type": "forum",
            "domain": "sample.com",
            "forum_id": "1",
            "max_threads": 5,
        },
    ],
)

plugin = BitTorrentPlugin(config=config)
await plugin.initialize()

# Discover sources
sources = await plugin.discover_sources()

# Archive a source
result = await plugin.archive(sources[0])
```

## Customization for Other Forums

The forum scraper is designed to work with PHPBB-style forums. To adapt it for other forums:

1. **Identify the listing page URL pattern**
2. **Find the CSS selector for thread links**
3. **Locate the infohash in thread pages**
4. **Update the regex patterns**

Example for a different forum:

```python
config = ForumSourceConfig(
    name="other_forum",
    domain="otherforum.com",
    forum_id="videos",
    max_threads=10,
    listing_url_template="https://{domain}/forum/{forum_id}",
    thread_url_template="https://{domain}{thread_path}",
    infohash_pattern=r"hash:\s*([A-Fa-f0-9]{40})",
    title_pattern=r"<h2 class='title'>(.+?)</h2>",
    size_pattern=r"size:\s*([\d.]+)\s*(GB|MB|KB)",
)
```

## Health Check

The forum scraper includes a health check that verifies:

1. The listing page is accessible
2. Thread URLs can be extracted
3. The source is properly configured

```python
health = await source.health_check()

if health.status == SourceHealthStatus.HEALTHY:
    print("Source is healthy")
elif health.status == SourceHealthStatus.DEGRADED:
    print("Source is degraded:", health.message)
else:
    print("Source is unhealthy:", health.message)
```

## Error Handling

The forum scraper handles errors gracefully:

- **Network errors**: Logged and skipped
- **Missing infohash**: Thread is skipped
- **Invalid magnet link**: Thread is skipped
- **HTML parsing errors**: Logged and skipped

## Performance Considerations

- **Sequential fetching**: Threads are fetched sequentially to avoid overwhelming the server
- **Rate limiting**: Consider adding delays between requests
- **Caching**: Consider caching thread pages to avoid re-fetching
- **Timeout**: Default timeout is 30 seconds per request

## Security Considerations

- **User-Agent**: Uses a standard browser User-Agent
- **No authentication**: Works with publicly accessible forums
- **No cookies**: Doesn't store or send cookies
- **HTTPS**: Uses HTTPS when available

## Limitations

- **First page only**: Only fetches the first page of the forum listing
- **No pagination**: Doesn't automatically navigate to subsequent pages
- **No search**: Doesn't support search queries (uses latest threads)
- **No authentication**: Doesn't support logged-in users

## Future Enhancements

Potential improvements:

1. **Pagination support**: Fetch multiple pages of the forum listing
2. **Search support**: Search for specific keywords
3. **Authentication**: Support for logged-in users
4. **Rate limiting**: Configurable delays between requests
5. **Caching**: Cache thread pages to reduce requests
6. **Parallel fetching**: Fetch multiple threads concurrently
7. **Incremental updates**: Track seen threads to avoid duplicates

## Troubleshooting

### No thread URLs found

- Check the CSS selector matches the forum's HTML structure
- Verify the forum is accessible without authentication
- Ensure the forum_id is correct

### No infohash found

- Check the infohash_pattern matches the forum's format
- Verify the thread contains torrent information
- Some threads may be announcements without torrents

### Network errors

- Check your internet connection
- Verify the forum domain is correct
- The forum may be blocking automated requests

## License

MIT License - See LICENSE file for details.
