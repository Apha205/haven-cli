"""Test the forum scraper source."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from haven_cli.plugins.builtin.bittorrent.sources.forum import (
    ForumScraperSource,
    ForumSourceConfig,
)


async def test_forum_scraper():
    """Test the forum scraper with sample.com."""
    
    # Configure the forum source
    config = ForumSourceConfig(
        name="sample_test",
        domain="sample.com",
        forum_id="1",  
        max_threads=3,  # Only fetch 3 threads for testing
    )
    
    # Create the source
    source = ForumScraperSource(config=config)
    
    # Initialize
    print("Initializing forum scraper...")
    initialized = await source.initialize()
    print(f"Initialized: {initialized}")
    
    # Health check
    print("\nPerforming health check...")
    health = await source.health_check()
    print(f"Health status: {health.status.value}")
    print(f"Health message: {health.message}")
    print(f"Health details: {health.details}")
    
    # Search for magnet links
    print("\nSearching for magnet links...")
    magnets = await source.search("")
    
    print(f"\nFound {len(magnets)} magnet links:")
    for i, magnet in enumerate(magnets, 1):
        print(f"\n{i}. {magnet.title}")
        print(f"   Infohash: {magnet.infohash}")
        print(f"   Size: {magnet.size / (1024**3):.2f} GB")
        print(f"   URI: {magnet.uri}")
        print(f"   Source: {magnet.source_name}")
        print(f"   Metadata: {magnet.metadata}")


async def test_multiple_forums():
    """Test multiple forum configurations."""
    
    configs = [
        ForumSourceConfig(
            name="sample_fid1",
            domain="sample.com",
            forum_id="1",
            max_threads=2,
        ),
        ForumSourceConfig(
            name="sample_fid2",
            domain="sample.com",
            forum_id="2",
            max_threads=2,
        ),
    ]
    
    for config in configs:
        print(f"\n{'='*60}")
        print(f"Testing: {config.name}")
        print(f"{'='*60}")
        
        source = ForumScraperSource(config=config)
        await source.initialize()
        
        health = await source.health_check()
        print(f"Health: {health.status.value} - {health.message}")
        
        magnets = await source.search("")
        print(f"Found {len(magnets)} magnet links")
        
        for magnet in magnets[:2]:  # Show first 2
            print(f"  - {magnet.title[:60]}... ({magnet.size / (1024**3):.2f} GB)")


async def test_custom_patterns():
    """Test with custom regex patterns."""
    
    config = ForumSourceConfig(
        name="sample_custom",
        domain="sample.com",
        forum_id="26",
        max_threads=2,
        # Custom patterns can be specified here
        infohash_pattern=r"【特徵全碼】：([A-Fa-f0-9]{40})",
        title_pattern=r"<title>(.+?)</title>",
        size_pattern=r"【影片大小】：([\d.]+)(GB|MB|KB)",
    )
    
    source = ForumScraperSource(config=config)
    await source.initialize()
    
    magnets = await source.search("")
    print(f"\nCustom patterns test: Found {len(magnets)} magnet links")


if __name__ == "__main__":
    print("Testing Forum Scraper Source")
    print("=" * 60)
    
    # Run basic test
    asyncio.run(test_forum_scraper())
    
    # Test multiple forums
    # asyncio.run(test_multiple_forums())
    
    # Test custom patterns
    # asyncio.run(test_custom_patterns())
