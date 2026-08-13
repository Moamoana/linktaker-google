"""
HTTP fetchers: curl_cffi (primary) and cloudscraper (Cloudflare fallback).

Both functions return the raw HTML string on success, or ``None`` on failure.
Callers should treat ``None`` as a signal to skip or retry the page.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

from config import (
    BLOCKED_DOMAINS,
    REQUEST_TIMEOUT,
    RETRY_FAILED_PAGES,
    USE_CLOUDFLARE_BYPASS,
    USE_PROXY,
    USER_AGENTS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    import curl_cffi.requests as _curl_requests
    _CURL_AVAILABLE = True
except ImportError:
    _curl_requests = None  # type: ignore[assignment]
    _CURL_AVAILABLE = False
    logger.warning("curl_cffi not installed — install with: pip install curl_cffi")

try:
    import cloudscraper as _cloudscraper_lib
    _CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    _cloudscraper_lib = None  # type: ignore[assignment]
    _CLOUDSCRAPER_AVAILABLE = False
    logger.warning("cloudscraper not installed — install with: pip install cloudscraper")

try:
    from browserforge.headers import HeaderGenerator as _HeaderGenerator
    _BROWSERFORGE_AVAILABLE = True
except ImportError:
    _HeaderGenerator = None  # type: ignore[assignment]
    _BROWSERFORGE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_headers() -> dict[str, str]:
    """Construct realistic browser request headers.

    Merges a safe baseline with browserforge-generated headers when available.
    """
    base: dict[str, str] = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }
    if _BROWSERFORGE_AVAILABLE:
        try:
            generated = _HeaderGenerator().generate()  # type: ignore[union-attr]
            if generated:
                base.update(generated)
        except Exception:
            pass
    return base


def _proxy_dict(proxy: Optional[str]) -> Optional[dict[str, str]]:
    if proxy and USE_PROXY:
        return {"http": proxy, "https": proxy}
    return None


def _auth_tuple(auth: Optional[dict]) -> Optional[tuple[str, str]]:
    if auth:
        return (auth.get("username", ""), auth.get("password", ""))
    return None


def _is_cloudflare(html: str) -> bool:
    return "cf_challenge" in html or "Checking your browser" in html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_with_curl(
    url: str,
    proxy: Optional[str] = None,
    auth: Optional[dict] = None,
    _retry: int = 0,
) -> Optional[str]:
    """Fetch *url* using curl_cffi with Chrome impersonation.

    Falls back to :func:`fetch_with_cloudscraper` automatically when a
    Cloudflare challenge is detected and the bypass is enabled.

    Args:
        url:    Target URL.
        proxy:  Proxy address (used only when ``USE_PROXY`` is ``True``).
        auth:   Basic-auth dict with ``username`` / ``password`` keys.
        _retry: Internal retry counter; do not set manually.

    Returns:
        HTML string on success, ``None`` on permanent failure.
    """
    if not _CURL_AVAILABLE:
        return None

    try:
        response = _curl_requests.get(  # type: ignore[union-attr]
            url,
            headers=_build_headers(),
            impersonate="chrome",
            timeout=REQUEST_TIMEOUT,
            proxies=_proxy_dict(proxy),
            allow_redirects=True,
            verify=False,
            auth=_auth_tuple(auth),
        )
        response.raise_for_status()

        if _is_cloudflare(response.text):
            if USE_CLOUDFLARE_BYPASS and _CLOUDSCRAPER_AVAILABLE:
                logger.debug("Cloudflare challenge detected; switching to cloudscraper")
                return fetch_with_cloudscraper(url, proxy, auth)
            logger.warning("Cloudflare challenge on %s — bypass disabled", url)
            return None

        return response.text

    except Exception as exc:
        if _retry < RETRY_FAILED_PAGES:
            backoff = random.uniform(2.0, 5.0) * (_retry + 1)
            logger.warning(
                "Fetch attempt %d/%d failed for %s (retry in %.1fs): %s",
                _retry + 1, RETRY_FAILED_PAGES, url, backoff, exc,
            )
            time.sleep(backoff)
            return fetch_with_curl(url, proxy, auth, _retry + 1)

        logger.error("Permanently failed to fetch %s: %s", url, exc)
        return None


def fetch_with_cloudscraper(
    url: str,
    proxy: Optional[str] = None,
    auth: Optional[dict] = None,
) -> Optional[str]:
    """Fetch *url* using cloudscraper for advanced Cloudflare bypass.

    Args:
        url:   Target URL.
        proxy: Proxy address (used only when ``USE_PROXY`` is ``True``).
        auth:  Basic-auth dict with ``username`` / ``password`` keys.

    Returns:
        HTML string on success, ``None`` on failure.
    """
    if not _CLOUDSCRAPER_AVAILABLE:
        logger.error("cloudscraper is not installed")
        return None

    try:
        scraper = _cloudscraper_lib.create_scraper()  # type: ignore[union-attr]
        response = scraper.get(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=REQUEST_TIMEOUT,
            proxies=_proxy_dict(proxy),
            auth=_auth_tuple(auth),
            verify=False,
        )
        response.raise_for_status()
        logger.debug("cloudscraper bypassed Cloudflare for %s", url)
        return response.text
    except Exception as exc:
        logger.error("cloudscraper failed for %s: %s", url, exc)
        return None
