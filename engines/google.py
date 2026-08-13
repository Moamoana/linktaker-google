"""
Google Search URL collector.

Navigates paginated Google Search results using Playwright (primary) or
curl_cffi (fallback) and returns clean article URLs.
"""

from __future__ import annotations

import base64
import logging
import random
import re
import time
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from config import (
    CONSECUTIVE_EMPTY_PAGES,
    FETCH_MODE,
    MAX_PAGES_PER_SEARCH,
    PAGE_DELAY_MAX,
    PAGE_DELAY_MIN,
    RSS_DECODE_DELAY,
    USE_GOOGLE_RSS,
)
from core.browser_manager import BrowserManager
from core.utils import is_valid_url, strip_amp
from engines import BaseEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Google-specific CSS selectors
# ---------------------------------------------------------------------------

#: Selectors that identify organic search result entries.
_RESULT_SELECTORS: tuple[str, ...] = (
    "div.g a[href]",
    "div.SoaBEf a[href]",
    "div.yuRUbf a[href]",
    "div.MjjYud a[href]",
    "a[jsname='UWckNb']",
)

#: Selector used to confirm a page contains actual results.
_RESULTS_READY_SELECTOR: str = "div.g, div.SoaBEf, div.yuRUbf, div.MjjYud"

#: Selector set passed to :meth:`BrowserManager.wait_for_page_ready`.
_WAIT_SELECTOR: str = "#search, #rso, " + _RESULTS_READY_SELECTOR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

try:
    import curl_cffi.requests as _curl
    _CURL_AVAILABLE = True
except ImportError:
    _curl = None  # type: ignore[assignment]
    _CURL_AVAILABLE = False

try:
    import feedparser as _feedparser
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _feedparser = None  # type: ignore[assignment]
    _FEEDPARSER_AVAILABLE = False


def _paginate_url(base_url: str, page_index: int) -> str:
    parts = urlparse(base_url)
    qs = parse_qs(parts.query, keep_blank_values=True)
    qs["start"] = [str(page_index * 10)]
    new_query = urlencode(
        {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in qs.items()},
        doseq=True,
    )
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))


def _parse_links(html: str) -> set[str]:
    """Extract and validate article URLs from a Google SERP HTML blob."""
    links: set[str] = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
        for selector in _RESULT_SELECTORS:
            for tag in soup.select(selector):
                href = tag.get("href", "")
                if is_valid_url(href):
                    links.add(strip_amp(href))
    except Exception:
        logger.exception("HTML parse error")
    return links


