"""
DuckDuckGo Search Engine Implementation.

Navigates DuckDuckGo search results using Playwright and returns
clean article URLs.  Accepts either a plain-text query or a full
``https://duckduckgo.com/…`` URL.  DuckDuckGo uses a "More Results"
button rather than traditional pagination.
"""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote_plus

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
    # Playwright pagination (infinite scroll + "More Results" button)
    # ------------------------------------------------------------------

    def _paginate_playwright(self, start_url: str) -> set[str]:
        page = self._browser.new_page()  # type: ignore[union-attr]
        if page is None:
            return set()

        links: set[str] = set()
        consecutive_empty = 0

        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)

            for page_num in range(1, MAX_PAGES_PER_SEARCH + 1):
                time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

                # -------------------------------------------------------
                # Extract ALL <a href> from the page, then filter via
                # is_valid_url.  DDG wraps results in various containers
                # that change frequently, so a broad approach is safer.
                # -------------------------------------------------------
                page_links: set[str] = set()
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
                            page_links.add(strip_amp(href))
                except Exception as exc:
                    logger.debug("[%s] Link extraction error: %s", self.name, exc)

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
