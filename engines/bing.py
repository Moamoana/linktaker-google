"""
Bing Search URL collector.

Navigates Bing Search results using Playwright (primary) or curl_cffi
(fallback), decodes Bing's proprietary redirect URLs, and returns
clean article URLs.
"""

from __future__ import annotations

import base64
import logging
import random
import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse, unquote

from bs4 import BeautifulSoup

from config import (
    CONSECUTIVE_EMPTY_PAGES,
    FETCH_MODE,
    MAX_PAGES_PER_SEARCH,
    PAGE_DELAY_MAX,
    PAGE_DELAY_MIN,
)
from core.browser_manager import BrowserManager
from core.utils import is_valid_url, strip_amp
from engines import BaseEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bing-specific constants
# ---------------------------------------------------------------------------

#: Bing needs longer delays than Google to avoid IP bans.
_BING_DELAY_MIN: float = 3.0
_BING_DELAY_MAX: float = 6.0

#: CSS selectors for organic Bing result links (ordered by specificity).
_RESULT_SELECTORS: tuple[str, ...] = (
    "li.b_algo h2 a[href]",
    "li.b_algo .b_title a[href]",
    "h2 a[href]",
)

#: Selector used to confirm that a Bing page has loaded results.
_RESULTS_READY_SELECTOR: str = "li.b_algo"

#: Full selector string for :meth:`BrowserManager.wait_for_page_ready`.
_WAIT_SELECTOR: str = "#b_results, li.b_algo, #b_content"

#: Next-page button selectors tried in order.
_NEXT_PAGE_SELECTORS: tuple[str, ...] = (
    "#pnnext",
    "a.sb_pagN",
    "a[title='Next page']",
    ".sb_pagN",
)

#: Indonesian news portal domains used as a fallback filter for Bing,
#: which tends to return more off-topic results than Google.
_INDONESIAN_NEWS_DOMAINS: frozenset[str] = frozenset({
    "kompas.com", "detik.com", "cnnindonesia.com", "tempo.co",
    "tribunnews.com", "okezone.com", "liputan6.com", "republika.co.id",
    "sindonews.com", "merdeka.com", "antaranews.com", "viva.co.id",
    "suara.com", "kumparan.com", "bisnis.com", "jpnn.com",
})

#: Error patterns that indicate Bing has blocked our IP.
_IP_BAN_ERRORS: tuple[str, ...] = (
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_EMPTY_RESPONSE",
)


# ---------------------------------------------------------------------------
# Redirect decoding
# ---------------------------------------------------------------------------

