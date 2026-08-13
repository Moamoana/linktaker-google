"""
Utility helpers: URL cleaning, validation, and I/O.

These functions are engine-agnostic and shared across all collectors.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional
from urllib.parse import (
    parse_qs,
    urlencode,
    urlparse,
    urlunparse,
)

from config import BLOCKED_DOMAINS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def read_urls(path: str) -> list[str]:
    """Return non-empty, non-comment lines from *path*.

    Args:
        path: Absolute or relative path to the URL list file.

    Returns:
        List of URL strings; empty list if the file does not exist.
    """
    if not os.path.exists(path):
        logger.warning("URL file not found: %s", path)
        return []
    with open(path, encoding="utf-8") as fh:
        return [
            line.strip()
            for line in fh
            if line.strip() and not line.strip().startswith("#")
        ]


def read_proxies(path: str) -> list[str]:
    """Return proxy strings from *path*, one per line.

    Args:
        path: Path to the proxy list file.

    Returns:
        List of proxy strings; empty list if the file does not exist.
    """
    if not os.path.exists(path):
        logger.warning("Proxy file not found: %s — running without proxies", path)
        return []
    with open(path, encoding="utf-8") as fh:
        proxies = [
            line.strip()
            for line in fh
            if line.strip() and not line.strip().startswith("#")
        ]
    logger.info("Loaded %d proxy entries", len(proxies))
    return proxies


def read_auth(path: str = "auth.json") -> Optional[dict]:
    """Load basic-auth credentials from a JSON file.

    Expected JSON schema::

        {"username": "...", "password": "..."}

    Args:
        path: Path to the auth credentials file.

    Returns:
        Dict with ``username``/``password`` keys, or ``None`` if unavailable.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            auth = json.load(fh)
        logger.info("Loaded credentials for user: %s", auth.get("username"))
        return auth
    except Exception:
        logger.exception("Failed to parse auth file: %s", path)
        return None


def load_existing_urls(path: str) -> set[str]:
    """Read previously collected URLs from *path* (resume support).

    Args:
        path: Path to the output file.

    Returns:
        Set of URL strings already persisted to disk.
    """
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        urls = {line.strip() for line in fh if line.strip()}
    if urls:
        logger.info("Resume mode: %d existing URLs loaded from %s", len(urls), path)
    return urls


def append_url(url: str, path: str) -> None:
    """Append a single URL to *path*, creating parent directories as needed.

    Args:
        url:  The URL string to write.
        path: Destination file path.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(url + "\n")


# ---------------------------------------------------------------------------
# URL sanitisation
# ---------------------------------------------------------------------------

_AMP_PATH_RE = re.compile(r"/amp(/|$)")

#: Query-string keys injected by AMP that carry no informational value.
_AMP_QUERY_KEYS: frozenset[str] = frozenset({"amp", "amp_js_v", "usqp", "outputType"})


def strip_amp(url: str) -> str:
    """Remove Google AMP artefacts from *url*.

    Handles:
    - ``amp.`` subdomain prefix (``amp.example.com`` → ``example.com``)
    - ``/amp/`` and trailing ``/amp`` path segments
    - AMP-specific query-string parameters

    Args:
        url: Raw URL string.

    Returns:
        Cleaned URL string; returns *url* unchanged on parse failure.
    """
    try:
        parts = urlparse(url)

        netloc = parts.netloc
        if netloc.startswith("amp."):
            netloc = netloc[4:]

        path = _AMP_PATH_RE.sub("/", parts.path)
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")

        qs = parse_qs(parts.query, keep_blank_values=True)
        for key in _AMP_QUERY_KEYS:
            qs.pop(key, None)

        new_query = urlencode(
            {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in qs.items()},
            doseq=True,
        )
        return urlunparse((parts.scheme, netloc, path, parts.params, new_query, parts.fragment))
    except Exception:
        return url


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_GOOGLE_HOSTS: tuple[str, ...] = ("google.com", "google.co.", "gstatic.com", "googleusercontent.com")
_BING_HOSTS:   tuple[str, ...] = ("bing.com", "bing.net", "msn.com")


def _resolve_google_redirect(href: str) -> str:
    """Unwrap ``/url?q=`` Google redirect wrappers."""
    if "/url?q=" not in href:
        return href
    try:
        qs = parse_qs(urlparse(href).query)
        return qs["q"][0] if "q" in qs else href
    except Exception:
        return href


def is_blocked_domain(url: str) -> bool:
    """Return ``True`` when *url* belongs to a blocked domain.

    Args:
        url: URL to evaluate.

    Returns:
        ``True`` if the host matches any entry in ``BLOCKED_DOMAINS``.
    """
    try:
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        if netloc in BLOCKED_DOMAINS:
            return True
        return any(netloc.endswith("." + d) for d in BLOCKED_DOMAINS)
    except Exception:
        return False


def is_valid_url(href: str) -> bool:
    """Validate that *href* is a collectable article URL.

    A URL is considered invalid if it:
    - Is empty or ``None``
    - Is a Google redirect wrapper
    - Belongs to a blocked domain (social media, developer platforms, etc.)
    - Has a non-HTTP/HTTPS scheme
    - Lacks a network location
    - Points back to Google or Bing infrastructure

    Args:
        href: Raw href string.

    Returns:
        ``True`` when the URL should be collected.
    """
    if not href:
        return False

    href = _resolve_google_redirect(href)

    if is_blocked_domain(href):
        return False

    try:
        parts = urlparse(href)
    except Exception:
        return False

    if parts.scheme not in ("http", "https"):
        return False
    if not parts.netloc:
        return False

    netloc = parts.netloc.lower()
    if any(host in netloc for host in (*_GOOGLE_HOSTS, *_BING_HOSTS)):
        return False

    return True
