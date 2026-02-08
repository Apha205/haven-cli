"""Standalone test of forum scraper logic."""

import asyncio
import re
import httpx
from bs4 import BeautifulSoup


def extract_thread_urls(html: str, domain: str) -> list:
    """Extract thread URLs from forum listing page."""
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
    forum_id = "26"
    max_threads = 3
    
    print(f"Testing forum scraper for {domain}")
    print(f"Forum ID: {forum_id}")
    print(f"Max threads: {max_threads}")
    print("=" * 60)
    
    # Fetch listing page
    listing_url = f"https://{domain}/thread0806.php?fid={forum_id}"
    print(f"\nFetching listing page: {listing_url}")
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(
            listing_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        html = response.text
    
    print(f"✓ Fetched {len(html)} bytes")
    
    # Extract thread URLs
    thread_urls = extract_thread_urls(html, domain)
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
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i, thread_url in enumerate(thread_urls, 1):
            print(f"\n[{i}/{len(thread_urls)}] Processing: {thread_url}")
            
            try:
                # Fetch thread page
                response = await client.get(
                    thread_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    },
                )
                thread_html = response.text
                
                # Extract magnet info
                info = extract_magnet_info(thread_html)
                
                if not info["infohash"]:
                    print("  ✗ No infohash found")
                    continue
                
                # Build magnet link
                magnet_uri = f"magnet:?xt=urn:btih:{info['infohash']}"
                
                all_magnets.append({
                    "title": info["title"],
                    "infohash": info["infohash"],
                    "size": info["size"],
                    "uri": magnet_uri,
                    "thread_url": thread_url,
                })
                
                print(f"  ✓ Extracted: {info['title'][:60]}...")
                print(f"    Size: {info['size'] / (1024**3):.2f} GB")
                print(f"    Infohash: {info['infohash']}")
            
            except Exception as e:
                print(f"  ✗ Error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"SUMMARY: Successfully extracted {len(all_magnets)} magnet links")
    print("=" * 60)
    
    for i, magnet in enumerate(all_magnets, 1):
        print(f"\n{i}. {magnet['title']}")
        print(f"   Infohash: {magnet['infohash']}")
        print(f"   Size: {magnet['size'] / (1024**3):.2f} GB")
        print(f"   URI: {magnet['uri']}")


if __name__ == "__main__":
    print("Testing Forum Scraper (Standalone Version)")
    print("=" * 60)
    asyncio.run(test_forum_scraper())