_B64_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def _decode_bing_redirect(href: str) -> str:
    """Resolve a Bing ``/ck/a`` redirect to the destination article URL.

    Bing wraps result links in a base64-encoded redirect URL of the form::

        https://www.bing.com/ck/a?...&u=a1<base64>...

    Args:
        href: Raw href from the Bing SERP.

    Returns:
        Decoded article URL, or *href* unchanged if decoding fails.
    """
    if "/ck/a" not in href and "bing.com/ck/" not in href:
        return href

    try:
        qs = parse_qs(urlparse(href).query, keep_blank_values=True)
        raw = qs.get("u", [""])[0]

        if raw.startswith("a1"):
            raw = raw[2:]

        padded = raw + "=" * (4 - len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")

        match = _B64_URL_RE.search(decoded)
        if match:
            return match.group(0)

        if raw:
            return unquote(qs.get("u", [""])[0])
    except Exception:
        pass

    return href


def _is_ip_ban_error(error: Exception) -> bool:
    """Check if the error indicates Bing IP ban."""
    error_str = str(error)
    return any(pattern in error_str for pattern in _IP_BAN_ERRORS)


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _parse_links(html: str, strict: bool) -> set[str]:
    """Extract and validate article URLs from a Bing SERP HTML blob.

    Args:
        html:   Raw HTML string from Bing.
        strict: When ``True``, apply :data:`_INDONESIAN_NEWS_DOMAINS` as
                an additional allow-list filter (recommended for
                ``site:``-filtered queries where Bing may mix in ad results).

    Returns:
        Set of clean, deduplicated article URLs.
    """
    links: set[str] = set()
    try:
        soup = BeautifulSoup(html, "html.parser")

        for selector in _RESULT_SELECTORS:
            for tag in soup.select(selector):
                href = tag.get("href", "")
                if not href:
                    continue
                real = _decode_bing_redirect(href)
                if is_valid_url(real):
                    links.add(strip_amp(real))

        # Fallback — sweep all anchors inside #b_results
        if not links:
            for tag in soup.select("#b_results a[href]"):
                href = tag.get("href", "")
                if not href or not href.startswith("http"):
                    continue
                real = _decode_bing_redirect(href)
                if not is_valid_url(real):
                    continue
                if strict and not any(d in real for d in _INDONESIAN_NEWS_DOMAINS):
                    continue
                links.add(strip_amp(real))

    except Exception:
        logger.exception("HTML parse error for Bing response")

    return links


# ---------------------------------------------------------------------------
# BingEngine
# ---------------------------------------------------------------------------

class BingEngine(BaseEngine):
    """Collect article URLs from Bing Search results.

    Automatically detects ``site:``-constrained queries and applies a
    stricter domain allow-list during fallback link extraction to prevent
    irrelevant international results from polluting the output.
    """

    name = "bing"

    def collect(self, search_url: str) -> set[str]:
        """Return all article URLs found for *search_url*.

        Args:
            search_url: A Bing Search URL (``https://www.bing.com/search?q=…``).

        Returns:
            Set of clean article URLs.
        """
        strict = "site:" in search_url

        if FETCH_MODE == "playwright" and self._browser:
            return self._paginate_playwright(search_url, strict)

        return self._paginate_curl(search_url, strict)

    # ------------------------------------------------------------------
    # Playwright path
    # ------------------------------------------------------------------

    def _paginate_playwright(self, start_url: str, strict: bool) -> set[str]:
        page = self._browser.new_page()  # type: ignore[union-attr]
        if page is None:
            return set()

        links: set[str] = set()
        consecutive_empty = 0

        try:
            page.set_default_timeout(0)

            # --- Initial page load with IP Ban detection ---
            try:
                page.goto(start_url, wait_until="domcontentloaded")
            except Exception as e:
                if _is_ip_ban_error(e):
                    logger.error(
                        "🛑 [BING IP BAN] Koneksi ditutup paksa oleh Bing. "
                        "IP Anda sementara diblokir."
                    )
                    print(
                        "  ⚠️  Bing memblokir IP Anda (IP Ban). "
                        "Saran: restart modem atau tunggu 10-15 menit."
                    )
                    return links
                raise

            if not self._browser.wait_for_page_ready(page, _WAIT_SELECTOR):  # type: ignore[union-attr]
                logger.warning("Could not load Bing results for %s", start_url)
                return links

            for page_idx in range(MAX_PAGES_PER_SEARCH):
                page_links = _parse_links(page.content(), strict)
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
                        break

                next_btn = None
                for sel in _NEXT_PAGE_SELECTORS:
                    next_btn = page.query_selector(sel)
                    if next_btn:
                        break

                if not next_btn:
                    logger.debug("No next-page button — end of Bing results")
                    break

                # --- Click next with IP Ban detection ---
                print("  Clicking next...")
                try:
                    next_btn.click()
                    page.wait_for_load_state("domcontentloaded")

                    if not self._browser.wait_for_page_ready(page, _WAIT_SELECTOR):  # type: ignore[union-attr]
                        logger.warning("Next page failed to load — stopping")
                        break
                except Exception as e:
                    if _is_ip_ban_error(e):
                        logger.warning(
                            "🛑 [BING IP BAN] Bing memutus koneksi di halaman %d. "
                            "Menyimpan %d URL yang sudah didapat.",
                            page_idx + 1, len(links),
                        )
                        print(
                            f"  ⚠️  Bing memblokir IP di halaman {page_idx + 1}. "
                            f"Menyimpan {len(links)} URL yang sudah didapat."
                        )
                        break
                    raise

                # Use Bing-specific longer delay
                time.sleep(random.uniform(_BING_DELAY_MIN, _BING_DELAY_MAX))

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

    def _paginate_curl(self, start_url: str, strict: bool) -> set[str]:
        from core.fetcher import fetch_with_curl

        links: set[str] = set()
        consecutive_empty = 0
        parts = urlparse(start_url)

        for page_idx in range(MAX_PAGES_PER_SEARCH):
            qs = parse_qs(parts.query, keep_blank_values=True)
            qs["first"] = [str(page_idx * 10 + 1)]
            page_url = urlunparse((
                parts.scheme, parts.netloc, parts.path, parts.params,
                urlencode({k: v[0] if len(v) == 1 else v for k, v in qs.items()}, doseq=True),
                parts.fragment,
            ))

            html = fetch_with_curl(page_url)
            if html is None:
                break

            page_links = _parse_links(html, strict)
            new = page_links - links
            links |= page_links

            if new:
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty >= CONSECUTIVE_EMPTY_PAGES:
                    break

            time.sleep(random.uniform(_BING_DELAY_MIN, _BING_DELAY_MAX))

        return links
