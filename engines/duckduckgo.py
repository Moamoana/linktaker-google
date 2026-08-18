"""
DuckDuckGo Search Engine Implementation.

Navigates DuckDuckGo search results using Playwright and returns
clean article URLs.  Accepts either a plain-text query or a full
``https://duckduckgo.com/…`` URL.  DuckDuckGo uses a "More Results"
button rather than traditional pagination.

NOTE: DuckDuckGo is blocked by Indonesian ISPs (Kominfo).
      This engine requires USE_PROXY=True or a VPN connection.
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
# DuckDuckGo-specific selectors
# ---------------------------------------------------------------------------

_WAIT_SELECTOR = "body"
_MORE_BTN = 'button#more-results, button[id="more-results"], a.result--more__btn'

#: Specific CSS selectors for DDG organic results (tried first).
_RESULT_SELECTORS: tuple[str, ...] = (
    'article[data-testid="result"] a[data-testid="result-title-a"]',
    "a.result__a",
    "div.result__body a[href]",
    "h2.result__title a[href]",
    "ol.react-results--main a[href]",
)

#: Error patterns that indicate DDG is blocked or connection failed.
_CONNECTION_ERRORS: tuple[str, ...] = (
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_REFUSED",
    "ERR_EMPTY_RESPONSE",
    "ERR_NAME_NOT_RESOLVED",
)


class DuckDuckGoEngine(BaseEngine):
    """Collect article URLs from DuckDuckGo search results."""

    name = "duckduckgo"

    def __init__(self, browser_mgr: BrowserManager | None = None) -> None:
        super().__init__(browser_mgr)

    # ------------------------------------------------------------------
    # Public API (called by BaseEngine.run)
    # ------------------------------------------------------------------

    def collect(self, query_or_url: str) -> set[str]:
        """Harvest URLs from DuckDuckGo for *query_or_url*.

        Args:
            query_or_url: Either a plain search query (``"kabar terbaru"``)
                          or a full DuckDuckGo search URL.

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
            search_url = f"https://duckduckgo.com/?q={quote_plus(query_or_url)}&ia=web"

        logger.info("[%s] Fetching: %s", self.name, search_url)
        return self._paginate_playwright(search_url)

    # ------------------------------------------------------------------
    # Link extraction helpers
    # ------------------------------------------------------------------

    def _extract_links_specific(self, page) -> set[str]:
        """Extract links using DDG-specific CSS selectors (precise)."""
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
                    parsed = urlparse(href)
                    if any(d in parsed.netloc for d in ("duckduckgo.com", "duck.co")):
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
                if "duckduckgo.com" in href or "duck.co" in href:
                    continue
                if is_valid_url(href):
                    links.add(strip_amp(href))
        except Exception as exc:
            logger.debug("[%s] Broad link extraction error: %s", self.name, exc)
        return links

    # ------------------------------------------------------------------
    # Playwright pagination (infinite scroll + "More Results" button)
    # ------------------------------------------------------------------

    def _paginate_playwright(self, start_url: str) -> set[str]:
        page = self._browser.new_page()  # type: ignore[union-attr]
        if page is None:
            return set()

        links: set[str] = set()
        consecutive_empty = 0

        try:
            # --- Initial page load with ISP block detection ---
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                error_str = str(e)
                if any(p in error_str for p in _CONNECTION_ERRORS):
                    logger.error(
                        "🛑 [DDG BLOCKED] DuckDuckGo tidak bisa diakses. "
                        "Kemungkinan diblokir oleh ISP/Kominfo Indonesia."
                    )
                    print(
                        "  ⚠️  DuckDuckGo diblokir oleh provider internet Anda (Kominfo).\n"
                        "  ⚠️  Solusi: Nyalakan VPN atau set USE_PROXY=True di config.py"
                    )
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

                # DDG uses a "More Results" button instead of page numbers
                more_btn = page.locator(_MORE_BTN).first
                try:
                    if more_btn.is_visible(timeout=3_000):
                        print("  Clicking 'More Results'...")
                        more_btn.click()
                        page.wait_for_timeout(2_000)
                    else:
                        # Fallback: scroll to bottom to trigger infinite load
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(2_000)
                except Exception:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2_000)

        except Exception as exc:
            logger.error("[%s] Unexpected error: %s", self.name, exc)
        finally:
            page.close()

        return links
