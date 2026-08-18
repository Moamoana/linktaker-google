"""
Yahoo Search Engine Implementation.

Navigates paginated Yahoo search results using Playwright and returns
clean article URLs.  Accepts either a plain-text query or a full
``https://search.yahoo.com/…`` URL.
"""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote_plus, urlparse

from config import MAX_PAGES_PER_SEARCH, PAGE_DELAY_MAX, PAGE_DELAY_MIN
from core.browser_manager import BrowserManager
from core.utils import is_valid_url, strip_amp
from engines import BaseEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Yahoo-specific selectors
# ---------------------------------------------------------------------------

_WAIT_SELECTOR = "body"
_NEXT_SELECTOR = 'a.next, a[class*="next"], nav a:has-text("Next")'

#: Specific CSS selectors for Yahoo organic search results (tried first).
_RESULT_SELECTORS: tuple[str, ...] = (
    "div.compTitle a[href]",          # Yahoo main result title link
    "h3.title a[href]",               # Alternative result title
    "#web ol li a[href]",             # Web results list
    "div.algo a[href]",               # Algo results container
    "div.dd.algo a[href]",            # Alternative algo results
    "section.algo a.ac-algo a[href]", # Another variant
)

#: Error patterns that indicate Yahoo connection issues.
_CONNECTION_ERRORS: tuple[str, ...] = (
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_EMPTY_RESPONSE",
)


class YahooEngine(BaseEngine):
    """Collect article URLs from Yahoo search results."""

    name = "yahoo"

    def __init__(self, browser_mgr: BrowserManager | None = None) -> None:
        super().__init__(browser_mgr)

    # ------------------------------------------------------------------
    # Public API (called by BaseEngine.run)
    # ------------------------------------------------------------------

    def collect(self, query_or_url: str) -> set[str]:
        """Harvest URLs from Yahoo for *query_or_url*.

        Args:
            query_or_url: Either a plain search query (``"kabar terbaru"``)
                          or a full Yahoo search URL.

        Returns:
            Set of clean article URLs.
        """
        if not self._browser:
            logger.error("[%s] Requires Playwright browser", self.name)
            return set()

        # Accept both plain queries and full URLs
        if query_or_url.startswith("http"):
            search_url = query_or_url
        else:
            search_url = f"https://search.yahoo.com/search?p={quote_plus(query_or_url)}"

        logger.info("[%s] Fetching: %s", self.name, search_url)
        return self._paginate_playwright(search_url)

    # ------------------------------------------------------------------
    # Playwright pagination
    # ------------------------------------------------------------------

    def _extract_links_specific(self, page) -> set[str]:
        """Extract links using Yahoo-specific CSS selectors (precise)."""
        links: set[str] = set()
        try:
            html = page.content()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            for selector in _RESULT_SELECTORS:
                for tag in soup.select(selector):
                    href = tag.get("href", "")
                    if not href or not href.startswith("http"):
                        continue
                    # Skip Yahoo internal links
                    parsed = urlparse(href)
                    if any(d in parsed.netloc for d in ("yahoo.com", "yimg.com", "yahoo.net")):
                        continue
                    if is_valid_url(href):
                        links.add(strip_amp(href))
        except Exception as exc:
            logger.debug("[%s] Specific selector extraction error: %s", self.name, exc)
        return links

    def _extract_links_broad(self, page) -> set[str]:
        """Extract links using broad JavaScript approach (fallback)."""
        links: set[str] = set()
        try:
            hrefs: list[str] = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => h.startsWith('http'));
            }""")
            for href in hrefs:
                if "yahoo.com" in href or "yimg.com" in href:
                    continue
                if is_valid_url(href):
                    links.add(strip_amp(href))
        except Exception as exc:
            logger.debug("[%s] Broad link extraction error: %s", self.name, exc)
        return links

    def _paginate_playwright(self, start_url: str) -> set[str]:
        page = self._browser.new_page()  # type: ignore[union-attr]
        if page is None:
            return set()

        links: set[str] = set()
        consecutive_empty = 0

        try:
            # --- Initial page load with connection error handling ---
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                error_str = str(e)
                if any(p in error_str for p in _CONNECTION_ERRORS):
                    logger.error(
                        "🛑 [YAHOO CONNECTION ERROR] Gagal terhubung ke Yahoo: %s",
                        error_str.split("at ")[0] if "at " in error_str else error_str[:100],
                    )
                    print("  ⚠️  Gagal terhubung ke Yahoo. Kemungkinan koneksi bermasalah.")
                    return links
                raise

            page.wait_for_timeout(3_000)

            for page_num in range(1, MAX_PAGES_PER_SEARCH + 1):
                time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

                # Try specific selectors first, fallback to broad
                page_links = self._extract_links_specific(page)
                if not page_links:
                    page_links = self._extract_links_broad(page)

                new_links = page_links - links
                links.update(new_links)

                logger.info(
                    "[%s] page %d: +%d new (%d total)",
                    self.name, page_num, len(new_links), len(links),
                )
                if new_links:
                    print(f"  page {page_num}: +{len(new_links)} new ({len(links)} total)")
                else:
                    print(f"  page {page_num}: No new links")

                if not new_links:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        logger.info("[%s] No new results for 2 pages — stopping", self.name)
                        break
                else:
                    consecutive_empty = 0

                if page_num >= MAX_PAGES_PER_SEARCH:
                    break

                # Try clicking "Next" with error handling
                next_btn = page.locator(_NEXT_SELECTOR).first
                try:
                    if next_btn.is_visible(timeout=3_000):
                        print("  Clicking next...")
                        next_btn.click()
                        page.wait_for_load_state("domcontentloaded")
                        page.wait_for_timeout(2_000)
                    else:
                        logger.debug("[%s] No next-page button — end of results", self.name)
                        break
                except Exception as e:
                    error_str = str(e)
                    if any(p in error_str for p in _CONNECTION_ERRORS):
                        logger.warning(
                            "[%s] Koneksi terputus di halaman %d. Menyimpan %d URL.",
                            self.name, page_num, len(links),
                        )
                        print(f"  ⚠️  Koneksi terputus. Menyimpan {len(links)} URL yang sudah didapat.")
                        break
                    logger.debug("[%s] Could not click next — stopping", self.name)
                    break

        except Exception as exc:
            logger.error("[%s] Unexpected error: %s", self.name, exc)
        finally:
            page.close()

        return links
