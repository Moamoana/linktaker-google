import random
import subprocess
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .browser import BrowserManager
from .config import (
    KEYWORDS_FILE, URLS_FILE, PROXIES_FILE, OUT_FILE, RUN_BATCH,
    USE_PROXY, FETCH_MODE, USE_GOOGLE_RSS, RSS_DECODE_DELAY,
    USE_CLOUDFLARE_BYPASS, PARALLEL_WORKERS, SOCIAL_MEDIA_DOMAINS,
)
from .deps import CLOUDSCRAPER_AVAILABLE, STEALTH_AVAILABLE, BROWSERFORGE_AVAILABLE, PLAYWRIGHT_AVAILABLE
from .fetchers import process_one_url
from .io_utils import read_urls, read_proxies, read_auth
from .keywords import build_search_url, read_keywords
from .url_utils import strip_amp


import argparse

def main():
    """Main execution with Issue #2 CLI Parameters."""
    parser = argparse.ArgumentParser(description="LinkTaker - Advanced News Scraper")
    parser.add_argument("--engine", choices=["google", "yahoo"], default="google", help="Search engine to use")
    parser.add_argument("--input", type=str, help="Path to input text file containing keywords.")
    parser.add_argument("--from", dest="date_from", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", dest="date_until", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--sort", choices=["latest", "relevance"], default="relevance", help="Sort method")
    parser.add_argument("--tab", choices=["news", "all"], default="news", help="Google tab (Issue #3)")
    parser.add_argument("--output", type=str, default="output.txt", help="Output file path")
    parser.add_argument("--max-pages", type=int, default=0, help="Max pages to crawl per keyword (0 = all)")
    parser.add_argument("--proxy", type=str, help="Manual proxy string")
    
    args = parser.parse_args()

    urls = []

    # Issue #2: Parse keywords from --input
    if args.input and os.path.exists(args.input):
        with open(args.input, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        for kw in keywords:
            if args.engine == "google":
                # Issue #3: Tab 'Semua' atau 'Berita'
                google_mode = "nws" if args.tab == "news" else ""
                urls.append(build_search_url(kw, args.date_from, args.date_until, args.sort, google_mode))
        print(f"Built {len(urls)} search URL(s) from {args.input}")

    if not urls:
        print(f"No input found. Please use --input with a valid keyword file.")
        sys.exit(1)

    proxies = [args.proxy] if args.proxy else []
    auth = read_auth()

    print(f"Processing {len(urls)} URL(s) — engine: {args.engine}, mode: {FETCH_MODE}")
    print(f"Filtering social media URLs ({len(SOCIAL_MEDIA_DOMAINS)} domains excluded)")

    if proxies:
        print(f"Proxy rotation enabled ({len(proxies)} proxy/proxies)")
    else:
        print("No proxies loaded - proceeding without proxy rotation")

    if STEALTH_AVAILABLE:
        print(f"Playwright stealth: ENABLED")

    # Create persistent browser manager (shared across all pages)
    browser_mgr = None
    if FETCH_MODE in ("auto", "playwright") and PLAYWRIGHT_AVAILABLE:
        proxy = random.choice(proxies) if proxies else None
        browser_mgr = BrowserManager(proxy=proxy)
        print(f"Persistent browser: READY (will launch on first use)")

    all_links = set()

    try:
        if FETCH_MODE == "playwright":
            shuffled = list(urls)
            random.shuffle(shuffled)
            for i, u in enumerate(shuffled):
                all_links |= (process_one_url(u, None, auth, browser_mgr, max_pages=args.max_pages) or set())
                if i < len(shuffled) - 1:
                    delay = random.uniform(8, 20)
                    time.sleep(delay)
        else:
            workers = min(PARALLEL_WORKERS, len(urls))
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = {}
                    for u in urls:
                        proxy = random.choice(proxies) if proxies else None
                        futures[ex.submit(process_one_url, u, proxy, auth, browser_mgr, max_pages=args.max_pages)] = u

                    for fut in as_completed(futures):
                        try:
                            res = fut.result() or set()
                            all_links |= res
                        except Exception as e:
                            print(f"[{futures[fut]}] Failed: {e}")
            else:
                for u in urls:
                    proxy = random.choice(proxies) if proxies else None
                    all_links |= (process_one_url(u, proxy, auth, browser_mgr, max_pages=args.max_pages) or set())
    finally:
        if browser_mgr:
            browser_mgr.close()
            print(f"Browser closed")

    all_links = {strip_amp(link) for link in all_links}

    with open(args.output, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\nLinks saved to {args.output} (unique: {len(all_links)})")
