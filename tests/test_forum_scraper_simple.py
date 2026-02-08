"""Simple test of forum scraper logic without full plugin system."""

import asyncio
import re
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import only what we need
from haven_cli.plugins.builtin.bittorrent.sources.base import MagnetLink
from haven_cli.plugins.builtin.bittorrent.sources.steps import FetchHtmlStep, ExtractionContext


def extract_thread_urls(html: str, domain: str) -> list:
    """Extract thread URLs from forum listing page."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    
    # Find all thread links in listing
    # Pattern: /htm_data/YYMM/fid/threadid.html
    for link in soup.select("tr.tr3.t_one.tac h3 a"):
        href = link.get("href", "")
        if href.startswith("/htm_data/") and href.endswith(".html"):
            # Build full URL
            full_url = f"https://{domain}{href}"
            urls.append(full_url)
    
    return urls


def extract_magnet_info(html: str) -> dict:
    """Extract magnet info from thread page."""
    infohash_pattern = r"【特徵全碼】：([A-Fa-f0-9]{40})"
    title_pattern = r"<title>(.+?)</title>"
    size_pattern = r"【影片大小】：([\d.]+)(GB|MB|KB)"
    
    # Extract infohash
    infohash_match = re.search(infohash_pattern, html)
    infohash = infohash_match.group(1) if infohash_match else None
    
    # Extract title
    title_match = re.search(title_pattern, html)
    title = title_match.group(1) if title_match else ""
    
    # Clean up title
    title = re.sub(r"\s*-\s*.*?\|\s*.*$", "", title)
    title = re.sub(r"\s*-\s*.*?-\s*.*$", "", title)
    title = title.strip()
    
    # Extract size
    size = 0
    size_match = re.search(size_pattern, html)
    if size_match:
        size_value = float(size_match.group(1))
        size_unit = size_match.group(2).upper()
        
        multipliers = {
            "KB": 1024,
            "MB": 1024 ** 2,
            "GB": 1024 ** 3,
        }
        size = int(size_value * multipliers.get(size_unit, 1))
    
    return {
        "infohash": infohash,
        "title": title,
        "size": size,
    }


async def test_forum_scraper():
    """Test forum scraper logic."""
    domain = "sample.com"
    forum_id = "1"
    max_threads = 3
    
    print(f"Testing forum scraper for {domain}")
    print(f"Forum ID: {forum_id}")
    print(f"Max threads: {max_threads}")
    print("=" * 60)
    
    # Fetch listing page
    listing_url = f"https://{domain}/thread0806.php?fid={forum_id}"
    print(f"\nFetching listing page: {listing_url}")
    
    fetch_step = FetchHtmlStep(url_template=listing_url)
    context = await fetch_step.execute(ExtractionContext())
    
    if not context.raw_html:
        print("Failed to fetch listing page")
        return
    
    print(f"✓ Fetched {len(context.raw_html)} bytes")
    
    # Extract thread URLs
    thread_urls = extract_thread_urls(context.raw_html, domain)
    print(f"\n✓ Found {len(thread_urls)} thread URLs")
    
    if not thread_urls:
        print("No thread URLs found")
        return
    
    # Show first few URLs
    print("\nFirst 5 thread URLs:")
    for i, url in enumerate(thread_urls[:5], 1):
        print(f"  {i}. {url}")
    
    # Limit to max_threads
    thread_urls = thread_urls[:max_threads]
    print(f"\nProcessing {len(thread_urls)} threads...")
    
    # Process each thread
    all_magnets = []
    for i, thread_url in enumerate(thread_urls, 1):
        print(f"\n[{i}/{len(thread_urls)}] Processing: {thread_url}")
        
        try:
            # Fetch thread page
            fetch_step = FetchHtmlStep(url_template=thread_url)
            context = await fetch_step.execute(ExtractionContext())
            
            if not context.raw_html:
                print("  ✗ Failed to fetch thread page")
                continue
            
            # Extract magnet info
            info = extract_magnet_info(context.raw_html)
            
            if not info["infohash"]:
                print("  ✗ No infohash found")
                continue
            
            # Build magnet link
            magnet_uri = f"magnet:?xt=urn:btih:{info['infohash']}"
            
            # Create MagnetLink
            try:
                magnet = MagnetLink(
                    infohash=info["infohash"],
                    uri=magnet_uri,
                    title=info["title"],
                    size=info["size"],
                    category="video",
                    source_name=f"forum_{domain}_{forum_id}",
                    metadata={
                        "thread_url": thread_url,
                        "domain": domain,
                        "forum_id": forum_id,
                    },
                )
                all_magnets.append(magnet)
                print(f"  ✓ Extracted: {info['title'][:60]}...")
                print(f"    Size: {info['size'] / (1024**3):.2f} GB")
                print(f"    Infohash: {info['infohash']}")
            except ValueError as e:
                print(f"  ✗ Failed to create magnet link: {e}")
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY: Successfully extracted {len(all_magnets)} magnet links")
    print("=" * 60)
    
    for i, magnet in enumerate(all_magnets, 1):
        print(f"\n{i}. {magnet.title}")
        print(f"   Infohash: {magnet.infohash}")
        print(f"   Size: {magnet.size / (1024**3):.2f} GB")
        print(f"   URI: {magnet.uri}")


if __name__ == "__main__":
    print("Testing Forum Scraper (Simple Version)")
    print("=" * 60)
    asyncio.run(test_forum_scraper())
