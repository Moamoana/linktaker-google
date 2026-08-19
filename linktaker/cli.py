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


def main():
    """Main execution."""
    urls = []

    # Preferred: build search URLs from keyword + date, no need to hand-craft a Google URL.
    if os.path.exists(KEYWORDS_FILE):
        keyword_entries = read_keywords(KEYWORDS_FILE)
        if keyword_entries:
            urls = [build_search_url(kw, date_filter, mode) for kw, date_filter, mode in keyword_entries]
            print(f"Built {len(urls)} search URL(s) from {KEYWORDS_FILE}")

    # Fallback: pre-built Google search URLs (backwards compatible).
    if not urls and os.path.exists(URLS_FILE):
        urls = read_urls(URLS_FILE)
        if urls:
            print(f"Loaded {len(urls)} search URL(s) from {URLS_FILE}")

    if not urls:
        print(f"No input found. Create {KEYWORDS_FILE} (keyword | date | mode) or {URLS_FILE} (full Google search URLs).")
        sys.exit(1)

    proxies = []
    if USE_PROXY:
        proxies = read_proxies(PROXIES_FILE)

    auth = read_auth()

    print(f"Processing {len(urls)} URL(s) — mode: {FETCH_MODE}")
    print(f"Filtering social media URLs ({len(SOCIAL_MEDIA_DOMAINS)} domains excluded)")

    if USE_GOOGLE_RSS:
        print(f"Google News RSS: ENABLED (decode delay: {RSS_DECODE_DELAY}s)")

    if proxies:
        print(f"Proxy rotation enabled ({len(proxies)} proxy/proxies)")
    else:
        print("No proxies loaded - proceeding without proxy rotation")

    if USE_CLOUDFLARE_BYPASS:
        if CLOUDSCRAPER_AVAILABLE:
            print(f"Cloudflare bypass: ENABLED (cloudscraper)")
        else:
            print(f"Cloudflare bypass: curl_cffi only")

    if STEALTH_AVAILABLE:
        print(f"Playwright stealth: ENABLED")
    if BROWSERFORGE_AVAILABLE:
        print(f"browserforge fingerprints: ENABLED")

    # Create persistent browser manager (shared across all pages)
    browser_mgr = None
    if FETCH_MODE in ("auto", "playwright") and PLAYWRIGHT_AVAILABLE:
        proxy = random.choice(proxies) if proxies else None
        browser_mgr = BrowserManager(proxy=proxy)
        # Lazy start — only launches when first needed
        print(f"Persistent browser: READY (will launch on first use)")

    all_links = set()

    try:
        # When using playwright mode, run sequentially (one browser)
        if FETCH_MODE == "playwright":
            # Shuffle so the date walk isn't sequential (less scraper-like)
            shuffled = list(urls)
            random.shuffle(shuffled)
            for i, u in enumerate(shuffled):
                all_links |= (process_one_url(u, None, auth, browser_mgr) or set())
                # Jitter between search URLs to avoid burst-rate detection
                if i < len(shuffled) - 1:
                    delay = random.uniform(8, 20)
                    print(f"  Waiting {delay:.1f}s before next URL...")
                    time.sleep(delay)
        else:
            workers = min(PARALLEL_WORKERS, len(urls))
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = {}
                    for u in urls:
                        proxy = random.choice(proxies) if proxies else None
                        futures[ex.submit(process_one_url, u, proxy, auth, browser_mgr)] = u

                    for fut in as_completed(futures):
                        u = futures[fut]
                        try:
                            res = fut.result() or set()
                            all_links |= res
                        except Exception as e:
                            print(f"[{u}] Failed: {e}")
            else:
                for u in urls:
                    proxy = random.choice(proxies) if proxies else None
                    all_links |= (process_one_url(u, proxy, auth, browser_mgr) or set())
    finally:
        # Always close browser
        if browser_mgr:
            browser_mgr.close()
            print(f"Browser closed")

    # Strip AMP from all collected links
    all_links = {strip_amp(link) for link in all_links}

    # Write results
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\nLinks saved to {OUT_FILE} (unique: {len(all_links)})")

    if RUN_BATCH:
        try:
            subprocess.run(["scrape-onm-list.bat"], check=True, shell=True)
            print("scrape-onm-list.bat executed.")
            print(f"\ncount of links: (unique: {len(all_links)})")
        except subprocess.CalledProcessError as e:
            print(f"Error executing scrape-onm-list.bat: {e}")
        except FileNotFoundError:
            print("scrape-onm-list.bat not found")