def _decode_google_news_url(source_url: str) -> str:
    """Attempt to resolve a Google News RSS redirect to the real article URL."""
    try:
        match = re.search(r"/articles/([A-Za-z0-9_-]+)", urlparse(source_url).path)
        if not match:
            return source_url

        token = match.group(1)
        padded = token + "=" * (4 - len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
        hit = re.search(r"https?://[^\s\"'<>]+", decoded)
        if hit:
            return hit.group(0)

        if _CURL_AVAILABLE:
            resp = _curl.get(source_url, impersonate="chrome", timeout=10, allow_redirects=True, verify=False)  # type: ignore[union-attr]
            final = str(resp.url)
            if final != source_url and "news.google.com" not in final:
                return final
    except Exception:
        pass
    return source_url


# ---------------------------------------------------------------------------
# GoogleEngine
# ---------------------------------------------------------------------------

class GoogleEngine(BaseEngine):
    """Collect article URLs from Google Search results.

    Supports Playwright pagination (default), curl_cffi page-by-page
    fetching, and an optional Google News RSS bypass.
    """

    name = "google"

    def collect(self, search_url: str) -> set[str]:
        """Return all article URLs found for *search_url*.

        Args:
            search_url: A Google Search URL (``https://www.google.com/search?q=…``).

        Returns:
            Set of clean article URLs.
        """
        links: set[str] = set()

        if USE_GOOGLE_RSS:
            rss_links = self._collect_via_rss(search_url)
            links |= rss_links
            if rss_links:
                logger.info("RSS: +%d links", len(rss_links))

        if FETCH_MODE == "playwright" and self._browser:
            links |= self._paginate_playwright(search_url)
        else:
            links |= self._paginate_curl(search_url)

        return links

    # ------------------------------------------------------------------
    # Playwright path
    # ------------------------------------------------------------------

    def _paginate_playwright(self, start_url: str) -> set[str]:
        page = self._browser.new_page()  # type: ignore[union-attr]
        if page is None:
            return set()

        links: set[str] = set()
        consecutive_empty = 0

        try:
            page.set_default_timeout(0)
            page.goto(start_url, wait_until="domcontentloaded")

            if not self._browser.wait_for_page_ready(page, _WAIT_SELECTOR):  # type: ignore[union-attr]
                logger.warning("Could not load Google results for %s", start_url)
                return links

            for page_idx in range(MAX_PAGES_PER_SEARCH):
                page_links = _parse_links(page.content())
                new = page_links - links
                links |= page_links

                if new:
                    consecutive_empty = 0
                    logger.debug("Page %d: +%d new (%d total)", page_idx + 1, len(new), len(links))
                    print(f"  page {page_idx + 1}: +{len(new)} new ({len(links)} total)")
                else:
                    consecutive_empty += 1
                    print(f"  page {page_idx + 1}: No new links ({consecutive_empty}/{CONSECUTIVE_EMPTY_PAGES})")
                    if consecutive_empty >= CONSECUTIVE_EMPTY_PAGES:
                        logger.debug("Stopping after %d empty pages", CONSECUTIVE_EMPTY_PAGES)
                        break

                next_btn = page.query_selector("#pnnext")
                if not next_btn:
                    logger.debug("No next-page button — end of results")
                    break

                print("  Clicking next...")
                next_btn.click()
                page.wait_for_load_state("domcontentloaded")

                if not self._browser.wait_for_page_ready(page, _WAIT_SELECTOR):  # type: ignore[union-attr]
                    logger.warning("Next page failed to load — stopping")
                    break

                time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

        except Exception:
            logger.exception("Playwright pagination error for %s", start_url)
        finally:
            try:
                page.close()
            except Exception:
                pass

        return links

    # ------------------------------------------------------------------
    # curl fallback path
    # ------------------------------------------------------------------

    def _paginate_curl(self, start_url: str) -> set[str]:
        from core.fetcher import fetch_with_curl

        links: set[str] = set()
        consecutive_empty = 0

        for page_idx in range(MAX_PAGES_PER_SEARCH):
            html = fetch_with_curl(_paginate_url(start_url, page_idx))
            if html is None:
                break

            page_links = _parse_links(html)
            if not page_links and FETCH_MODE == "auto" and self._browser:
                logger.info("No curl results on page %d — switching to Playwright", page_idx + 1)
                links |= self._paginate_playwright(_paginate_url(start_url, page_idx))
                break

            new = page_links - links
            links |= page_links

            if new:
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty >= CONSECUTIVE_EMPTY_PAGES:
                    break

            time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

        return links

    # ------------------------------------------------------------------
    # RSS path
    # ------------------------------------------------------------------

    def _collect_via_rss(self, search_url: str) -> set[str]:
        if not _FEEDPARSER_AVAILABLE or not _CURL_AVAILABLE:
            return set()

        parts = urlparse(search_url)
        qs = parse_qs(parts.query, keep_blank_values=True)
        query = qs.get("q", [""])[0]

        if not query or qs.get("tbm", [""])[0] != "nws":
            return set()

        tbs = qs.get("tbs", [""])[0]
        params: dict = {"q": query, "hl": "id", "gl": "ID", "ceid": "ID:id"}
        for marker, period in (("qdr:h", "1h"), ("qdr:d", "1d"), ("qdr:w", "7d"), ("qdr:m", "30d")):
            if marker in tbs:
                params["when"] = period
                break

        rss_url = "https://news.google.com/rss/search?" + urlencode(params)
        logger.debug("Google News RSS: %s", rss_url)

        try:
            resp = _curl.get(rss_url, impersonate="chrome", timeout=15, verify=False)  # type: ignore[union-attr]
            resp.raise_for_status()
            feed = _feedparser.parse(resp.text)  # type: ignore[union-attr]
        except Exception:
            logger.exception("RSS fetch failed")
            return set()

        links: set[str] = set()
        for i, entry in enumerate(feed.entries):
            raw = entry.get("link", "")
            if not raw:
                continue
            real = _decode_google_news_url(raw)
            if real and is_valid_url(real):
                links.add(strip_amp(real))
            if RSS_DECODE_DELAY > 0 and i < len(feed.entries) - 1:
                time.sleep(RSS_DECODE_DELAY)

        return links
