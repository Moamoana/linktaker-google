import random
import time

import curl_cffi.requests as requests

from .browser import BrowserManager
from .config import (
    USER_AGENTS, USE_PROXY, WAIT_SEC, RETRY_FAILED_PAGES,
    USE_CLOUDFLARE_BYPASS, FETCH_MODE, MAX_PAGES_PER_SEARCH,
    CONSECUTIVE_EMPTY_PAGES, USE_GOOGLE_RSS,
)
from .deps import CLOUDSCRAPER_AVAILABLE, cloudscraper, BROWSERFORGE_AVAILABLE, HeaderGenerator
from .news_rss import fetch_google_news_rss
from .url_utils import build_paginated_url, extract_google_links


def is_cloudflare_challenge(response_text: str) -> bool:
    """Detect if response is a Cloudflare challenge."""
    return "cf_challenge" in response_text or "Checking your browser" in response_text


def fetch_page_curl_cffi(url: str, proxy: str = None, retry: int = 0, auth: dict = None) -> str:
    """Fetch page using curl_cffi with browser impersonation."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }

    # Use browserforge headers if available
    if BROWSERFORGE_AVAILABLE:
        try:
            hg = HeaderGenerator()
            bf_headers = hg.generate()
            if bf_headers:
                headers.update(bf_headers)
        except:
            pass

    proxies_dict = None
    if proxy and USE_PROXY:
        proxies_dict = {"https": proxy, "http": proxy}

    auth_tuple = None
    if auth:
        auth_tuple = (auth.get("username"), auth.get("password"))

    try:
        response = requests.get(
            url,
            headers=headers,
            impersonate="chrome",
            timeout=WAIT_SEC,
            proxies=proxies_dict,
            allow_redirects=True,
            verify=False,
            auth=auth_tuple,
        )
        response.raise_for_status()

        if is_cloudflare_challenge(response.text):
            if USE_CLOUDFLARE_BYPASS and CLOUDSCRAPER_AVAILABLE:
                print(f"  Cloudflare challenge detected. Using cloudscraper...")
                return fetch_page_cloudscraper(url, proxy, auth)
            else:
                print(f"  Cloudflare challenge detected but bypass disabled")
                return None

        return response.text

    except Exception as e:
        if retry < RETRY_FAILED_PAGES:
            wait_time = random.uniform(2, 5) * (retry + 1)
            print(f"  Retry {retry + 1}/{RETRY_FAILED_PAGES} for {url} (wait {wait_time:.1f}s): {e}")
            time.sleep(wait_time)
            return fetch_page_curl_cffi(url, proxy, retry + 1, auth)
        else:
            print(f"  Failed to fetch {url}: {e}")
            return None


def fetch_page_cloudscraper(url: str, proxy: str = None, auth: dict = None) -> str:
    """Use cloudscraper for advanced Cloudflare bypass."""
    if not CLOUDSCRAPER_AVAILABLE:
        print(f"  cloudscraper not available")
        return None

    try:
        scraper = cloudscraper.create_scraper()

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
        }

        proxies_dict = None
        if proxy and USE_PROXY:
            proxies_dict = {"https": proxy, "http": proxy}

        auth_tuple = None
        if auth:
            auth_tuple = (auth.get("username"), auth.get("password"))

        response = scraper.get(
            url,
            headers=headers,
            timeout=WAIT_SEC,
            proxies=proxies_dict,
            auth=auth_tuple,
            verify=False,
        )
        response.raise_for_status()

        print(f"  Successfully bypassed Cloudflare")
        return response.text

    except Exception as e:
        print(f"  cloudscraper failed: {e}")
        return None


def fetch_page(url: str, proxy: str = None, auth: dict = None, browser_mgr: BrowserManager = None) -> str:
    """
    Main fetch function with mode-based fallback chain.
    - "curl": curl_cffi only
    - "playwright": playwright only (uses persistent browser)
    - "auto": curl_cffi first, fallback to playwright if no links
    """
    if FETCH_MODE == "playwright":
        if browser_mgr:
            return browser_mgr.fetch(url)
        print("  Playwright mode but no browser manager")
        return None

    if FETCH_MODE == "curl":
        return fetch_page_curl_cffi(url, proxy, auth=auth)

    # "auto" mode: try curl_cffi first
    return fetch_page_curl_cffi(url, proxy, auth=auth)


def process_one_url(search_url: str, proxy: str = None, auth: dict = None, browser_mgr: BrowserManager = None):
    """Process a single search URL across multiple pages."""
    links_all = set()

    print(f"\n[{search_url}] Starting... (mode: {FETCH_MODE})")
    if proxy and USE_PROXY:
        print(f"  Using proxy: {proxy}")

    # Try Google News RSS first (free, no CAPTCHA)
    if USE_GOOGLE_RSS:
        rss_links = fetch_google_news_rss(search_url)
        if rss_links:
            links_all |= rss_links
            print(f"[{search_url}] RSS: +{len(rss_links)} links")

    # Playwright mode: open one tab, click "Next" to paginate
    if FETCH_MODE == "playwright" and browser_mgr:
        pw_links = browser_mgr.browse_and_paginate(search_url, MAX_PAGES_PER_SEARCH, CONSECUTIVE_EMPTY_PAGES)
        links_all |= pw_links
        print(f"[{search_url}] Complete: {len(links_all)} total links")
        return links_all

    # curl / auto mode: fetch each page separately
    consecutive_empty = 0
    for page_idx in range(MAX_PAGES_PER_SEARCH):
        page_url = build_paginated_url(search_url, page_idx)

        html = fetch_page(page_url, proxy, auth, browser_mgr)
        if html is None:
            print(f"[{search_url}] page {page_idx+1}: Failed to fetch (stopping)")
            break

        page_links = extract_google_links(html)

        # Auto mode: if curl_cffi got HTML but 0 links, fall back to Playwright
        if not page_links and FETCH_MODE == "auto" and browser_mgr:
            print(f"[{search_url}] page {page_idx+1}: No links from curl_cffi, switching to Playwright...")
            # Use browse_and_paginate for the rest — no point retrying curl
            pw_links = browser_mgr.browse_and_paginate(
                build_paginated_url(search_url, page_idx),
                MAX_PAGES_PER_SEARCH - page_idx,
                CONSECUTIVE_EMPTY_PAGES
            )
            links_all |= pw_links
            break

        new = page_links - links_all
        links_all |= page_links

        if new:
            consecutive_empty = 0
            print(f"[{search_url}] page {page_idx+1}: +{len(new)} new ({len(links_all)} total)")
        else:
            consecutive_empty += 1
            print(f"[{search_url}] page {page_idx+1}: No new links ({consecutive_empty}/{CONSECUTIVE_EMPTY_PAGES})")

            if consecutive_empty >= CONSECUTIVE_EMPTY_PAGES:
                print(f"[{search_url}] Stopping: {CONSECUTIVE_EMPTY_PAGES} consecutive empty pages")
                break

        time.sleep(random.uniform(1.5, 3.5))

    print(f"[{search_url}] Complete: {len(links_all)} total links")
    return links_all
